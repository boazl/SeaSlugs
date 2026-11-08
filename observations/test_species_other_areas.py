from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .gallery_data import same_species_areas, UNMARKED_SP_EPITHETS
from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea


class SpeciesPageOtherAreasTests(TestCase):
    """A species page ends (below "תצפיות נוספות") with "המין באזורים נוספים" / "This species in other areas": a card
    with photo, place and observation count linking to every other live SpeciesArea of the same species -- the same
    catalog species and the same undetermined-variant letter (gallery_data.same_species_areas, the gallery's
    "species from multiple areas" rule). A bare "Genus sp." with no number or letter is unidentified and never
    matches; "sp. 7" / "sp. A" in the catalog name, or a variant letter on the area, does. A species seen in one
    area has no section; another species' areas never appear."""

    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_superuser('admin', password='testing')
        self.ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        self.scs = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        self.il = Country.objects.create(name='ישראל', name_en='Israel')
        self.med = Sea.objects.create(name='הים התיכון', name_en='Mediterranean')
        self.anilao = Region.objects.create(name='Anilao', country=self.ph, sea=self.scs)
        self.haifa = Region.objects.create(name='Haifa', country=self.il, sea=self.med)
        self.trip_ph = DiveTrip.objects.create(title='Anilao', year=2024, country=self.ph, region=self.anilao)
        self.trip_ph2 = DiveTrip.objects.create(title='Anilao 2', year=2025, country=self.ph, region=self.anilao)
        self.trip_il = DiveTrip.objects.create(title='Haifa', year=2026, country=self.il, region=self.haifa)
        self.species = Species.objects.create(scientific_name='Phyllodesmium colemani', genus='Phyllodesmium',
                                              species='colemani', author='Rudman, 1991')
        self.other_species = Species.objects.create(scientific_name='Hypselodoris infucata', genus='Hypselodoris',
                                                    species='infucata', author='(Rüppell & Leuckart, 1830)')

    def _sample(self, trip, video, species=None):
        s = Sample(owner=self.manager, trip=trip, kind=Sample.Kind.SPECIES, species=species or self.species,
                   video_url=f'https://youtu.be/{video}')
        s.save_reviewed(self.manager, approve=True)
        return s

    def _area(self, country, species=None):
        return SpeciesArea.objects.get(species=species or self.species, country=country)

    def test_other_area_card_links_with_count(self):
        self._sample(self.trip_ph, '11111111111')
        self._sample(self.trip_ph2, '22222222222')
        self._sample(self.trip_il, '33333333333')
        ph, il = self._area(self.ph), self._area(self.il)
        html = self.client.get(reverse('species-page', args=[il.slug])).content.decode()
        self.assertIn('המין באזורים נוספים', html)
        section = html.split('id="other-areas"', 1)[1]
        self.assertIn(reverse('species-page', args=[ph.slug]), section)
        self.assertIn('פיליפינים', section)
        self.assertIn('<span class="count-badge other-areas" aria-hidden="true" title="המין נצפה ב-2 אזורים, 3 תצפיות בסך הכול">2</span>', section)
        self.assertNotIn(reverse('species-page', args=[il.slug]) + '"', section)   # not the page's own area
        # And the other way round, in English.
        html = self.client.get(reverse('species-page', args=[ph.slug]) + '?lang=en').content.decode()
        self.assertIn('This species in other areas (1)', html)
        self.assertIn(reverse('species-page', args=[il.slug]) + '?lang=en', html)
        self.assertNotIn('המין באזורים נוספים', html)

    def test_section_comes_after_more_observations(self):
        self._sample(self.trip_ph, '11111111111')
        self._sample(self.trip_ph2, '22222222222')
        self._sample(self.trip_il, '33333333333')
        html = self.client.get(reverse('species-page', args=[self._area(self.ph).slug])).content.decode()
        self.assertLess(html.index('תצפיות נוספות'), html.index('id="other-areas"'))

    def test_no_section_for_single_area_or_other_species(self):
        self._sample(self.trip_ph, '11111111111')
        self._sample(self.trip_il, '44444444444', species=self.other_species)
        html = self.client.get(reverse('species-page', args=[self._area(self.ph).slug])).content.decode()
        self.assertNotIn('id="other-areas"', html)
        self.assertNotIn(self._area(self.il, self.other_species).slug, html)

    def test_area_without_published_observations_is_left_out(self):
        self._sample(self.trip_ph, '11111111111')
        gone = self._sample(self.trip_il, '33333333333')
        il = self._area(self.il)
        Sample.objects.filter(pk=gone.pk).update(status='pending')
        html = self.client.get(reverse('species-page', args=[self._area(self.ph).slug])).content.decode()
        self.assertNotIn(il.slug, html)
        self.assertNotIn('id="other-areas"', html)


    def _sp(self, epithet):
        return Species.objects.create(scientific_name=f'Okenia {epithet}', genus='Okenia', species=epithet)

    def _sp_sample(self, trip, video, species, variant=''):
        s = Sample(owner=self.manager, trip=trip, kind=Sample.Kind.SPECIES, species=species,
                   undetermined_variant=variant, video_url=f'https://youtu.be/{video}')
        s.save_reviewed(self.manager, approve=True)
        return s

    def test_bare_sp_never_matches(self):
        bare = self._sp('sp.')
        self._sp_sample(self.trip_ph, '55555555555', bare)
        self._sp_sample(self.trip_il, '66666666666', bare)
        ph = SpeciesArea.objects.get(species=bare, country=self.ph)
        self.assertFalse(same_species_areas(ph).exists())
        html = self.client.get(reverse('species-page', args=[ph.slug])).content.decode()
        self.assertNotIn('id="other-areas"', html)

    def test_numbered_or_lettered_sp_matches(self):
        numbered = self._sp('sp. 7')
        self._sp_sample(self.trip_ph, '55555555555', numbered)
        self._sp_sample(self.trip_il, '66666666666', numbered)
        ph = SpeciesArea.objects.get(species=numbered, country=self.ph)
        il = SpeciesArea.objects.get(species=numbered, country=self.il)
        self.assertEqual(list(same_species_areas(ph)), [il])
        html = self.client.get(reverse('species-page', args=[ph.slug])).content.decode()
        self.assertIn(il.slug, html.split('id="other-areas"', 1)[1])

    def test_variant_letter_must_match(self):
        bare = self._sp('sp.')
        self._sp_sample(self.trip_ph, '55555555555', bare, 'A')
        self._sp_sample(self.trip_il, '66666666666', bare, 'A')
        self._sp_sample(self.trip_il, '77777777777', bare, 'B')
        ph = SpeciesArea.objects.get(species=bare, country=self.ph)
        il_a = SpeciesArea.objects.get(species=bare, country=self.il, undetermined_variant='A')
        self.assertEqual(list(same_species_areas(ph)), [il_a])


