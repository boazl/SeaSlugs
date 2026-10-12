"""A manager's order / family / genus observation is never put back to "pending" by saving it, and a
media-less one transfers between environments."""
import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from .admin import SampleAdmin
from .models import DiveTrip, Sample, TaxonGenus
from .table_transfer import apply, export_table, fingerprint, plan


class TaxonSamplesStayPublishedTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('boss', password='test-password-x1')
        self.genus = TaxonGenus.objects.create(name='Chromodoris')

    def genus_sample(self, **extra):
        return Sample.objects.create(owner=self.user, kind=Sample.Kind.GENUS, genus='Chromodoris',
                                     video_url='https://youtu.be/abcdefghijk', **extra)

    def admin_save(self, obj):
        request = RequestFactory().post('/'); request.user = self.user
        class Form: changed_data = []
        SampleAdmin(Sample, None).save_model(request, obj, Form(), True)

    def test_saving_a_genus_observation_in_the_admin_publishes_it(self):
        sample = self.genus_sample()
        self.assertEqual(sample.status, 'pending')
        self.admin_save(sample)
        sample.refresh_from_db()
        self.assertEqual(sample.status, 'published')
        self.assertEqual(sample.approved_by_id, self.user.pk)
        sample.video_url = 'https://youtu.be/bbbbbbbbbbb'
        self.admin_save(sample)                          # a later edit keeps it published
        sample.refresh_from_db()
        self.assertEqual(sample.status, 'published')

    def test_an_incomplete_taxon_observation_is_saved_as_pending_not_an_error(self):
        sample = self.genus_sample(site_other='Somewhere')
        self.admin_save(sample)
        sample.refresh_from_db()
        self.assertEqual(sample.status, 'pending')

    def test_a_taxon_observation_without_media_transfers_but_a_species_one_is_still_skipped(self):
        order = Sample.objects.create(owner=self.user, kind=Sample.Kind.ORDER, order='Nudibranchia')
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        order.delete()
        items = plan(doc)
        self.assertEqual([i['action'] for i in items], ['new'])
        with patch('observations.table_transfer.create_backup', return_value=Path('x.sqlite3')):
            apply(doc, fingerprint())
        self.assertTrue(Sample.objects.filter(kind=Sample.Kind.ORDER, order='Nudibranchia').exists())
        row = dict(doc['rows'][0], kind='species', transfer_id='12345678-1234-5678-1234-567812345678')
        items = plan(dict(doc, rows=[row]))
        self.assertEqual(items[0]['action'], 'skipped')
