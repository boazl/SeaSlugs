"""Species page: "עריכת תצפית" (edit the observation) and, for staff who may change species, "עריכת מין" (the species' admin page)."""
from django.contrib.auth.models import Permission, User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea


class SpeciesPageEditButtonsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', password='x')
        self.country = Country.objects.create(name='Israel')
        self.sea = Sea.objects.create(name='Mediterranean')
        region = Region.objects.create(name='Akhziv', country=self.country, sea=self.sea)
        trip = DiveTrip.objects.create(title='t', year=2026, month=2, country=self.country, region=region)
        self.species = Species.objects.create(scientific_name='Test species', genus='Test', species='species')
        Sample(owner=self.owner, species=self.species, trip=trip, video_url='https://youtu.be/00000000001').save_reviewed()
        self.url = f'/species/{SpeciesArea.objects.get(species=self.species).slug}/'
        self.admin_url = f'/admin/observations/species/{self.species.pk}/change/'

    def test_visitor_sees_neither_button(self):
        page = self.client.get(self.url).content.decode()
        self.assertNotIn('עריכת תצפית', page)
        self.assertNotIn('עריכת מין', page)

    def test_the_observation_owner_sees_edit_observation_only(self):
        self.client.force_login(self.owner)
        page = self.client.get(self.url).content.decode()
        self.assertIn('עריכת תצפית</a>', page)
        self.assertNotIn('עריכת מין', page)
        self.assertNotIn('עריכה</a>', page)

    def test_a_superuser_sees_both_and_the_species_button_opens_its_admin_page(self):
        self.client.force_login(User.objects.create_superuser('boss', 'b@example.org', 'x'))
        page = self.client.get(self.url).content.decode()
        self.assertIn('עריכת תצפית</a>', page)
        self.assertIn(f'<a class="edit-button" href="{self.admin_url}">עריכת מין</a>', page)
        self.assertEqual(self.client.get(self.admin_url).status_code, 200)

    def test_staff_without_permission_to_change_species_do_not_get_the_species_button(self):
        staff = User.objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        self.assertNotIn('עריכת מין', self.client.get(self.url).content.decode())
        staff.user_permissions.add(Permission.objects.get(codename='change_species'))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_login(staff)
        self.assertIn('עריכת מין', self.client.get(self.url).content.decode())

    def test_english_labels(self):
        self.client.force_login(User.objects.create_superuser('boss', 'b@example.org', 'x'))
        page = self.client.get(self.url + '?lang=en').content.decode()
        self.assertIn('Edit observation</a>', page)
        self.assertIn('Edit species</a>', page)
