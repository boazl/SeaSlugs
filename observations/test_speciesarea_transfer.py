from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea
from .table_transfer import export_table, plan, fingerprint, apply, TABLES


class SpeciesAreaTransferTests(TestCase):
    """speciesareas transfer mirrors every other reference table (export/preview/apply,
    natural-key matching, no raw pks) -- but unlike them it depends on Samples (via
    defining_sample), so it must come after 'samples' in TABLES and can only resolve once
    the target already has the referenced sample."""
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser('admin', password='testing')
        self.country = Country.objects.create(name='Israel')
        self.sea = Sea.objects.create(name='Mediterranean')
        self.region = Region.objects.create(name='Mikhmoret', country=self.country, sea=self.sea)
        self.trip = DiveTrip.objects.create(title='Mikhmoret trip', year=2026, country=self.country, region=self.region)
        self.species = Species.objects.create(scientific_name='Aplysia dactylomela', genus='Aplysia', species='dactylomela')
        self.sample = Sample(owner=self.owner, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species,
                              status=Sample.Status.PUBLISHED, video_url='https://youtu.be/11111111111')
        self.sample.save()
        self.area = SpeciesArea.objects.create(species=self.species, country=self.country, sea=self.sea,
                                                defining_sample=self.sample)

    def test_table_comes_after_samples(self):
        self.assertLess(list(TABLES).index('samples'), list(TABLES).index('speciesareas'))

    def test_export_uses_natural_keys_not_raw_pks(self):
        doc = export_table('speciesareas')
        row = doc['rows'][0]
        self.assertEqual(row['species'], 'Aplysia dactylomela')
        self.assertEqual(row['country'], 'Israel')
        self.assertEqual(row['sea'], 'Mediterranean')
        self.assertEqual(row['defining_sample'], str(self.sample.transfer_id))
        self.assertNotIn('id', row)

    def test_unchanged_row_reports_same(self):
        doc = export_table('speciesareas')
        self.assertEqual(plan(doc)[0]['action'], 'same')

    def test_repointing_defining_sample_is_an_update_and_preserves_slug(self):
        other = Sample(owner=self.owner, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species,
                        status=Sample.Status.PUBLISHED, video_url='https://youtu.be/22222222222')
        other.save()
        original_slug = self.area.slug
        doc = export_table('speciesareas')
        doc['rows'][0]['defining_sample'] = str(other.transfer_id)
        plan_items = plan(doc)
        self.assertEqual(plan_items[0]['action'], 'update')
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())
        self.area.refresh_from_db()
        self.assertEqual(self.area.defining_sample_id, other.pk)
        self.assertEqual(self.area.slug, original_slug)  # not reset to a freshly generated one

    def test_creates_a_new_row_for_a_species_country_sea_combination_not_yet_present(self):
        new_species = Species.objects.create(scientific_name='Hypselodoris infucata', genus='Hypselodoris', species='infucata')
        new_sample = Sample(owner=self.owner, trip=self.trip, kind=Sample.Kind.SPECIES, species=new_species,
                             status=Sample.Status.PUBLISHED, video_url='https://youtu.be/33333333333')
        new_sample.save()
        doc = export_table('speciesareas')
        doc['rows'].append({'species': 'Hypselodoris infucata', 'country': 'Israel', 'sea': 'Mediterranean',
                             'undetermined_variant': '', 'defining_sample': str(new_sample.transfer_id)})
        items = plan(doc)
        self.assertEqual(items[1]['action'], 'new')
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())
        self.assertTrue(SpeciesArea.objects.filter(species=new_species, country=self.country, sea=self.sea).exists())

    def test_unresolvable_defining_sample_self_heals_instead_of_blocking_the_import(self):
        # Regression: a real-world speciesareas transfer blocked on its very first
        # unresolved row with "חסר ערך מקושר (defining_sample: ...)" -- the defining
        # sample simply hadn't had its own image transferred yet (that happens separately,
        # one photo at a time), which is routine mid-transfer, not a data error. The whole
        # species+area must still come through, falling back to whatever sample this
        # environment already has for it -- exactly like a plain samples-table transfer and
        # a normal publish already self-heal a missing defining sample.
        doc = export_table('speciesareas')
        doc['rows'][0]['defining_sample'] = '00000000-0000-0000-0000-000000000000'
        items = plan(doc)  # must not raise
        self.assertEqual(items[0]['object'].defining_sample_id, self.sample.pk)  # only local candidate

    def test_unresolvable_defining_sample_does_not_block_other_rows_in_the_same_batch(self):
        # The actual shape of the regression: one row's defining sample hasn't arrived yet,
        # but every other row in the same batch must still go through.
        new_species = Species.objects.create(scientific_name='Hypselodoris infucata', genus='Hypselodoris', species='infucata')
        doc = export_table('speciesareas')
        doc['rows'].append({'species': 'Hypselodoris infucata', 'country': 'Israel', 'sea': 'Mediterranean',
                             'undetermined_variant': '', 'defining_sample': '00000000-0000-0000-0000-000000000000'})
        items = plan(doc)  # must not raise even though neither row's defining_sample resolves as given
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['action'], 'same')
        self.assertEqual(items[1]['action'], 'new')
        self.assertIsNone(items[1]['object'].defining_sample_id)  # no local sample at all for this one yet
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())
        self.assertTrue(SpeciesArea.objects.filter(species=new_species).exists())

    def test_missing_species_blocks_import(self):
        doc = export_table('speciesareas')
        doc['rows'][0]['species'] = 'Nonexistent species'
        with self.assertRaises(ValidationError):
            plan(doc)

    def test_access_and_export_via_the_admin_view(self):
        self.client.force_login(self.owner)
        response = self.client.post('/admin/table-transfer/', {'action': 'export', 'table': 'speciesareas'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['rows'][0]['species'], 'Aplysia dactylomela')
