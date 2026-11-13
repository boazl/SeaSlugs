"""Photographer tracking: who took a card's picture, and how it relates to the visitor."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Country, DiveTrip, Region, Sample, Sea, Species
from .photo_credit import credit, species_key, viewer_data, viewer_species_keys

APP_JS = Path(settings.BASE_DIR) / 'dist' / 'app.js'


class PhotoCreditTests(TestCase):
    """Under a card's picture, an anonymous visitor always sees the photographer's name; a signed-in member sees it
    only when the picture is someone else's, and then the picture has a thin frame -- white ("viewer-has") when he
    has a live observation (published or pending) of the same species (+ undetermined-variant letter) himself,
    green ("viewer-new") when he has none. His own pictures show neither. A collection card follows the name rule
    without a frame. The cards of the trip / genus / family / order / species pages (server) and of the gallery
    (app.js photoCredit, catalog.js "viewer") follow the same rule."""

    def setUp(self):
        self.boaz = User.objects.create_user('boazl', first_name='בעז', last_name='ליבס', password='pw-test-12345')
        self.ofer = User.objects.create_user('ofer', first_name='עפר', last_name='בן-צבי', password='pw-test-12345')
        country = Country.objects.create(name='ישראל', name_en='Israel')
        region = Region.objects.create(name='אילת', name_en='Eilat', country=country, sea=Sea.objects.create(name='ים סוף'))
        self.trip = DiveTrip.objects.create(title='Eilat', year=2025, country=country, region=region, code='e1')
        self.other_trip = DiveTrip.objects.create(title='Eilat 2', year=2024, country=country, region=region, code='e2')
        self.species = Species.objects.create(scientific_name='Phyllidia ocellata', genus='Phyllidia', species='ocellata', author='Cuvier, 1804')
        self.sample = Sample(owner=self.boaz, trip=self.trip, species=self.species, video_url='https://youtu.be/aaaaaaaaaaa')
        self.sample.save_reviewed()
        self.key = species_key(self.species.pk)

    def own(self, user, trip=None, variant='', deleted=False):
        sample = Sample(owner=user, trip=trip or self.other_trip, species=self.species, undetermined_variant=variant,
                        video_url=f'https://youtu.be/bbbbbbbbbb{Sample.objects.count()}')
        sample.save_reviewed()
        if deleted:
            sample.soft_delete(user)
        return sample

    def test_anonymous_visitor_always_sees_the_name(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertEqual(credit(self.sample, AnonymousUser(), set(), 'he', self.key), {'name': 'בעז ליבס', 'frame': ''})

    def test_own_picture_shows_nothing(self):
        self.assertEqual(credit(self.sample, self.boaz, viewer_species_keys(self.boaz), 'he', self.key), {'name': '', 'frame': ''})

    def test_someone_elses_picture_green_without_the_species_white_with_it(self):
        self.assertEqual(credit(self.sample, self.ofer, viewer_species_keys(self.ofer), 'he', self.key)['frame'], 'viewer-new')
        self.own(self.ofer)
        result = credit(self.sample, self.ofer, viewer_species_keys(self.ofer), 'he', self.key)
        self.assertEqual(result, {'name': 'בעז ליבס', 'frame': 'viewer-has'})

    def test_pending_counts_deleted_and_other_variants_do_not(self):
        self.own(self.ofer, variant='A')
        self.own(self.ofer, deleted=True)
        self.assertNotIn(self.key, viewer_species_keys(self.ofer))
        self.assertIn(species_key(self.species.pk, 'A'), viewer_species_keys(self.ofer))
        pending = self.own(self.ofer)
        Sample.objects.filter(pk=pending.pk).update(status='pending')
        self.assertIn(self.key, viewer_species_keys(self.ofer))

    def test_collection_card_has_the_name_but_no_frame(self):
        self.assertEqual(credit(self.sample, self.ofer, set(), 'he', None), {'name': 'בעז ליבס', 'frame': ''})

    def card(self, user=None):
        if not Sample.objects.filter(kind='collection').exists():   # the trip page is a trip with a collection
            Sample(kind='collection', owner=self.boaz, trip=self.trip, title='Eilat 2025',
                   video_url='https://youtu.be/ccccccccccc').save_reviewed(approve=True)
        if user:
            self.client.force_login(user)
        html = self.client.get('/trip/e1/').content.decode()
        return html.split('<article class="card">')[1].split('</article>')[0]

    def test_trip_page_card(self):
        card = self.card()
        self.assertIn('צילום: בעז ליבס', card)
        self.assertIn('class="image-wrap"', card)
        card = self.card(self.ofer)
        self.assertIn('צילום: בעז ליבס', card)
        self.assertIn('class="image-wrap viewer-new"', card)
        self.own(self.ofer)
        self.assertIn('class="image-wrap viewer-has"', self.card(self.ofer))
        card = self.card(self.boaz)
        self.assertNotIn('צילום:', card)
        self.assertIn('class="image-wrap"', card)

    def catalog(self):
        text = self.client.get('/catalog.js').content.decode()
        return json.loads(text.removeprefix('window.SEASLUGS = ').removesuffix(';'))

    def test_catalog_carries_the_viewer_and_the_owners(self):
        data = self.catalog()
        self.assertIsNone(data['viewer'])
        entry = data['species'][0]
        self.assertEqual(entry['defining_sample_id'], self.sample.pk)
        self.assertEqual(entry['samples'][0]['owner'], self.boaz.pk)
        self.own(self.ofer)
        self.client.force_login(self.ofer)
        self.assertEqual(self.catalog()['viewer'], {'id': self.ofer.pk, 'species': [self.key]})
        self.assertEqual(viewer_data(self.ofer), {'id': self.ofer.pk, 'species': [self.key]})


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


def _lines(source, first, last):
    """The source from the line that starts `first` to the end of the line that starts `last`."""
    start = source.index(first)
    end = source.index('\n', source.index(last, start))
    return source[start:end + 1]


@unittest.skipUnless(shutil.which('node'), 'node is needed to run app.js code')
class GalleryPhotoCreditAndPhotographerFilterTests(TestCase):
    """app.js mirrors observations/photo_credit.py (photoCredit), and the gallery's photographer filter ticks a
    photographer's "species", "collections" and "exclusive" (species no other photographer has observed, over all
    areas) separately -- each box "<name>::<kind>"; ticking his species alone hides his collections and the other way
    round."""

    def run_js(self, viewer, body):
        source = APP_JS.read_text(encoding='utf-8')
        script = '\n'.join([
            "const language = 'he';",
            f"const catalog = {{viewer: {json.dumps(viewer)}}};",
            # Phyllidia: only Boaz (two areas). Chromodoris: Boaz and Ofer. Doris sp. (unmarked): Ofer only.
            "const speciesList = ["
            " {area_id: 1, species_id: 1, epithet: 'ocellata', variant: '', defining_sample_id: 11, samples: [{sample_id: 11, owner: 1, photographer: 'בעז'}]},"
            " {area_id: 2, species_id: 1, epithet: 'ocellata', variant: '', defining_sample_id: 12, samples: [{sample_id: 12, owner: 1, photographer: 'בעז'}]},"
            " {area_id: 3, species_id: 2, epithet: 'annae', variant: '', defining_sample_id: 14, samples: [{sample_id: 13, owner: 1, photographer: 'בעז'}, {sample_id: 14, owner: 2, photographer: 'עפר'}]},"
            " {area_id: 4, species_id: 3, epithet: 'sp.', variant: '', defining_sample_id: 15, samples: [{sample_id: 15, owner: 2, photographer: 'עפר'}]}];",
            "const state = {photographers: new Set()};",
            "const UNMARKED_SP_EPITHETS = ['', 'sp', 'sp.', 'spp', 'spp.'];",
            _function_source(source, 'sameSpeciesKey'),
            "function photographerLabel(e) { return e.photographer; }",
            _lines(source, 'const viewer = catalog.viewer', 'const viewerSpecies'),
            _function_source(source, 'photoCredit'),
            _function_source(source, 'definingSample'),
            _lines(source, 'const speciesPhotographers = new Map();', '    for (const sm of sp.samples) if (sm.photographer)') + '}',
            _function_source(source, 'exclusivePhotographer'),
            _lines(source, 'const PHOTOGRAPHER_KINDS', 'const photographerKey'),
            _function_source(source, 'photographerMatchesSample'),
            body,
        ])
        return json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)

    def test_photo_credit(self):
        body = "console.log(JSON.stringify(speciesList.map(sp => photoCredit(definingSample(sp), sp)).concat([photoCredit({owner: 2, photographer: 'עפר'}, null)])));"
        anonymous = self.run_js(None, body)
        self.assertEqual([c['name'] for c in anonymous], ['בעז', 'בעז', 'עפר', 'עפר', 'עפר'])
        self.assertEqual({c['frame'] for c in anonymous}, {''})
        ofer = self.run_js({'id': 2, 'species': ['2|']}, body)
        self.assertEqual(ofer, [{'name': 'בעז', 'frame': 'viewer-new'}, {'name': 'בעז', 'frame': 'viewer-new'},
                                {'name': '', 'frame': ''}, {'name': '', 'frame': ''}, {'name': '', 'frame': ''}])
        boaz = self.run_js({'id': 1, 'species': ['1|', '2|']}, body)
        self.assertEqual(boaz[2], {'name': 'עפר', 'frame': 'viewer-has'})
        self.assertEqual(boaz[3], {'name': 'עפר', 'frame': 'viewer-new'})

    def test_exclusive_species(self):
        out = self.run_js(None, "console.log(JSON.stringify(speciesList.map(exclusivePhotographer)));")
        self.assertEqual(out, ['בעז', 'בעז', None, 'עפר'])

    def matching(self, keys):
        return self.run_js(None, f"for (const k of {json.dumps(keys)}) state.photographers.add(k);"
                           "console.log(JSON.stringify(speciesList.map(sp => sp.samples.filter(sm => photographerMatchesSample(sm, sp)).map(sm => sm.sample_id))));")

    def test_filter_by_kind(self):
        self.assertEqual(self.matching(['בעז::species']), [[11], [12], [13], []])
        self.assertEqual(self.matching(['בעז::exclusive']), [[11], [12], [], []])
        self.assertEqual(self.matching(['עפר::exclusive']), [[], [], [], [15]])
        self.assertEqual(self.matching(['בעז::collections']), [[], [], [], []])

    def test_collections_and_sidebar_use_the_kinds(self):
        source = APP_JS.read_text(encoding='utf-8')
        self.assertIn("state.photographers.has(photographerKey(c.photographer, 'collections'))", source)
        sidebar = source.split("const photographerBox = document.querySelector('#photographerOptions');")[1].split('const yearEntries')[0]
        for kind in ('species', 'collections', 'exclusive'):
            self.assertIn(f"photographerKey(name, '{kind}')", sidebar)
        self.assertIn("head.className = 'filter-photographer-name'", sidebar)
        self.assertIn('function photographerExclusiveCount(', source)
