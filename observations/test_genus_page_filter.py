from pathlib import Path
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from .models import Country, Sea, Region, DiveTrip, Species, Sample, SpeciesArea, TaxonGenus, TaxonFamily, TaxonOrder


class GenusPageFilterTests(TestCase):
    """A genus card clicked in a filtered gallery view (a dive trip, region, photographer, year...) carries the
    filter to the genus page: ?areas=<SpeciesArea ids>&samples=<observation ids>[&trip=<trip id>]
    (dist/app.js genusPageHref, views.genus_page_focus). The page then shows only those species in the main
    grid -- each card with the matching observation's photo and the matching observations' count -- with
    a link to all the species, and the genus's other species after them as small cards. Without the
    parameters, or with stale/junk ones, the page shows every species as before."""

    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        sea = Sea.objects.create(name='ים סוף', name_en='Red Sea')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=sea)
        self.trip1 = DiveTrip.objects.create(title='Eilat spring', year=2025, country=country, region=region)
        self.trip2 = DiveTrip.objects.create(title='Eilat autumn', year=2026, country=country, region=region)
        family = TaxonFamily.objects.create(name='Chromodorididae', order=TaxonOrder.objects.create(name='Nudibranchia'))
        self.genus = TaxonGenus.objects.create(name='Chromodoris', family=family)
        self.annae = Species.objects.create(scientific_name='Chromodoris annae', genus='Chromodoris', species='annae', author='Bergh, 1877')
        self.willani = Species.objects.create(scientific_name='Chromodoris willani', genus='Chromodoris', species='willani', author='Rudman, 1982')
        self.annae_1 = self._sample(self.annae, self.trip1, 'aaaaaaaaaa1')
        self.annae_2 = self._sample(self.annae, self.trip2, 'aaaaaaaaaa2')
        self.annae_3 = self._sample(self.annae, self.trip2, 'aaaaaaaaaa3')
        self.willani_1 = self._sample(self.willani, self.trip1, 'wwwwwwwwww1')
        self.area_annae = SpeciesArea.objects.get(species=self.annae)
        self.area_willani = SpeciesArea.objects.get(species=self.willani)
        self.url = f'/genus/{self.genus.name}/'

    def _sample(self, species, trip, video):
        sample = Sample(owner=self.owner, trip=trip, species=species, video_url=f'https://youtu.be/{video}')
        sample.save_reviewed()
        return sample

    def _parts(self, response):
        html = response.content.decode()
        main, _, others = html.partition('genus-others')
        return main, others

    def test_without_a_filter_every_species_is_in_the_main_grid(self):
        response = self.client.get(self.url)
        main, others = self._parts(response)
        self.assertIn(f'/species/{self.area_annae.slug}/', main)
        self.assertIn(f'/species/{self.area_willani.slug}/', main)
        self.assertEqual(others, '')
        self.assertNotContains(response, 'הצגת כל המינים בסוג')

    def test_filtered_species_first_and_the_others_as_small_cards(self):
        response = self.client.get(self.url, {'areas': str(self.area_annae.pk), 'trip': str(self.trip2.pk)})
        main, others = self._parts(response)
        self.assertIn(f'/species/{self.area_annae.slug}/', main)
        self.assertNotIn(f'/species/{self.area_willani.slug}/', main)
        self.assertIn('grid grid-small', others)
        self.assertIn(f'/species/{self.area_willani.slug}/', others)
        self.assertIn('מינים נוספים בסוג זה', others)
        self.assertContains(response, 'במסע Eilat autumn')
        self.assertContains(response, f'<a href="{self.url}#species">הצגת כל המינים בסוג</a>', html=True)

    def test_card_shows_the_matching_observations(self):
        ids = f'{self.annae_2.pk},{self.annae_3.pk}'
        response = self.client.get(self.url, {'areas': str(self.area_annae.pk), 'samples': ids, 'trip': str(self.trip2.pk)})
        main, _ = self._parts(response)
        self.assertIn('https://i.ytimg.com/vi/aaaaaaaaaa2/hqdefault.jpg', main)   # the trip's first observation's photo
        self.assertIn('<span class="count-badge" aria-hidden="true">2</span>', main)   # the trip's 2, not all 3
        response = self.client.get(self.url, {'areas': str(self.area_annae.pk), 'samples': str(self.annae_1.pk)})
        main, _ = self._parts(response)
        self.assertIn('https://i.ytimg.com/vi/aaaaaaaaaa1/hqdefault.jpg', main)
        self.assertNotIn('count-badge', main.split('id="species"')[1])
        self.assertContains(response, 'לפי הסינון בגלריה')   # no trip: the generic wording

    def test_observations_of_another_species_are_ignored(self):
        response = self.client.get(self.url, {'areas': str(self.area_annae.pk), 'samples': str(self.willani_1.pk)})
        main, _ = self._parts(response)
        self.assertIn('<span class="count-badge" aria-hidden="true">3</span>', main)   # the whole area, as without samples

    def test_stale_or_junk_parameters_show_the_whole_genus(self):
        for params in ({'areas': '999999'}, {'areas': 'x,-3,'}, {'areas': ''}):
            response = self.client.get(self.url, params)
            main, others = self._parts(response)
            self.assertIn(f'/species/{self.area_willani.slug}/', main)
            self.assertEqual(others, '')

    def test_english(self):
        response = self.client.get(self.url, {'areas': str(self.area_annae.pk), 'trip': str(self.trip2.pk), 'lang': 'en'})
        self.assertContains(response, 'Species in this genus — on the trip Eilat autumn')
        self.assertContains(response, 'More species of this genus')
        self.assertContains(response, f'<a href="{self.url}?lang=en#species">Show all the species of the genus</a>', html=True)
        self.assertNotContains(response, 'מינים נוספים בסוג זה')

    def test_gallery_sends_the_filter_with_the_genus_card(self):
        js = (Path(settings.BASE_DIR) / 'dist' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function genusPageHref(href, key, members)', js)
        self.assertIn("window.location.href = genusPageHref(href, key, members);", js)
        for param in ("params.set('areas'", "params.set('samples'", "params.set('trip', state.collection)"):
            self.assertIn(param, js)


class DrillStopsAtTheGenusTests(TestCase):
    """Drilling down in the gallery never jumps over the genus: when what is left under the clicked taxon is a
    single genus (e.g. a filtered view -- one trip -- with only one species of a superfamily), the gallery shows
    that genus's card, which opens the genus page with the filter, instead of going straight to the species
    card (dist/app.js nextLevel)."""

    def test_next_level_stops_at_a_single_genus(self):
        import json, subprocess
        js = (Path(settings.BASE_DIR) / 'dist' / 'app.js').read_text(encoding='utf-8')
        start = js.index("const LEVELS = ")
        levels = js[start:js.index('\n', start)]
        rank = js[js.index('function rankKey('):js.index('\n}\n', js.index('function rankKey(')) + 3]
        nxt = js[js.index('function nextLevel('):js.index('\n}\n', js.index('function nextLevel(')) + 3]
        sp = lambda slug, family, genus: {'slug': slug, 'order': 'Nudibranchia', 'superfamily': 'Doridoidea',
                                          'taxon_family_id': family, 'taxon_genus_id': genus}
        cases = [
            ('superfamily', [sp('a', 1, 10)], 'genus'),                       # one species: its genus card
            ('superfamily', [sp('a', 1, 10), sp('b', 1, 10)], 'genus'),       # one genus, two species
            ('superfamily', [sp('a', 1, 10), sp('b', 1, 11)], 'genus'),       # two genera of one family
            ('superfamily', [sp('a', 1, 10), sp('b', 2, 11)], 'family'),
            ('genus', [sp('a', 1, 10), sp('b', 1, 10)], 'species'),           # inside a genus: its species
            ('superfamily', [sp('a', 1, None)], 'species'),                   # no genus to show
        ]
        script = f"{levels}\n{rank}\n{nxt}\nconst cases = {json.dumps(cases)};\n" \
                 "console.log(JSON.stringify(cases.map(([level, list]) => nextLevel(level, list))));"
        out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [expected for _, _, expected in cases])
