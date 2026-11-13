"""Shareable gallery links: the address bar always holds the gallery view on screen, and opening such a link
draws that view -- e.g. the Mediterranean species in alphabetical order are "/?area=med&sort=alpha".

Rules:
- A sea is named in links by its short code (Sea.url_code, e.g. "med"; catalog.js areas[...].code), or by
  "sea-<id>" when it has none. Codes are unique, lower-case, and never one of the gallery's own pseudo-area codes
  ("all", "multi", "migrant") or a "sea-" name. Migration 0090 gives the known seas their codes by name.
- app.js writes the view into the address (galleryUrl, used for every history entry) and reads it on load
  (applyGalleryQuery) after "back to the gallery" (?restore / ?up) and the history entry's own view. Unknown values
  are skipped; other parameters (lang...) are kept.
- "trips=hide" hides the dive-trip collection cards (sidebar "Dive trip collections" unticked, state.hideTrips);
  the taxonomic view has no such cards, so the checkbox is hidden there.
- A manager's gallery has a "copy a link to this view" button (#copyLink); a visitor's has none. The copied link
  has no "lang", so its recipient sees the site in their own browser's language (test_browser_language).
"""
import importlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from .models import Country, Sea, Region, Species, Sample, DiveTrip

APP_JS = Path(settings.BASE_DIR) / 'dist' / 'app.js'


def catalog(client):
    response = client.get('/catalog.js')
    return json.loads(response.content.decode().split('=', 1)[1].strip().removesuffix(';'))


class SeaUrlCodeTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_superuser('manager', password='test-password')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        self.sea = Sea.objects.create(name='הים התיכון', name_en='Mediterranean', url_code='med')
        region = Region.objects.create(name='אכזיב', name_en='Achziv', country=country, sea=self.sea)
        trip = DiveTrip.objects.create(title='Trip', year=2026, country=country, region=region)
        species = Species.objects.create(scientific_name='Test species')
        Sample(owner=self.owner, trip=trip, species=species, video_url='https://youtu.be/abcdefghijk').save_reviewed()

    def test_catalog_gives_each_area_its_link_code(self):
        self.assertEqual(catalog(self.client)['areas'][f'sea-{self.sea.pk}']['code'], 'med')

    def test_a_sea_without_a_code_is_linked_by_its_id(self):
        self.sea.url_code = ''
        self.sea.save()
        self.assertEqual(catalog(self.client)['areas'][f'sea-{self.sea.pk}']['code'], f'sea-{self.sea.pk}')

    def test_codes_are_unique(self):
        other = Sea(name='ים סוף', url_code='MED')
        with self.assertRaises(ValidationError):
            other.full_clean()

    def test_reserved_codes_are_refused(self):
        for code in ('all', 'multi', 'migrant', 'sea-3'):
            with self.subTest(code=code), self.assertRaises(ValidationError):
                Sea(name='ים', url_code=code).full_clean()

    def test_code_is_stored_lower_case(self):
        sea = Sea(name='ים סוף - מפרץ אילת', url_code='Eilat')
        sea.full_clean()
        self.assertEqual(sea.url_code, 'eilat')

    def test_migration_gives_known_seas_their_codes_by_name(self):
        migration = importlib.import_module('observations.migrations.0090_sea_url_code')
        red = Sea.objects.create(name='ים סוף - מפרץ אילת')
        bali = Sea.objects.create(name='שם אחר', name_en='Indo Pacific - Bali Sea')
        unknown = Sea.objects.create(name='ים לא מוכר')
        migration.set_codes(django_apps, None)
        self.assertEqual(Sea.objects.get(pk=red.pk).url_code, 'eilat')
        self.assertEqual(Sea.objects.get(pk=bali.pk).url_code, 'bali')
        self.assertEqual(Sea.objects.get(pk=unknown.pk).url_code, '')
        self.assertEqual(Sea.objects.get(pk=self.sea.pk).url_code, 'med')   # an existing code is kept


class CopyLinkButtonTests(TestCase):
    def test_manager_gallery_has_the_copy_link_button(self):
        User.objects.create_superuser('manager', password='test-password')
        self.client.login(username='manager', password='test-password')
        self.assertContains(self.client.get('/'), 'id="copyLink"')

    def test_visitor_gallery_has_no_copy_link_button(self):
        self.assertNotContains(self.client.get('/'), 'id="copyLink"')


def _function_source(source, name):
    start = source.index(f'function {name}(')
    depth, i = 0, source.index('{', start)
    while True:
        if source[i] == '{':
            depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1


