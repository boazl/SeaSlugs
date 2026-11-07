"""Small hand-rolled bilingual helpers for the server-rendered, non-SPA pages
(the /observations/ listing and the per-species pages). The public gallery
(dist/app.js) already does the same thing client-side with a plain lookup
table of fixed Hebrew strings to their English equivalents; this mirrors
that approach server-side rather than pulling in Django's full
gettext/locale-file i18n machinery for a couple of pages.
"""

LANG_COOKIE = 'seaslugs_lang'
LANGUAGES = ('he', 'en')


# User-agent fragments of search-engine crawlers and link-preview fetchers: they always get the default (Hebrew), so
# the Hebrew pages stay the indexed ones whatever language such a client announces.
CRAWLER_HINTS = ('bot', 'crawl', 'spider', 'slurp', 'facebookexternalhit', 'preview', 'whatsapp')


def browser_lang(request):
    """The language of the visitor's browser (the Accept-Language header): Hebrew when its first choice is Hebrew
    ('he', or the old code 'iw'), English for any other language. No header (crawlers usually send none) and
    crawlers get Hebrew, the site's default."""
    agent = request.META.get('HTTP_USER_AGENT', '').lower()
    if any(hint in agent for hint in CRAWLER_HINTS):
        return 'he'
    best, best_q = None, 0.0
    for part in request.META.get('HTTP_ACCEPT_LANGUAGE', '').split(','):
        tag, _, params = part.strip().partition(';')
        tag = tag.strip().lower()
        if not tag or tag == '*':
            continue
        q = 1.0
        for param in params.split(';'):
            key, _, value = param.strip().partition('=')
            if key.strip() == 'q':
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
        if q > best_q:  # the first of equal choices wins
            best, best_q = tag, q
    if best is None:
        return 'he'
    return 'he' if best.split('-')[0] in ('he', 'iw') else 'en'


def get_lang(request):
    """An explicit ?lang=he/en always wins (and is what the toggle link and every internal link of an English page
    send); otherwise the language remembered in the cookie (set by any ?lang= visit, so it carries over between
    pages); otherwise, on a first visit, the browser's language (browser_lang)."""
    param = request.GET.get('lang')
    if param in LANGUAGES:
        return param
    cookie = request.COOKIES.get(LANG_COOKIE)
    return cookie if cookie in LANGUAGES else browser_lang(request)


def lang_toggle_url(request, lang):
    """URL for the *other* language, keeping every other query parameter (filters,
    sort, etc. on the observations listing) untouched."""
    other = 'en' if lang == 'he' else 'he'
    params = request.GET.copy()
    params['lang'] = other
    return f'{request.path}?{params.urlencode()}'
