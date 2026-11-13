import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from .models import Country, DiveTrip, Profile, Region, Sample, Sea, Species
from .photographers import mark_photographer


class FolderImportPhotographerAndCollectionTests(TestCase):
    """The folder import (/admin/images/folder/) opens its new observations under the trip's photographer --
    not the manager running the import: the owner of most of the trip's observations, else the photographer
    whose letter starts the trip code, else the site owner; the operator may pick another photographer on the
    preview. An existing observation keeps its own photographer. At the end it can add the trip's collection
    observation ("אוסף מינים / מסע צלילה") under that photographer, its picture one of the imported photos
    (a gallery image, gallery_source) chosen on the preview -- only when the trip has no collection yet."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        settings = override_settings(DATA_DIR=self.temp.name, MEDIA_ROOT=self.temp.name + '/media')
        settings.enable(); self.addCleanup(settings.disable)
        self.manager = User.objects.create_superuser('importer', password='test')
        self.photographer = User.objects.create_user('oren.kline', first_name='אורן', last_name='קליין', is_active=False)
        mark_photographer(self.photographer)
        self.country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        self.region = Region.objects.create(name='רומבלון', name_en='Romblon', country=self.country, sea=Sea.objects.create(name='Pacific'))
        self.trip = DiveTrip.objects.create(title='Trip', code='oR26Jan', year=2026, month=1, country=self.country, region=self.region)
        self.first = Species.objects.create(scientific_name='Micromelo undatus')
        self.second = Species.objects.create(scientific_name='Elysia ornata')
        self.client.force_login(self.manager)

    def photo(self, name, colour):
        output = io.BytesIO(); Image.new('RGB', (40, 30), colour).save(output, 'JPEG')
        return SimpleUploadedFile(name, output.getvalue(), content_type='image/jpeg')

    def preview(self):
        return self.client.post('/admin/images/folder/', {'action': 'preview', 'trip': self.trip.pk, 'images': [
            self.photo('001-Micromelo undatus.jpg', 'blue'), self.photo('002-Elysia ornata.jpg', 'red')]})

    def apply(self, token, **extra):
        data = {'action': 'apply', 'token': token, 'selected': ['0', '1'], 'species_0': 'Micromelo undatus',
                'species_1': 'Elysia ornata', 'confirm': 'yes', **extra}
        with patch('observations.folder_import.create_backup', return_value=Path('backup.sqlite3')):
            return self.client.post('/admin/images/folder/', data, follow=True)

    def test_photographer_comes_from_the_trip_code_letter(self):
        Profile.objects.create(user=self.photographer, trip_code='o')
        response = self.preview()
        self.assertEqual(response.context['photographer'], self.photographer.pk)
        self.apply(response.context['token'])
        self.assertEqual({s.owner for s in Sample.objects.filter(kind='species')}, {self.photographer})

    def test_photographer_is_the_owner_of_the_trips_observations(self):
        other_trip = DiveTrip.objects.create(title='Other', year=2025, country=self.country, region=self.region)
        Sample.objects.create(kind='species', species=Species.objects.create(scientific_name='Doto sp.'), trip=self.trip,
                              owner=self.photographer, video_url='https://youtu.be/abcdefghijk')
        Sample.objects.create(kind='species', species=self.first, trip=other_trip, owner=self.manager, video_url='https://youtu.be/bbcdefghijk')
        response = self.preview()
        self.assertEqual(response.context['photographer'], self.photographer.pk)
        self.apply(response.context['token'])
        self.assertEqual(Sample.objects.get(trip=self.trip, species=self.first).owner, self.photographer)

    def test_without_a_clue_the_new_observations_belong_to_the_site_owner(self):
        owner = User.objects.create_user('boazl')
        self.trip.code = 'R26Jan'; self.trip.save()
        with override_settings(TRIP_DEFAULT_PHOTOGRAPHER='boazl'):
            response = self.preview()
        self.assertEqual(response.context['photographer'], owner.pk)

    def test_operator_can_choose_another_photographer_and_existing_observations_keep_theirs(self):
        existing = Sample.objects.create(kind='species', species=self.first, trip=self.trip, owner=self.manager,
                                         video_url='https://youtu.be/abcdefghijk')
        response = self.preview()
        self.assertEqual(response.context['photographer'], self.manager.pk)
        self.apply(response.context['token'], photographer=str(self.photographer.pk))
        existing.refresh_from_db()
        self.assertEqual(existing.owner, self.manager)
        self.assertEqual(Sample.objects.get(trip=self.trip, species=self.second).owner, self.photographer)

    def test_a_photographer_outside_the_list_is_refused(self):
        stranger = User.objects.create_user('stranger')
        response = self.preview()
        response = self.apply(response.context['token'], photographer=str(stranger.pk))
        self.assertIn('יש לבחור צלם', response.context['error'])
        self.assertFalse(Sample.objects.exists())

    def test_creates_the_trip_collection_with_the_chosen_photo(self):
        Profile.objects.create(user=self.photographer, trip_code='o')
        response = self.preview()
        self.assertTrue(response.context['rows'][0]['cover'])
        self.assertEqual(response.context['collection_title'], 'רומבלון - 2026')
        self.assertEqual(response.context['collection_title_en'], 'Romblon - 2026')
        self.assertContains(response, 'name="collection_image"')
        response = self.apply(response.context['token'], collection='yes', collection_image='1',
                              collection_title='רומבלון - 2026', collection_title_en='Romblon - 2026')
        self.assertNotIn('error', response.context, response.context.get('error'))
        collection = Sample.objects.get(kind='collection')
        cover = Sample.objects.get(trip=self.trip, species=self.second)
        self.assertEqual(collection.owner, self.photographer)
        self.assertEqual(collection.trip, self.trip)
        self.assertEqual(collection.gallery_source, cover)
        self.assertEqual(collection.image.name, cover.image.name)
        self.assertEqual(collection.status, 'published')
        self.assertEqual((collection.title, collection.title_en), ('רומבלון - 2026', 'Romblon - 2026'))
        self.assertContains(response, 'נוצרה תצפית אוסף')

    def test_no_collection_without_the_checkbox(self):
        response = self.preview()
        self.apply(response.context['token'], collection_image='0')
        self.assertFalse(Sample.objects.filter(kind='collection').exists())
        self.assertEqual(Sample.objects.filter(kind='species').count(), 2)

    def test_collection_photo_must_be_one_of_the_imported_photos(self):
        response = self.preview()
        response = self.apply(response.context['token'], selected=['0'], collection='yes', collection_image='1', collection_title='T')
        self.assertIn('תמונת תצפית האוסף', response.context['error'])
        self.assertFalse(Sample.objects.exists())

    def test_collection_needs_a_title(self):
        response = self.preview()
        response = self.apply(response.context['token'], collection='yes', collection_image='0', collection_title=' ')
        self.assertIn('כותרת', response.context['error'])
        self.assertFalse(Sample.objects.exists())

    def test_a_trip_that_already_has_a_collection_gets_no_second_one(self):
        existing = Sample.objects.create(kind='collection', trip=self.trip, owner=self.manager, title='Old',
                                         video_url='https://youtu.be/abcdefghijk')
        response = self.preview()
        self.assertEqual(response.context['existing_collection'], existing)
        self.assertNotContains(response, 'name="collection_image"')
        response = self.apply(response.context['token'], collection='yes', collection_image='0', collection_title='New')
        self.assertIn('כבר יש תצפית אוסף', response.context['error'])
        self.assertEqual(Sample.objects.filter(kind='collection').count(), 1)
