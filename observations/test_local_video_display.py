"""Offline videos, phase 3: what a manager sees -- the red gallery mark, the local player on the observation page,
the local-video file view and the /admin/local-videos/ tool. Visitors never see any of it."""
import json
import re
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.conf import settings

from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea


class LocalVideoDisplayBase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser('admin', password='testing')
        self.member = User.objects.create_user('member', password='testing')
        country = Country.objects.create(name='Philippines'); sea = Sea.objects.create(name='Indo Pacific')
        region = Region.objects.create(name='Romblon', country=country, sea=sea)
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.trip = DiveTrip.objects.create(code='V', title='Romblon 2026', year=2026, country=country, region=region,
                                            local_video_folder=self.folder.name)
        self.species = Species.objects.create(scientific_name='Chromodoris kalawakan', genus='Chromodoris', species='kalawakan', author='Gosliner, 2018')
        self.with_copy = Sample(owner=self.admin, trip=self.trip, kind=Sample.Kind.SPECIES, species=self.species,
                                status=Sample.Status.PUBLISHED, video_url='https://youtu.be/11111111111', local_video_file='Chromodoris kalawakan.mov')
        self.with_copy.save_reviewed()
        other = Species.objects.create(scientific_name='Aegires villosus', genus='Aegires', species='villosus', author='Farran, 1905')
        self.without_copy = Sample(owner=self.admin, trip=self.trip, kind=Sample.Kind.SPECIES, species=other,
                                   status=Sample.Status.PUBLISHED, video_url='https://youtu.be/22222222222')
        self.without_copy.save_reviewed()
        self.content = bytes(range(256)) * 40   # 10,240 bytes
        (Path(self.folder.name) / 'Chromodoris kalawakan.mov').write_bytes(self.content)
        self.area_with = SpeciesArea.objects.get(species=self.species)
        self.area_without = SpeciesArea.objects.get(species=other)
        self.url = f'/observations/{self.with_copy.pk}/local-video/'


class LocalVideoFileViewTests(LocalVideoDisplayBase):
    """/observations/<pk>/local-video/ serves the Mac file to managers only, with byte ranges (206) -- Safari needs
    them to play a <video> -- and 404 when the copy is not recorded or not on this machine."""
    def test_managers_only(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_whole_file_and_ranges(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200); self.assertEqual(response['Accept-Ranges'], 'bytes')
        self.assertEqual(b''.join(response.streaming_content), self.content)
        response = self.client.get(self.url, HTTP_RANGE='bytes=100-199')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], f'bytes 100-199/{len(self.content)}')
        self.assertEqual(b''.join(response.streaming_content), self.content[100:200])
        response = self.client.get(self.url, HTTP_RANGE='bytes=-10')
        self.assertEqual(b''.join(response.streaming_content), self.content[-10:])
        response = self.client.get(self.url, HTTP_RANGE='bytes=10000-')
        self.assertEqual(b''.join(response.streaming_content), self.content[10000:])
        self.assertEqual(self.client.get(self.url, HTTP_RANGE='bytes=99999-').status_code, 416)

    def test_missing_copy_is_404(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(f'/observations/{self.without_copy.pk}/local-video/').status_code, 404)
        (Path(self.folder.name) / 'Chromodoris kalawakan.mov').unlink()
        self.assertEqual(self.client.get(self.url).status_code, 404)


class LocalVideoGalleryTests(LocalVideoDisplayBase):
    """The gallery page carries {sample id: status} for a manager only; app.js marks a video red when its status is
    "missing"/"not_found" (a recorded copy that is merely unreachable -- the live site -- is not red)."""
    def data(self, response):
        match = re.search(r'<script id="local-videos" type="application/json">(.*?)</script>', response.content.decode(), re.S)
        return json.loads(match.group(1)) if match else None

    def test_manager_gets_statuses_visitors_nothing(self):
        self.assertIsNone(self.data(self.client.get('/')))
        self.client.force_login(self.member)
        self.assertIsNone(self.data(self.client.get('/')))
        self.client.force_login(self.admin)
        self.assertEqual(self.data(self.client.get('/')), {str(self.with_copy.pk): 'ok', str(self.without_copy.pk): 'missing'})

    def test_app_js_marks(self):
        js = (settings.BASE_DIR / 'dist' / 'app.js').read_text()
        self.assertIn("document.getElementById('local-videos')", js)
        self.assertIn("const NO_LOCAL = ['missing', 'not_found'];", js)
        self.assertIn('if (hasVideo && samples.some(lacksLocalVideo)) markNoLocal(mark);', js)
        self.assertIn('if (lacksLocalVideo(c)) markNoLocal(icon);', js)
        self.assertIn('.play.no-local{color:#ff3b3b', (settings.BASE_DIR / 'dist' / 'styles.css').read_text())


