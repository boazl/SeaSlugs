from django.test import SimpleTestCase
from .names import name_html


class NameHtmlTests(SimpleTestCase):
    def test_genus_and_epithet_are_italic_and_the_rest_is_roman(self):
        self.assertEqual(name_html('Chromodoris strigata'), '<i>Chromodoris strigata</i>')
        self.assertEqual(name_html('Chromodoris strigata Rudman, 1982'), '<i>Chromodoris strigata</i> Rudman, 1982')
        self.assertEqual(name_html('Chromodoris cf. strigata Rudman, 1982 juv.'), '<i>Chromodoris</i> cf. <i>strigata</i> Rudman, 1982 juv.')
        self.assertEqual(name_html('Plakobranchus ocellatus van Hasselt, 1824'), '<i>Plakobranchus ocellatus</i> van Hasselt, 1824')
        self.assertEqual(name_html('Triopa principis-walliae'), '<i>Triopa principis-walliae</i>')

    def test_placeholders_and_variant_letters_stay_roman(self):
        self.assertEqual(name_html('Atagema sp. 13'), '<i>Atagema</i> sp. 13')
        self.assertEqual(name_html('Coryphellina sp. A'), '<i>Coryphellina</i> sp. A')
        self.assertEqual(name_html('Chromodoris'), '<i>Chromodoris</i>')       # a genus on its own
        self.assertEqual(name_html('Aegires aff. villosus'), '<i>Aegires</i> aff. <i>villosus</i>')

    def test_text_is_escaped(self):
        self.assertEqual(name_html('Chromodoris <b>x</b>'), '<i>Chromodoris</i> &lt;b&gt;x&lt;/b&gt;')
        self.assertEqual(name_html(''), '')
        self.assertEqual(name_html(None), '')


