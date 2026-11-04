"""A samples-table transfer respects "one trip records a species once" against the target as it will be
after the import, not row by row against the target as it is now:

- a row whose observation is deleted in the target, while the target already has a live observation of
  that species on that trip (re-entered there under another transfer id), updates that live observation
  instead of failing the whole import;
- two rows that swap species between two observations of one trip import together;
- a real conflict (the row's own observation would become a second one of a species the trip already has,
  and the file doesn't move the other one away) is blocked with BOTH observations named -- the row in the
  file and the one in the target -- so the operator knows which to fix."""
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species
from .table_transfer import apply, export_table, fingerprint, plan


class SampleTransferSameSpeciesTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser('boazl', password='testing')
        country = Country.objects.create(name='Solomon Islands')
        region = Region.objects.create(name='Bilikiki', country=country, sea=Sea.objects.create(name='Solomon Sea'))
        self.trip = DiveTrip.objects.create(code='G', title='Solomon 2023', year=2023, country=country, region=region)
        self.minor = Species.objects.create(scientific_name='Notodoris minor', genus='Notodoris', species='minor')
        self.gardineri = Species.objects.create(scientific_name='Notodoris gardineri', genus='Notodoris', species='gardineri')

    def sample(self, species, video):
        s = Sample(owner=self.owner, trip=self.trip, kind=Sample.Kind.SPECIES, species=species,
                   status=Sample.Status.PUBLISHED, video_url=f'https://youtu.be/{video}')
        s.save()
        return s

    def row(self, doc, sample):
        return next(r for r in doc['rows'] if r['transfer_id'] == str(sample.transfer_id))

    def run_apply(self, doc):
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())

    def test_a_row_whose_observation_was_deleted_updates_the_live_one_of_the_same_species(self):
        old = self.sample(self.minor, '11111111111')
        doc = export_table('samples')
        old.soft_delete(self.owner)
        live = self.sample(self.minor, '22222222222')       # re-entered in the target with another video
        [item] = [i for i in plan(doc) if i['object'] is not None]
        self.assertEqual(item['object'].pk, live.pk)
        self.run_apply(doc)
        self.assertEqual(Sample.objects.filter(trip=self.trip, species=self.minor, deleted_at__isnull=True).count(), 1)

    def test_two_rows_that_swap_species_import_together(self):
        a = self.sample(self.minor, '11111111111'); b = self.sample(self.gardineri, '22222222222')
        doc = export_table('samples')
        self.row(doc, a)['species'] = 'Notodoris gardineri'; self.row(doc, b)['species'] = 'Notodoris minor'
        self.run_apply(doc)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((a.species, b.species), (self.gardineri, self.minor))

    def test_a_real_conflict_names_the_row_and_the_existing_observation(self):
        a = self.sample(self.minor, '11111111111'); b = self.sample(self.gardineri, '22222222222')
        doc = export_table('samples')
        doc['rows'] = [self.row(doc, a)]; doc['rows'][0]['species'] = 'Notodoris gardineri'
        items = plan(doc)   # the row is skipped with the reason; the rest of a file would still be applied
        self.assertEqual([i['action'] for i in items], ['skipped'])
        message = items[0]['reason']
        self.assertIn(str(a.transfer_id), message); self.assertIn(str(b.transfer_id), message)
        self.assertIn(f'#{b.pk}', message); self.assertIn('מסע G', message)
