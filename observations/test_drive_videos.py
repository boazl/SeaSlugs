"""Offline videos on the live site: copy_to_drive copies the site and every observation's local video into the
Google Drive folder (Videos/<path under home>, mirrored; secrets and the live SQLite file never copied), and
Sample.drive_video_id (filled from Drive's xattr, carried by table transfer) lets the live site -- where the Mac's
files are unreachable -- show a manager Drive's player instead, without the red "no local copy" mark."""
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings

from .local_videos import statuses, STATUS_DRIVE, validate_drive_video_id
from .management.commands import copy_to_drive
from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea
from .table_transfer import export_table


class DriveVideoBase(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('admin', password='testing')
        country = Country.objects.create(name='Philippines'); sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='Romblon', country=country, sea=sea)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.folder = self.home / 'Romblon Island' / 'Video Output'; self.folder.mkdir(parents=True)
        (self.folder / 'Chromodoris kalawakan.mov').write_bytes(b'video')
        self.trip = DiveTrip.objects.create(code='V', title='Romblon 2026', year=2026, country=country, region=region,
                                            local_video_folder=str(self.folder))
        species = Species.objects.create(scientific_name='Chromodoris kalawakan', genus='Chromodoris', species='kalawakan', author='Gosliner, 2018')
        self.sample = Sample(owner=self.admin, trip=self.trip, kind=Sample.Kind.SPECIES, species=species, status=Sample.Status.PUBLISHED,
                             video_url='https://youtu.be/11111111111', local_video_file='Chromodoris kalawakan.mov')
        self.sample.save_reviewed()
        self.area = SpeciesArea.objects.get(species=species)


class CopyToDriveTests(DriveVideoBase):
    def test_videos_mirrored_in_home_structure(self):
        dest = Path(self.tmp.name) / 'drive'; dest.mkdir()
        stale = dest / 'Videos' / 'Old' / 'gone.mov'; stale.parent.mkdir(parents=True); stale.write_bytes(b'x')
        with patch.object(Path, 'home', return_value=self.home), patch.dict('os.environ', {'HOME': str(self.home)}):
            call_command('copy_to_drive', dest=str(dest), videos_only=True, stdout=io.StringIO())
            self.assertEqual((dest / 'Videos' / 'Romblon Island' / 'Video Output' / 'Chromodoris kalawakan.mov').read_bytes(), b'video')
            self.assertFalse(stale.exists())
            out = io.StringIO(); call_command('copy_to_drive', dest=str(dest), videos_only=True, stdout=out)
            self.assertIn('copied 0 files', out.getvalue())   # unchanged files are skipped

    def test_site_copy_skips_secrets_and_backs_up_the_database(self):
        base = Path(self.tmp.name) / 'site'; (base / '.venv').mkdir(parents=True); (base / 'observations').mkdir()
        for name in ('.env', '.secret_key', 'manage.py', 'db.sqlite3-journal', 'observations/models.py', '.venv/x'):
            (base / name).write_text('x')
        dest = Path(self.tmp.name) / 'drive2'; (dest / 'observations').mkdir(parents=True)
        (dest / 'observations' / 'old.py').write_text('old'); (dest / 'Invoice.pdf').write_text('keep')
        with override_settings(BASE_DIR=base), \
             patch('observations.management.commands.copy_to_drive.backup_database', side_effect=lambda t: t.write_text('db')):
            call_command('copy_to_drive', dest=str(dest), site_only=True, stdout=io.StringIO())
        self.assertTrue((dest / 'manage.py').exists()); self.assertTrue((dest / 'observations' / 'models.py').exists())
        self.assertTrue((dest / 'db.sqlite3').exists())
        for gone in ('.env', '.secret_key', 'db.sqlite3-journal', '.venv', 'observations/old.py'):
            self.assertFalse((dest / gone).exists(), gone)
        self.assertTrue((dest / 'Invoice.pdf').exists())   # top-level files kept there by hand stay