class GalleryScriptTests(SimpleTestCase):
    """The gallery cards are built in dist/app.js; it must use the same italic rule."""
    def test_gallery_cards_and_player_title_use_the_italic_helper(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parent.parent / 'dist' / 'app.js').read_text(encoding='utf-8')
        self.assertIn('function setLatinName(', js)
        self.assertIn('setLatinName(h3, sp.title)', js)
        self.assertIn("setLatinName(document.querySelector('#playerTitle'), species.title)", js)

    def test_sidebar_counts_go_through_the_area_filter_so_pseudo_areas_do_not_show_zero(self):
        # "migrant" / "multi-area" are not real values of sp.area: comparing sp.area === area in a
        # count function made every sidebar count 0 while those buttons were active.
        from pathlib import Path
        js = (Path(__file__).resolve().parent.parent / 'dist' / 'app.js').read_text(encoding='utf-8')
        self.assertNotIn('sp.area !== area', js)
        self.assertNotIn('c.area !== area', js)
        self.assertNotIn("sp.area === area)", js)
        for fn in ('regionCount', 'siteCount', 'tripCount', 'photographerSpeciesCount', 'photographerCollectionCount', 'yearCount'):
            body = js.split('function %s(' % fn)[1].split('\nfunction ')[0]
            self.assertIn('matchesAreaFilter(sp, area)' if fn != 'photographerCollectionCount' else 'collectionMatchesArea(c, area)', body, fn)

    def test_gallery_card_shows_the_author_small_and_the_photographer_filter_splits_species_and_collections(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / 'dist'
        js, css = (root / 'app.js').read_text(encoding='utf-8'), (root / 'styles.css').read_text(encoding='utf-8')
        self.assertIn("author.className = 'card-author'", js)
        self.assertIn('if (sp.author)', js)
        self.assertIn('function photographerSpeciesCount(', js)
        self.assertIn('function photographerCollectionCount(', js)
        self.assertIn("'מינים'", js)
        self.assertIn("'אוספים'", js)
        self.assertIn('font-size:12px;color:var(--muted)', css.split('.card h3 .card-author{')[1].split('}')[0])
        self.assertIn('.card h3 .card-author{display:block;', css)    # the author always sits on the line below the name
        self.assertIn('direction:ltr;text-align:left;font-weight:400;font-size:18px', css)   # names align left in Hebrew too
        self.assertIn('.card-meta>span:last-child{color:var(--accent)}', css)   # the photographer inside card-where is not teal
        self.assertIn("where.className = 'card-where'", js)
        self.assertIn("where.append(' · ', credit)", js)                      # place/year and photographer on one line
        self.assertIn('info.append(meta);', js)
        self.assertNotIn('info.append(credit, meta)', js)
        self.assertEqual(css.count('.card h3{'), 2)        # the later override must not bring the old 24px back
        for rule in css.split('}'):
            if rule.strip().startswith('.card h3{'): self.assertIn('font-size:18px', rule + '}')

    def test_taxonomic_level_drill_down(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / 'dist'
        js, html = (root / 'app.js').read_text(encoding='utf-8'), (root / 'index.html').read_text(encoding='utf-8')
        # Level selector next to the sort: order (default), family, genus, species.
        self.assertIn('<select id="levelSelect"', html)
        self.assertIn('<option value="order" selected>', html)
        self.assertIn("level: 'order',", js)
        # The taxonomic view hides dive-trip collections and draws one card per taxon above species level.
        self.assertIn("const filteredCollections = taxonomic ? [] :", js)
        self.assertIn('function renderTaxonLevel(', js)
        # A card click drills one rank down; picking a taxon in the search jumps to its own rank.
        self.assertIn('state.drill = { level, id: String(key) };', js)
        self.assertIn('setLevel(nextLevel(level, members));', js)
        # Full hierarchy, empty ranks skipped while drilling.
        self.assertIn("const LEVELS = ['order', 'suborder', 'superfamily', 'family', 'genus', 'species'];", js)
        for value in ('suborder', 'superfamily'):
            self.assertIn(f'<option value="{value}">', html)
        self.assertIn('state.drill = { level: c.kind, id: String(c.id) };', js)

    def test_others_card_keeps_species_without_a_rank_reachable(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parent.parent / 'dist' / 'app.js').read_text(encoding='utf-8')
        # Inside a drilled-into taxon, a species with no value at the shown rank is not folded back
        # into a card for the taxon being browsed: it gets an "Others" card (last), which drills on.
        self.assertIn('if (state.drill && below && LEVELS.indexOf(ck.level) <= drillIndex) ck = { level, key: \'\', others: true };', js)
        self.assertIn('const below = LEVELS.indexOf(level) > drillIndex;', js)
        self.assertIn('.sort((a, b) => (a.others ? 1 : 0) - (b.others ? 1 : 0))', js)
        self.assertIn("function othersLabel() { return language === 'he' ? 'אחרים' : 'Others'; }", js)
        self.assertIn("if (others) state.drill = { ...state.drill, blanks: [...(state.drill.blanks || []), level] };", js)
        # The narrowed drill filters on the blank ranks, is named in the status line, and goes back up to the taxon.
        self.assertIn('return !(drill.blanks || []).some(rank => rankKey(sp, rank));', js)
        self.assertIn('if (state.drill && !inDrill(sp, state.drill)) return false;', js)
        self.assertIn('if (drill.blanks && drill.blanks.length) {', js)

    def test_observation_year_sort_and_migrant_card_years(self):
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / 'dist'
        js, css, html = (root / 'app.js').read_text(encoding='utf-8'), (root / 'styles.css').read_text(encoding='utf-8'), (root / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<option value="year">', html)
        self.assertIn("if (state.sort === 'year')", js)
        self.assertIn('function speciesYearCompare(', js)
        # Migrant view defaults to the year sort, but never overrides a sort the visitor picked.
        self.assertIn("return state.area === 'migrant' ? 'year' : 'taxonomic';", js)
        self.assertIn('if (!state.sortChosen) state.sort = defaultSort();', js)
        self.assertIn('if (!state.sortChosen)', js)
        self.assertIn('state.sortChosen = true', js)
        self.assertIn('state.sortChosen = false', js)
        # The year sort is offered only while the migrant filter is active: the option is
        # removed otherwise, and a year sort falls back to taxonomic on leaving that view.
        self.assertIn('function syncSortControl()', js)
        self.assertIn('yearSortOption.remove()', js)
        self.assertIn("if (state.sort === 'year') { state.sort = defaultSort(); state.sortChosen = false; }", js)
        self.assertEqual(js.count('syncSortControl();'), 4)   # area click, observations filter, reset, initial load
        # The years line only appears under the migrant filter.
        self.assertIn("if (state.area === 'migrant' && (sp.first_observed_year || sp.last_observed_year))", js)
        self.assertIn("'נצפה לראשונה בים התיכון'", js)
        self.assertIn("'נראה לאחרונה'", js)
        self.assertIn("'Mediterranean first sight'", js)
        # Each date on its own row, the year bold, the years aligned one under the other.
        self.assertIn('.card-years{display:grid;grid-template-columns:minmax(0,max-content) max-content;', css)
        self.assertIn('.card-years strong{', css)
        self.assertIn("document.createElement('strong')", js)
        self.assertNotIn("parts.join(' · ')", js)
