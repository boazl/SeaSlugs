"""Image storage shared by the folder importer, the live edit form, and the image
manager. Two naming conventions coexist: the legacy content-hash name (the same bytes
always resolve to the same stored name, so a transferred Sample row's image reference is
valid without re-uploading unchanged files) and the current canonical, identity-based name
(trip code + species/title -- see Sample.canonical_image_name), which is stable across
environments without depending on the bytes matching at all, and is reused -- overwritten
with new bytes -- whenever that same observation's photo is replaced."""
import hashlib
import re
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


# Two valid shapes: the legacy content-hash name (observations/transfer/<sha256>.jpg,
# still produced by anything not yet migrated to the canonical scheme) and the canonical
# trip-code+identity name (observations/<slug>.jpg -- see Sample.canonical_image_name).
# Restricting the canonical shape to slug characters (word characters/hyphens, Unicode-
# aware so Hebrew titles pass through) rather than accepting any string is deliberate: this
# value arrives from an uploaded JSON transfer file, so it must not be able to smuggle a
# path-traversal segment or point outside the observations/ folder.
_LEGACY_IMAGE_NAME_RE = re.compile(r'observations/transfer/[0-9a-f]{64}\.jpg')
_CANONICAL_IMAGE_NAME_RE = re.compile(r'observations/[\w\-]+\.jpg', re.UNICODE)


def validate_image_name(name):
    if not isinstance(name,str) or not (_LEGACY_IMAGE_NAME_RE.fullmatch(name) or _CANONICAL_IMAGE_NAME_RE.fullmatch(name)):
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
    for name, data in images.items():
        if _LEGACY_IMAGE_NAME_RE.fullmatch(name):
            # Content-addressed: if this exact hash-name already exists, its bytes must
            # already match by construction -- a mismatch means real corruption, not
            # legitimate reuse, so it's rejected rather than overwritten.
            if default_storage.exists(name):
                with default_storage.open(name, 'rb') as existing:
                    if hashlib.sha256(existing.read()).digest() != hashlib.sha256(data).digest():
                        raise ValidationError('קובץ יעד אינו תקין.')
                continue
        elif default_storage.exists(name):
            # Identity-addressed (canonical) name: the same name is legitimately reused
            # when an observation's photo is replaced, so the old bytes there are simply
            # replaced -- deleted first, since Django's storage would otherwise treat the
            # existing file as a collision and silently save under a different name instead.
            default_storage.delete(name)
        saved = default_storage.save(name, ContentFile(data))
        if saved != name:
            raise ValidationError('התנגשות בעת שמירת תמונה; נסו שוב.')