class DriveVideoDisplayTests(DriveVideoBase):
    def test_validation_and_transfer_field(self):
        validate_drive_video_id(''); validate_drive_video_id('1AbC-dEf_123456789')
        with self.assertRaises(ValidationError): validate_drive_video_id('bad id/..')
        self.assertIn('drive_video_id', export_table('samples')['rows'][0])

    def test_live_site_shows_drive_player(self):
        DiveTrip.objects.filter(pk=self.trip.pk).update(local_video_folder='/no/such/folder')   # as on the live site
        Sample.objects.filter(pk=self.sample.pk).update(drive_video_id='1AbC-dEf_123456789')
        self.sample.refresh_from_db()
        self.assertEqual(statuses([self.sample])[self.sample.pk], STATUS_DRIVE)
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertNotIn('drive.google.com', html)            # visitors: nothing
        self.client.force_login(self.admin)
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertIn('src="https://drive.google.com/file/d/1AbC-dEf_123456789/preview"', html)
        self.assertNotIn('local-video-missing">', html)

    def test_mac_prefers_its_own_file(self):
        Sample.objects.filter(pk=self.sample.pk).update(drive_video_id='1AbC-dEf_123456789')
        self.client.force_login(self.admin)
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertIn(f'/observations/{self.sample.pk}/local-video/', html)
        self.assertNotIn('drive.google.com/file', html)

    def test_fill_ids_from_xattr(self):
        dest = Path(self.tmp.name) / 'drive'; dest.mkdir()
        with patch.dict('os.environ', {'HOME': str(self.home)}), \
             patch('observations.management.commands.fill_drive_video_ids.drive_id', return_value='1AbC-dEf_123456789'), \
             patch('observations.management.commands.fill_drive_video_ids.create_backup', return_value=Path('b.sqlite3')):
            call_command('copy_to_drive', dest=str(dest), videos_only=True, stdout=io.StringIO())
            call_command('fill_drive_video_ids', dest=str(dest), apply=True, stdout=io.StringIO())
        self.sample.refresh_from_db(); self.assertEqual(self.sample.drive_video_id, '1AbC-dEf_123456789')


class TransferErrorNamesTheRowTests(DriveVideoBase):
    """A samples-table row that fails validation names the observation (title/species, trip, transfer id)."""
    def test_message_names_the_row(self):
        from .table_transfer import plan
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        doc['rows'][0]['local_video_file'] = 'bad/name.mov'
        items = plan(doc)
        self.assertEqual(items[0]['action'], 'skipped')
        text = items[0]['reason']
        self.assertIn('Chromodoris kalawakan', text); self.assertIn('מסע V', text); self.assertIn(str(self.sample.transfer_id), text)


class SampleTransferRowByRowTests(DriveVideoBase):
    """The samples transfer applies row by row: a row that cannot be applied is skipped with its reason and the
    others are applied. A row whose transfer id is unknown here, for an observation that exists here under another
    id the file does not use (entered separately on each side), is matched by trip + species (or a collection's
    title) and updated in place -- taking the file's id -- instead of clashing with it as a second copy."""
    def _apply(self, doc):
        from .table_transfer import apply, fingerprint
        with patch('observations.table_transfer.create_backup', return_value=Path('b.sqlite3')):
            apply(doc, fingerprint())

    def test_same_observation_under_another_id_is_updated_in_place(self):
        import uuid
        from .table_transfer import plan
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        source_id = str(uuid.uuid4())
        doc['rows'][0]['transfer_id'] = source_id; doc['rows'][0]['drive_video_id'] = '1AbC-dEf_123456789'
        self.assertEqual(plan(doc)[0]['action'], 'update')
        self._apply(doc)
        self.assertEqual(Sample.objects.count(), 1)
        self.sample.refresh_from_db()
        self.assertEqual(self.sample.drive_video_id, '1AbC-dEf_123456789')
        self.assertEqual(str(self.sample.transfer_id), source_id)   # the two environments' ids now agree

    def test_bad_row_is_skipped_and_the_rest_applied(self):
        from .table_transfer import plan
        other = Species.objects.create(scientific_name='Aegires villosus', genus='Aegires', species='villosus', author='Farran, 1905')
        second = Sample(owner=self.admin, trip=self.trip, kind=Sample.Kind.SPECIES, species=other, status=Sample.Status.PUBLISHED,
                        video_url='https://youtu.be/22222222222')
        second.save_reviewed()
        doc = export_table('samples'); doc['media_mode'] = 'separate'
        rows = {r['species']: r for r in doc['rows']}
        rows['Aegires villosus']['species'] = 'Nonexistent species'
        rows['Chromodoris kalawakan']['drive_video_id'] = '1AbC-dEf_123456789'
        self.assertEqual(sorted(i['action'] for i in plan(doc)), ['skipped', 'update'])
        self._apply(doc)
        self.sample.refresh_from_db(); second.refresh_from_db()
        self.assertEqual(self.sample.drive_video_id, '1AbC-dEf_123456789')
        self.assertEqual(second.species_id, other.pk)


class LiveSiteRedMarkTests(DriveVideoBase):
    """On the live site (the Mac folder is unreachable) a video is red for a manager until its Google Drive copy is
    recorded; with a Drive id it is not."""
    def test_red_until_drive_copy(self):
        DiveTrip.objects.filter(pk=self.trip.pk).update(local_video_folder='/no/such/folder')
        self.client.force_login(self.admin)
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertIn('<p class="local-video-missing">', html)
        Sample.objects.filter(pk=self.sample.pk).update(drive_video_id='1AbC-dEf_123456789')
        html = self.client.get(f'/species/{self.area.slug}/').content.decode()
        self.assertNotIn('<p class="local-video-missing">', html)
