"""Search-result text for the public species pages: the <title> and the fallback meta description.

Pure functions over already-loaded objects, so the wording can be tested without rendering a page.
Nothing here changes a URL or a record -- it only decides what a search engine reads.
"""
from django.db.models import Count

from .models import SpeciesArea


def multi_sea_country_ids():
    """Ids of countries that have species areas in more than one sea (Israel: the Mediterranean and
    the Red Sea). For those the sea is what tells two populations of one species apart."""
    rows = SpeciesArea.objects.values('country_id').annotate(seas=Count('sea_id', distinct=True))
    return {row['country_id'] for row in rows if row['seas'] > 1}


def _name(obj, lang):
    if not obj:
        return ''
    return ((obj.name_en or obj.name) if lang == 'en' else (obj.name or obj.name_en)) or ''


def area_label(area, lang, multi_sea_countries):
    """Where the population lives: the country, plus the sea when the country spans several
    ("ישראל, ים התיכון" / "Israel, Mediterranean")."""
    country = _name(area.country, lang)
    if area.country_id in multi_sea_countries:
        sea = _name(area.sea, lang)
        return f'{country}, {sea}' if sea else country
    return country or _name(area.sea, lang)


def is_mediterranean(area):
    sea = area.sea
    return bool(sea and (sea.name == 'ים התיכון' or 'Mediterranean' in (sea.name_en or '')))


def species_title(species_label, common_name, label):
    """'Hypselodoris infucata — חינניית … · ישראל, ים התיכון | SeaSlugs'. The place goes after the
    name so two populations that share one scientific name get two different titles."""
    title = species_label + (f' — {common_name}' if common_name else '')
    if label:
        title += f' · {label}'
    return f'{title} | SeaSlugs'


def species_description(species_label, common_name, family_label, order_label, observation_count,
                        label, lang, migrant_year=None, migrant=False):
    """A factual description built from the data, for species with no written one."""
    en = lang == 'en'
    head = f'{species_label} ({common_name})' if common_name else species_label
    parts = []
    taxa = []
    if family_label:
        taxa.append(f'family {family_label}' if en else f'ממשפחת {family_label}')
    if order_label:
        taxa.append(f'order {order_label}' if en else f'מסדרת {order_label}')
    kind = 'A sea slug' if en else 'חיננית ים'
    sentence = f'{head}: {kind}'
    if taxa:
        sentence += (' of the ' if en else ' ') + ', '.join(taxa)
    parts.append(sentence + '.')
    if observation_count:
        n = observation_count
        if en:
            parts.append(f'{n} observation{"" if n == 1 else "s"}' + (f' in {label}.' if label else '.'))
        else:
            parts.append(f'{n} תצפיות' + (f' – {label}.' if label else '.'))
    elif label:
        parts.append(f'Region: {label}.' if en else f'אזור: {label}.')
    if migrant:
        if en:
            parts.append('A migrant species in the Mediterranean' + (f', first recorded in {migrant_year}.' if migrant_year else '.'))
        else:
            parts.append('מין מהגר בים התיכון' + (f', נרשם לראשונה בשנת {migrant_year}.' if migrant_year else '.'))
    return ' '.join(parts)
