"""The media mark on a dive-trip collection card in the gallery."""
import json
import shutil
import subprocess
import unittest

from django.test import SimpleTestCase

from .test_gallery_links import APP_JS, _function_source


@unittest.skipUnless(shutil.which('node'), 'node is needed to run app.js code')
class CollectionCardMarkTests(SimpleTestCase):
    """A collection card carries the same mark as a species card (mediaMarks): ▶ for a video only, ⤢ for a photo
    only, and both in one circle when the collection has a video and a photo (e.g. a photo picked from the gallery)."""

    def mark(self, collection):
        source = APP_JS.read_text(encoding='utf-8')
        script = '\n'.join([
            'const document = {createElement: tag => ({tag, className: "", textContent: "", children: [],'
            ' setAttribute() {}, append(...kids) { this.children.push(...kids); }})};',
            'const lacksLocalVideo = () => false; function markNoLocal() {}',
            _function_source(source, 'mediaMarks'),
            f'const [m] = mediaMarks([{json.dumps(collection)}]);',
            'console.log(JSON.stringify({cls: m.className, text: m.textContent + m.children.map(c => c.textContent).join("")}));',
        ])
        return json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)

    def test_marks(self):
        self.assertEqual(self.mark({'video_id': 'x', 'image_url': '/observations/1/photo/'}), {'cls': 'play play-both', 'text': '▶⤢'})
        self.assertEqual(self.mark({'video_id': 'x', 'image_url': None}), {'cls': 'play', 'text': '▶'})
        self.assertEqual(self.mark({'video_id': None, 'image_url': '/p'}), {'cls': 'play', 'text': '⤢'})

    def test_the_collection_card_uses_it(self):
        source = _function_source(APP_JS.read_text(encoding='utf-8'), 'buildCollectionCard')
        self.assertIn('wrap.append(img, ...mediaMarks([c]));', source)
