import json
from pathlib import Path
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.test import TestCase
from .models import Country, Sea, Region, Site, DiveTrip, Sample, Profile
from .table_transfer import export_table, plan, apply, fingerprint, apply_location_sync


class LocationSyncTests(TestCase):
    def setUp(self):
        self.country = Country.objects.create(name='Israel')
        self.sea = Sea.objects.create(name='Mediterranean')
        self.old = Region.objects.create(name='Akhziv', country=self.country, sea=self.sea, trip_code='I')
        self.new = Region.objects.create(name='Eastern Mediterranean', country=self.country, sea=self.sea)
        self.site = Site.objects.create(name='Canyon', region=self.old)
        self.user = User.objects.create_superuser('root', 'root@example.org', 'pw')

    def sites_doc(self):
        doc = export_table('sites')
        doc['rows'] = [{'name': 'Canyon', 'name_en': '', 'region': {'name': self.new.name, 'country': self.country.name}}]
        doc['sync_missing'] = True
        return doc

    def run_apply(self, doc, expected=None):
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            return apply(doc, expected or fingerprint())

    def test_reassignment_updates_in_place_and_trip_location(self):
        trip = DiveTrip.objects.create(code='I26', title='Trip', site=self.site, region=self.old, country=self.country)
        sample = Sample.objects.create(owner=self.user, site=self.site, trip=trip)
        doc = self.sites_doc()
        self.assertEqual(plan(doc)[0]['action'], 'update')
        self.run_apply(doc)
        self.site.refresh_from_db(); trip.refresh_from_db(); sample.refresh_from_db()
        self.assertEqual(self.site.region, self.new)
        self.assertEqual(trip.region, self.new)
        self.assertEqual(sample.site_id, self.site.pk)
        self.assertEqual(Site.objects.count(), 1)

    def test_duplicate_merge_preserves_sample_trip_and_region_code(self):
        target = Site.objects.create(name='Canyon', region=self.new)
        trip = DiveTrip.objects.create(code='I26', title='Trip', site=self.site, region=self.old, country=self.country)
        sample = Sample.objects.create(owner=self.user, site=self.site, trip=trip)
        self.run_apply(self.sites_doc())
        trip.refresh_from_db(); sample.refresh_from_db()
        self.assertEqual(sample.site_id, target.pk)
        self.assertEqual((trip.site_id, trip.region_id), (target.pk, self.new.pk))
        self.assertEqual(Sample.objects.count(), 1)
        self.assertEqual(DiveTrip.objects.count(), 1)
        # Regular region imports must not reset the local trip naming code.
        self.run_apply(export_table('regions'))
        self.old.refresh_from_db(); self.assertEqual(self.old.trip_code, 'I')

    def test_delete_unreferenced_only_and_default_stays_additive(self):
        self.run_apply(self.sites_doc())
        doc = export_table('regions')
        doc['rows'] = [r for r in doc['rows'] if r['name'] == self.new.name]
        self.run_apply(doc)
        self.assertTrue(Region.objects.filter(pk=self.old.pk).exists())
        doc['sync_missing'] = True
        self.assertIn('delete', [i['action'] for i in plan(doc)])
        self.run_apply(doc)
        self.assertFalse(Region.objects.filter(pk=self.old.pk).exists())
        self.assertTrue(all(i['action'] == 'same' for i in plan(doc)))

    def test_links_block_deletion_and_entire_transaction(self):
        doc = export_table('regions'); doc['rows'] = [r for r in doc['rows'] if r['name'] == self.new.name]
        doc['rows'][0]['name_en'] = 'changed'; doc['sync_missing'] = True
        self.assertIn('blocked', [i['action'] for i in plan(doc)])
        with self.assertRaises(ValidationError): self.run_apply(doc)
        self.new.refresh_from_db(); self.assertEqual(self.new.name_en, '')
        # Even an M2M profile preference must prevent a silent loss of data.
        self.site.delete()
        profile = Profile.objects.create(user=self.user); profile.regions.add(self.old)
        self.assertIn('blocked', [i['action'] for i in plan(doc)])

    def test_empty_sync_and_stale_preview_are_rejected(self):
        doc = self.sites_doc(); snapshot = fingerprint()
        Site.objects.create(name='Other', region=self.old)
        with self.assertRaises(ValidationError): self.run_apply(doc, snapshot)
        self.assertEqual(Site.objects.count(), 2)
        doc['rows'] = []
        with self.assertRaises(ValidationError): plan(doc)

    def test_preview_requires_explicit_checkbox_and_shows_removals(self):
        self.client.force_login(self.user)
        Site.objects.create(name='Obsolete', region=self.new)
        doc = self.sites_doc(); doc.pop('sync_missing')
        def upload(): return SimpleUploadedFile('sites.json', json.dumps(doc).encode(), content_type='application/json')
        page = self.client.post('/admin/table-transfer/', {'action': 'preview', 'file': upload()})
        self.assertNotContains(page, 'מחיקה — הרשומה אינה בקובץ')
        page = self.client.post('/admin/table-transfer/', {'action': 'preview', 'file': upload(), 'synchronize': 'on'})
        self.assertContains(page, 'מחיקה — הרשומה אינה בקובץ')
        self.assertContains(page, 'גיבוי והחלת שינויים')

    def test_duplicate_name_without_exact_target_is_ambiguous(self):
        Site.objects.create(name='Canyon', region=self.new)
        third = Region.objects.create(name='Third', country=self.country, sea=self.sea)
        doc = self.sites_doc(); doc['rows'][0]['region']['name'] = third.name
        with self.assertRaises(ValidationError): plan(doc)

    def test_two_file_sync_rolls_back_site_changes_if_region_has_links(self):
        trip = DiveTrip.objects.create(title='Region only', code='R', country=self.country, region=self.old)
        regions = export_table('regions'); regions['rows'] = [r for r in regions['rows'] if r['name'] == self.new.name]
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            with self.assertRaises(ValidationError):
                apply_location_sync(regions, self.sites_doc(), fingerprint())
        self.site.refresh_from_db(); self.assertEqual(self.site.region, self.old)
        self.assertTrue(DiveTrip.objects.filter(pk=trip.pk).exists())

    def test_two_file_sync_can_add_region_then_reassign_and_remove(self):
        regions = export_table('regions'); regions['rows'] = [r for r in regions['rows'] if r['name'] == self.new.name]
        self.new.delete()
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply_location_sync(regions, self.sites_doc(), fingerprint())
        self.assertEqual(Region.objects.count(), 1)
        self.site.refresh_from_db(); self.assertEqual(self.site.region.name, 'Eastern Mediterranean')