class GallerySameSpeciesCountTests(TestCase):
    """In every gallery sort a species card's observation count is shown above 1, and also at 1 when the same
    species has cards from other areas; then the number is yellow (.count-badge.other-areas) and its tooltip gives
    the species' number of areas and total observations. A single observation in a single area shows no number.
    "Same species" = sameSpeciesKey in app.js (species + variant letter; a bare "sp." never matches), mirroring
    gallery_data.same_species_areas; catalog.js carries the variant for it. The "species from multiple areas"
    button uses the same rule."""

    def setUp(self):
        self.js = (Path(settings.BASE_DIR) / 'dist' / 'app.js').read_text(encoding='utf-8')
        self.css = (Path(settings.BASE_DIR) / 'dist' / 'styles.css').read_text(encoding='utf-8')

    def test_badge_rule_in_every_sort(self):
        self.assertIn('if (displayCount > 1 || otherAreas) {', self.js)
        self.assertIn("badge.classList.add('other-areas');", self.js)
        self.assertNotIn('alphaView', self.js)

    def test_same_species_key_skips_bare_sp(self):
        self.assertIn("const UNMARKED_SP_EPITHETS = ['', 'sp', 'sp.', 'spp', 'spp.'];", self.js)
        self.assertIn("if (!sp.variant && UNMARKED_SP_EPITHETS.includes((sp.epithet || '').trim())) return null;", self.js)
        self.assertEqual(UNMARKED_SP_EPITHETS, ('', 'sp', 'sp.', 'spp', 'spp.'))
        self.assertIn("if (area === 'multi-area') return alsoInOtherAreas(sp);", self.js)

    def test_tooltip_bilingual_with_totals(self):
        self.assertIn('`המין נצפה ב-${t.areas} אזורים, ${t.observations} תצפיות בסך הכול`', self.js)
        self.assertIn('`This species was observed in ${t.areas} areas, ${t.observations} observations in total`', self.js)

    def test_badge_is_yellow(self):
        self.assertIn('.count-badge.other-areas{background:#ffd23f', self.css)


class CatalogVariantTests(TestCase):
    """catalog.js gives each species card its undetermined-variant letter ('variant') and epithet, which app.js
    needs to tell one species in several areas apart from unidentified "sp." cards."""

    def test_catalog_has_variant(self):
        User = get_user_model()
        manager = User.objects.create_superuser('admin', password='testing')
        country = Country.objects.create(name='Israel'); sea = Sea.objects.create(name='Mediterranean')
        region = Region.objects.create(name='Haifa', country=country, sea=sea)
        trip = DiveTrip.objects.create(title='Haifa', year=2026, country=country, region=region)
        species = Species.objects.create(scientific_name='Okenia sp.', genus='Okenia', species='sp.')
        s = Sample(owner=manager, trip=trip, kind=Sample.Kind.SPECIES, species=species, undetermined_variant='A',
                   video_url='https://youtu.be/11111111111')
        s.save_reviewed(manager, approve=True)
        js = self.client.get('/catalog.js').content.decode()
        self.assertIn('"variant": "A"', js)
        self.assertIn('"epithet": "sp."', js)


