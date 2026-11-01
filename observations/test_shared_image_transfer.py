import base64
import io
import json
import tempfile
from pathlib import Path
from PIL import Image
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from .models import Country, DiveTrip, Region, Sample, Sea, Species


class SharedImageTransferTests(TestCase):
    """A photo shown by several observations (e.g. a dive-trip collection built from a species
    photo in the gallery) travels with ALL of them: the downloaded file carries every live
    observation using it, the owning one first. Uploading it on the other side creates/updates
    each of them -- the species observation is never left behind -- and the others show the
    owner's file as a gallery image instead of a second copy."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        override = override_settings(MEDIA_ROOT=self.temp.name, DATA_DIR=self.temp.name)
        override.enable(); self.addCleanup(override.disable)
        self.user = User.objects.create_superuser('admin', password='testing')
        country = Country.objects.create(name='Australia'); sea = Sea.objects.create(name='Coral Sea')
        region = Region.objects.create(name='Lady Elliot', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(code='Z1', title='Australia 1998', year=1998, country=country, region=region)
        self.species = Species.objects.create(scientific_name='Aplysia dactylomela', author='Rang, 1828')
        self.owner = Sample(owner=self.user, species=self.species, trip=self.trip)
        output = io.BytesIO(); Image.new('RGB', (100, 80), 'blue').save(output, 'JPEG')
        self.owner.image.save('owner.jpg', ContentFile(output.getvalue()), save=False)
        self.owner.save_reviewed()
        self.collection = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.COLLECTION,
                                 title='האי של גברת אליוט - 1998', gallery_source=self.owner,
                                 image=self.owner.image.name)
        self.collection.save_reviewed()
        self.collection.refresh_from_db()
        self.assertEqual(self.collection.image.name, self.owner.image.name)
        self.client.force_login(self.user)

    def download(self):
        from .image_manager import files
        row = next(r for r in files() if self.owner in r['refs'])
        response = self.client.get('/admin/images/file/', {'file': row['token'], 'download': '1'})
        raw = b''.join(response.streaming_content); response.close()
        return raw

    def upload(self, raw, **extra):
        return self.client.post('/admin/images/', {'action': 'upload', **extra,
                                'images': SimpleUploadedFile('transfer.jpg', raw, content_type='image/jpeg')})

    def test_download_embeds_every_observation_using_the_file_owner_first(self):
        with Image.open(io.BytesIO(self.download())) as image:
            metadata = image.getexif()[270]
        rows = json.loads(base64.b64decode(metadata[len('SeaSlugsB64:'):]).decode('utf-8'))
        self.assertEqual([r['transfer_id'] for r in rows],
                         [str(self.owner.transfer_id), str(self.collection.transfer_id)])
        self.assertEqual(rows[1]['gallery_source'], str(self.owner.transfer_id))

    def test_a_single_observation_still_downloads_as_a_single_row(self):
        self.collection.delete()
        with Image.open(io.BytesIO(self.download())) as image:
            metadata = image.getexif()[270]
        self.assertIsInstance(json.loads(base64.b64decode(metadata[len('SeaSlugsB64:'):]).decode('utf-8')), dict)

    def test_upload_on_an_empty_side_creates_the_species_and_the_collection(self):
        raw = self.download()
        owner_tid, collection_tid = self.owner.transfer_id, self.collection.transfer_id
        old = Path(self.owner.image.path)
        Sample.objects.all().delete(); old.unlink()
        response = self.upload(raw)
        self.assertEqual(response.status_code, 302)
        owner = Sample.objects.get(transfer_id=owner_tid); collection = Sample.objects.get(transfer_id=collection_tid)
        self.assertEqual(owner.species, self.species)
        self.assertEqual(owner.image.name, 'observations/z1-aplysia-dactylomela.jpg')
        self.assertTrue(Path(owner.image.path).exists())
        self.assertEqual((collection.gallery_source_id, collection.image.name), (owner.pk, owner.image.name))
        self.assertEqual(Sample.objects.count(), 2)

    def test_upload_where_only_the_collection_arrived_adds_the_species_and_relinks_the_collection(self):
        # the state an older version left behind: the collection came with its own copy of the
        # photo under its own name, the species observation never arrived
        raw = self.download()
        owner_tid = self.owner.transfer_id
        old = Path(self.owner.image.path)
        Sample.objects.filter(pk=self.collection.pk).update(gallery_source=None)
        self.owner.delete(); old.unlink()
        copy = io.BytesIO(); Image.new('RGB', (100, 80), 'blue').save(copy, 'JPEG')
        self.collection.refresh_from_db()
        self.collection.image.save('z1-collection-copy.jpg', ContentFile(copy.getvalue()), save=False)
        Sample.objects.filter(pk=self.collection.pk).update(image=self.collection.image.name)
        stale = Path(self.collection.image.path)
        response = self.upload(raw, replace='yes')
        self.assertEqual(response.status_code, 302)
        owner = Sample.objects.get(transfer_id=owner_tid); self.collection.refresh_from_db()
        self.assertEqual(self.collection.gallery_source_id, owner.pk)
        self.assertEqual(self.collection.image.name, owner.image.name)
        self.assertFalse(stale.exists())
        self.assertEqual(Sample.objects.count(), 2)
