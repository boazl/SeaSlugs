"""Small hand-rolled bilingual helpers for the server-rendered, non-SPA pages
(the /observations/ listing and the per-species pages). The public gallery
(dist/app.js) already does the same thing client-side with a plain lookup
table of fixed Hebrew strings to their English equivalents; this mirrors
that approach server-side rather than pulling in Django's full
gettext/locale-file i18n machinery for a couple of pages.
"""

LANG_COOKIE = 'seaslugs_lang'
LANGUAGES = ('he', 'en')


def get_lang(request):
    """An explicit ?lang=he/en always wins (and is what the toggle link sends);
    otherwise fall back to a previously remembered cookie, then Hebrew."""
    param = request.GET.get('lang')
    if param in LANGUAGES:
        return param
    cookie = request.COOKIES.get(LANG_COOKIE)
    return cookie if cookie in LANGUAGES else 'he'


def lang_toggle_url(request, lang):
    """URL for the *other* language, keeping every other query parameter (filters,
    sort, etc. on the observations listing) untouched."""
    other = 'en' if lang == 'he' else 'he'
    params = request.GET.copy()
    params['lang'] = other
    return f'{request.path}?{params.urlencode()}'
