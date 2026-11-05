from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea
from .table_transfer import export_table, plan, fingerprint, apply


class MainObservationTests(TestCase):
    """On a species page a manager can make one of the other observations the main one ("הפוך לתצפית הראשית"):
    it becomes the area's defining sample and is remembered (SpeciesArea.chosen_sample), so a later publish,
    rebuild or transfer keeps it. Visitors don't see the button and can't use the action. An "other observation"
    card shows its region next to the year when it differs from the main observation's region."""

    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_superuser('admin', password='testing')
        self.visitor = User.objects.create_user('visitor', password='testing')
        self.country = Country.objects.create(name='Philippines')
        self.sea = Sea.objects.create(name='South China Sea')
        self.region = Region.objects.create(name='Anilao', country=self.country, sea=self.sea)
        self.region2 = Region.objects.create(name='Romblon', name_en='Romblon', country=self.country, sea=self.sea)
        self.trip = DiveTrip.objects.create(title='Anilao', year=2025, country=self.country, region=self.region)
        self.trip2 = DiveTrip.objects.create(title='Romblon', year=2026, country=self.country, region=self.region2)
        self.species = Species.objects.create(scientific_name='Phyllodesmium colemani', genus='Phyllodesmium',
                                              species='colemani', author='Rudman, 1991')
        self.first = self._sample(self.trip, '11111111111')
        self.second = self._sample(self.trip2, '22222222222')
        self.area = SpeciesArea.objects.get(species=self.species)
        self.assertEqual(self.area.defining_sample_id, self.first.pk)
        self.url = reverse('species-page', args=[self.area.slug])

    def _sample(self, trip, video):
        s = Sample(owner=self.manager, trip=trip, kind=Sample.Kind.SPECIES, species=self.species,
                   video_url=f'https://youtu.be/{video}')
        s.save_reviewed(self.manager, approve=True)
        return s

    def test_manager_sees_button_and_other_region(self):
        self.client.force_login(self.manager)
        html = self.client.get(self.url).content.decode()
        self.assertIn(reverse('observation-make-main', args=[self.second.pk]), html)
        self.assertIn('הפוך לתצפית הראשית', html)
        self.assertIn('Romblon', html)

    def test_visitor_has_no_button_and_cannot_post(self):
        html = self.client.get(self.url).content.decode()
        self.assertNotIn('הפוך לתצפית הראשית', html)
        self.client.force_login(self.visitor)
        self.assertEqual(self.client.post(reverse('observation-make-main', args=[self.second.pk])).status_code, 404)
        self.area.refresh_from_db()
        self.assertEqual(self.area.defining_sample_id, self.first.pk)

    def test_make_main_sets_defining_and_keeps_language(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('observation-make-main', args=[self.second.pk]) + '?lang=en')
        self.assertEqual(response.url, self.url + '?lang=en')
        self.area.refresh_from_db()
        self.assertEqual((self.area.defining_sample_id, self.area.chosen_sample_id), (self.second.pk, self.second.pk))
        html = self.client.get(self.url).content.decode()
        self.assertIn(reverse('observation-make-main', args=[self.first.pk]), html)   # the old main is now an "other"

    def test_choice_survives_publish_and_rebuild(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('observation-make-main', args=[self.second.pk]))
        trip3 = DiveTrip.objects.create(title='Anilao 2', year=2027, country=self.country, region=self.region)
        self._sample(trip3, '33333333333')              # another publish in the area
        self.first.title = 'edited'; self.first.save_reviewed(self.manager, approve=True)
        self.area.refresh_from_db()
        self.assertEqual(self.area.defining_sample_id, self.second.pk)
        SpeciesArea.rebuild()
        area = SpeciesArea.objects.get(species=self.species)
        self.assertEqual((area.defining_sample_id, area.chosen_sample_id), (self.second.pk, self.second.pk))

    def test_deleted_choice_falls_back_to_automatic(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('observation-make-main', args=[self.second.pk]))
        self.second.soft_delete(self.manager)
        self.area.refresh_from_db()
        self.assertEqual(self.area.defining_sample_id, self.first.pk)

    def test_choice_transfers_and_older_files_keep_target_choice(self):
        self.area.chosen_sample = self.area.defining_sample = self.second
        self.area.save()
        doc = export_table('speciesareas')
        self.assertEqual(doc['rows'][0]['chosen_sample'], str(self.second.transfer_id))
        self.assertEqual(plan(doc)[0]['action'], 'same')
        SpeciesArea.objects.filter(pk=self.area.pk).update(chosen_sample=None, defining_sample=self.first)
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())
        self.area.refresh_from_db()
        self.assertEqual(self.area.chosen_sample_id, self.second.pk)
        older = export_table('speciesareas')
        del older['rows'][0]['chosen_sample']
        SpeciesArea.objects.filter(pk=self.area.pk).update(chosen_sample=self.first)
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(older, fingerprint())
        self.area.refresh_from_db()
        self.assertEqual(self.area.chosen_sample_id, self.first.pk)
