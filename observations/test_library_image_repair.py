"""0075 points a library observation renamed to <name>-2.jpg (its file missing) back at the existing <name>.jpg."""
import importlib, shutil, tempfile
from pathlib import Path
from django.apps import apps
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from observations.models import Sample


class LibraryImageRepairTests(TestCase):
    def test_missing_suffixed_file_falls_back_to_the_plain_name(self):
        media = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, media, True)
        (media / 'observations').mkdir()
        (media / 'observations' / 'genera-berthellina.jpg').write_bytes(b'x')
        (media / 'observations' / 'genera-fiona-2.jpg').write_bytes(b'x')
        u = User.objects.create(username='boaz')
        a = Sample.objects.create(kind='genus', genus='Berthellina', owner=u, image='observations/genera-berthellina-2.jpg')
        b = Sample.objects.create(kind='genus', genus='Fiona', owner=u, image='observations/genera-fiona-2.jpg')   # its file is there
        c = Sample.objects.create(kind='genus', genus='Haminoea', owner=u, image='observations/genera-haminoea-2.jpg')  # no plain file
        mod = importlib.import_module('observations.migrations.0075_repair_library_image_names')
        with override_settings(MEDIA_ROOT=str(media)):
            mod.forwards(apps, None)
        a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
        self.assertEqual(a.image.name, 'observations/genera-berthellina.jpg')
        self.assertEqual(b.image.name, 'observations/genera-fiona-2.jpg')
        self.assertEqual(c.image.name, 'observations/genera-haminoea-2.jpg')
