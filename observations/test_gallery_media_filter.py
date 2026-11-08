"""The manager's photo / video filters in the gallery (alphabetical sort only)."""
import json
import re
import shutil
import subprocess
import unittest

from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species
from .test_gallery_links import APP_JS, GalleryQueryTests, _function_source


class GalleryMediaFilterPageTests(TestCase):
    """A manager's gallery page carries the ids of the observations whose video has a copy in Google Drive and a
    "photo and video (manager)" filter group; a visitor's page carries neither."""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser('admin', password='testing')
        self.member = User.objects.create_user('member', password='testing')
        country = Country.objects.create(name='Philippines'); sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='Romblon', country=country, sea=sea)
        trip = DiveTrip.objects.create(code='M', title='Romblon 2026', year=2026, country=country, region=region)
        mk = lambda epithet: Species.objects.create(scientific_name=f'Chromodoris {epithet}', genus='Chromodoris',
                                                     species=epithet, author='Gosliner, 2018')
        self.in_drive = Sample(owner=self.admin, trip=trip, kind=Sample.Kind.SPECIES, species=mk('a'),
                               status=Sample.Status.PUBLISHED, video_url='https://youtu.be/11111111111', drive_video_id='1AbCdEfGhIjKlMnOpQrStUvWxYz012345')
        self.in_drive.save_reviewed()
        self.not_in_drive = Sample(owner=self.admin, trip=trip, kind=Sample.Kind.SPECIES, species=mk('b'),
                                   status=Sample.Status.PUBLISHED, video_url='https://youtu.be/22222222222')
        self.not_in_drive.save_reviewed()

    def data(self, html):
        match = re.search(r'<script id="drive-videos" type="application/json">(.*?)</script>', html, re.S)
        return json.loads(match.group(1)) if match else None

    def test_manager_only(self):
        for login in (None, self.member):
            if login: self.client.force_login(login)
            html = self.client.get('/').content.decode()
            self.assertIsNone(self.data(html))
            self.assertNotIn('id="mediaOptions"', html)
        self.client.force_login(self.admin)
        html = self.client.get('/').content.decode()
        self.assertEqual(self.data(html), [self.in_drive.pk])
        self.assertIn('id="mediaGroup" hidden', html)                  # shown by app.js under the alphabetical sort
        self.assertIn('id="mediaOptions"', html)
        self.assertIn('תמונה וסרטון (מנהל)', html)


@unittest.skipUnless(shutil.which('node'), 'node is needed to run app.js code')
class GalleryMediaFilterLogicTests(GalleryQueryTests):
    """mediaMatches: 'video' = a video with no photo, 'photo' = a photo with no video, 'nodrive' = a video whose id is
    not in the manager's Google Drive list. The filter is in effect, and kept in the address (?media=...), only under
    the alphabetical sort."""

    def matches(self, item, kind):
        source = APP_JS.read_text(encoding='utf-8')
        script = '\n'.join(["const driveVideoIds = new Set(['5']);", _function_source(source, 'mediaMatches'),
                            f'console.log(JSON.stringify(mediaMatches({json.dumps(item)}, {json.dumps(kind)})));'])
        return json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)

    def test_media_matches(self):
        video_only = {'sample_id': 1, 'video_id': 'x', 'image_url': None}
        photo_only = {'sample_id': 2, 'video_id': None, 'image_url': '/p'}
        both_in_drive = {'sample_id': 5, 'video_id': 'y', 'image_url': '/p'}
        both_not_in_drive = {'sample_id': 6, 'video_id': 'z', 'image_url': '/p'}
        self.assertEqual([self.matches(i, 'video') for i in (video_only, photo_only, both_in_drive)], [True, False, False])
        self.assertEqual([self.matches(i, 'photo') for i in (video_only, photo_only, both_in_drive)], [False, True, False])
        self.assertEqual([self.matches(i, 'nodrive') for i in (video_only, photo_only, both_in_drive, both_not_in_drive)],
                         [True, False, False, True])

    def test_address_round_trip(self):
        self.assertEqual(self.url('state.sort = "alpha"; state.sortChosen = true; state.media.add("nodrive");'),
                         '/?lang=he&sort=alpha&media=nodrive')
        # under another sort the filter is not in effect and not in the address
        self.assertEqual(self.url('state.media.add("nodrive");'), '/?lang=he')
        state = self.run_js('applyGalleryQuery(new URLSearchParams("sort=alpha&media=photo"));'
                            'console.log(JSON.stringify([...state.media, activeMedia()]));')
        self.assertEqual(state, ['photo', 'photo'])
        state = self.run_js('applyGalleryQuery(new URLSearchParams("sort=alpha&media=bogus"));'
                            'console.log(JSON.stringify([...state.media]));')
        self.assertEqual(state, [])

    def test_wired_into_the_gallery(self):
        source = APP_JS.read_text(encoding='utf-8')
        self.assertIn("if (media && !(scopedSamples(sp) || sp.samples).some(sm => mediaMatches(sm, media))) return false;", source)
        self.assertIn('if (activeMedia() && !mediaMatches(c, activeMedia())) return false;', source)
        self.assertIn("if (mediaGroup) mediaGroup.hidden = state.sort !== 'alpha';", source)
