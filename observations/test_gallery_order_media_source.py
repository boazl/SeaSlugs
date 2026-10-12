"""An order / sub-order card in the taxonomic gallery shows the photo of its curated defining sample (set in
the admin on the TaxonOrder row); only without one does it fall back to its first species."""
from pathlib import Path

from django.test import SimpleTestCase

APP_JS = (Path(__file__).resolve().parent.parent / 'dist' / 'app.js').read_text(encoding='utf-8')


class OrderCardMediaSourceTests(SimpleTestCase):
    def test_order_cards_look_up_their_row_through_order_pages(self):
        self.assertIn('function orderRowEntry(level, key)', APP_JS)
        self.assertIn("(taxaData.order_pages || {})[key]", APP_JS)
        self.assertIn("e.sub_value === key", APP_JS)

    def test_card_prefers_the_curated_entry_and_falls_back_to_the_first_species(self):
        self.assertIn("(taxonEntry(level, key) || orderRowEntry(level, key) || {})", APP_JS)
        self.assertIn("img.src = entry.thumbnail || members[0].thumbnail;", APP_JS)


class TaxonCardPageLinkSourceTests(SimpleTestCase):
    def test_sub_order_and_superfamily_cards_link_to_their_row_page(self):
        self.assertIn("(level === 'suborder' || level === 'superfamily') && entry.pk) href = `/order/${entry.pk}/`;", APP_JS)
