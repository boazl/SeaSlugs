"""The readable content of the gallery home page (everything around the interactive gallery):
the hero, "what are sea slugs", the Mediterranean project, how to contribute, the honest numbers line
and the footer invitation.

The server renders each section in the language the URL asks for (/ is Hebrew, /?lang=en is English), so
search engines and visitors without JavaScript get real text and real links. The sections of BOTH languages
are also embedded as JSON so the language button can swap them without a reload (see app.js, setLanguage).

Wording rules: "חינניות ים" is the umbrella term for Sea slugs; "חשופיות" means nudibranchs only; the
collection is international (mostly the Philippines) and is never described as mainly Israeli.
"""
from django.core.cache import cache
from django.template.loader import render_to_string
from django.urls import reverse

SECTIONS = ('hero', 'what', 'project', 'contribute', 'collection_note', 'footer_invite')
CACHE_KEY = 'home-content-data-v1'
CACHE_SECONDS = 300


def clear_cache():
    cache.delete(CACHE_KEY)


def _compute_data():
    from .views import gallery_areas
    areas = gallery_areas()
    species_ids = {a.species_id for a in areas}
    observations = sum(a.observation_count for a in areas)

    israeli = {a.species_id for a in areas
               if a.country.name_en == 'Israel' and a.sea.name_en == 'Mediterranean' and a.observation_count > 0}

    return {
        'species_count': len(species_ids), 'observation_count': observations,
        'israeli_count': len(israeli),
    }


def home_data():
    """Counts, computed from the gallery's own data and cached for a few minutes."""
    data = cache.get(CACHE_KEY)
    if data is None:
        data = _compute_data()
        cache.set(CACHE_KEY, data, CACHE_SECONDS)
    return data


def _sections_for(lang, data, context):
    context = dict(context, lang=lang, suffix='?lang=en' if lang == 'en' else '', **data)
    return {name: render_to_string(f'observations/home/{name}.html', context).strip() for name in SECTIONS}


def home_sections(lang, request, has_site_image):
    """(the sections in `lang` as HTML, {'he': {...}, 'en': {...}} for the language button)."""
    data = home_data()
    context = {
        'contribute_url': reverse('observation-new') if request.user.is_authenticated else reverse('signup'),
        'has_site_image': has_site_image,
    }
    both = {code: _sections_for(code, data, context) for code in ('he', 'en')}
    return both[lang], both
