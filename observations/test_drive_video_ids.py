"""/admin/drive-videos/ and fill_drive_video_ids: rescanning the Google Drive copies stores a copy's new Drive id
(a replaced file is a new Drive file), empties the id of a copy that is gone (or of an observation without a local
file), keeps the id while Drive has not uploaded the new copy yet, and never runs without the Drive folder
(the live site). xattr is mocked (drive_videos.drive_id: path -> id)."""
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from .drive_videos import scan, SAME, UPDATE, CLEAR, WAITING, MISSING
from .models import Country, Sea, Region, DiveTrip, Species, Sample

OLD, NEW = '1OldOldOldOldOld', '1NewNewNewNewNew'


class DriveIdRescanTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('admin', password='testing')
        country = Country.objects.create(name='Philippines'); sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='Romblon', country=country, sea=sea)
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / 'home'; self.drive = Path(tmp.name) / 'drive'
        folder = self.home / 'Trip' / 'Video Output'; folder.mkdir(parents=True)
        self.copies = self.drive / 'Videos' / 'Trip' / 'Video Output'; self.copies.mkdir(parents=True)
        env = patch.dict('os.environ', {'HOME': str(self.home)}); env.start(); self.addCleanup(env.stop)
        root = patch('observations.management.commands.copy_to_drive.DRIVE_ROOT', str(self.drive)); root.start(); self.addCleanup(root.stop)
        self.ids = {}
        xattr = patch('observations.drive_videos.drive_id', side_effect=lambda p: self.ids.get(Path(p).name, '')); xattr.start(); self.addCleanup(xattr.stop)
        backup = patch('observations.drive_video_views.create_backup'); backup.start(); self.addCleanup(backup.stop)
        trip = DiveTrip.objects.create(code='V', title='Trip 2026', year=2026, country=country, region=region, local_video_folder=str(folder))
        self.samples = {}
        for n, name in enumerate(('same', 'replaced', 'gone', 'uploading', 'nocopy', 'nofile'), 1):
            species = Species.objects.create(scientific_name=f'Chromodoris {name}', genus='Chromodoris', species=name, author='X, 2000')
            s = Sample(owner=self.admin, trip=trip, species=species, video_url=f'https://youtu.be/{n:011d}',
                       local_video_file='' if name == 'nofile' else f'{name}.mov', drive_video_id='' if name == 'nocopy' else OLD + str(n))
            s.save_reviewed(); self.samples[name] = s
        for name in ('same', 'replaced', 'uploading'): (self.copies / f'{name}.mov').write_bytes(b'v')
        self.ids = {'same.mov': OLD + '1', 'replaced.mov': NEW}
        self.client.force_login(self.admin)

    def actions(self):
        return {row['sample'].pk: row['action'] for row in scan()}

    def stored(self, name):
        self.samples[name].refresh_from_db(); return self.samples[name].drive_video_id

    def test_scan_sorts_every_case(self):
        s = self.samples
        self.assertEqual(self.actions(), {s['same'].pk: SAME, s['replaced'].pk: UPDATE, s['gone'].pk: CLEAR,
                                          s['uploading'].pk: WAITING, s['nocopy'].pk: MISSING, s['nofile'].pk: CLEAR})

    def test_page_shows_the_changes_and_saves_them(self):
        html = self.client.get('/admin/drive-videos/').content.decode()
        self.assertIn(NEW, html); self.assertIn('עדכון 3 מזהים', html)
        self.client.post('/admin/drive-videos/')
        self.assertEqual(self.stored('replaced'), NEW)
        self.assertEqual(self.stored('gone'), ''); self.assertEqual(self.stored('nofile'), '')
        self.assertEqual(self.stored('same'), OLD + '1'); self.assertEqual(self.stored('uploading'), OLD + '4')
        self.assertContains(self.client.get('/admin/drive-videos/'), 'כל המזהים מעודכנים')

    def test_command_does_the_same(self):
        with patch('observations.management.commands.fill_drive_video_ids.create_backup', return_value=Path('b')):
            call_command('fill_drive_video_ids', apply=True, stdout=io.StringIO())
        self.assertEqual(self.stored('replaced'), NEW); self.assertEqual(self.stored('gone'), '')

    def test_nothing_without_the_drive_folder(self):
        with patch('observations.management.commands.copy_to_drive.DRIVE_ROOT', str(self.drive / 'nope')):
            self.assertContains(self.client.get('/admin/drive-videos/'), 'לא נמצאת במחשב הזה')
            self.client.post('/admin/drive-videos/')
            with self.assertRaises(CommandError): call_command('fill_drive_video_ids', apply=True, stdout=io.StringIO())
        self.assertEqual(self.stored('gone'), OLD + '3')

    def test_admin_index_and_local_videos_link_here(self):
        self.assertContains(self.client.get('/admin/'), '/admin/drive-videos/')
        self.assertContains(self.client.get('/admin/local-videos/'), '/admin/drive-videos/')

    def test_superuser_only(self):
        get_user_model().objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(get_user_model().objects.get(username='staff'))
        self.assertEqual(self.client.get('/admin/drive-videos/').status_code, 403)
