"""Offline video copies, phase 1: the Mac folder per trip and the file name per observation (local_videos.py)."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.admin.sites import site as admin_site
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, RequestFactory

from .forms import SampleForm
from .local_videos import (validate_local_video_folder, validate_local_video_file, local_video_path, local_video_status,
                           STATUS_NONE, STATUS_MISSING, STATUS_NOT_FOUND, STATUS_OK, STATUS_UNREACHABLE)
from .models import Country, Sea, Region, DiveTrip, Species, Sample
from .table_transfer import export_table, plan, fingerprint, apply


class LocalVideoValidationTests(TestCase):
    """The trip folder is blank or an absolute Mac path (no ".."); the observation's file is a bare
    video file name (.mp4/.mov/.m4v, any case) -- never a path, so it can only point inside its trip's folder."""
    def test_folder(self):
        for ok in ('', '/Users/boazliebes/Movies/Anilao 2025', '/Volumes/Video/אנילאו', '~/Movies/Trip'):
            validate_local_video_folder(ok)
        for bad in ('Movies/Anilao', 'C:\\Videos', '/Users/x/../y'):
            with self.assertRaises(ValidationError): validate_local_video_folder(bad)

    def test_file(self):
        for ok in ('', 'Phyllidia ocellata.mp4', 'A-1.MOV', 'clip.m4v'):
            validate_local_video_file(ok)
        for bad in ('sub/clip.mp4', '../clip.mp4', 'a\\b.mp4', 'clip.avi', 'clip'):
            with self.assertRaises(ValidationError): validate_local_video_file(bad)


class LocalVideoBase(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_superuser('admin', password='testing')
        self.country = Country.objects.create(name='Israel')
        self.sea = Sea.objects.create(name='Mediterranean')
        self.region = Region.objects.create(name='Mikhmoret', country=self.country, sea=self.sea)
        self.trip = DiveTrip.objects.create(code='M26', title='Mikhmoret trip', year=2026, country=self.country, region=self.region)
        self.species = Species.objects.create(scientific_name='Aplysia dactylomela', genus='Aplysia', species='dactylomela')
        self.sample = Sample(owner=self.owner, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species,
                             status=Sample.Status.PUBLISHED, video_url='https://youtu.be/11111111111')
        self.sample.save()


class LocalVideoStatusTests(LocalVideoBase):
    """Status of the local copy: none (no YouTube video), missing (folder or file name not set),
    unreachable (set, but the folder is not on this machine -- the live site), not_found (folder here, file
    not in it), ok (the file exists). The path is always trip folder / file name."""
    def test_statuses(self):
        self.assertEqual(local_video_status(self.sample), STATUS_MISSING)
        self.sample.local_video_file = 'clip.mp4'
        self.assertEqual(local_video_status(self.sample), STATUS_MISSING)  # trip folder still empty
        self.trip.local_video_folder = '/no/such/folder/on/this/machine'
        self.assertEqual(local_video_status(self.sample), STATUS_UNREACHABLE)
        with tempfile.TemporaryDirectory() as folder:
            self.trip.local_video_folder = folder
            self.assertEqual(local_video_path(self.sample), Path(folder) / 'clip.mp4')
            self.assertEqual(local_video_status(self.sample), STATUS_NOT_FOUND)
            (Path(folder) / 'clip.mp4').write_bytes(b'x')
            self.assertEqual(local_video_status(self.sample), STATUS_OK)
        self.sample.video_url = ''
        self.assertEqual(local_video_status(self.sample), STATUS_NONE)

    def test_model_fields_validate(self):
        self.trip.local_video_folder = 'relative/folder'
        with self.assertRaises(ValidationError) as caught: self.trip.full_clean()
        self.assertIn('local_video_folder', caught.exception.message_dict)
        self.sample.local_video_file = 'folder/clip.mp4'
        with self.assertRaises(ValidationError) as caught: self.sample.full_clean()
        self.assertIn('local_video_file', caught.exception.message_dict)


class LocalVideoTransferTests(LocalVideoBase):
    """Both fields travel through table transfer (trips: local_video_folder, samples: local_video_file). A row
    from an older file/environment without the field leaves the target's value unchanged (never blanks it)."""
    def _apply(self, doc):
        with patch('observations.table_transfer.create_backup', return_value=Path('test.sqlite3')):
            apply(doc, fingerprint())

    def test_trip_folder_exported_and_imported(self):
        doc = export_table('trips')
        self.assertEqual(doc['rows'][0]['local_video_folder'], '')
        doc['rows'][0]['local_video_folder'] = '/Users/boazliebes/Movies/Mikhmoret'
        items = plan(doc)
        self.assertEqual(items[0]['action'], 'update')
        self.assertIn('תיקיית הסרטונים במק', [c['field'] for c in items[0]['changes']])
        self._apply(doc)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.local_video_folder, '/Users/boazliebes/Movies/Mikhmoret')

    def test_older_trip_row_keeps_target_folder(self):
        doc = export_table('trips')
        DiveTrip.objects.filter(pk=self.trip.pk).update(local_video_folder='/Users/boazliebes/Movies/Keep')
        del doc['rows'][0]['local_video_folder']
        doc['rows'][0]['title'] = 'Renamed trip'
        self._apply(doc)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.title, 'Renamed trip')
        self.assertEqual(self.trip.local_video_folder, '/Users/boazliebes/Movies/Keep')

    def test_invalid_trip_folder_is_rejected(self):
        doc = export_table('trips')
        doc['rows'][0]['local_video_folder'] = 'relative/folder'
        with self.assertRaises(ValidationError): plan(doc)

    def test_sample_file_exported_and_imported(self):
        doc = export_table('samples')
        self.assertEqual(doc['rows'][0]['local_video_file'], '')
        doc['rows'][0]['local_video_file'] = 'Aplysia dactylomela.mp4'
        doc['media_mode'] = 'separate'
        items = plan(doc)
        self.assertEqual(items[0]['action'], 'update')
        self._apply(doc)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.local_video_file, 'Aplysia dactylomela.mp4')

    def test_older_sample_row_keeps_target_file(self):
        doc = export_table('samples')
        Sample.objects.filter(pk=self.sample.pk).update(local_video_file='keep.mp4')
        del doc['rows'][0]['local_video_file']
        doc['rows'][0]['note_he'] = 'הערה'
        doc['media_mode'] = 'separate'
        self._apply(doc)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.note_he, 'הערה')
        self.assertEqual(self.sample.local_video_file, 'keep.mp4')

    def test_invalid_sample_file_is_rejected(self):
        doc = export_table('samples')
        doc['rows'][0]['local_video_file'] = '../../etc/passwd.mp4'
        doc['media_mode'] = 'separate'
        with self.assertRaises(ValidationError): plan(doc)


class LocalVideoAdminTests(LocalVideoBase):
    """The file name is edited in the admin only -- the members' observation form does not show it. The trip
    folder is a normal DiveTrip admin field."""
    def test_admin_forms(self):
        request = RequestFactory().get('/'); request.user = self.owner
        self.assertNotIn('local_video_file', SampleForm.base_fields)
        sample_form = admin_site._registry[Sample].get_form(request, self.sample)
        self.assertIn('local_video_file', sample_form.base_fields)
        trip_form = admin_site._registry[DiveTrip].get_form(request, self.trip)
        self.assertIn('local_video_folder', trip_form.base_fields)

    def test_admin_change_pages_render(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(f'/admin/observations/sample/{self.sample.pk}/change/'), 'local_video_file')
        self.assertContains(self.client.get(f'/admin/observations/divetrip/{self.trip.pk}/change/'), 'local_video_folder')
