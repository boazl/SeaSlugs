"""Every order / family / genus observation belongs to a non-real "library" trip of its kind --
Genera, Families, Orders (thematic, not dives) -- and its image file is named after it:
genera-<genus>.jpg, families-<family>.jpg, orders-<order>.jpg.

Creates the trips (the existing Genera trip becomes thematic), moves the observations into them
and renames their own image files that don't follow the rule yet (e.g. notrip-berthellina.jpg ->
genera-berthellina.jpg): the file on disk (when present in this environment) and every sample
showing it. The same data gives the same names in both environments, so the image comparison
keeps matching them.
"""
import os
from pathlib import Path
from django.conf import settings
from django.db import migrations
from django.utils.text import slugify

TRIPS = {'genus': ('Genera', 'ספריית זיהוי לפי סוג'), 'family': ('Families', 'ספריית זיהוי לפי משפחה'), 'order': ('Orders', 'ספריית זיהוי לפי סדרה')}


def forwards(apps, schema_editor):
    DiveTrip = apps.get_model('observations', 'DiveTrip')
    Sample = apps.get_model('observations', 'Sample')
    root = Path(settings.MEDIA_ROOT)
    trips = {}
    for kind, (code, title) in TRIPS.items():
        trip = DiveTrip.objects.filter(code=code).first()
        if trip is None and not Sample.objects.filter(kind=kind).exists():
            continue            # nothing to move: the trip is created the first time it is needed
        if trip is None:
            trip = DiveTrip.objects.create(code=code, title=title, kind='thematic')
        else:
            DiveTrip.objects.filter(pk=trip.pk).update(kind='thematic')
        trips[kind] = trip
    for kind, trip in trips.items():
        Sample.objects.filter(kind=kind).exclude(trip=trip).update(trip=trip)
    used = set(Sample.objects.exclude(image='').values_list('image', flat=True))
    for sample in Sample.objects.filter(kind__in=list(TRIPS), deleted_at__isnull=True, gallery_source__isnull=True).exclude(image='').order_by('pk'):
        old = sample.image if isinstance(sample.image, str) else sample.image.name
        code = TRIPS[sample.kind][0]
        if Path(old).name.startswith(slugify(code) + '-'):
            continue
        name = {'order': sample.order, 'family': sample.family, 'genus': sample.genus}[sample.kind]
        base = slugify(f'{code} {name}', allow_unicode=True) or f'sample-{sample.pk}'
        candidate, n = base, 2
        # A file already on disk under the new name that no sample shows is this sample's own photo when
        # its old file isn't here (e.g. fetched from the website by the image manager): take it over.
        own_file_missing = not (root / old).is_file()
        while f'observations/{candidate}.jpg' in used or ((root / f'observations/{candidate}.jpg').exists() and not own_file_missing):
            candidate = f'{base}-{n}'; n += 1
        new = f'observations/{candidate}.jpg'
        if (root / old).is_file():
            os.replace(root / old, root / new)
        Sample.objects.filter(image=old).update(image=new)
        used.discard(old); used.add(new)


class Migration(migrations.Migration):
    dependencies = [('observations', '0072_defining_samples_descend_empty_levels')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
