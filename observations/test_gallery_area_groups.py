"""One gallery card per species: a species' cards from several areas are grouped (dist/app.js groupSpeciesByArea)."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .test_gallery_links import _function_source, _const_line

APP_JS = Path(settings.BASE_DIR) / 'dist' / 'app.js'
STYLES = Path(settings.BASE_DIR) / 'dist' / 'styles.css'


@unittest.skipUnless(shutil.which('node'), 'node is needed to run app.js code')
class GalleryAreaGroupTests(SimpleTestCase):
    """Among the species cards on screen, the cards of one species (sameSpeciesKey: the same catalog species and
    variant letter; a bare "Genus sp." never groups) from several areas become one card showing the number of
    areas. The card shown is the Mediterranean one when there is one, else the one with the most observations
    (first in order on a tie); the group stands where its first card was. Only the cards that pass the filters
    count: a species left with one card is an ordinary card. Clicking the number opens the other area cards right
    after the group's card; opening / closing a group is not a new history view."""

    def run_js(self, body):
        source = APP_JS.read_text(encoding='utf-8')
        script = '\n'.join([
            "let language = 'he';",
            "const areaLabelsData = {'sea-1': {label: 'הים התיכון', code: 'med'}, 'sea-2': {label: 'ים סוף', code: 'red'}, 'sea-3': {label: 'ים סין'}};",
            'const scopedSamples = () => null;',
            _const_line(source, 'UNMARKED_SP_EPITHETS'),
            _const_line(source, 'MED_AREA_CODE'),
            _function_source(source, 'sameSpeciesKey'),
            _function_source(source, 'observationCount'),
            _function_source(source, 'isMediterraneanArea'),
            _function_source(source, 'groupRepresentative'),
            _function_source(source, 'groupSpeciesByArea'),
            _function_source(source, 'otherAreasTip'),
            _function_source(source, 'areaGroupText'),
            _function_source(source, 'areaGroupTip'),
            _function_source(source, 'sameView'),
            'const sp = (id, species_id, area, n, extra = {}) => ({id, species_id, area, epithet: "x", variant: "",'
            ' samples: Array.from({length: n}, () => ({})), ...extra});',
            body,
        ])
        out = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def groups(self, cards):
        return self.run_js(f'const list = [{cards}];'
                           'console.log(JSON.stringify(groupSpeciesByArea(list).map(e => [e.sp.id, e.members.map(m => m.id), e.key])));')

    def test_species_from_several_areas_is_one_card_in_place_of_its_first(self):
        result = self.groups("sp('a1', 1, 'sea-2', 1), sp('b', 2, 'sea-2', 1), sp('a2', 1, 'sea-3', 3), sp('a3', 1, 'sea-2', 1)")
        self.assertEqual(result, [['a2', ['a2', 'a1', 'a3'], '1|'], ['b', ['b'], None]])

    def test_the_mediterranean_card_wins(self):
        result = self.groups("sp('ph', 1, 'sea-3', 9), sp('il', 1, 'sea-1', 1), sp('gr', 1, 'sea-1', 2)")
        self.assertEqual(result, [['gr', ['gr', 'ph', 'il'], '1|']])

    def test_tie_keeps_the_first(self):
        self.assertEqual(self.groups("sp('x', 1, 'sea-2', 2), sp('y', 1, 'sea-3', 2)")[0][0], 'x')

    def test_unmarked_sp_and_other_variants_are_not_grouped(self):
        result = self.groups("sp('s1', 5, 'sea-2', 1, {epithet: 'sp.'}), sp('s2', 5, 'sea-3', 1, {epithet: 'sp.'}),"
                             "sp('va', 6, 'sea-2', 1, {variant: 'A'}), sp('vb', 6, 'sea-3', 1, {variant: 'B'})")
        self.assertEqual([r[2] for r in result], [None, None, None, None])

    def test_single_card_left_by_the_filters_is_ordinary(self):
        self.assertEqual(self.groups("sp('only', 1, 'sea-2', 4)"), [['only', ['only'], None]])

    def test_number_and_tooltip(self):
        result = self.run_js("const m = [sp('a', 1, 'sea-1', 2), sp('b', 1, 'sea-2', 3)];"
                             "const he = [areaGroupText(2), areaGroupTip(m)]; language = 'en';"
                             "console.log(JSON.stringify([...he, areaGroupText(2), areaGroupTip(m)]));")
        self.assertEqual(result[0], '2 אזורים')
        self.assertIn('המין נצפה ב-2 אזורים, 5 תצפיות בסך הכול', result[1])
        self.assertEqual(result[2], '2 areas')
        self.assertIn('observed in 2 areas, 5 observations in total', result[3])

    def test_opening_a_group_is_the_same_history_view(self):
        result = self.run_js("const a = {state: {area: 'all', openGroups: []}}, b = {state: {area: 'all', openGroups: ['1|']}};"
                             "const c = {state: {area: 'sea-1', openGroups: []}};"
                             'console.log(JSON.stringify([sameView(a, b), sameView(a, c)]));')
        self.assertEqual(result, [True, False])

    def test_render_and_card_wiring(self):
        source = APP_JS.read_text(encoding='utf-8')
        render = _function_source(source, 'render')
        self.assertIn('groupSpeciesByArea(filteredSpecies)', render)
        self.assertIn('members.slice(1)', render)            # the open group's other area cards follow it
        card = _function_source(source, 'buildSpeciesCard')
        self.assertIn("toggle.className = 'area-group-toggle'", card)
        self.assertIn("'aria-expanded'", card)
        self.assertIn('if (!group && (displayCount > 1 || otherAreas))', card)   # no observation badge on a group
        self.assertIn('openGroups: [],', source)
        self.assertIn('state.openGroups = Array.isArray(entry.state.openGroups)', source)
        self.assertIn('state.openGroups = Array.isArray(saved.state.openGroups)', source)
        styles = STYLES.read_text(encoding='utf-8')
        self.assertIn('.area-group-toggle{', styles)
        self.assertIn('.card.area-group{position:relative}', styles)
