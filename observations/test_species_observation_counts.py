"""Every counter shows the number of distinct species; only the gallery's "All areas" button also gives the observations.

A card is a species in an area; the same species in two areas is two cards but one species."""
import io
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from PIL import Image

from . import counts
from .models import Country, DiveTrip, Region, Sample, Sea, Species, TaxonFamily, TaxonGenus, TaxonOrder

ROOT = Path(__file__).resolve().parent.parent / 'dist'


def png(color):
    buffer = io.BytesIO()
    Image.new('RGB', (40, 30), color).save(buffer, 'PNG')
    return SimpleUploadedFile('p.png', buffer.getvalue(), content_type='image/png')


class CountWordingTests(SimpleTestCase):
    def test_species_wording_in_both_languages(self):
        self.assertEqual(counts.count_text(30), '30 מינים')
        self.assertEqual(counts.count_text(1), 'מין אחד')
        self.assertEqual(counts.count_text(2, 'en'), '2 species')

    def test_observations_wording_for_the_all_areas_button(self):
        self.assertEqual(counts.observations_text(266, 301), '266 מינים ב-301 תצפיות')
        self.assertEqual(counts.observations_text(266, 301, 'en'), '266 species in 301 observations')
        self.assertEqual(counts.observations_text(1, 1), 'מין אחד ב-תצפית אחת')


class CountsOnTheTaxonPagesTests(TestCase):
    def setUp(self):
        owner = User.objects.create_superuser('manager', password='test-password')
        israel = Country.objects.create(name='ישראל', name_en='Israel')
        philippines = Country.objects.create(name='הפיליפינים', name_en='Philippines')
        red = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        pacific = Sea.objects.create(name='האוקיינוס השקט', name_en='Pacific')
        trips = [DiveTrip.objects.create(title=title, year=2026, country=country, region=Region.objects.create(name=title, country=country, sea=sea))
                 for title, country, sea in (('Eilat', israel, red), ('Anilao', philippines, pacific))]
        order = TaxonOrder.objects.create(name='Nudibranchia')
        family = TaxonFamily.objects.create(name='Chromodorididae', order=order)
        TaxonGenus.objects.create(name='Chromodoris', family=family)
        colour = 0
        # annae: seen in both areas (2 cards, 1 species); willani: Anilao only (1 card).
        for epithet, place in (('annae', 0), ('annae', 1), ('willani', 1)):
            species, _ = Species.objects.get_or_create(scientific_name=f'Chromodoris {epithet}', defaults={'genus': 'Chromodoris', 'species': epithet})
            colour += 60
            Sample(owner=owner, trip=trips[place], species=species, image=png((colour, 40, 90))).save_reviewed()
        self.order = order

    def test_the_order_page_counts_species_only(self):
        html = self.client.get(reverse('order-page', args=[self.order.pk])).content.decode()
        self.assertIn('<h2>2 מינים</h2>', html)
        self.assertIn('<dd>2</dd>', html)
        self.assertIn('<small>2</small>', html)          # the family under it
        self.assertNotIn('תצפיות)', html)

    def test_the_family_and_genus_pages_too(self):
        family = self.client.get(reverse('family-page', args=['Chromodorididae'])).content.decode()
        self.assertIn('<h2>2 מינים</h2>', family)
        self.assertIn('<small>2</small>', family)        # the genus under it
        genus = self.client.get(reverse('genus-page', args=['Chromodoris'])).content.decode()
        self.assertIn('<span class="group-count">(2)</span>', genus)

    def test_the_english_page_is_in_english(self):
        html = self.client.get(reverse('family-page', args=['Chromodorididae']) + '?lang=en').content.decode()
        self.assertIn('<h2>2 species</h2>', html)


class CountsInTheGalleryTests(SimpleTestCase):
    def setUp(self):
        self.js = (ROOT / 'app.js').read_text(encoding='utf-8')

    def test_the_gallery_counts_species(self):
        for fragment in ('function countText(species)', 'function observationsText(species, observations)',
                         'function tally(list)', 'function speciesIn(list)',
                         "rank.textContent = rankText + ' · ' + countText(speciesIn(members));",
                         'badge.textContent = memberTally.compact;', 'groupCount(filteredSpecies.length, filteredSpecies, true)',
                         "countText(speciesIn(speciesList))"):
            self.assertIn(fragment, self.js)

    def test_only_the_all_areas_button_gives_the_observations(self):
        self.assertIn("key === 'all' ? observationsText(areaTally.species, areaTally.observations) : areaTally.compact", self.js)
        self.assertEqual(self.js.count('observationsText('), 2)       # its definition and that one use
