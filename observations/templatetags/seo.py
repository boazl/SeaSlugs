"""Share / search metadata for the public pages: canonical URL, hreflang alternates, Open
Graph and Twitter-card tags, and the optional Google Search Console verification tag.

Every URL here is absolute and on the real production domain (the django.contrib.sites
row -- the same source /sitemap.xml and /robots.txt use), so a page shared from any
environment always points at https://seaslugs.org.il, and WhatsApp/Facebook previews get
an image URL they can actually fetch.
"""
from django import template
from django.conf import settings
from django.contrib.sites.models import Site

from .seaslugs_i18n import t

register = template.Library()

DEFAULT_DESCRIPTION = 'תצפיות, תמונות ומידע מאתר SeaSlugs, אתר חינניות הים.'


def site_base():
    return 'https://' + Site.objects.get_current().domain


def absolute(url, base):
    if not url:
        return ''
    if url.startswith('http://'):
        return 'https://' + url[len('http://'):]
    if url.startswith('https://'):
        return url
    return base + (url if url.startswith('/') else '/' + url)


@register.inclusion_tag('observations/_share_meta.html', takes_context=True)
def share_meta(context, name, common_name='', description='', image='', bilingual=True):
    """name / common_name make the share title ("Chromodoris annae — Annae's chromodoris");
    description falls back to the site's generic line; image may be a site-relative path
    (an observation photo) or an absolute URL (a YouTube thumbnail). bilingual=False for a
    page whose HTML has one language only (the gallery home, which switches in JavaScript):
    no hreflang, and its canonical URL never carries ?lang."""
    request = context['request']
    lang = context.get('lang', 'he')
    base = site_base()
    he_url = base + request.path
    en_url = he_url + '?lang=en'
    canonical = en_url if (bilingual and lang == 'en') else he_url
    title = f'{name} — {common_name}' if common_name else str(name)
    if not description:
        description = f'{name} — {t(DEFAULT_DESCRIPTION, lang)}'
    return {
        'lang': lang if bilingual else 'he',
        'bilingual': bilingual,
        'canonical': canonical, 'he_url': he_url, 'en_url': en_url,
        'title': title, 'description': description,
        'image': absolute(image, base),
        'google_verification': getattr(settings, 'GOOGLE_SITE_VERIFICATION', ''),
    }
