"""Species cards on the genus / family / order pages: ⤢ when the species' observations are photos, ▶ when videos,
and both glyphs inside a single circle when the species has both kinds."""
import io

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from PIL import Image

from .models import Country, DiveTrip, Region, Sample, Sea, Species, SpeciesArea, TaxonFamily, TaxonGenus, TaxonOrder


def png(color):
    buffer = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(buffer, 'PNG')
    return SimpleUploadedFile('p.png', buffer.getvalue(), content_type='image/png')


class CardMediaMarksTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        order = TaxonOrder.objects.create(name='Nudibranchia')
        family = TaxonFamily.objects.create(name='Chromodorididae', order=order)
        TaxonGenus.objects.create(name='Chromodoris', family=family)
        self.urls = ['/genus/Chromodoris/', '/family/Chromodorididae/', f'/order/{order.pk}/']
        self.counter = 0

    def species(self, name, *, photos=0, videos=0, photos_first=False):
        species = Species.objects.create(scientific_name=f'Chromodoris {name}', genus='Chromodoris', species=name)

        def add_videos():
            for _ in range(videos):
                self.counter += 1
                Sample(owner=self.owner, trip=self.trip, species=species, video_url=f'https://youtu.be/{self.counter:011d}').save_reviewed()

        def add_photos():
            for _ in range(photos):
                self.counter += 1
                Sample(owner=self.owner, trip=self.trip, species=species, image=png((self.counter * 7 % 256, self.counter * 13 % 256, 90))).save_reviewed()
        for step in ((add_photos, add_videos) if photos_first else (add_videos, add_photos)):
            step()
        return species

    def card(self, url, name):
        """The markup of the species' image block (the marks live inside it, before the species name)."""
        page = self.client.get(url).content.decode()
        start = page.index(f'Chromodoris {name}')
        return page[page.rindex('<span class="image-wrap">', 0, start):start]

    def marks(self, url, name):
        card = self.card(url, name)
        return ('⤢' in card, '▶' in card, card.count('class="play'))

    def test_photo_only_species_shows_arrows_only(self):
        self.species('photo', photos=1)
        for url in self.urls:
            self.assertEqual(self.marks(url, 'photo'), (True, False, 1), url)

    def test_video_only_species_shows_the_triangle_only(self):
        self.species('video', videos=1)
        for url in self.urls:
            self.assertEqual(self.marks(url, 'video'), (False, True, 1), url)

    def test_species_with_both_kinds_shows_both_marks_whichever_defines_the_card(self):
        self.species('both', videos=1, photos=1)       # the video observation was first, so it defines the card
        self.species('bothtwo', photos=1, videos=1, photos_first=True)   # the photo observation was first
        for url in self.urls:
            for name in ('both', 'bothtwo'):
                self.assertEqual(self.marks(url, name), (True, True, 1), (url, name))
                self.assertIn('play play-both', self.card(url, name))

    def test_a_second_video_does_not_add_a_second_triangle(self):
        self.species('videos', videos=2)
        self.assertEqual(self.marks(self.urls[0], 'videos'), (False, True, 1))


class GalleryCardMarksSourceTests(TestCase):
    """The gallery cards are built in dist/app.js: they must use the same rule: one circle, with both glyphs inside it when the species has both kinds."""

    def test_gallery_cards_use_media_marks_and_the_second_mark_is_offset(self):
        from pathlib import Path
        from django.conf import settings
        js = (Path(settings.BASE_DIR) / 'dist' / 'app.js').read_text(encoding='utf-8')
        css = (Path(settings.BASE_DIR) / 'dist' / 'styles.css').read_text(encoding='utf-8')
        self.assertIn('wrap.append(img, ...mediaMarks(pickSamples || sp.samples));', js)
        self.assertIn('hasVideo = samples.some(s => s.video_id)', js)
        self.assertIn('.play.play-both{', css)
        self.assertIn("mark.className = 'play play-both';", js)
        self.assertNotIn('play-2', css + js)
