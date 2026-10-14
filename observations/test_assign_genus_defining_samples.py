"""assign_genus_defining_samples (and the genus admin action that runs it): every order / family /
genus row gets a defining sample that fits it -- an observation one level below (defining.py)."""
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from .models import DiveTrip, Sample, Species, TaxonFamily, TaxonGenus, TaxonOrder


class AssignDefiningSamplesTests(TestCase):
    def setUp(self):
        # create_backup() does real file I/O (backing up the live sqlite file) -- irrelevant here
        patcher = patch('observations.management.commands.assign_genus_defining_samples.create_backup', return_value=Path('backup-stub.sqlite3'))
        self.addCleanup(patcher.stop)
        patcher.start()
        self.user = User.objects.create_superuser('owner', password='a-valid-password-927')
        self.trip = DiveTrip.objects.create(title='Library', year=2026)
        self.order = TaxonOrder.objects.create(name='Nudibranchia')
        self.family = TaxonFamily.objects.create(name='Chromodorididae', order=self.order)
        self.genus = TaxonGenus.objects.create(name='Chromodoris', family=self.family)
        self.species = Species.objects.create(scientific_name='Chromodoris annae', genus='Chromodoris', species='annae')
        self.n = 0

    def sample(self, **kwargs):
        self.n += 1
        item = Sample(owner=self.user, trip=self.trip, video_url=f'https://youtu.be/{str(self.n).zfill(11)}', status='published', **kwargs)
        item.save()
        return item

    def test_saving_fills_each_level_with_an_observation_one_level_below(self):
        species = self.sample(kind=Sample.Kind.SPECIES, species=self.species)
        genus = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris')
        family = self.sample(kind=Sample.Kind.FAMILY, family='Chromodorididae')
        self.sample(kind=Sample.Kind.ORDER, order='Nudibranchia')
        for row in (self.genus, self.family, self.order): row.refresh_from_db()
        self.assertEqual((self.genus.defining_sample_id, self.family.defining_sample_id, self.order.defining_sample_id),
                         (species.pk, genus.pk, family.pk))

    def test_dry_run_makes_no_changes_and_apply_replaces_an_unfit_value(self):
        species = self.sample(kind=Sample.Kind.SPECIES, species=self.species)
        genus_kind = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris')
        TaxonGenus.objects.filter(pk=self.genus.pk).update(defining_sample=genus_kind)     # old rule: wrong level
        call_command('assign_genus_defining_samples')
        self.genus.refresh_from_db(); self.assertEqual(self.genus.defining_sample_id, genus_kind.pk)
        call_command('assign_genus_defining_samples', '--apply')
        self.genus.refresh_from_db(); self.assertEqual(self.genus.defining_sample_id, species.pk)
        call_command('assign_genus_defining_samples', '--apply')   # idempotent
        self.genus.refresh_from_db(); self.assertEqual(self.genus.defining_sample_id, species.pk)

    def test_a_deleted_defining_sample_is_replaced_by_the_next_that_fits(self):
        older = self.sample(kind=Sample.Kind.SPECIES, species=self.species)
        newer = self.sample(kind=Sample.Kind.SPECIES, species=self.species)
        TaxonGenus.objects.filter(pk=self.genus.pk).update(defining_sample=newer)
        newer.soft_delete(self.user)
        self.genus.refresh_from_db(); self.assertEqual(self.genus.defining_sample_id, older.pk)

    def test_the_admin_offers_only_fitting_observations_in_alphabetical_order(self):
        other = Species.objects.create(scientific_name='Chromodoris africana', genus='Chromodoris', species='africana')
        b = self.sample(kind=Sample.Kind.SPECIES, species=self.species)
        a = self.sample(kind=Sample.Kind.SPECIES, species=other)
        self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris')
        self.client.force_login(self.user)
        page = self.client.get(f'/admin/observations/taxongenus/{self.genus.pk}/change/')
        field = page.context['adminform'].form.fields['defining_sample']
        self.assertEqual([s.pk for s in field.queryset], [a.pk, b.pk])
        self.assertContains(page, 'select_search.js')

    def test_refresh_action_runs_regardless_of_selection(self):
        species = self.sample(kind=Sample.Kind.SPECIES, species=self.species)
        TaxonGenus.objects.filter(pk=self.genus.pk).update(defining_sample=None)
        self.client.force_login(self.user)
        response = self.client.post('/admin/observations/taxongenus/',
            {'action': 'refresh_defining_samples', '_selected_action': [str(self.genus.pk)]})
        self.assertEqual(response.status_code, 302)
        self.genus.refresh_from_db()
        self.assertEqual(self.genus.defining_sample_id, species.pk)

    def test_an_empty_level_is_skipped_down_to_the_next(self):
        # no family observation: the order takes a genus one; no genus observation either: a species one
        from .defining import choices
        species = self.sample(kind=Sample.Kind.SPECIES, species=self.species)
        for row in (self.family, self.order): row.refresh_from_db()
        self.assertEqual((self.family.defining_sample_id, self.order.defining_sample_id), (species.pk, species.pk))
        genus = self.sample(kind=Sample.Kind.GENUS, genus='Chromodoris')
        for row in (self.family, self.order): row.refresh_from_db()
        self.assertEqual((self.family.defining_sample_id, self.order.defining_sample_id), (genus.pk, genus.pk))
        self.assertEqual(list(choices(self.order)), [genus])
        # a family observation without a photo or video doesn't count: the level is still "empty"
        silent = Sample(owner=self.user, trip=self.trip, kind=Sample.Kind.FAMILY, family='Chromodorididae', status='published'); silent.save()
        self.order.refresh_from_db(); self.assertEqual(self.order.defining_sample_id, genus.pk)
        family = self.sample(kind=Sample.Kind.FAMILY, family='Chromodorididae')
        self.order.refresh_from_db(); self.assertEqual(self.order.defining_sample_id, family.pk)
