"""Taxonomic gallery: taxon cards are framed by rank (lighter the lower the rank), species cards have no frame."""
import re
from pathlib import Path

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species, TaxonFamily, TaxonGenus, TaxonOrder

ROOT = Path(__file__).resolve().parent.parent / 'dist'


class TaxonCardFrameTests(SimpleTestCase):
    def setUp(self):
        self.js = (ROOT / 'app.js').read_text(encoding='utf-8')
        self.css = (ROOT / 'styles.css').read_text(encoding='utf-8')

    def test_taxon_cards_carry_their_rank_class(self):
        self.assertIn("article.className = `card taxon-card taxon-level-${level}`;", self.js)

    def test_every_taxon_rank_has_a_frame_and_species_has_none(self):
        for level in ('order', 'suborder', 'superfamily', 'family', 'genus'):
            self.assertIn(f'.taxon-card.taxon-level-{level} .image-wrap', self.css)
            self.assertIn(f'.frame-{level},', self.css)
        self.assertNotIn('taxon-level-species', self.css)

    def test_frame_widths_get_thinner_down_the_ranks_and_colours_are_variables(self):
        def width(level):
            return int(re.search(rf'--frame-{level}-color:#[0-9a-f]{{6}};\s*--frame-{level}-width:(\d+)px', self.css).group(1))
        widths = [width(level) for level in ('order', 'suborder', 'superfamily', 'family')]
        self.assertEqual(widths, sorted(widths, reverse=True))
        self.assertEqual(len(set(widths)), 4)
        self.assertEqual(width('family'), width('genus'))
        self.assertGreater(width('family'), 0)


class HeroFrameTests(TestCase):
    """The main picture of an order / family / genus page carries the frame of that rank."""

    def setUp(self):
        owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        self.order = TaxonOrder.objects.create(name='Nudibranchia')
        family = TaxonFamily.objects.create(name='Chromodorididae', order=self.order)
        TaxonGenus.objects.create(name='Chromodoris', family=family)
        species = Species.objects.create(scientific_name='Chromodoris annae', genus='Chromodoris', species='annae')
        Sample(owner=owner, trip=trip, species=species, video_url='https://youtu.be/00000000001').save_reviewed()

    def media_class(self, url):
        html = self.client.get(url).content.decode()
        return re.search(r'<div class="(species-media[^"]*)"', html).group(1)

    def test_each_page_has_its_rank_frame(self):
        self.assertEqual(self.media_class(f'/order/{self.order.pk}/'), 'species-media frame-order')
        self.assertEqual(self.media_class('/family/Chromodorididae/'), 'species-media frame-family')
        self.assertEqual(self.media_class('/genus/Chromodoris/'), 'species-media frame-genus')
