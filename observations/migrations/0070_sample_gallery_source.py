"""Sample.gallery_source ("תמונה קיימת בגלריה"): every stored photo gets exactly one owner.

Until now a gallery image chosen for an observation simply copied the other observation's
file name into its own `image`, so one file could belong to several samples with nothing
saying which one it really is. This migration adds the explicit reference and converts every
file shared by several active samples: one sample keeps it as its own image (the owner) and
the others point at the owner through gallery_source (their `image` stays as the mirror).

The owner is the sample the file is named after (its taxon / species name appears in the file
name, e.g. genera-coryphellina.jpg -> the Coryphellina genus observation), else the earliest.
"""
import re
from django.db import migrations, models
import django.db.models.deletion

# Decided by the site manager (2026-10-13): the Flabellinidae family observation does not show
# the Coryphellina genus photo it shared -- its image is cleared instead of becoming a reference.
CLEAR_INSTEAD = {'0b6e181c-be53-440c-957e-52a59372755a'}


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', (text or '').lower()).strip('-')


def _taxon_name(sample):
    if sample.kind == 'order': return sample.order
    if sample.kind == 'family': return sample.family
    if sample.kind == 'genus': return sample.genus
    if sample.kind == 'collection': return sample.title
    return sample.species.scientific_name if sample.species_id else sample.species_other


def assign_owners(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    shared = {}
    for sample in Sample.objects.filter(deleted_at__isnull=True).exclude(image='').select_related('species').order_by('created_at', 'pk'):
        shared.setdefault(sample.image.name if hasattr(sample.image, 'name') else sample.image, []).append(sample)
    for name, samples in shared.items():
        if len(samples) < 2: continue
        stem = name.rsplit('/', 1)[-1].rsplit('.', 1)[0].lower()
        named = [s for s in samples if _slug(_taxon_name(s)) and _slug(_taxon_name(s)) in stem]
        owner = (named or samples)[0]
        for sample in samples:
            if sample.pk == owner.pk: continue
            if str(sample.transfer_id) in CLEAR_INSTEAD:
                Sample.objects.filter(pk=sample.pk).update(image='', image_hash='')
            else:
                Sample.objects.filter(pk=sample.pk).update(gallery_source=owner, image_hash=owner.image_hash)


class Migration(migrations.Migration):
    dependencies = [('observations', '0069_samples_follow_taxonomy')]
    operations = [
        migrations.AddField(
            model_name='sample', name='gallery_source',
            field=models.ForeignKey(blank=True, help_text='התצפית מציגה את התמונה של תצפית אחרת, בלי להעתיק את הקובץ.', null=True,
                                    on_delete=django.db.models.deletion.SET_NULL, related_name='gallery_references',
                                    to='observations.sample', verbose_name='תמונה קיימת בגלריה'),
        ),
        migrations.RunPython(assign_owners, migrations.RunPython.noop),
    ]
