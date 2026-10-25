"""Template tags for the species counts (see observations/counts.py)."""
from django import template

from observations import counts as _counts

register = template.Library()


@register.simple_tag
def areas_count_text(areas, lang):
    """'30 מינים': the distinct species among a list of gallery cards (SpeciesArea rows)."""
    return _counts.count_text(_counts.species_count(list(areas)), lang)


@register.filter
def species_of(areas):
    """The number of distinct species among a list of gallery cards."""
    return _counts.species_count(list(areas))
