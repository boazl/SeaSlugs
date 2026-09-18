"""Content-addressed image storage shared by the folder importer, the live
edit form, and the image manager -- the same bytes always resolve to the same
stored name, regardless of which of those wrote it or which environment it
ran in, which is what makes a transferred Sample row's image reference valid
without re-uploading unchanged files."""
import hashlib
import re
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def validate_image_name(name):
    if not isinstance(name,str) or not re.fullmatch(r'observations/transfer/[0-9a-f]{64}\.jpg',name):
        raise ValidationError('שם קובץ תמונה לא תקין.')


def delete_image_if_unused(name):
    """Delete the stored file at `name` only if no Sample or SiteImage still references it --
    images are content-addressed and can be shared across records (the same photo can back
    several samples, or a sample and a SiteImage), so removing one record's reference must
    not break another's. Returns True if the underlying file was actually deleted."""
    from .models import Sample, SiteImage
    if not name:
        return False
    if Sample.objects.filter(image=name).exists() or SiteImage.objects.filter(image=name).exists():
        return False
    default_storage.delete(name)
    return True


def save_images(images):
    # Content-addressed files preserve old images for database-backup recovery.
    for name, data in images.items():
        if default_storage.exists(name):
            with default_storage.open(name, 'rb') as existing:
                if hashlib.sha256(existing.read()).digest() != hashlib.sha256(data).digest():
                    raise ValidationError('קובץ יעד אינו תקין.')
        else:
            saved = default_storage.save(name, ContentFile(data))
            if saved != name:
                raise ValidationError('התנגשות בעת שמירת תמונה; נסו שוב.')
