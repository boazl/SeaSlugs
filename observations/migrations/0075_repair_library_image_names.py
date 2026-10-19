"""Repairs the library (order / family / genus) observations that 0073 renamed to <name>-2.jpg:
where the observation's own file wasn't on disk but a file under the plain name was (fetched from the
website by the image manager), 0073 counted it as taken and pointed the observation at a file that
doesn't exist -- so its card showed no picture. Points such an observation back at the plain-named
file, when that file exists and no other sample shows it.
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
        old = sample.image if isinstance(sample.image, str) else sample.image.name
        match = SUFFIX.match(old)
        if not match or (root / old).is_file():
            continue
        base = f'{match.group(1)}.jpg'
        if base in used or not (root / base).is_file():
            continue
        Sample.objects.filter(image=old).update(image=base)
        used.discard(old); used.add(base)


class Migration(migrations.Migration):
    dependencies = [('observations', '0074_sample_title_en')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
