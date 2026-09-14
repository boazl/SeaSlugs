import json
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from .models import Country, Sea, Region, Species, Sample


class GalleryTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        species = Species.objects.create(scientific_name='Test species')
        self.item = Sample(owner=self.owner, country=country, region=region, species=species, year=2026, video_url='https://youtu.be/abcdefghijk')
        self.item.save_reviewed()

    def catalog(self):
        response = self.client.get('/catalog.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        return json.loads(response.content.decode().split('=', 1)[1].strip().removesuffix(';'))

    def test_database_updates_and_soft_delete_reach_gallery(self):
        self.assertEqual(self.catalog()['videos'][0]['title'], 'Test species')
        self.item.title = 'Updated title'
        self.item.save()
        self.assertEqual(self.catalog()['videos'][0]['title'], 'Updated title')
        self.item.soft_delete(self.owner)
        self.assertEqual(self.catalog()['videos'], [])

    def test_pending_and_incomplete_records_are_not_public(self):
        self.item.status = 'pending'
        self.item.save()
        self.assertEqual(self.catalog()['videos'], [])
        self.item.year = None
        with self.assertRaises(ValidationError):
            self.item.save_reviewed(actor=self.owner, approve=True)
        self.item.status = 'published'
        self.item.save()
        self.assertEqual(self.catalog()['videos'], [])

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