def _const_line(source, name):
    start = source.index(f'const {name} = ')
    return source[start:source.index(';\n', start) + 1]


@unittest.skipUnless(shutil.which('node'), 'node is needed to run app.js code')
class GalleryQueryTests(SimpleTestCase):
    """galleryQuery (state -> address) and applyGalleryQuery (address -> state), run from app.js itself."""

    def run_js(self, body, href='https://seaslugs.org.il/?lang=he'):
        source = APP_JS.read_text(encoding='utf-8')
        script = '\n'.join([
            f'const window = {{location: {{href: {json.dumps(href)}}}}};',
            "const areaLabelsData = {'sea-1': {label: 'הים התיכון', code: 'med'}, 'sea-2': {label: 'ים סוף'}};",
            "const tripLabelsData = {'7': {label: 'Trip', area: 'sea-1'}};",
            "const LEVELS = ['order', 'suborder', 'superfamily', 'family', 'genus', 'species'];",
            "const speciesList = [{order: 'Nudibranchia', taxon_family_id: 5}];",
            "const rankKey = (sp, level) => level === 'order' ? sp.order : level === 'family' ? String(sp.taxon_family_id) : '';",
            'const drillMembers = drill => speciesList.filter(sp => rankKey(sp, drill.level) === drill.id);',
            "const nextLevel = () => 'family';",
            "const search = {value: ''};",
            'const state = {area: "all", regions: new Set(), sites: new Set(), photographers: new Set(), years: new Set(),'
            ' observations: new Set(), level: "order", drill: null, collection: null, hideTrips: false, media: new Set(), sort: "taxonomic", sortChosen: false};',
            'const driveVideoIds = new Set();   // a manager\'s page',
            'const multiObsOn = () => state.observations.has("multi");',
            'function setLevel(level) { state.level = LEVELS.includes(level) ? level : "order"; }',
            'function defaultSort() { return multiObsOn() ? "count" : state.area === "migrant" ? "year" : "taxonomic"; }',
            # the real syncSortControl drops a sort the view doesn't offer; its <select> handling is left out here
            'function syncSortControl() { if ((state.sort === "year" && state.area !== "migrant") || (state.sort === "count" && !multiObsOn())) { state.sort = defaultSort(); state.sortChosen = false; } }',
            _const_line(source, 'AREA_PSEUDO_CODES'),
            _const_line(source, 'GALLERY_URL_KEYS'),
            _const_line(source, 'GALLERY_URL_SETS'),
            _const_line(source, 'MEDIA_SORTS'),
            _const_line(source, 'GALLERY_SORTS'),
            _const_line(source, 'MEDIA_FILTERS'),
            _const_line(source, 'PHOTOGRAPHER_KINDS'),
            _const_line(source, 'photographerKey'),
            _function_source(source, 'normalizePhotographerKeys'),
            _const_line(source, 'activeMedia'),
            _function_source(source, 'areaCode'),
            _function_source(source, 'areaFromCode'),
            _function_source(source, 'galleryQuery'),
            _function_source(source, 'galleryUrl'),
            _function_source(source, 'applyGalleryQuery'),
            body,
        ])
        out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def view(self, query):
        return self.run_js(
            f'const applied = applyGalleryQuery(new URLSearchParams({json.dumps(query)}));'
            'console.log(JSON.stringify({applied, area: state.area, sort: state.sort, sortChosen: state.sortChosen,'
            ' level: state.level, drill: state.drill, regions: [...state.regions], photographers: [...state.photographers],'
            ' obs: [...state.observations], trip: state.collection, hideTrips: state.hideTrips, q: search.value}));')

    def url(self, setup, href='https://seaslugs.org.il/?lang=he'):
        return self.run_js(setup + '\nconsole.log(JSON.stringify(galleryUrl()));', href)

    def test_mediterranean_alphabetical_link(self):
        self.assertEqual(self.url('state.area = "sea-1"; state.sort = "alpha"; state.sortChosen = true;'),
                         '/?lang=he&area=med&sort=alpha')

    def test_link_opens_the_mediterranean_alphabetically(self):
        v = self.view('area=med&sort=alpha')
        self.assertTrue(v['applied'])
        self.assertEqual((v['area'], v['sort'], v['sortChosen']), ('sea-1', 'alpha', True))

    def test_default_view_has_a_clean_address(self):
        self.assertEqual(self.url(''), '/?lang=he')

    def test_a_sea_without_a_code_and_the_pseudo_areas(self):
        self.assertEqual(self.url('state.area = "sea-2";'), '/?lang=he&area=sea-2')
        self.assertEqual(self.url('state.area = "multi-area";'), '/?lang=he&area=multi')
        self.assertEqual(self.view('area=sea-2')['area'], 'sea-2')
        self.assertEqual(self.view('area=MULTI')['area'], 'multi-area')
        self.assertEqual(self.view('area=migrant')['sort'], 'year')   # the migrant view's own default sort

    def test_filters_round_trip(self):
        query = self.url('state.regions.add("3"); state.regions.add("4"); state.photographers.add("בעז ליבס::exclusive");'
                         ' state.observations.add("multi"); state.collection = "7"; search.value = "Flabellina";')
        v = self.view(query.split('?', 1)[1])
        self.assertEqual(v['regions'], ['3', '4'])
        self.assertEqual(v['photographers'], ['בעז ליבס::exclusive'])
        self.assertEqual((v['obs'], v['trip'], v['q'], v['level']), (['multi'], '7', 'Flabellina', 'species'))

    def test_an_old_photographer_link_means_his_species_and_collections(self):
        # links from before the per-kind boxes carried the bare name; an unknown kind is dropped
        v = self.view('photographer=בעז+ליבס&photographer=דנה::nonsense')
        self.assertEqual(v['photographers'], ['בעז ליבס::species', 'בעז ליבס::collections'])

    def test_taxon_drilled_into_round_trips(self):
        query = self.url('state.drill = {level: "order", id: "Nudibranchia"}; state.level = "family";')
        self.assertEqual(query, '/?lang=he&in=order%3ANudibranchia&level=family')
        v = self.view(query.split('?', 1)[1])
        self.assertEqual((v['drill'], v['level']), ({'level': 'order', 'id': 'Nudibranchia'}, 'family'))

    def test_unknown_values_are_skipped(self):
        v = self.view('area=atlantis&sort=random&trip=999&in=order:Nothing&level=kingdom')
        self.assertEqual((v['area'], v['sort'], v['trip'], v['drill'], v['level']), ('all', 'taxonomic', None, None, 'order'))
        self.assertEqual(self.view('sort=year')['sort'], 'taxonomic')   # year only exists under "migrant"

    def test_an_address_without_gallery_parameters_changes_nothing(self):
        self.assertFalse(self.view('lang=en')['applied'])

    def test_other_parameters_are_kept(self):
        self.assertEqual(self.url('state.area = "sea-1";', 'https://seaslugs.org.il/?lang=en&area=sea-2&sort=alpha#gallery'),
                         '/?lang=en&area=med#gallery')


    def test_hidden_trip_collections_round_trip(self):
        self.assertEqual(self.url('state.area = "sea-1"; state.sort = "alpha"; state.sortChosen = true; state.hideTrips = true;'),
                         '/?lang=he&area=med&sort=alpha&trips=hide')
        self.assertTrue(self.view('area=med&sort=alpha&trips=hide')['hideTrips'])
        self.assertFalse(self.view('area=med&sort=alpha')['hideTrips'])


