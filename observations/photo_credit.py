"""Who took the picture on a card, and how it relates to the visitor (the "photographer tracking" rule).

A card's picture is one observation's photo (or video thumbnail), and its photographer is that observation's owner
(Sample.photographer_name). Under the picture:
  * a visitor who is not signed in always sees the photographer's name;
  * a signed-in member sees the name only when the picture is someone else's -- and then the picture gets a thin
    frame: white ("viewer-has") when the member has an observation of the same species himself, green ("viewer-new")
    when he has none, so a photographer sees at a glance which species he still lacks;
  * his own pictures get neither the name nor a frame.
"The same species" is the catalog species with the same undetermined-variant letter (Sample.undetermined_variant),
and counts every live observation of his (published or still pending).

Mirrored in dist/app.js (photoCredit; the visitor's data comes from catalog.js "viewer", built by viewer_data).
"""
from .models import Sample


def species_key(species_id, variant=''):
    return f'{species_id}|{variant or ""}'


def viewer_species_keys(user):
    """species_key of every species the user has a live observation of (empty for an anonymous visitor)."""
    if not getattr(user, 'is_authenticated', False):
        return set()
    return {species_key(sid, variant) for sid, variant in Sample.objects.filter(
        owner=user, kind=Sample.Kind.SPECIES, deleted_at__isnull=True, species__isnull=False,
    ).values_list('species_id', 'undetermined_variant')}


def viewer_data(user):
    """catalog.js "viewer": None for an anonymous visitor, else his user id and his species keys."""
    if not getattr(user, 'is_authenticated', False):
        return None
    return {'id': user.pk, 'species': sorted(viewer_species_keys(user))}


def credit(sample, user, keys, lang, key=None):
    """{'name': the credit to show ('' = none), 'frame': '' / 'viewer-has' / 'viewer-new'} for a card whose picture
    is `sample`'s. `keys` is viewer_species_keys(user); `key` the card's species_key (None: a card that is not a
    species, such as a dive-trip collection -- the name follows the same rule, without a frame)."""
    if sample is None or not sample.owner_id:
        return {'name': '', 'frame': ''}
    signed_in = getattr(user, 'is_authenticated', False)
    if signed_in and sample.owner_id == user.pk:
        return {'name': '', 'frame': ''}
    name = sample.photographer_display_name(lang)
    if not signed_in or key is None:
        return {'name': name, 'frame': ''}
    return {'name': name, 'frame': 'viewer-has' if key in keys else 'viewer-new'}
