import io
import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from . import identification_transfer as it
from .models import TaxonGenus


def picture(color='red', size=(40, 30)):
    out = io.BytesIO()
    Image.new('RGB', size, color).save(out, 'JPEG')
    return out.getvalue()


def no_backup():
    return patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3'))


class IdentificationTransferTests(TestCase):
    """Genus identification files move between the environments on /admin/article-files/ like articles: a manifest of
    every genus's files (fingerprint, stored name) and preview pages; a comparison listing files missing here, only here,
    and differing files or pages; per genus a details file plus its files to download; and an upload that stores each file
    under its source name with its preview page -- the genus must exist here, an existing different file is replaced only
    when confirmed, the same file is not stored again. The image manager points to this page, since these files are not
    observation images."""

    def setUp(self):
        self.boss = User.objects.create_superuser('boss', password='x')
        self.client.force_login(self.boss)
        self.genus = TaxonGenus.objects.create(name='Thuridilla')
        self.genus.identification_file.save('Thuridilla sp ID.jpeg', ContentFile(picture()), save=False)
        self.genus.save()

    def upload(self, name, data, kind='application/octet-stream'):
        return SimpleUploadedFile(name, data, content_type=kind)

    def details(self, genus=None):
        return self.upload(f'{(genus or self.genus).name}.identification.json',
                           json.dumps(it.details_document(genus or self.genus)).encode(), 'application/json')

    def test_manifest_and_comparison(self):
        TaxonGenus.objects.create(name='Elysia')
        manifest = it.build_manifest()
        self.assertEqual([e['genus'] for e in manifest['genera']], ['Thuridilla'])
        entry = manifest['genera'][0]
        self.assertIsNone(entry['files']['en'])
        self.assertTrue(entry['files']['he'][3].startswith('Thuridilla'))
        self.assertEqual(it.compare_manifest(manifest), {'missing_here': [], 'only_here': [], 'different': [], 'send': []})
        other = json.loads(json.dumps(manifest))
        other['genera'][0]['files']['he'][0] = 'x' * 64
        other['genera'][0]['pages']['en'] = 3
        other['genera'].append({'genus': 'Elysia', 'files': {'he': ['y' * 64, 1, 10, 'e.pdf'], 'en': None}, 'pages': {'he': 2, 'en': 1}})
        other['genera'].append({'genus': 'Nowhere', 'files': {'he': ['z' * 64, 1, 10, 'n.pdf'], 'en': None}, 'pages': {'he': 1, 'en': 1}})
        result = it.compare_manifest(other)
        self.assertEqual([(g['genus'], g['no_genus']) for g in result['missing_here']], [('Elysia', False), ('Nowhere', True)])
        self.assertEqual(result['different'][0]['items'][0]['state'], 'תוכן שונה')
        self.assertEqual(result['send'], ['Thuridilla'])
        self.assertEqual(it.compare_manifest({**manifest, 'genera': []})['only_here'][0]['genus'], 'Thuridilla')
        with self.assertRaises(ValidationError):
            it.compare_manifest({'format': 'seaslugs-image-manifest-v1', 'images': []})

    def test_download_files(self):
        url = reverse('identification-transfer-file')
        response = self.client.get(url, {'genus': 'Thuridilla', 'part': 'details'})
        self.assertIn('Thuridilla.identification.json', response['Content-Disposition'])
        self.assertEqual(json.loads(response.content)['genus']['genus'], 'Thuridilla')
        response = self.client.get(url, {'genus': 'Thuridilla', 'part': 'he'})
        self.assertIn('Thuridilla-identification-he.jpeg', response['Content-Disposition'])
        self.assertEqual(self.client.get(url, {'genus': 'Thuridilla', 'part': 'en'}).status_code, 404)
        staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(url, {'genus': 'Thuridilla', 'part': 'details'}).status_code, 403)

    def test_receive_new_same_and_replace(self):
        details = it.details_document(self.genus)
        data = self.genus.identification_file.read()
        stored_name = details['genus']['files']['he'][3]
        target = TaxonGenus.objects.create(name='Phyllidia')
        details['genus']['genus'] = 'Phyllidia'
        details['genus']['pages']['he'] = 1
        doc = lambda: self.upload('Phyllidia.identification.json', json.dumps(details).encode())
        with no_backup():
            done, notes = it.receive([doc(), self.upload('Phyllidia-identification-he.jpeg', data)])
        target.refresh_from_db()
        # the source's name (here the same storage holds it already, so the storage adds a suffix)
        self.assertTrue(Path(target.identification_file.name).name.startswith(Path(stored_name).stem))
        self.assertEqual((done, notes), ([('Phyllidia', 'קובץ בעברית')], []))
        with no_backup():
            self.assertEqual(it.receive([doc(), self.upload('Phyllidia-identification-he.jpeg', data)])[0], [('Phyllidia', 'ללא שינוי')])
            other = picture('blue', (50, 20))
            done, notes = it.receive([doc(), self.upload('Phyllidia-identification-he.jpeg', other)])
            self.assertIn('לא הוחלף', notes[0])
            it.receive([doc(), self.upload('Phyllidia-identification-he.jpeg', other)], replace=True)
        target.refresh_from_db()
        self.assertEqual(target.identification_file.read(), other)

    def test_receive_refuses(self):
        data = self.genus.identification_file.read()
        with self.assertRaises(ValidationError):
            it.receive([self.upload('Thuridilla-identification-he.jpeg', data)])           # no details file
        with self.assertRaises(ValidationError):
            it.receive([self.details(), self.upload('Thuridilla-identification-he.jpeg', b'not a picture')])
        with self.assertRaises(ValidationError):
            it.receive([self.details(), self.upload('Thuridilla-identification-he.pdf', b'not a pdf')])
        with self.assertRaises(ValidationError):
            it.receive([self.upload('photo.jpeg', data)])
        details = it.details_document(self.genus)
        details['genus']['genus'] = 'Unknown'
        with no_backup():
            done, notes = it.receive([self.upload('Unknown.identification.json', json.dumps(details).encode())])
        self.assertEqual(done, [])
        self.assertIn('אינו קיים כאן', notes[0])

    def test_page_upload_and_links(self):
        page = self.client.get(reverse('article-files')).content.decode()
        self.assertIn('id="identification-transfer"', page)
        self.assertIn('class="genus-box" value="Thuridilla"', page)
        self.assertIn(reverse('article-files') + '#identification-transfer', self.client.get(reverse('image-manager')).content.decode())
        export = self.client.post(reverse('article-files'), {'action': 'export_identification'})
        self.assertEqual(json.loads(export.content)['format'], it.MANIFEST_FORMAT)
        compare = self.client.post(reverse('article-files'), {'action': 'compare_identification',
                                   'manifest': self.upload('m.json', json.dumps({'format': 'x'}).encode())})
        self.assertIn('קובץ השוואת קובצי זיהוי לא תקין', compare.content.decode())
        TaxonGenus.objects.filter(pk=self.genus.pk).update(identification_page=1)
        with no_backup():
            response = self.client.post(reverse('article-files'), {'action': 'upload_identification', 'files': [
                self.details(), self.upload('Thuridilla-identification-he.jpeg', self.genus.identification_file.read())]}, follow=True)
        self.assertIn('Thuridilla (ללא שינוי)', response.content.decode())
