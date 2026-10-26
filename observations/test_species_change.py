"""Changing the species of an existing observation: it is updated in place (same observation, same transfer id), the species it
leaves stops showing it, its photo is replaced by an updated one (or deliberately kept) under the new species' file name,
and a new species that is already on the trip needs an explicit choice (merge into it / remove this one)."""
import io
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea, TaxonFamily, TaxonGenus, TaxonOrder


def png(color):
    buffer = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(buffer, 'PNG')
    return SimpleUploadedFile('p.png', buffer.getvalue(), content_type='image/png')


class SpeciesChangeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='pw-test-12345')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Eilat', year=2026, country=country, region=region, code='ti1')
        self.trip2 = DiveTrip.objects.create(title='Eilat2', year=2025, country=country, region=region, code='ti2')
        order = TaxonOrder.objects.create(name='Nudibranchia')
        family = TaxonFamily.objects.create(name='Phyllidiidae', order=order)
        TaxonGenus.objects.create(name='Phyllidiella', family=family)
        mk = lambda epithet: Species.objects.create(scientific_name=f'Phyllidiella {epithet}', genus='Phyllidiella', species=epithet,
                                                     family='Phyllidiidae', order='Nudibranchia')
        self.pust, self.nigra, self.lizae = mk('pustulosa'), mk('nigra'), mk('lizae')
        self.sample = Sample(owner=self.owner, trip=self.trip, species=self.pust, image=png((10, 20, 30)))
        self.sample.save_reviewed()
        self.old_file = self.sample.image.name
        self.transfer_id = self.sample.transfer_id
        self.client.login(username='manager', password='pw-test-12345')

    def post(self, sample=None, **extra):
        sample = sample or self.sample
        data = dict(kind='species', order='Nudibranchia', family='Phyllidiidae', genus='Phyllidiella', species='nigra', trip=self.trip.pk,
                    site='', title='', title_en='', video_url='', identification_qualifier='', life_stage='')
        data.update(extra)
        return self.client.post(f'/observations/{sample.pk}/edit/', data)

    def gallery(self):
        data = self.client.get('/catalog.js').content.decode().split('=', 1)[1].strip().removesuffix(';')
        return [e['title'] for e in json.loads(data)['species']]

    def other_nigra(self):
        sample = Sample(owner=self.owner, trip=self.trip, species=self.nigra, image=png((90, 90, 90)))
        sample.save_reviewed()
        return sample

    # --- the species changes, no other observation in the way

    def test_a_species_change_without_an_updated_photo_asks_for_one(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertIn('keep_old_media', response.context['form'].errors)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.species, self.pust)                       # nothing changed
        self.assertTrue(default_storage.exists(self.old_file))

    def test_an_updated_photo_replaces_the_old_one_in_the_same_observation(self):
        response = self.post(image=png((200, 20, 30)))
        self.assertEqual(response.status_code, 302)
        sample = Sample.objects.get(pk=self.sample.pk)
        self.assertEqual(sample.transfer_id, self.transfer_id)               # the same observation: a transfer updates it
        self.assertEqual(sample.species, self.nigra)
        self.assertEqual(sample.image.name, 'observations/ti1-phyllidiella-nigra.jpg')
        self.assertTrue(default_storage.exists(sample.image.name))
        self.assertFalse(default_storage.exists(self.old_file))               # the old file is gone
        self.assertEqual(sample.status, 'published')

    def test_the_species_it_leaves_stops_showing_it(self):
        self.post(image=png((200, 20, 30)))
        old_area = SpeciesArea.objects.get(species=self.pust)
        self.assertIsNone(old_area.defining_sample)
        self.assertEqual(self.gallery(), ['Phyllidiella nigra'])
        genus = self.client.get('/genus/Phyllidiella/').content.decode()
        self.assertIn('Phyllidiella nigra', genus)
        self.assertNotIn('Phyllidiella pustulosa', genus)

    def test_the_species_it_leaves_hands_its_card_to_another_observation(self):
        other = Sample(owner=self.owner, trip=self.trip2, species=self.pust, image=png((99, 99, 99)))
        other.save_reviewed()
        self.post(image=png((200, 20, 30)))
        self.assertEqual(SpeciesArea.objects.get(species=self.pust).defining_sample_id, other.pk)
        self.assertEqual(sorted(self.gallery()), ['Phyllidiella nigra', 'Phyllidiella pustulosa'])

    def test_keeping_the_photo_renames_it_for_the_new_species(self):
        with default_storage.open(self.old_file, 'rb') as handle:
            before = handle.read()
        response = self.post(keep_old_media='on')
        self.assertEqual(response.status_code, 302)
        sample = Sample.objects.get(pk=self.sample.pk)
        self.assertEqual(sample.image.name, 'observations/ti1-phyllidiella-nigra.jpg')
        with default_storage.open(sample.image.name, 'rb') as handle:
            self.assertEqual(handle.read(), before)
        self.assertFalse(default_storage.exists(self.old_file))

    def test_editing_without_changing_the_species_needs_nothing_extra(self):
        response = self.post(species='pustulosa', title='x')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(default_storage.exists(self.old_file))

    def test_a_video_only_observation_needs_no_photo(self):
        video = Sample(owner=self.owner, trip=self.trip2, species=self.pust, video_url='https://youtu.be/abcdefghijk')
        video.save_reviewed()
        response = self.post(sample=video, trip=self.trip2.pk, video_url='https://youtu.be/abcdefghijk')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Sample.objects.get(pk=video.pk).species, self.nigra)

    # --- the new species is already on the trip

    def test_a_collision_asks_what_to_do(self):
        other = self.other_nigra()
        response = self.post(image=png((200, 20, 30)))
        self.assertEqual(response.status_code, 200)
        self.assertIn('on_conflict', response.context['form'].errors)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.species, self.pust)
        other.refresh_from_db()
        self.assertTrue(default_storage.exists(other.image.name))

    def test_merge_puts_the_new_photo_in_the_existing_observation_and_removes_this_one(self):
        other = self.other_nigra()
        response = self.post(image=png((200, 20, 30)), on_conflict='merge')
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'#obs-{other.pk}', response['Location'])
        other.refresh_from_db(); self.sample.refresh_from_db()
        self.assertEqual(other.image.name, 'observations/ti1-phyllidiella-nigra.jpg')
        self.assertTrue(default_storage.exists(other.image.name))
        self.assertIsNotNone(self.sample.deleted_at)
        self.assertEqual((self.sample.image.name, self.sample.video_url), ('', ''))
        self.assertFalse(default_storage.exists(self.old_file))
        self.assertEqual(self.gallery(), ['Phyllidiella nigra'])
        self.assertIsNone(SpeciesArea.objects.get(species=self.pust).defining_sample)

    def test_merge_with_the_current_photo_keeps_its_bytes(self):
        other = self.other_nigra()
        with default_storage.open(self.old_file, 'rb') as handle:
            before = handle.read()
        response = self.post(keep_old_media='on', on_conflict='merge')
        self.assertEqual(response.status_code, 302)
        other.refresh_from_db()
        with default_storage.open(other.image.name, 'rb') as handle:
            self.assertEqual(handle.read(), before)

    def test_merge_without_a_photo_decision_still_asks_for_one(self):
        self.other_nigra()
        response = self.post(on_conflict='merge')
        self.assertEqual(response.status_code, 200)
        self.assertIn('keep_old_media', response.context['form'].errors)

    def test_remove_deletes_this_observation_with_its_media_and_leaves_the_other_alone(self):
        other = self.other_nigra()
        other_file = other.image.name
        response = self.post(on_conflict='remove')
        self.assertEqual(response.status_code, 302)
        self.sample.refresh_from_db(); other.refresh_from_db()
        self.assertIsNotNone(self.sample.deleted_at)
        self.assertEqual(self.sample.image.name, '')
        self.assertFalse(default_storage.exists(self.old_file))
        self.assertEqual(other.image.name, other_file)
        self.assertTrue(default_storage.exists(other_file))
        self.assertEqual(other.species, self.nigra)

    def test_a_failure_changes_nothing(self):
        other = self.other_nigra()
        other_file = other.image.name
        with patch.object(Sample, 'save_reviewed', side_effect=ValidationError('boom')):
            response = self.post(image=png((200, 20, 30)), on_conflict='merge')
        self.assertEqual(response.status_code, 200)
        self.sample.refresh_from_db(); other.refresh_from_db()
        self.assertIsNone(self.sample.deleted_at)                             # still there
        self.assertEqual(self.sample.species, self.pust)
        self.assertTrue(default_storage.exists(self.old_file))
        self.assertEqual(other.image.name, other_file)
        self.assertEqual(SpeciesArea.objects.get(species=self.pust).defining_sample_id, self.sample.pk)

    def test_a_photo_shown_by_other_observations_blocks_the_change(self):
        self.other_nigra()
        showing = Sample(owner=self.owner, trip=self.trip2, species=self.lizae, gallery_source=self.sample, image=self.sample.image.name)
        showing.save_reviewed()
        response = self.post(image=png((200, 20, 30)), on_conflict='merge')
        self.assertEqual(response.status_code, 200)
        self.sample.refresh_from_db()
        self.assertIsNone(self.sample.deleted_at)

    def test_the_form_script_asks_the_server_about_a_collision(self):
        other = self.other_nigra()
        response = self.client.get('/observations/species-area-status/', {'species': 'Phyllidiella nigra', 'trip': self.trip.pk, 'sample': self.sample.pk})
        self.assertEqual(response.json()['conflict']['id'], other.pk)
        response = self.client.get('/observations/species-area-status/', {'species': 'Phyllidiella lizae', 'trip': self.trip.pk, 'sample': self.sample.pk})
        self.assertIsNone(response.json()['conflict'])

    def test_the_edit_form_offers_the_two_choices_only_for_an_existing_observation(self):
        html = self.client.get(f'/observations/{self.sample.pk}/edit/').content.decode()
        self.assertIn('name="keep_old_media"', html)
        self.assertIn('name="on_conflict"', html)
        self.assertIn('species-change-notice', html)
        self.assertNotIn('name="keep_old_media"', self.client.get('/observations/new/').content.decode())
