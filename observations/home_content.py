"""The readable content of the gallery home page (everything around the interactive gallery):
the hero, "what are sea slugs", the Mediterranean project, how to contribute, the honest numbers line
the footer invitation and a collapsed block of links to the groups and Israeli species.

The server renders each section in the language the URL asks for (/ is Hebrew, /?lang=en is English), so
search engines and visitors without JavaScript get real text and real links. The sections of BOTH languages
are also embedded as JSON so the language button can swap them without a reload (see app.js, setLanguage).

Wording rules: "חינניות ים" is the umbrella term for Sea slugs; "חשופיות" means nudibranchs only; the
collection is international (mostly the Philippines) and is never described as mainly Israeli.
"""
from django.core.cache import cache
from django.template.loader import render_to_string
from django.urls import reverse

from .home_defaults import DEFAULTS
from .home_markup import render_markup

CACHE_KEY = 'home-content-data-v2'
CACHE_SECONDS = 300


def clear_cache():
    cache.delete(CACHE_KEY)


def _compute_data():
    from .views import gallery_areas
    areas = gallery_areas()
    species_ids = {a.species_id for a in areas}
    observations = sum(a.observation_count for a in areas)

    israeli_rows = []
    for a in areas:
        if (a.country.name_en == 'Israel' and a.sea.name_en == 'Mediterranean'
                and a.slug and a.observation_count > 0):
            variant = f' {a.undetermined_variant}' if a.undetermined_variant else ''
            israeli_rows.append({
                'slug': a.slug, 'name': f'{a.species.scientific_name}{variant}',
                'he': a.species.name_he, 'en': a.species.name_en, 'migrant': bool(a.species.is_migrant),
            })
    israeli_rows.sort(key=lambda row: row['name'].lower())

    groups = {}
    for a in areas:
        order, family = a.taxon_order, a.taxon_family
        if not order:
            continue
        group = groups.setdefault(order.pk, {'pk': order.pk, 'name': order.name, 'he': order.name_he,
                                              'en': order.name_en, 'families': {}})
        if family:
            group['families'].setdefault(family.name, {'name': family.name, 'he': family.name_he,
                                                       'en': family.name_en})
    orders = []
    for group in sorted(groups.values(), key=lambda g: g['name'].lower()):
        group['families'] = sorted(group['families'].values(), key=lambda f: f['name'].lower())
        orders.append(group)

    return {
        'species_count': len(species_ids), 'observation_count': observations,
        'israeli_count': len({row['name'] for row in israeli_rows}),
        'israeli': israeli_rows, 'orders': orders,
    }


def home_data():
    """Counts, computed from the gallery's own data and cached for a few minutes."""
    data = cache.get(CACHE_KEY)
    if data is None:
        data = _compute_data()
        cache.set(CACHE_KEY, data, CACHE_SECONDS)
    return data


def overrides():
    """{(key, lang): text} of the sections edited on the edit screen."""
    from django.db import DatabaseError
    from .models import HomeText
    try:
        return {(row.key, row.lang): row.content for row in HomeText.objects.all()}
    except DatabaseError:  # the table does not exist yet (migration not applied): the home page still works
        return {}


def current_text(key, lang, edited=None):
    edited = overrides() if edited is None else edited
    return edited.get((key, lang)) or DEFAULTS[key][lang]


def _sections_for(lang, data, contribute_url, has_site_image, edited):
    numbers = {'species': data['species_count'], 'observations': data['observation_count'], 'israeli': data['israeli_count']}
    text = lambda key: current_text(key, lang, edited)
    render = lambda key, **kw: render_markup(text(key), numbers, contribute_url, **kw)
    sections = {
        'hero': render_to_string('observations/home/hero.html', {
            'lang': lang, 'has_site_image': has_site_image,
            'body': render('hero', paragraph_class='intro-copy')}).strip(),
        'collection_note': str(render('collection_note', inline=True)),
        'footer_invite': str(render('footer_invite', inline=True)),
        # Not editable: a collapsed list of links to the taxonomic groups and the Israeli Mediterranean species,
        # so crawlers (and visitors) reach every group and species page from the home page.
        'browse': render_to_string('observations/home/browse.html', {
            'lang': lang, 'suffix': '?lang=en' if lang == 'en' else '',
            'orders': data['orders'], 'israeli': data['israeli'], 'israeli_count': data['israeli_count']}).strip(),
    }
    for key in ('what', 'project', 'contribute'):
        sections[key] = str(render(key))
    return sections


def home_sections(lang, request, has_site_image):
    """(the sections in `lang` as HTML, {'he': {...}, 'en': {...}} for the language button)."""
    data = home_data()
    edited = overrides()
    contribute_url = reverse('observation-new') if request.user.is_authenticated else reverse('signup')
    both = {code: _sections_for(code, data, contribute_url, has_site_image, edited) for code in ('he', 'en')}
    return both[lang], both
