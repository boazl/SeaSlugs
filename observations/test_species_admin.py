from django.contrib.auth.models import User
from django.test import TestCase

from .models import Species, TaxonFamily, TaxonOrder


class SpeciesAdminMigrantColumnTests(TestCase):
    """Species.is_migrant, name_he, name_en, author, family and order are all editable
    straight from the species changelist (see observations/admin.py's list_editable) --
    a manager can fix these without opening the full change form. family/order
    additionally get an HTML5 datalist of known values (existing Species values plus the
    curated TaxonFamily/TaxonOrder names) for a dropdown-with-autocomplete feel, without
    being restricted to it -- they stay plain text fields, so an unlisted value still
    saves fine."""

    def setUp(self):
        self.manager = User.objects.create_superuser('manager', password='test-password')
        self.species = Species.objects.create(
            scientific_name='Test species', name_he='שם בדיקה', name_en='Test name',
            author='(Someone, 2020)', family='Flabellinidae', order='Nudibranchia',
        )

    def changelist_post(self, **field_overrides):
        # Mirrors what a real changelist page actually submits: every list_editable
        # input keeps its current value unless the test overrides it -- a bare click on
        # "Save" must never blank out fields the user didn't touch.
        data = {
            'form-TOTAL_FORMS': '1', 'form-INITIAL_FORMS': '1', 'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000',
            'form-0-id': str(self.species.pk),
            'form-0-name_he': self.species.name_he,
            'form-0-name_en': self.species.name_en,
            'form-0-author': self.species.author,
            'form-0-family': self.species.family,
            'form-0-order': self.species.order,
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

    def test_editing_author_family_and_order_from_the_changelist(self):
        response = self.changelist_post(**{
            'form-0-author': '(Someone Else, 2024)',
            'form-0-family': 'Facelinidae',
            'form-0-order': 'Pleurobranchida',
        })
        self.assertEqual(response.status_code, 200)
        self.species.refresh_from_db()
        self.assertEqual(self.species.author, '(Someone Else, 2024)')
        self.assertEqual(self.species.family, 'Facelinidae')
        self.assertEqual(self.species.order, 'Pleurobranchida')

    def test_editing_name_he_and_name_en_from_the_changelist(self):
        response = self.changelist_post(**{
            'form-0-name_he': 'שם חדש',
            'form-0-name_en': 'New name',
        })
        self.assertEqual(response.status_code, 200)
        self.species.refresh_from_db()
        self.assertEqual(self.species.name_he, 'שם חדש')
        self.assertEqual(self.species.name_en, 'New name')

    def test_saving_a_different_field_does_not_clear_the_other_editable_fields(self):
        # Regression guard for the exact failure mode a naive list_editable addition risks:
        # Django's changelist formset blanks out any list_editable field missing from the
        # POST, so a page that doesn't resend every input's current value would silently
        # wipe name_he/name_en/author/family/order the moment someone just toggles
        # is_migrant.
        response = self.changelist_post(**{'form-0-is_migrant': 'on'})
        self.assertEqual(response.status_code, 200)
        self.species.refresh_from_db()
        self.assertEqual(self.species.name_he, 'שם בדיקה')
        self.assertEqual(self.species.name_en, 'Test name')
        self.assertEqual(self.species.author, '(Someone, 2020)')
        self.assertEqual(self.species.family, 'Flabellinidae')
        self.assertEqual(self.species.order, 'Nudibranchia')

    def test_author_renders_as_a_single_line_text_input(self):
        self.client.force_login(self.manager)
        html = self.client.get('/admin/observations/species/').content.decode()
        self.assertIn('name="form-0-author"', html)
        self.assertNotIn('<textarea name="form-0-author"', html)

    def test_family_and_order_datalists_include_known_values(self):
        TaxonFamily.objects.create(name='Aeolidiidae')
        TaxonOrder.objects.create(name='Cephalaspidea')
        self.client.force_login(self.manager)
        html = self.client.get('/admin/observations/species/').content.decode()
        # The species' own current value is offered...
        self.assertIn('<option value="Flabellinidae">', html)
        self.assertIn('<option value="Nudibranchia">', html)
        # ...as is a curated TaxonFamily/TaxonOrder name no species uses yet.
        self.assertIn('<option value="Aeolidiidae">', html)
        self.assertIn('<option value="Cephalaspidea">', html)
