"""Template tags for the species / observation counts (see observations/counts.py)."""
from django import template

from observations import counts as _counts

register = template.Library()


@register.simple_tag
def areas_count_text(areas, lang):
    """'30 מינים (50 תצפיות)' for a list of gallery cards (SpeciesArea rows): its species and its cards."""
    areas = list(areas)
    return _counts.count_text(_counts.species_count(areas), len(areas), lang)


@register.simple_tag
def count_text(species, observations, lang):
    """Both numbers in words, always -- the tooltip of a compact '30 (50)' counter."""
    return _counts.count_text(species, observations, lang, full=True)


@register.simple_tag
def count_compact(species, observations):
    return _counts.count_compact(species, observations)


@register.filter
def species_of(areas):
    """The number of distinct species among a list of gallery cards."""
    return _counts.species_count(list(areas))
