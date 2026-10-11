"""Taxonomic gallery: taxon cards are framed by rank (lighter the lower the rank), species cards have no frame."""
from pathlib import Path

from django.test import SimpleTestCase

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
        self.assertNotIn('taxon-level-species', self.css)

    def test_frames_get_lighter_down_the_ranks(self):
        def brightness(level):
            marker = f'.taxon-card.taxon-level-{level} .image-wrap'
            rule = self.css[self.css.index(marker):]
            color = rule[rule.index('outline-color:#') + len('outline-color:#'):][:6]
            r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
            return 0.299 * r + 0.587 * g + 0.114 * b
        values = [brightness(level) for level in ('order', 'suborder', 'superfamily', 'family')]
        self.assertEqual(values, sorted(values))
        self.assertEqual(len(set(values)), 4)
        self.assertEqual(brightness('family'), brightness('genus'))
