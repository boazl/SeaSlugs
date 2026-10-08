"""Exact historical species aliases approved on 2026-10-08 after the GSC audit.

The manifest records literal URL pairs and a historical observation's transfer UUID.
No species-name or geographic-suffix matching is performed. The UUID also prevents a
reused destination slug from redirecting visitors to an unrelated population.
"""
import json
from pathlib import Path
import re
from types import MappingProxyType
from uuid import UUID

from django.core.exceptions import ValidationError
from django.http import HttpResponsePermanentRedirect
from django.urls import reverse

from .gallery_data import area_samples, taxon_media
from .models import SpeciesArea


def validate_mappings(records):
    """Reject malformed paths, duplicate sources, self redirects and chains/loops."""
    if not isinstance(records, list):
        raise ValueError('Historical species redirects must be a list.')
    mappings = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {'old_slug', 'current_slug', 'sample_transfer_id'}:
            raise ValueError('Each redirect must specify two slugs and a sample transfer UUID.')
        old, current = record['old_slug'], record['current_slug']
        for slug in (old, current):
            if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9-]{1,220}', slug):
                raise ValueError('Redirect slugs must be literal species slugs, without paths or queries.')
        if old == current or old in mappings:
            raise ValueError('Self redirects and duplicate historical slugs are not allowed.')
        try:
            sample_id = UUID(record['sample_transfer_id'])
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError('A valid historical sample transfer UUID is required.') from exc
        mappings[old] = (current, sample_id)
    if any(current in mappings for current, _ in mappings.values()):
        raise ValueError('Historical species redirects must point directly to current URLs, without chains.')
    return MappingProxyType(mappings)


HISTORICAL_SPECIES_REDIRECTS = validate_mappings(json.loads(
    (Path(__file__).parent / 'data' / 'historical_species_redirects.json').read_text(encoding='utf-8')))


def historical_species_redirect(request, slug):
    """Return a 301 only when an approved target still serves the verified population."""
    mapping = HISTORICAL_SPECIES_REDIRECTS.get(slug)
    if mapping is None:
        return None
    current, sample_id = mapping
    area = SpeciesArea.objects.select_related('defining_sample').filter(slug=current).first()
    if area is None:
        return None
    try:
        has_media = any(taxon_media(area.defining_sample)[1:])
    except ValidationError:
        # Invalid imported media cannot be a publicly available redirect target.
        return None
    if not has_media:
        return None
    # Uses exactly the species page's publication, geography and variant checks.
    if not area_samples(area).filter(transfer_id=sample_id).exists():
        return None
    target = reverse('species-page', args=[current])
    lang = request.GET.get('lang')
    if lang in ('en', 'he'):
        target += '?lang=' + lang
    return HttpResponsePermanentRedirect(target)