class LocalVideoSpeciesPageTests(LocalVideoDisplayBase):
    """The observation (species) page shows a manager a local player box when the copy exists here, and a red
    "no local copy" note when a video has none. Visitors see neither."""
    def page(self, area, lang=''):
        return self.client.get(f'/species/{area.slug}/' + (f'?lang={lang}' if lang else '')).content.decode()

    def test_visitor_sees_nothing(self):
        html = self.page(self.area_with)
        self.assertNotIn('local-video', html.split('<style')[0] + html.split('</style>')[-1].split('<script')[0])
        self.assertNotIn('/local-video/', html)

    def test_manager_player_and_missing_note(self):
        self.client.force_login(self.admin)
        html = self.page(self.area_with)
        self.assertIn(f'<video controls playsinline preload="metadata" src="{self.url}"', html)
        self.assertIn('סרטון מקומי (offline)', html)
        html = self.page(self.area_without)
        self.assertIn('<p class="local-video-missing">אין גרסה מקומית (offline) לסרטון</p>', html)
        self.assertIn('Local video (offline)', self.page(self.area_with, 'en'))


class LocalVideoToolTests(LocalVideoDisplayBase):
    """/admin/local-videos/ (superuser): per-trip summary, the trip's folder, the files of the folder with the
    automatic match pre-selected, automatic fill of empty names, and saving chosen names (validated)."""
    def test_superuser_only(self):
        self.client.force_login(self.member)
        self.assertNotEqual(self.client.get('/admin/local-videos/').status_code, 200)

    def test_tool(self):
        self.client.force_login(self.admin)
        (Path(self.folder.name) / 'Aegires villosus.mov').write_bytes(b'x')
        html = self.client.get('/admin/local-videos/?trip=V').content.decode()
        self.assertIn('Romblon 2026 [V]', html)
        self.assertIn('<option value="Aegires villosus.mov" selected>', html)
        self.assertIn('הצעה — טרם נשמרה', html)
        self.client.post('/admin/local-videos/', {'trip': 'V', 'action': 'auto'})
        self.without_copy.refresh_from_db(); self.assertEqual(self.without_copy.local_video_file, 'Aegires villosus.mov')
        self.client.post('/admin/local-videos/', {'trip': 'V', 'action': 'files', f'file-{self.without_copy.pk}': ''})
        self.without_copy.refresh_from_db(); self.assertEqual(self.without_copy.local_video_file, '')
        self.client.post('/admin/local-videos/', {'trip': 'V', 'action': 'files', f'file-{self.without_copy.pk}': '../x.mov'})
        self.without_copy.refresh_from_db(); self.assertEqual(self.without_copy.local_video_file, '')
        self.client.post('/admin/local-videos/', {'trip': 'V', 'action': 'folder', 'folder': '/Users/boazliebes/Other'})
        self.trip.refresh_from_db(); self.assertEqual(self.trip.local_video_folder, '/Users/boazliebes/Other')


class LocalVideoTaxonCardTests(LocalVideoDisplayBase):
    """The genus / family / order pages' species cards carry the same red ▶ for a manager when one of the card's
    observations has a video without a local copy; visitors' cards never change."""
    def setUp(self):
        super().setUp()
        from .models import TaxonGenus, TaxonFamily, TaxonOrder
        order = TaxonOrder.objects.create(name='Nudibranchia')
        family = TaxonFamily.objects.create(order=order, name='Chromodorididae')
        TaxonGenus.objects.create(family=family, name='Chromodoris', defining_sample=self.with_copy)
        TaxonGenus.objects.create(family=family, name='Aegires', defining_sample=self.without_copy)
        Species.objects.update(family='Chromodorididae', order='Nudibranchia')

    def test_genus_page(self):
        self.assertNotIn('no-local', self.client.get('/genus/Aegires/').content.decode())
        self.client.force_login(self.admin)
        self.assertIn('class="play no-local"', self.client.get('/genus/Aegires/').content.decode())
        self.assertNotIn('class="play no-local"', self.client.get('/genus/Chromodoris/').content.decode())

    def test_family_page(self):
        self.client.force_login(self.admin)
        html = self.client.get('/family/Chromodorididae/').content.decode()
        self.assertEqual(html.count('class="play no-local"'), 1)
