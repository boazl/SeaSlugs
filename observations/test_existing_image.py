import hashlib
import tempfile

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Country, DiveTrip, Region, Sample, Sea, Species

STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
            'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}


@override_settings(STORAGES=STORAGES)
class ExistingImageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner', password='a-valid-password-927')
        country = Country.objects.create(name='Israel')
        region = Region.objects.create(name='Akhziv', country=country, sea=Sea.objects.create(name='Mediterranean'))
        self.trip = DiveTrip.objects.create(title='Akhziv dive', code='I26Aug', year=2026, month=2, country=country, region=region)
        self.source_species = Species.objects.create(scientific_name='Source species')
        self.target_species = Species.objects.create(scientific_name='Target species')
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.name = default_storage.save('observations/transfer/source.jpg', ContentFile(b'fake-bytes'))
        self.source = Sample.objects.create(owner=self.user, species=self.source_species, trip=self.trip, image=self.name,
            kind='species', status='published')
        self.client.force_login(self.user)

    def data(self, **extra):
        return dict({'species': 'Target species', 'trip': str(self.trip.pk), 'site': '', 'kind': 'species'}, **extra)

    def test_the_observation_points_at_the_same_file_as_the_chosen_gallery_image(self):
        response = self.client.post('/observations/new/', self.data(existing_image=f'https://seaslugs.org.il/observations/{self.source.pk}/photo/'))
        self.assertEqual(response.status_code, 302)
        item = Sample.objects.get(species=self.target_species)
        self.assertEqual(item.image.name, self.name)
        self.assertEqual(item.image_hash, hashlib.sha256(b'fake-bytes').hexdigest())
        self.assertEqual(Sample.objects.filter(image=self.name).count(), 2)

    def test_removing_the_image_from_one_observation_keeps_the_file_for_the_other(self):
        self.client.post('/observations/new/', self.data(existing_image=f'/observations/{self.source.pk}/photo/'))
        item = Sample.objects.get(species=self.target_species)
        self.client.post(f'/observations/{item.pk}/action/', {'action': 'release_species'})   # it defines its species until released
        self.client.post(f'/observations/{item.pk}/action/', {'action': 'delete_image'})
        item.refresh_from_db()
        self.assertFalse(item.image)
        self.assertTrue(default_storage.exists(self.name))
        self.assertEqual(Sample.objects.get(pk=self.source.pk).image.name, self.name)

    def test_an_upload_and_an_existing_image_together_are_refused(self):
        upload = SimpleUploadedFile('a.png', b'x', content_type='image/png')
        response = self.client.post('/observations/new/', self.data(existing_image=f'/observations/{self.source.pk}/photo/', image=upload))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Sample.objects.filter(species=self.target_species).exists())

    def test_only_a_published_existing_image_can_be_chosen(self):
        pending = Sample.objects.create(owner=self.user, species=self.target_species, trip=self.trip, kind='species', status='pending',
            image=default_storage.save('observations/transfer/pending.jpg', ContentFile(b'other')))
        for reference in (f'/observations/{pending.pk}/photo/', '/observations/999999/photo/', 'https://example.com/x.jpg', '/observations/1/edit/'):
            response = self.client.post('/observations/new/', self.data(existing_image=reference, species='Source species'))
            self.assertEqual(response.status_code, 200, reference)
        self.assertEqual(Sample.objects.filter(species=self.source_species).count(), 1)

    def test_replacing_an_old_own_image_with_a_gallery_image_cleans_up_the_unused_file(self):
        own_name = default_storage.save('observations/transfer/own.jpg', ContentFile(b'my-own-bytes'))
        mine = Sample.objects.create(owner=self.user, species=self.target_species, trip=self.trip, image=own_name, kind='species', status='published')
        response = self.client.post(f'/observations/{mine.pk}/edit/', self.data(existing_image=f'/observations/{self.source.pk}/photo/'))
        self.assertEqual(response.status_code, 302)
        mine.refresh_from_db()
        self.assertEqual(mine.image.name, self.name)
        self.assertFalse(default_storage.exists(own_name))
        self.assertTrue(default_storage.exists(self.name))


@override_settings(STORAGES=STORAGES)
class ImageSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner', password='a-valid-password-927')
        country = Country.objects.create(name='Israel')
        region = Region.objects.create(name='Akhziv', country=country, sea=Sea.objects.create(name='Mediterranean'))
        self.trip = DiveTrip.objects.create(title='Akhziv dive', code='I26Aug', year=2026, country=country, region=region)
        self.other_trip = DiveTrip.objects.create(title='Eilat dive', code='J26Aug', year=2026, country=country, region=region)
        chromo, doris = Species.objects.create(scientific_name='Chromodoris magnifica'), Species.objects.create(scientific_name='Doris pseudoargus')
        make = lambda species, trip, n, **kw: Sample.objects.create(owner=self.user, species=species, trip=trip, kind='species',
            status=kw.pop('status', 'published'), image=f'observations/{n}.jpg', **kw)
        self.a = make(chromo, self.trip, 'a')
        self.b = make(doris, self.other_trip, 'b')
        self.pending = make(chromo, self.other_trip, 'c', status='pending')
        self.no_image = Sample.objects.create(owner=self.user, species=doris, trip=self.trip, kind='species', status='published', video_url='https://youtu.be/abcdefghijk')

    def ids(self, **params):
        return [r['id'] for r in self.client.get('/observations/image-search/', params).json()['results']]

    def test_requires_login(self):
        self.assertEqual(self.client.get('/observations/image-search/').status_code, 302)

    def test_lists_only_published_observations_with_an_image(self):
        self.client.force_login(self.user)
        self.assertEqual(set(self.ids()), {self.a.pk, self.b.pk})

    def test_filters_by_name_and_by_trip(self):
        self.client.force_login(self.user)
        self.assertEqual(self.ids(q='chromodoris'), [self.a.pk])
        self.assertEqual(self.ids(q='doris pseudo'), [self.b.pk])
        self.assertEqual(self.ids(trip=self.other_trip.pk), [self.b.pk])
        self.assertEqual(self.ids(q='I26Aug'), [self.a.pk])
        self.assertEqual(self.ids(q='nothing like this'), [])

    def test_result_has_the_photo_address_label_and_trip(self):
        self.client.force_login(self.user)
        row = self.client.get('/observations/image-search/', {'q': 'chromodoris'}).json()['results'][0]
        self.assertEqual(row['url'], f'/observations/{self.a.pk}/photo/')
        self.assertEqual(row['trip'], 'Akhziv dive')
        self.assertIn('Chromodoris', row['label'])

    def test_copy_address_button_is_for_signed_in_users_only(self):
        self.assertNotContains(self.client.get('/observations/trips/'), 'data-copy-url')
        self.client.force_login(self.user)
        page = self.client.get('/observations/')
        self.assertContains(page, f'data-copy-url="/observations/{self.a.pk}/photo/"')
