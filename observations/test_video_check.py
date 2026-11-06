"""/admin/video-check/: a scan finds observations whose YouTube video is gone, and offers per observation
"update the link" (re-uploaded video), "remove the link" (only with a photo) or "delete the observation" (only
without a photo). YouTube's oEmbed answer decides: 200 ok, 404/400 deleted, 401/403 private or embedding blocked,
no answer = check failed. The network is mocked here (video_check._oembed_code)."""
import io
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from .models import ActivityEvent, Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea
from .video_check import status_for_code, scan, STATUS_OK, STATUS_NOT_FOUND, STATUS_RESTRICTED, STATUS_ERROR

GONE, PRIVATE, ALIVE, ALIVE2, NEW, NEW_GONE = 'gonegonegon', 'privateprvt', 'alivealivea', 'alive2alive', 'newnewnewne', 'newgonenewg'
CODES = {GONE: 404, PRIVATE: 401, ALIVE: 200, ALIVE2: 200, NEW: 200, NEW_GONE: 404}


def png():
    buffer = io.BytesIO(); Image.new('RGB', (40, 30), (10, 120, 200)).save(buffer, 'PNG')
    return SimpleUploadedFile('p.png', buffer.getvalue(), content_type='image/png')


def fake_code(video_id):
    return CODES.get(video_id)


class StatusTests(TestCase):
    """oEmbed codes map to statuses; the scan checks each id once."""
    def test_codes(self):
        self.assertEqual(status_for_code(200), STATUS_OK)
        self.assertEqual(status_for_code(404), STATUS_NOT_FOUND)
        self.assertEqual(status_for_code(400), STATUS_NOT_FOUND)
        self.assertEqual(status_for_code(401), STATUS_RESTRICTED)
        self.assertEqual(status_for_code(403), STATUS_RESTRICTED)
        self.assertEqual(status_for_code(None), STATUS_ERROR)
        self.assertEqual(status_for_code(500), STATUS_ERROR)

    def test_scan(self):
        with patch('observations.video_check._oembed_code', side_effect=fake_code) as mocked:
            self.assertEqual(scan([GONE, ALIVE, GONE, 'unknownunkn']),
                             {GONE: STATUS_NOT_FOUND, ALIVE: STATUS_OK, 'unknownunkn': STATUS_ERROR})
        self.assertEqual(mocked.call_count, 3)


