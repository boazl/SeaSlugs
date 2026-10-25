"""Every count of gallery cards also says how many distinct species they are: "30 מינים (50 תצפיות)".

A card is a species in an area; the same species in two areas is two observations but one species."""
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
    def test_full_text_in_both_languages(self):
        self.assertEqual(counts.count_text(30, 50), '30 מינים (50 תצפיות)')
        self.assertEqual(counts.count_text(1, 2), 'מין אחד (2 תצפיות)')
        self.assertEqual(counts.count_text(2, 3, 'en'), '2 species (3 observations)')
        self.assertEqual(counts.count_text(1, 1, 'en', full=True), '1 species (1 observation)')

    def test_equal_numbers_read_as_the_species_alone(self):
        self.assertEqual(counts.count_text(30, 30), '30 מינים')
        self.assertEqual(counts.count_text(30, 30, full=True), '30 מינים (30 תצפיות)')

    def test_compact_form_is_one_number_when_both_are_equal(self):
        self.assertEqual(counts.count_compact(30, 50), '30 (50)')
        self.assertEqual(counts.count_compact(7, 7), '7')


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
        self.order, self.family = order, family

    def test_the_order_page_counts_species_and_observations(self):
        html = self.client.get(reverse('order-page', args=[self.order.pk])).content.decode()
        self.assertIn('2 מינים (3 תצפיות)', html)
        # the family under it: "2 (3)" with the full wording as its tooltip
        self.assertIn('<small title="2 מינים (3 תצפיות)">2 (3)</small>', html)

    def test_the_family_and_genus_pages_too(self):
        family = self.client.get(reverse('family-page', args=['Chromodorididae'])).content.decode()
        self.assertIn('2 מינים (3 תצפיות)', family)
        self.assertIn('<small title="2 מינים (3 תצפיות)">2 (3)</small>', family)      # the genus under it
        genus = self.client.get(reverse('genus-page', args=['Chromodoris'])).content.decode()
        self.assertIn('2 מינים (3 תצפיות)', genus)

    def test_the_english_page_is_in_english(self):
        html = self.client.get(reverse('family-page', args=['Chromodorididae']) + '?lang=en').content.decode()
        self.assertIn('2 species (3 observations)', html)
        self.assertNotIn('תצפיות)', html)


class CountsInTheGalleryTests(SimpleTestCase):
    def setUp(self):
        self.js = (ROOT / 'app.js').read_text(encoding='utf-8')

    def test_the_gallery_has_the_same_wording_helpers(self):
        for fragment in ('function countText(species, observations, full = false)', 'function countCompact(species, observations)',
                         'function tally(list, extraCards = 0)', 'function speciesIn(list)'):
            self.assertIn(fragment, self.js)

    def test_every_counter_goes_through_tally(self):
        for fragment in ('const memberTally = tally(members);', 'badge.textContent = memberTally.compact;',
                         'rank.textContent = rankText + \' · \' + countText(speciesIn(members), members.length);',
                         'count.textContent = areaTally.compact;', 'return tally(speciesList.filter(sp => matchesAreaFilter(sp, key)));',
                         'groupCount(filteredSpecies.length, filteredSpecies, true)', 'heading.append(groupCount(n, species));',
                         "countText(speciesIn(speciesList), speciesList.length)"):
            self.assertIn(fragment, self.js)

    def test_the_sidebar_explains_the_numbers_in_both_languages(self):
        html = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="countLegend"', html)
        self.assertIn("['#countLegend', 'Numbers: species (observations = species per area)']", self.js)
