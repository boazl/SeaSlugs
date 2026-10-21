"""0075 gives a library observation's missing <name>-2.jpg file the photo stored here as <name>.jpg."""
import importlib, shutil, tempfile
from pathlib import Path
from django.apps import apps
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from observations.models import Sample


class LibraryImageRepairTests(TestCase):
    def test_missing_suffixed_file_gets_the_plain_named_photo(self):
        media = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, media, True)
        (media / 'observations').mkdir()
        (media / 'observations' / 'genera-berthellina.jpg').write_bytes(b'x')
        (media / 'observations' / 'genera-fiona-2.jpg').write_bytes(b'x')
        u = User.objects.create(username='boaz')
        a = Sample.objects.create(kind='genus', genus='Berthellina', owner=u, image='observations/genera-berthellina-2.jpg')
        b = Sample.objects.create(kind='genus', genus='Fiona', owner=u, image='observations/genera-fiona-2.jpg')   # its file is there
        c = Sample.objects.create(kind='genus', genus='Haminoea', owner=u, image='observations/genera-haminoea-2.jpg')  # no plain file
        mod = importlib.import_module('observations.migrations.0075_repair_library_image_names')
        with override_settings(MEDIA_ROOT=str(media)):
            mod.forwards(apps, None)
        a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
        self.assertEqual(a.image.name, 'observations/genera-berthellina-2.jpg')
        self.assertTrue((media / 'observations' / 'genera-berthellina-2.jpg').is_file())
        self.assertFalse((media / 'observations' / 'genera-berthellina.jpg').exists())
        self.assertEqual(b.image.name, 'observations/genera-fiona-2.jpg')
        self.assertEqual(c.image.name, 'observations/genera-haminoea-2.jpg')


class AlignNamesTests(TestCase):
    def test_swapped_and_shared_names_take_the_other_environments_names(self):
        from observations.image_manager import align_names, _rename_conflict
        media = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, media, True)
        (media / 'observations').mkdir()
        for name, data in (('a.jpg', b'A'), ('b.jpg', b'B'), ('trip.jpg', b'T'), ('taken.jpg', b'X')):
            (media / 'observations' / name).write_bytes(data)
        u = User.objects.create(username='boaz')
        one = Sample.objects.create(kind='species', owner=u, image='observations/a.jpg')
        two = Sample.objects.create(kind='species', owner=u, image='observations/b.jpg')
        own = Sample.objects.create(kind='species', owner=u, image='observations/trip.jpg')
        shown = Sample.objects.create(kind='collection', owner=u, image='observations/trip.jpg', gallery_source=own)
        with override_settings(MEDIA_ROOT=str(media)):
            self.assertTrue(_rename_conflict({'observations/a.jpg': 'observations/taken.jpg'}))
            align_names({'observations/a.jpg': 'observations/b.jpg', 'observations/b.jpg': 'observations/a.jpg',
                         'observations/trip.jpg': 'observations/species.jpg'})
        for s in (one, two, own, shown): s.refresh_from_db()
        self.assertEqual((one.image.name, two.image.name), ('observations/b.jpg', 'observations/a.jpg'))
        self.assertEqual((media / 'observations' / 'b.jpg').read_bytes(), b'A')
        self.assertEqual((own.image.name, shown.image.name), ('observations/species.jpg', 'observations/species.jpg'))
        self.assertEqual(sorted(p.name for p in (media / 'observations').iterdir()), ['a.jpg', 'b.jpg', 'species.jpg', 'taken.jpg'])


class DefiningPreviewTests(TestCase):
    def test_empty_family_observation_shows_the_defining_observations_photo_small(self):
        from django.core.files.base import ContentFile
        from observations.models import TaxonFamily
        import io
        from PIL import Image
        buf = io.BytesIO(); Image.new('RGB', (40, 30), 'red').save(buf, 'JPEG')
        media = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, media, True)
        u = User.objects.create(username='boaz', is_superuser=True, is_staff=True)
        with override_settings(MEDIA_ROOT=str(media)):
            genus = Sample(kind='genus', owner=u, genus='Felimare', family='Chromodorididae', status='published')
            genus.image.save('genera-felimare.jpg', ContentFile(buf.getvalue()), save=False)
            Sample.objects.bulk_create([genus]); genus = Sample.objects.get(genus='Felimare')
            empty = Sample.objects.create(kind='family', owner=u, family='Chromodorididae', status='published')
            TaxonFamily.objects.create(name='Chromodorididae', defining_sample=genus)
            self.client.force_login(u)
            html = self.client.get('/observations/?lang=he').content.decode()
        card = html.split(f'id="obs-{empty.pk}"')[1].split('</article>')[0]
        self.assertIn('class="defining-preview"', card)
        self.assertIn(f'/observations/{genus.pk}/photo/', card)
        self.assertIn('התמונה של התצפית המגדירה', card)
        self.assertIn('Felimare', card)
        other = html.split(f'id="obs-{genus.pk}"')[1].split('</article>')[0]
        self.assertNotIn('defining-preview', other)
