# Backing field + one-time backfill for the new "no duplicate photo/video across samples"
# validation added to Sample.clean(). The check itself compares a content hash (image_hash),
# not the storage filename, so it catches a duplicate no matter which upload path put the
# file there (plain admin upload, the observation edit form's content-hash renaming, the
# folder importer, ...). Existing samples need image_hash backfilled once so the check can
# see them; new/edited samples get it set automatically going forward via clean().
import hashlib

from django.db import migrations, models


def backfill_image_hashes(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    updated, skipped = 0, 0
    for sample in Sample.objects.exclude(image='').exclude(image__isnull=True):
        try:
            sample.image.open('rb')
            digest = hashlib.sha256(sample.image.read()).hexdigest()
            sample.image.close()
        except (FileNotFoundError, OSError):
            skipped += 1
            continue
        Sample.objects.filter(pk=sample.pk).update(image_hash=digest)
        updated += 1
    if updated or skipped:
        print(f'  Computed image_hash for {updated} sample(s) with an image; skipped {skipped} '
              f'whose image file could not be read from storage.')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('observations', '0029_set_site_domain_for_sitemaps'),
    ]
    operations = [
        migrations.AddField(
            model_name='sample',
            name='image_hash',
            field=models.CharField(blank=True, db_index=True, default='', editable=False, max_length=64),
        ),
        migrations.RunPython(backfill_image_hashes, noop_reverse),
    ]
