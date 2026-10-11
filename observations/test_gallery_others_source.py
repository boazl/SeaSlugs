"""Taxonomic gallery (dist/app.js): below the order, a species with no value at the shown rank goes to an "Others"
card of its order, and inside a chosen taxon a rank none of its species has is skipped. The behaviour itself is
checked with a jsdom script against a real catalog; these tests guard the rules in the source."""
from pathlib import Path

from django.test import SimpleTestCase

JS = (Path(__file__).resolve().parent.parent / 'dist' / 'app.js').read_text(encoding='utf-8')


class GalleryOthersSourceTests(SimpleTestCase):
    def test_a_species_without_the_shown_rank_gets_an_others_card_not_a_higher_rank_card(self):
        self.assertIn("!rankKey(sp, level)) ck = { level, key: '', others: true };", JS)

    def test_others_are_kept_inside_their_own_order(self):
        self.assertIn("'others:' + (state.drill ? '' : (sp.order || ''))", JS)
        self.assertIn('orderRank', JS)

    def test_a_rank_none_of_the_chosen_taxons_species_has_is_skipped(self):
        self.assertIn("!species.some(sp => rankKey(sp, level))", JS)

    def test_the_others_card_of_an_undrilled_view_drills_into_its_order(self):
        self.assertIn("else if (others) state.drill = { level: 'order', id: members[0].order || '', blanks: [level] };", JS)
