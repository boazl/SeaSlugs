"""The page of a dive trip's collection observation, /trip/<code>/ (trip_page.py)."""
import json
import re
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea


class TripPageBase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser('admin', password='testing')
        country = Country.objects.create(name='פיליפינים', name_en='Philippines')
        sea = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        region = Region.objects.create(name='פיליפינים - אנילאו', name_en='Philippines - Anilao', country=country, sea=sea)
        self.folder = tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.trip = DiveTrip.objects.create(code='C', title='אנילאו 2023', year=2023, month=3, country=country,
                                            region=region, description_he='מסע מרץ', local_video_folder=self.folder.name)
        self.other_trip = DiveTrip.objects.create(code='H', title='אנילאו 2025', year=2025, month=3, country=country, region=region)
        self.collection = Sample(owner=self.admin, kind='collection', trip=self.trip, title='87 מינים מאנילאו',
                                 title_en='87 species from Anilao', video_url='https://youtu.be/CCCCCCCCCCC',
                                 local_video_file='Anilao.mov')
        self.collection.save_reviewed(actor=self.admin, approve=True)
        mk = lambda name: Species.objects.create(scientific_name=name, genus=name.split()[0], species=name.split()[1],
                                                  author='Author, 1900')
        self.alcalai, self.colemani, self.elsewhere = mk('Chromodoris alcalai'), mk('Chromodoris colemani'), mk('Phyllidia ocellata')
        self.obs = {}
        for i, (species, trip) in enumerate(((self.colemani, self.trip), (self.alcalai, self.trip),
                                            (self.alcalai, self.other_trip), (self.elsewhere, self.other_trip))):
            s = Sample(owner=self.admin, kind='species', trip=trip, species=species, video_url=f'https://youtu.be/{str(i).zfill(11)}')
            s.save_reviewed(actor=self.admin, approve=True)
            self.obs.setdefault((species.pk, trip.pk), []).append(s)

    def page(self, url='/trip/C/'):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


class TripPageTests(TripPageBase):
    """/trip/<code>/ shows the trip's collection video (and its photo), its title, place, date and description, and
    below them one card per species observed on the trip -- alphabetically, each with the trip's own (single)
    observation of it and linking to that observation on its species page (#obs-<pk>), with no observation count
    even when the species has observations from other trips; species seen only on other trips are not listed. 404 for an unknown code or a trip with no published collection observation."""

    def test_page(self):
        html = self.page()
        self.assertIn('youtube-nocookie.com/embed/CCCCCCCCCCC', html)
        self.assertIn('<h1 class="trip-title">87 מינים מאנילאו</h1>', html)
        self.assertIn('פיליפינים - אנילאו · 3/2023', html)
        self.assertIn('מסע מרץ', html)
        self.assertIn('href="/observations/trips/"', html)
        self.assertIn('href="/?restore=1"', html)
        self.assertIn(f'href="/?sort=alpha&amp;trip={self.trip.pk}"', html)
        cards = re.findall(r'href="(/species/[^"]+)"', html.split('id="species"')[1])
        alcalai = SpeciesArea.objects.get(species=self.alcalai)
        colemani = SpeciesArea.objects.get(species=self.colemani)
        first_alcalai = self.obs[(self.alcalai.pk, self.trip.pk)][0]
        self.assertEqual(cards, [f'/species/{alcalai.slug}/#obs-{first_alcalai.pk}',
                                 f'/species/{colemani.slug}/#obs-{self.obs[(self.colemani.pk, self.trip.pk)][0].pk}'])
        self.assertNotIn('count-badge', html)        # alcalai has 2 observations (this trip and H): one card, no count
        self.assertNotIn(' תצפיות</span>', html)
        self.assertNotIn('Phyllidia', html)
        self.assertIn('2 מינים', html)

    def test_english(self):
        html = self.page('/trip/C/?lang=en')
        self.assertIn('<h1 class="trip-title">87 species from Anilao</h1>', html)
        self.assertIn('Species on this trip', html)
        self.assertIn('Philippines - Anilao · 3/2023', html)
        self.assertIn('href="/species/', html)
        self.assertIn('/?lang=en#obs-', html)

    def test_not_found(self):
        self.assertEqual(self.client.get('/trip/nope/').status_code, 404)
        self.assertEqual(self.client.get('/trip/H/').status_code, 404)      # a trip with no collection observation
        Sample.objects.filter(pk=self.collection.pk).update(status='pending')
        self.assertEqual(self.client.get('/trip/C/').status_code, 404)

    def test_manager_sees_the_local_copy_and_the_edit_link(self):
        (Path(self.folder.name) / 'Anilao.mov').write_bytes(b'x' * 10)
        self.assertNotIn('local-video-box"><p>', self.page())
        self.client.force_login(self.admin)
        html = self.page()
        self.assertIn(f'src="/observations/{self.collection.pk}/local-video/"', html)
        self.assertIn(f'/observations/{self.collection.pk}/edit/', html)
        Sample.objects.filter(pk=self.collection.pk).update(local_video_file='', drive_video_id='1AbCdEfGhIjKlMnOpQrStUvWxYz012345')
        self.assertIn('drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345', self.page())


class TripPageLinksTests(TripPageBase):
    """The gallery's collection card opens the trip page (catalog.js gives each collection its trip_code), the dive
    trips page's video card links to it, and the sitemap lists it."""

    def test_catalog_and_app_js(self):
        text = self.client.get('/catalog.js').content.decode()
        data = json.loads(text[text.index('{'):text.rindex('}') + 1])
        self.assertEqual([c['trip_code'] for c in data['collections']], ['C'])
        js = (Path(settings.BASE_DIR) / 'dist' / 'app.js').read_text()
        self.assertIn("if (c.trip_code) button.href = `/trip/${encodeURIComponent(c.trip_code)}/`", js)

    def test_trips_page_and_sitemap(self):
        self.assertIn('href="/trip/C/"', self.client.get('/observations/trips/').content.decode())
        self.assertIn('/trip/C/', self.client.get('/sitemap.xml').content.decode())
        self.assertNotIn('/trip/H/', self.client.get('/sitemap.xml').content.decode())
