from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from .models import DiveTrip, Sample, Species, TaxonGenus


class AssignGenusDefiningSamplesTests(TestCase):
    def setUp(self):
        # create_backup() does real file I/O (backing up the live sqlite file) -- irrelevant to
        # the assignment logic under test here, and the test runner's in-memory database isn't
        # a real file to back up in the first place.
        patcher = patch('observations.management.commands.assign_genus_defining_samples.create_backup', return_value=Path('backup-stub.sqlite3'))
        self.addCleanup(patcher.stop)
        patcher.start()
        self.user = User.objects.create_user('owner', password='a-valid-password-927')
        self.trip = DiveTrip.objects.create(title='Genus library', year=2026)
        self.genus = TaxonGenus.objects.create(name='Chromodoris')

    def genus_sample(self, **kwargs):
        if 'video_url' not in kwargs:
            self._video_counter = getattr(self, '_video_counter', 0) + 1
            kwargs = dict(kwargs, video_url=f'https://youtu.be/{str(self._video_counter).zfill(11)}')
        data = dict(owner=self.user, kind=Sample.Kind.GENUS, species_other='Chromodoris', trip=self.trip)
        data.update(kwargs)
        item = Sample(**data)
        item.save_reviewed(actor=self.user, approve=True)
        return item

    def test_dry_run_makes_no_database_changes(self):
        sample = self.genus_sample()
        call_command('assign_genus_defining_samples')
        self.genus.refresh_from_db()
        self.assertIsNone(self.genus.defining_sample_id)

    def test_apply_points_the_genus_at_its_own_genus_kind_sample(self):
        sample = self.genus_sample()
        call_command('assign_genus_defining_samples', '--apply')
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.defining_sample_id, sample.pk)

    def test_apply_overrides_an_existing_species_level_defining_sample(self):
        # The genus already has a species-level photo standing in for it (e.g. from
        # build_taxonomy_tables) -- a purpose-built genus photo should take priority.
        species = Species.objects.create(scientific_name='Chromodoris annae')
        species_sample = Sample(owner=self.user, species=species, trip=self.trip,
                                 video_url='https://youtu.be/zzzzzzzzzzz')
        species_sample.save_reviewed()
        self.genus.defining_sample = species_sample
        self.genus.save(update_fields=['defining_sample'])

        genus_sample = self.genus_sample()
        call_command('assign_genus_defining_samples', '--apply')
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.defining_sample_id, genus_sample.pk)

    def test_genus_without_a_matching_sample_is_left_untouched(self):
        species = Species.objects.create(scientific_name='Chromodoris annae')
        species_sample = Sample(owner=self.user, species=species, trip=self.trip,
                                 video_url='https://youtu.be/abcdefghijk')
        species_sample.save_reviewed()
        self.genus.defining_sample = species_sample
        self.genus.save(update_fields=['defining_sample'])

        other_genus = TaxonGenus.objects.create(name='Hypselodoris')  # no genus-kind sample at all
        call_command('assign_genus_defining_samples', '--apply')
        self.genus.refresh_from_db()
        other_genus.refresh_from_db()
        self.assertEqual(self.genus.defining_sample_id, species_sample.pk)
        self.assertIsNone(other_genus.defining_sample_id)

    def test_rerun_is_idempotent(self):
        sample = self.genus_sample()
        call_command('assign_genus_defining_samples', '--apply')
        call_command('assign_genus_defining_samples', '--apply')
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.defining_sample_id, sample.pk)

    def test_unpublished_genus_sample_is_not_used(self):
        # A pending (unapproved) genus-kind sample must not become the genus's public photo.
        pending = Sample.objects.create(owner=self.user, kind=Sample.Kind.GENUS, species_other='Chromodoris',
                                         trip=self.trip, video_url='https://youtu.be/abcdefghijk')
        self.assertEqual(pending.status, 'pending')
        call_command('assign_genus_defining_samples', '--apply')
        self.genus.refresh_from_db()
        self.assertIsNone(self.genus.defining_sample_id)
