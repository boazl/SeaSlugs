"""Small, cheap per-request context additions used by templates site-wide."""
from .i18n import get_lang, lang_toggle_url
from .maintenance import is_locked


def maintenance_status(request):
    # Exposed unconditionally (cheap: just a file-exists check); templates gate its
    # display behind `user.is_superuser` themselves, same as the other admin-only links.
    return {'site_locked': is_locked()}


def language(request):
    # Cheap (no DB access): the bilingual pages (observations listing, species pages)
    # read `lang`/`lang_toggle_url` from context; pages that don't render a toggle
    # simply never reference them.
    lang = get_lang(request)
    return {'lang': lang, 'lang_toggle_url': lang_toggle_url(request, lang)}
