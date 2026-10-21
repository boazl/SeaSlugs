"""Repairs the library (order / family / genus) observations that 0073 renamed to <name>-2.jpg in an
environment where their own file wasn't on disk but a file under the plain name was (fetched from the
website by the image manager): 0073 counted the plain name as taken and pointed the observation at a
<name>-2.jpg that doesn't exist here -- so its card showed no picture. The other environment has the photo
under that very <name>-2.jpg, so the plain-named file is renamed to it (when no sample shows the plain
name), keeping the names the same in both environments.
"""
import re
from pathlib import Path
from django.conf import settings
from django.db import migrations

SUFFIX = re.compile(r'^(observations/(?:genera|families|orders)-.+)-\d+\.jpg$')


def forwards(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    root = Path(settings.MEDIA_ROOT)
    used = set(Sample.objects.exclude(image='').values_list('image', flat=True))
    for sample in Sample.objects.filter(kind__in=('genus', 'family', 'order')).exclude(image='').order_by('pk'):
        name = sample.image if isinstance(sample.image, str) else sample.image.name
        match = SUFFIX.match(name)
        if not match or (root / name).exists():
            continue
        base = f'{match.group(1)}.jpg'
        if base in used or not (root / base).is_file():
            continue
        (root / base).replace(root / name)


class Migration(migrations.Migration):
    dependencies = [('observations', '0074_sample_title_en')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
