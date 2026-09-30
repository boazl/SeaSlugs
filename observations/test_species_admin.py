from django.contrib.auth.models import User
from django.test import TestCase

from .models import Species


class SpeciesAdminMigrantColumnTests(TestCase):
    """Species.is_migrant is checked far more often than any other admin field is edited,
    so it's a list_editable column on the species changelist (see observations/admin.py) --
    a manager can flag a species as migrant straight from the list, without opening its
    full change form."""

    def setUp(self):
        self.manager = User.objects.create_superuser('manager', password='test-password')
        self.species = Species.objects.create(scientific_name='Test species')

    def changelist_post(self, **field_overrides):
        data = {
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '1', 'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-id': str(self.species.pk),
            '_save': 'Save',
        }
        data.update(field_overrides)
        self.client.force_login(self.manager)
        return self.client.post('/admin/observations/species/', data, follow=True)

    def test_checking_the_changelist_box_flags_the_species_as_migrant(self):
        self.assertFalse(self.species.is_migrant)
        response = self.changelist_post(**{'form-0-is_migrant': 'on'})
        self.assertEqual(response.status_code, 200)
        self.species.refresh_from_db()
        self.assertTrue(self.species.is_migrant)

    def test_unchecking_the_changelist_box_clears_migrant_status(self):
        self.species.is_migrant = True
        self.species.save()
        response = self.changelist_post()  # checkbox omitted from POST == unchecked
        self.assertEqual(response.status_code, 200)
        self.species.refresh_from_db()
        self.assertFalse(self.species.is_migrant)

    def test_migrant_status_filters_the_changelist(self):
        self.species.is_migrant = True
        self.species.save()
        Species.objects.create(scientific_name='Ordinary species')
        self.client.force_login(self.manager)
        response = self.client.get('/admin/observations/species/', {'is_migrant__exact': '1'})
        self.assertContains(response, 'Test species')
        self.assertNotContains(response, 'Ordinary species')