@patch('observations.video_check._oembed_code', side_effect=fake_code)
class VideoCheckPageTests(TestCase):
    """Rule: only observations whose video failed the last scan are listed; a photo observation may lose its link,
    a video-only observation may be deleted (soft), and a new link must exist on YouTube and is not news."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        media = override_settings(MEDIA_ROOT=self.tmp.name); media.enable(); self.addCleanup(media.disable)
        self.admin = User.objects.create_superuser('manager', password='pw')
        country = Country.objects.create(name='ישראל', name_en='Israel'); sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        self.species = Species.objects.create(scientific_name='Chromodoris annae', genus='Chromodoris', species='annae', author='Bergh, 1877')
        other = Species.objects.create(scientific_name='Chromodoris willani', genus='Chromodoris', species='willani', author='Rudman, 1982')
        self.photo = self.sample(self.species, GONE, image=png(), local_video_file='annae.mov', drive_video_id='abcdefghijklmnopqrstu')
        self.video_only = self.sample(other, PRIVATE)
        self.fine = self.sample(other, ALIVE)
        self.client.force_login(self.admin)

    def sample(self, species, vid, **extra):
        item = Sample(owner=self.admin, trip=self.trip, species=species, video_url=f'https://youtu.be/{vid}', **extra)
        item.save_reviewed(); return item

    def scan(self):
        return self.client.post('/admin/video-check/', {'action': 'scan'}, follow=True)

    def post(self, action, sample, **data):
        return self.client.post('/admin/video-check/', {'action': action, 'sample': sample.pk, **data}, follow=True)

    def test_superuser_only(self, _):
        User.objects.create_user('member', password='pw', is_staff=True)
        self.client.force_login(User.objects.get(username='member'))
        self.assertEqual(self.client.get('/admin/video-check/').status_code, 403)

    def test_admin_index_links_to_the_page(self, _):
        self.assertContains(self.client.get('/admin/'), '/admin/video-check/')

    def test_scan_lists_only_problem_videos(self, _):
        response = self.scan()
        self.assertContains(response, GONE); self.assertContains(response, PRIVATE)
        self.assertNotContains(response, ALIVE)
        self.assertContains(response, 'לא נמצא ב-YouTube')
        self.assertContains(response, 'פרטי או חסום להטמעה')
        rows = {row['sample'].pk: row for row in response.context['rows']}
        self.assertTrue(rows[self.photo.pk]['has_image']); self.assertFalse(rows[self.video_only.pk]['has_image'])
        self.assertEqual(response.context['rows'][0]['status'], STATUS_NOT_FOUND)     # deleted videos first

    def test_remove_link_keeps_the_photo_observation(self, _):
        self.scan()
        response = self.post('remove_link', self.photo)
        self.photo.refresh_from_db()
        self.assertEqual((self.photo.video_url, self.photo.local_video_file, self.photo.drive_video_id), ('', '', ''))
        self.assertIsNone(self.photo.deleted_at); self.assertTrue(self.photo.image)
        self.assertEqual(SpeciesArea.objects.get(species=self.species).defining_sample_id, self.photo.pk)
        self.assertNotIn(self.photo.pk, [r['sample'].pk for r in response.context['rows']])
        self.assertNotIn(GONE, self.client.session['video_check']['problems'])

    def test_remove_link_refused_without_a_photo(self, _):
        self.scan()
        self.post('remove_link', self.video_only)
        self.video_only.refresh_from_db()
        self.assertTrue(self.video_only.video_url)

    def test_delete_observation_without_a_photo(self, _):
        self.scan()
        response = self.post('delete', self.video_only)
        self.video_only.refresh_from_db()
        self.assertIsNotNone(self.video_only.deleted_at); self.assertEqual(self.video_only.deleted_by, self.admin)
        self.assertNotIn(self.video_only.pk, [r['sample'].pk for r in response.context['rows']])

    def test_delete_refused_with_a_photo(self, _):
        self.scan()
        self.post('delete', self.photo)
        self.photo.refresh_from_db()
        self.assertIsNone(self.photo.deleted_at)

    def test_update_link_to_reuploaded_video(self, _):
        self.scan()
        news = ActivityEvent.objects.filter(kind=ActivityEvent.Kind.VIDEO_ADDED).count()
        response = self.post('update', self.photo, url=f'https://www.youtube.com/watch?v={NEW}')
        self.photo.refresh_from_db()
        self.assertEqual(self.photo.video_url, f'https://www.youtube.com/watch?v={NEW}')
        self.assertEqual(self.photo.local_video_file, 'annae.mov')                      # the same exported file
        self.assertEqual(ActivityEvent.objects.filter(kind=ActivityEvent.Kind.VIDEO_ADDED).count(), news)
        self.assertNotIn(self.photo.pk, [r['sample'].pk for r in response.context['rows']])

    def test_update_refuses_missing_same_or_used_video(self, _):
        self.scan()
        for url in (f'https://youtu.be/{NEW_GONE}', f'https://youtu.be/{GONE}', f'https://youtu.be/{ALIVE}', 'https://example.com/x'):
            self.post('update', self.photo, url=url)
            self.photo.refresh_from_db()
            self.assertEqual(self.photo.video_url, f'https://youtu.be/{GONE}', url)

    def test_all_fine_message(self, _):
        Sample.objects.filter(pk__in=[self.photo.pk, self.video_only.pk]).update(video_url=f'https://youtu.be/{ALIVE2}')
        Sample.objects.filter(pk=self.video_only.pk).update(deleted_at=self.photo.created_at)
        self.assertContains(self.scan(), 'כל הסרטונים נמצאו ב-YouTube')
