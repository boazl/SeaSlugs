"""/admin/local-videos/import/: attach a dive trip's video files to its observations. Each file of the chosen Mac
folder gets a row with its observation (the one already holding it, else the match by species name, else a new
observation with fields guessed from the file name), its Google Drive copy and a YouTube link that is required for
every selected row. Saving sets the trip's folder, writes the link, the file name and the Drive id, creates the new
observations (a manager's save publishes), copies missing files into Drive and refuses a link YouTube reports as
deleted. Nothing is saved while any selected row is invalid. A file that belongs to a deleted observation of the trip
(and to no live one) is offered with it, unselected; choosing it restores the observation. Selected rows come first. xattr and YouTube are mocked."""
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, IdentificationQualifier, LifeStage, Region, Sample, Sea, Site, Species

GONE = 'gonegonegon'


class VideoImportTests(TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name) / 'home'; self.drive = Path(tmp.name) / 'drive'
        self.folder = self.home / 'Red Sea' / 'Video Output'; self.folder.mkdir(parents=True); self.drive.mkdir()
        for name in ('Chromodoris annae.mov', 'Hypselodoris cf. infucata juv.mov', 'Eilat 2026.mp4', 'notes.txt'):
            (self.folder / name).write_bytes(b'video-' + name.encode())
        patches = [patch.dict('os.environ', {'HOME': str(self.home)}),
                   patch('observations.management.commands.copy_to_drive.DRIVE_ROOT', str(self.drive)),
                   patch('observations.drive_videos.drive_id', side_effect=lambda p: 'Drive' + Path(p).stem.replace(' ', '').replace('.', '')[:20]),
                   patch('observations.video_import.check_video', side_effect=lambda vid: 'not_found' if vid == GONE else 'ok'),
                   patch('observations.video_import.create_backup')]
        for p in patches: p.start(); self.addCleanup(p.stop)
        IdentificationQualifier.objects.get_or_create(code='cf.'); LifeStage.objects.get_or_create(code='juv.')
        self.admin = User.objects.create_superuser('manager', password='pw'); self.client.force_login(self.admin)
        country = Country.objects.create(name='ישראל', name_en='Israel'); sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.site = Site.objects.create(name='גן יפני', region=region)
        self.trip = DiveTrip.objects.create(code='J7', title='Eilat 2026', year=2026, month=6, country=country, region=region)
        self.annae = Species.objects.create(scientific_name='Chromodoris annae', genus='Chromodoris', species='annae', author='Bergh, 1877')
        self.infucata = Species.objects.create(scientific_name='Hypselodoris infucata', genus='Hypselodoris', species='infucata', author='Rüppell & Leuckart, 1830')
        self.existing = Sample(owner=self.admin, trip=self.trip, species=self.annae, image='observations/a.jpg', site=self.site, day=4)
        Sample.objects.bulk_create([self.existing]); self.existing = Sample.objects.get(species=self.annae)

    def url(self):
        return f'/admin/local-videos/import/?trip={self.trip.pk}&folder={self.folder}'

    def rows(self):
        return {r['name']: r for r in self.client.get(self.url()).context['rows']}

    def post(self, rows, **extra):
        data = {'trip': self.trip.pk, 'folder': str(self.folder), 'copy_to_drive': '1', 'selected': []}
        for name, r in self.rows().items():
            i = r['index']; data[f'name_{i}'] = name; data[f'sample_{i}'] = r['sample']
            for key, value in r['new'].items(): data[f'{key}_{i}'] = value
            if name in rows:
                data['selected'].append(str(i)); data.update({f'{k}_{i}': v for k, v in rows[name].items()})
        data.update(extra)
        return self.client.post('/admin/local-videos/import/', data)

    def test_superuser_only_and_linked(self):
        self.assertContains(self.client.get('/admin/'), '/admin/local-videos/import/')
        User.objects.create_user('staff', password='pw', is_staff=True)
        self.client.force_login(User.objects.get(username='staff'))
        self.assertEqual(self.client.get('/admin/local-videos/import/').status_code, 403)

    def test_rows_match_existing_and_guess_new(self):
        rows = self.rows()
        self.assertEqual(sorted(rows), ['Chromodoris annae.mov', 'Eilat 2026.mp4', 'Hypselodoris cf. infucata juv.mov'])
        self.assertEqual(rows['Chromodoris annae.mov']['sample'], str(self.existing.pk))
        new = rows['Hypselodoris cf. infucata juv.mov']
        self.assertEqual(new['sample'], 'new')
        self.assertEqual((new['new']['species'], new['new']['qualifier'], new['new']['life_stage']), ('Hypselodoris infucata', 'cf.', 'juv.'))
        self.assertEqual(new['drive']['path'], 'Videos/Red Sea/Video Output/Hypselodoris cf. infucata juv.mov')
        self.assertFalse(new['drive']['exists'])

    def test_youtube_link_required(self):
        response = self.post({'Chromodoris annae.mov': {}})
        self.assertContains(response, 'יש להזין קישור YouTube')
        self.existing.refresh_from_db(); self.assertEqual(self.existing.video_url, '')
        self.trip.refresh_from_db(); self.assertEqual(self.trip.local_video_folder, '')

    def test_save_updates_creates_and_copies_to_drive(self):
        response = self.post({'Chromodoris annae.mov': {'url': 'https://youtu.be/aaaaaaaaaaa'},
                              'Hypselodoris cf. infucata juv.mov': {'url': 'https://youtu.be/bbbbbbbbbbb', 'site': str(self.site.pk), 'day': '5', 'depth': '12.5'},
                              'Eilat 2026.mp4': {'url': 'https://youtu.be/ccccccccccc', 'kind': 'collection', 'title': 'Eilat 2026'}})
        self.assertEqual(response.status_code, 302, (response.context or {}).get('error') if response.status_code == 200 else '')
        self.trip.refresh_from_db(); self.assertEqual(self.trip.local_video_folder, str(self.folder))
        self.existing.refresh_from_db()
        self.assertEqual((self.existing.video_url, self.existing.local_video_file, self.existing.drive_video_id),
                         ('https://youtu.be/aaaaaaaaaaa', 'Chromodoris annae.mov', 'DriveChromodorisannae'))
        self.assertEqual(self.existing.status, 'published'); self.assertEqual(self.existing.day, 4)
        new = Sample.objects.get(species=self.infucata)
        self.assertEqual((new.identification_qualifier, new.life_stage, new.site, new.day, str(new.depth), new.owner, new.status),
                         ('cf.', 'juv.', self.site, 5, '12.5', self.admin, 'published'))
        collection = Sample.objects.get(kind='collection')
        self.assertEqual((collection.title, collection.status, collection.local_video_file), ('Eilat 2026', 'published', 'Eilat 2026.mp4'))
        copy = self.drive / 'Videos' / 'Red Sea' / 'Video Output' / 'Chromodoris annae.mov'
        self.assertEqual(copy.read_bytes(), b'video-Chromodoris annae.mov')
        rows = self.rows()
        self.assertTrue(rows['Chromodoris annae.mov']['done']); self.assertFalse(rows['Chromodoris annae.mov']['checked'])

    def test_nothing_saved_when_one_row_is_wrong(self):
        response = self.post({'Chromodoris annae.mov': {'url': 'https://youtu.be/aaaaaaaaaaa'},
                              'Hypselodoris cf. infucata juv.mov': {'url': f'https://youtu.be/{GONE}'}})
        self.assertContains(response, 'לא נמצא ב-YouTube')
        self.existing.refresh_from_db(); self.assertEqual(self.existing.video_url, '')
        self.assertFalse(Sample.objects.filter(species=self.infucata).exists())

    def test_unknown_species_duplicate_video_and_sample(self):
        response = self.post({'Hypselodoris cf. infucata juv.mov': {'url': 'https://youtu.be/aaaaaaaaaaa', 'species': 'Nonexistent thing'},
                              'Eilat 2026.mp4': {'url': 'https://youtu.be/aaaaaaaaaaa', 'sample': str(self.existing.pk)},
                              'Chromodoris annae.mov': {'url': 'https://youtu.be/ddddddddddd'}})
        self.assertContains(response, 'לא נמצא ברשימת המינים')
        self.assertContains(response, 'אותו סרטון YouTube נבחר גם')
        self.assertContains(response, 'התצפית נבחרה גם לקובץ')
        self.assertEqual(Sample.objects.exclude(video_url='').count(), 0)

    def test_video_used_by_another_observation_rolls_back(self):
        other = Sample(owner=self.admin, trip=self.trip, species=self.infucata, video_url='https://youtu.be/eeeeeeeeeee'); other.save_reviewed()
        response = self.post({'Chromodoris annae.mov': {'url': 'https://youtu.be/eeeeeeeeeee'}})
        self.assertContains(response, 'Chromodoris annae.mov:')
        self.existing.refresh_from_db(); self.assertEqual(self.existing.video_url, '')

    def test_missing_folder(self):
        self.assertContains(self.client.get(f'/admin/local-videos/import/?trip={self.trip.pk}&folder=/no/such/folder'), 'התיקייה לא נמצאה')

    def test_selected_rows_first(self):
        Sample.objects.filter(pk=self.existing.pk).update(video_url='https://youtu.be/aaaaaaaaaaa')
        self.trip.local_video_folder = str(self.folder); self.trip.save()
        Sample.objects.filter(pk=self.existing.pk).update(local_video_file='Chromodoris annae.mov')
        with patch('observations.video_import.drive_videos.available', return_value=False), \
             patch('observations.drive_videos.drive_root', return_value=self.drive / 'none'):
            rows = self.client.get(self.url()).context['rows']
        self.assertEqual([r['checked'] for r in rows], [True, True, False])
        self.assertEqual(rows[-1]['name'], 'Chromodoris annae.mov')

    def test_deleted_observation_offered_and_restored(self):
        gone = Sample(owner=self.admin, trip=self.trip, species=self.infucata, identification_qualifier='cf.', life_stage='juv.',
                      video_url='https://youtu.be/fffffffffff'); gone.save_reviewed()
        gone.soft_delete(self.admin)
        row = self.rows()['Hypselodoris cf. infucata juv.mov']
        self.assertEqual(row['sample'], str(gone.pk)); self.assertTrue(row['deleted_match']); self.assertFalse(row['checked'])
        self.assertContains(self.client.get(self.url()), 'הקובץ מתאים לתצפית שנמחקה')
        response = self.post({'Hypselodoris cf. infucata juv.mov': {'url': 'https://youtu.be/fffffffffff'}})
        self.assertEqual(response.status_code, 302)
        gone.refresh_from_db()
        self.assertIsNone(gone.deleted_at); self.assertEqual(gone.local_video_file, 'Hypselodoris cf. infucata juv.mov')
        self.assertEqual(gone.status, 'published')
        self.assertEqual(Sample.objects.filter(species=self.infucata).count(), 1)

    def test_live_observation_wins_over_deleted(self):
        gone = Sample(owner=self.admin, trip=self.trip, species=self.annae, video_url='https://youtu.be/fffffffffff'); gone.save_reviewed()
        gone.soft_delete(self.admin)
        self.assertEqual(self.rows()['Chromodoris annae.mov']['sample'], str(self.existing.pk))
