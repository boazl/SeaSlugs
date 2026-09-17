import json
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Country, Sea, Region, Species, Sample, DiveTrip


class GalleryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        species = Species.objects.create(scientific_name='Test species')
        self.item = Sample(owner=self.owner, trip=self.trip, species=species, video_url='https://youtu.be/abcdefghijk')
        self.item.save_reviewed()

    def catalog(self):
        response = self.client.get('/catalog.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        return json.loads(response.content.decode().split('=', 1)[1].strip().removesuffix(';'))

    def test_database_updates_and_soft_delete_reach_gallery(self):
        self.assertEqual(self.catalog()['species'][0]['title'], 'Test species')
        self.item.video_url = 'https://youtu.be/zyxwvutsrqp'
        self.item.save()
        self.assertEqual(self.catalog()['species'][0]['video_id'], 'zyxwvutsrqp')
        self.item.soft_delete(self.owner)
        self.assertEqual(self.catalog()['species'], [])

    def test_catalog_exposes_genus_and_epithet_for_alphabetical_sorting(self):
        # The gallery's alphabetical sort (genus, then specific epithet) is done client
        # side in app.js, so both fields must actually reach catalog.js.
        self.item.species.genus = 'Testus'
        self.item.species.species = 'exemplaris'
        self.item.species.save()
        entry = self.catalog()['species'][0]
        self.assertEqual(entry['genus'], 'Testus')
        self.assertEqual(entry['epithet'], 'exemplaris')

    def test_species_hidden_when_area_has_no_defining_sample(self):
        from .models import SpeciesArea
        area = SpeciesArea.objects.get(species=self.item.species)
        area.defining_sample = None
        area.save(update_fields=['defining_sample'])
        self.assertEqual(self.catalog()['species'], [])

    def test_soft_deleting_the_defining_sample_falls_back_to_another_published_one(self):
        second = Sample(owner=self.owner, trip=self.trip, species=self.item.species, video_url='https://youtu.be/12345678901')
        second.save_reviewed()
        self.item.soft_delete(self.owner)
        catalog = self.catalog()
        self.assertEqual(len(catalog['species']), 1)
        self.assertEqual(catalog['species'][0]['video_id'], '12345678901')

    def test_pending_and_incomplete_records_are_not_public(self):
        self.item.status = 'pending'
        self.item.save()
        self.assertEqual(self.catalog()['species'], [])
        self.trip.year = None
        self.trip.save()
        with self.assertRaises(ValidationError):
            self.item.save_reviewed(actor=self.owner, approve=True)
        self.item.status = 'published'
        self.item.save()
        self.assertEqual(self.catalog()['species'], [])

    def test_manager_links_and_admin_form(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/observations/'), f'/admin/observations/sample/{self.item.pk}/change/')
        self.assertEqual(self.client.get(f'/admin/observations/sample/{self.item.pk}/change/').status_code, 200)

    def test_account_navigation_and_private_observation_list(self):
        response = self.client.get('/')
        self.assertNotContains(response, 'href="/observations/"')
        self.assertContains(response, 'href="/observations/login/"')
        self.assertEqual(self.client.get('/observations/').status_code, 302)
        member = User.objects.create_user('ordinary-member', first_name='Dana', password='test-password')
        self.client.force_login(member)
        response = self.client.get('/')
        self.assertContains(response, '<bdi>Dana</bdi>');self.assertNotContains(response, 'ordinary-member')
        self.assertContains(response, 'href="/observations/"')
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        for suffix in ('', '?mine=0', '?owner=1'):
            self.assertNotContains(self.client.get('/observations/' + suffix), 'Test species')
        self.item.owner = member
        self.item.status = 'pending'
        self.item.save()
        self.assertContains(self.client.get('/observations/'), 'Test species')
        self.client.force_login(self.owner)
        self.assertContains(self.client.get('/observations/'), 'Test species')
        self.client.logout()
        self.assertNotContains(self.client.get('/'), 'ordinary-member')