class SpeciesCardsYellowCountOnPagesTests(TestCase):
    """Every page that shows species cards -- genus, family / order, dive trip and a species page's other areas --
    marks them like the gallery (_count_badge.html, gallery_data.annotate_same_species): the count is yellow
    (count-badge other-areas, shown even at 1) when the same species has cards from other areas, with "observed in
    N areas, M observations in total" as its tooltip, in the page's language. A species in one area keeps the plain
    badge (only above 1). The genus page's comment about filtered views is a real template comment, not page text."""

    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_superuser('admin', password='testing')
        self.ph = Country.objects.create(name='פיליפינים', name_en='Philippines')
        self.scs = Sea.objects.create(name='ים סין הדרומי', name_en='South China Sea')
        self.il = Country.objects.create(name='ישראל', name_en='Israel')
        self.med = Sea.objects.create(name='הים התיכון', name_en='Mediterranean')
        anilao = Region.objects.create(name='Anilao', country=self.ph, sea=self.scs)
        haifa = Region.objects.create(name='Haifa', country=self.il, sea=self.med)
        self.trip_ph = DiveTrip.objects.create(title='Anilao', code='A1', year=2024, country=self.ph, region=anilao)
        self.trip_ph2 = DiveTrip.objects.create(title='Anilao 2', code='A2', year=2025, country=self.ph, region=anilao)
        self.trip_il = DiveTrip.objects.create(title='Haifa', code='H1', year=2026, country=self.il, region=haifa)
        self.caloria = Species.objects.create(scientific_name='Caloria indica', genus='Caloria', species='indica',
                                              author='(Bergh, 1896)')
        self.militaris = Species.objects.create(scientific_name='Caloria militaris', genus='Caloria',
                                                species='militaris', author='(Alder & Hancock, 1864)')
        n = iter(range(10, 99))
        for trip in (self.trip_ph, self.trip_ph2, self.trip_il):
            self._sample(trip, self.caloria, next(n))
        for trip in (self.trip_il,):
            self._sample(trip, self.militaris, next(n))
        from .models import TaxonGenus
        TaxonGenus.objects.create(name='Caloria')

    def _sample(self, trip, species, n):
        s = Sample(owner=self.manager, trip=trip, kind=Sample.Kind.SPECIES, species=species,
                   video_url=f'https://youtu.be/{n:011d}')
        s.save_reviewed(self.manager, approve=True)
        return s

    def test_totals(self):
        from .gallery_data import same_species_totals
        totals = same_species_totals()
        self.assertEqual(totals[(self.caloria.pk, '')], [2, 3])
        self.assertEqual(totals[(self.militaris.pk, '')], [1, 1])

    def test_genus_page(self):
        html = self.client.get('/genus/Caloria/').content.decode()
        self.assertIn('<span class="count-badge other-areas" aria-hidden="true" title="המין נצפה ב-2 אזורים, 3 תצפיות בסך הכול">2</span>', html)
        self.assertIn('<span class="count-badge other-areas" aria-hidden="true" title="המין נצפה ב-2 אזורים, 3 תצפיות בסך הכול">1</span>', html)
        self.assertEqual(html.count('count-badge'), 2)          # militaris: one observation, one area -- no badge
        self.assertNotIn('A genus card clicked', html)
        html = self.client.get('/genus/Caloria/?lang=en').content.decode()
        self.assertIn('title="This species was observed in 2 areas, 3 observations in total"', html)

    def test_trip_page(self):
        main = Sample(owner=self.manager, trip=self.trip_il, kind=Sample.Kind.COLLECTION, title='Haifa', video_url='https://youtu.be/99999999999')
        main.save_reviewed(self.manager, approve=True)
        response = self.client.get(reverse('trip-page', args=['H1']))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('count-badge other-areas', html)
        self.assertEqual(html.count('count-badge'), 1)

    def test_species_page_other_areas_cards(self):
        il = SpeciesArea.objects.get(species=self.caloria, country=self.il)
        html = self.client.get(reverse('species-page', args=[il.slug])).content.decode()
        self.assertIn('title="המין נצפה ב-2 אזורים, 3 תצפיות בסך הכול">2</span>', html.split('id="other-areas"', 1)[1])

    def test_badge_partial_used_by_taxon_page(self):
        tpl = (Path(settings.BASE_DIR) / 'observations' / 'templates' / 'observations' / 'taxon_page.html').read_text(encoding='utf-8')
        self.assertIn("{% include 'observations/_count_badge.html' %}", tpl)