class GalleryLinkWiringTests(SimpleTestCase):
    def test_history_entries_carry_the_view_address(self):
        source = APP_JS.read_text(encoding='utf-8')
        body = _function_source(source, 'recordGalleryHistory')
        self.assertEqual(body.count('galleryUrl()'), 2)
        self.assertNotIn('window.location.href', body)

    def test_a_shared_link_is_read_after_restore_up_and_history(self):
        source = APP_JS.read_text(encoding='utf-8')
        order = [source.index(s) for s in ('let restoredScroll = restoreGalleryView();', 'if (applyUpParam())',
                                           'restoredScroll = restoreFromHistory();',
                                           'applyGalleryQuery(new URLSearchParams(window.location.search))')]
        self.assertEqual(order, sorted(order))

    def test_hidden_trip_collections_drop_their_cards(self):
        source = APP_JS.read_text(encoding='utf-8')
        self.assertIn('const filteredCollections = taxonomic || state.hideTrips ? [] :', source)
        self.assertIn("document.querySelector('#tripCardOptions').hidden = taxonomic;", source)
        self.assertIn('state.hideTrips = false;', _function_source(source, 'applyGalleryQuery') + source[source.index("document.querySelector('#reset')"):])

    def test_the_copied_link_carries_no_language(self):
        source = APP_JS.read_text(encoding='utf-8')
        start = source.index("copyLinkButton.addEventListener('click'")
        handler = source[start:source.index('copyLinkButton.title = link;', start)]
        self.assertIn("url.searchParams.delete('lang');", handler)
