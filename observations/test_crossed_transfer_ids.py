"""A species observation and the dive-trip collection made from its photo can end up in the other environment
with each other's transfer id (or the species one with an id the source never had). A transfer -- the samples
table or the image manager -- matches each row by what it is (species on a trip / collection by title) when its
transfer id names a different kind of observation there, gives both observations the source's transfer ids, and
relinks the collection's gallery image -- no error, no deletion, no duplicate."""
import io
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Country, DiveTrip, Region, Sample, Sea, Species
from .table_transfer import apply, export_table, fingerprint, plan


class CrossedTransferIdTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        override = override_settings(MEDIA_ROOT=self.temp.name, DATA_DIR=self.temp.name)
        override.enable(); self.addCleanup(override.disable)
        self.user = User.objects.create_superuser('boazl', password='testing')
        country = Country.objects.create(name='Solomon Islands'); sea = Sea.objects.create(name='Solomon Sea')
        region = Region.objects.create(name='Bilikiki', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(code='G', title='Solomon Islands 2023', year=2023, country=country, region=region)
        self.species = Species.objects.create(scientific_name='Notodoris minor', author='Eliot, 1904')
        self.owner = Sample(owner=self.user, species=self.species, trip=self.trip)
        output = io.BytesIO(); Image.new('RGB', (100, 80), 'yellow').save(output, 'JPEG')
        self.owner.image.save('g-notodoris-minor.jpg', ContentFile(output.getvalue()), save=False)
        self.owner.save_reviewed()
        self.collection = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.COLLECTION, title='איי שלמה 2023',
                                 gallery_source=self.owner, image=self.owner.image.name)
        self.collection.save_reviewed()
        self.species_tid, self.collection_tid = str(self.owner.transfer_id), str(self.collection.transfer_id)

    def cross(self):
        """The target as it was found: the collection holds the species observation's id, the species one another."""
        Sample.objects.filter(pk=self.owner.pk).update(transfer_id=uuid.uuid4())
        Sample.objects.filter(pk=self.collection.pk).update(transfer_id=self.species_tid)

    def assert_repaired(self):
        self.owner.refresh_from_db(); self.collection.refresh_from_db()
        self.assertEqual((str(self.owner.transfer_id), str(self.collection.transfer_id)), (self.species_tid, self.collection_tid))
        self.assertEqual((self.owner.kind, self.owner.species), (Sample.Kind.SPECIES, self.species))
        self.assertEqual((self.collection.kind, self.collection.title), (Sample.Kind.COLLECTION, 'איי שלמה 2023'))
        self.assertEqual(self.collection.gallery_source, self.owner)
        self.assertEqual(Sample.objects.count(), 2)

    def test_the_samples_table_transfer_matches_by_what_each_row_is(self):
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        self.cross()
        items = {str(i['object'].transfer_id): i['object'].pk for i in plan(doc)}
        self.assertEqual(items, {self.species_tid: self.owner.pk, self.collection_tid: self.collection.pk})
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())
        self.assert_repaired()

    def test_the_image_manager_upload_matches_by_what_each_row_is(self):
        from .image_manager import files
        self.client.force_login(self.user)
        row = next(r for r in files() if self.owner in r['refs'])
        response = self.client.get('/admin/images/file/', {'file': row['token'], 'download': '1'})
        raw = b''.join(response.streaming_content); response.close()
        self.cross()
        self.client.post('/admin/images/', {'action': 'upload', 'replace': 'yes',
                                            'images': SimpleUploadedFile('t.jpg', raw, content_type='image/jpeg')})
        self.assert_repaired()

    def test_rows_that_match_their_own_observation_are_not_touched(self):
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        self.assertTrue(all(i['action'] == 'same' for i in plan(doc)))
