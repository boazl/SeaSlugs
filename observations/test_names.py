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
