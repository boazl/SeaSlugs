"""The article library's public side: the list page (/articles/), each article's PDF, the "מאמרים" /
"Articles" section that every page with picked articles shows, and the page note of a species+area.

An article is uploaded once (Article, in the admin) and picked from the library by species, orders,
families, genera and dive trips (their `articles` field) -- see models.Article."""
import re

from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .i18n import get_lang
from .models import Article, Species, SpeciesArea, TaxonFamily, TaxonGenus, TaxonOrder
from .names import italicize_names, known_binomials


def with_lang(url, lang):
    return f'{url}?lang=en' if lang == 'en' and url else url


def article_links(articles, lang, binomials=None):
    """What a page shows for each of its articles, in the page's language: the title (scientific names in
    italics), the source, the PDF address and whether that PDF is in the other language."""
    if binomials is None:
        binomials = known_binomials()
    links = []
    for article in articles:
        written = article.is_written
        pdf_lang = article.pdf_lang(lang)
        figure = article.first_figure() if written else None
        other_language = (not getattr(article, 'title_' + lang)) if written else bool(pdf_lang and pdf_lang != lang)
        links.append({
            'slug': article.slug, 'title': italicize_names(article.title(lang), binomials), 'source': article.source,
            'link': article.link, 'pdf_url': article.pdf_url(lang), 'other_language': other_language,
            'written': written, 'url': article.url(lang),
            'thumb_url': reverse('observation-photo', args=[figure.pk]) if figure else article.thumb_url(lang),
            'list_url': with_lang(reverse('article-list'), lang) + f'#{article.slug}',
        })
    return links


_SEE_ARTICLE = {'he': re.compile(r'ראו מאמר'), 'en': re.compile(r'see article', re.I)}


def note_html(row, lang, articles, binomials=None):
    """A page note -- of a species+area (SpeciesArea) or of one observation (Sample), both have note_he /
    note_en -- in `lang` (falling back to the other language), names in italics and "ראו מאמר" /
    "see article" linked to the species' article: straight to its PDF when the species has one article,
    to the page's own articles section when it has several, left as text when it has none."""
    text_lang = lang if getattr(row, 'note_' + lang) else ('he' if lang == 'en' else 'en')
    text = getattr(row, 'note_' + text_lang)
    if not text:
        return ''
    html = str(italicize_names(text, binomials))
    if articles:
        target = articles[0].url(lang) if len(articles) == 1 else '#articles'
        html = _SEE_ARTICLE[text_lang].sub(
            lambda m: str(format_html('<a href="{}">{}</a>', target, m.group(0))), html, count=1)
    return mark_safe(html)


def _area_links(species, lang):
    from .gallery_data import taxon_media
    from .seo_text import area_label, multi_sea_country_ids
    multi = multi_sea_country_ids()
    links = []
    for area in species.areas.select_related('country', 'sea', 'defining_sample').exclude(slug__isnull=True).exclude(slug=''):
        _thumb, image_url, video_id = taxon_media(area.defining_sample)
        if image_url or video_id:
            links.append({'url': with_lang(reverse('species-page', args=[area.slug]), lang),
                          'name': species.scientific_name, 'place': area_label(area, lang, multi)})
    return links


def article_list(request):
    """Every article in the library, newest first, with its PDF and the pages that show it."""
    lang = get_lang(request)
    binomials = known_binomials()
    articles = list(Article.objects.prefetch_related('species', 'orders', 'families', 'genera', 'trips'))
    rows = []
    for article, link in zip(articles, article_links(articles, lang, binomials)):
        places = []
        for species in article.species.all():
            places += _area_links(species, lang)
        for genus in article.genera.all():
            places.append({'url': with_lang(reverse('genus-page', args=[genus.name]), lang), 'name': genus.name, 'place': ''})
        for family in article.families.all():
            places.append({'url': with_lang(reverse('family-page', args=[family.name]), lang), 'name': family.name, 'place': ''})
        for order in article.orders.all():
            places.append({'url': with_lang(reverse('order-page', args=[order.pk]), lang), 'name': str(order), 'place': ''})
        for trip in article.trips.all():
            places.append({'url': with_lang(reverse('dive-trips'), lang) + f'#trip-{trip.pk}', 'name': trip.title, 'place': '', 'trip': True})
        rows.append({**link, 'published_on': article.published_on, 'places': places})
    return render(request, 'observations/articles.html', {'articles': rows})


def article_pdf(request, slug, lang):
    """Streams an article's PDF in `lang` (production never serves MEDIA_ROOT directly)."""
    from .views import _article_response
    article = get_object_or_404(Article, slug=slug)
    field = getattr(article, 'pdf_' + lang, None) if lang in ('he', 'en') else None
    if not field:
        raise Http404
    return _article_response(request, field, slug, filename=f'{slug}-{lang}.pdf')


# Shown instead of a preview when a PDF cannot be rendered: a plain document outline.
DOCUMENT_ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" fill="#0d2732"/>'
                 '<path d="M22 14h14l8 8v28H22z" fill="none" stroke="#64dfce" stroke-width="2.5" stroke-linejoin="round"/>'
                 '<path d="M36 14v8h8M27 32h12M27 38h12M27 44h8" stroke="#64dfce" stroke-width="2.5" fill="none"/></svg>')


def article_thumb(request, slug, lang):
    """The preview (first page) of an article's PDF in `lang`, made now if it was never made; a document
    icon when the PDF cannot be rendered."""
    from .article_thumbs import ensure_thumbnail
    from .views import _article_response
    article = get_object_or_404(Article, slug=slug)
    if lang not in ('he', 'en') or not getattr(article, 'pdf_' + lang):
        raise Http404
    thumb = ensure_thumbnail(article, lang)
    if thumb is None:
        response = HttpResponse(DOCUMENT_ICON, content_type='image/svg+xml')
        response['Cache-Control'] = 'public, no-cache'
        return response
    return _article_response(request, thumb, slug, content_type='image/jpeg', filename=f'{slug}-{lang}.jpg')


def legacy_redirect(request, owner):
    """The old one-file addresses (/genus/<name>/article.pdf etc.) keep working: they lead to the first
    article the page picks, in the visitor's language."""
    article = owner.articles.first() if owner is not None else None
    url = article.pdf_url(get_lang(request)) if article else ''
    if not url:
        raise Http404
    return HttpResponseRedirect(url)


def species_article(request, slug):
    area = get_object_or_404(SpeciesArea.objects.select_related('species'), slug=slug)
    return legacy_redirect(request, area.species)


def genus_article(request, name):
    return legacy_redirect(request, get_object_or_404(TaxonGenus, name=name))


def family_article(request, name):
    families = list(TaxonFamily.objects.filter(name=name))
    return legacy_redirect(request, next((f for f in families if not f.sub_family), families[0] if families else None))


def order_article(request, pk):
    return legacy_redirect(request, get_object_or_404(TaxonOrder, pk=pk))


def home_articles_html(lang):
    """The home page's short list of the articles ticked "הצגה בדף הבית" (empty when none)."""
    articles = list(Article.objects.filter(show_on_home=True))
    if not articles:
        return ''
    items = ''.join(
        str(format_html('<li><a class="home-article-thumb" href="{0}" aria-hidden="true" tabindex="-1"><img src="{3}" alt="" width="48" height="48" loading="lazy"></a>'
                        '<a href="{0}">{1}</a>{2}</li>', link['url'] or link['list_url'], link['title'],
                        format_html(' <small>({})</small>', 'in Hebrew' if lang == 'en' else 'באנגלית') if link['other_language'] else '',
                        link['thumb_url']))
        for link in article_links(articles, lang))
    heading = 'Articles' if lang == 'en' else 'מאמרים'
    more = 'All articles' if lang == 'en' else 'כל המאמרים'
    return format_html('<h2>{}</h2><ul class="home-articles">{}</ul><p><a href="{}">{} ›</a></p>',
                       heading, mark_safe(items), with_lang(reverse('article-list'), lang), more)


def _figure_page(sample, lang, multi):
    """The species+area page an article figure's observation belongs to, as {'url', 'name', 'place'} -- or None."""
    from .seo_text import area_label
    trip = sample.trip
    if not (sample.species_id and trip and trip.country_id and trip.region_id):
        return None
    area = SpeciesArea.objects.filter(species_id=sample.species_id, country_id=trip.country_id, sea_id=trip.region.sea_id,
                                      undetermined_variant=sample.undetermined_variant).exclude(slug='').exclude(slug__isnull=True).first()
    if area is None:
        return None
    return {'url': with_lang(reverse('species-page', args=[area.slug]), lang), 'name': sample.taxon_label,
            'place': area_label(area, lang, multi)}


OWN_OBSERVATION_HEADINGS = {'תצפיות באתר', 'התצפיות באתר', 'Observations on the site'}


def article_page(request, slug):
    """An article written on the site, in the page's language (a PDF-only article: its PDF)."""
    from .article_render import inline, plain, reference_list, render_blocks
    from .seo_text import multi_sea_country_ids
    lang = get_lang(request)
    article = get_object_or_404(Article.objects.prefetch_related('blocks', 'references'), slug=slug)
    if not article.is_written:
        url = article.pdf_url(lang)
        if not url:
            raise Http404
        return HttpResponseRedirect(url)
    binomials = known_binomials()
    blocks, untranslated = render_blocks(article, lang, binomials)
    multi = multi_sea_country_ids()
    observed = []
    # An article that has its own "observations on the site" section (as written) does not get the automatic one.
    own_list = any(b.kind == 'heading' and (b.text_he.strip() in OWN_OBSERVATION_HEADINGS or b.text_en.strip() in OWN_OBSERVATION_HEADINGS)
                   for b in article.blocks.all())
    for _html, sample, number in ([] if own_list else blocks):
        if sample is not None:
            page = _figure_page(sample, lang, multi)
            if page:
                observed.append({**page, 'figure': number})
    other = 'he' if lang == 'en' else 'en'
    subtitle = getattr(article, 'subtitle_' + lang) or ''
    figure = article.first_figure()
    return render(request, 'observations/article_page.html', {
        'article': article, 'title': article.title(lang), 'title_html': italicize_names(article.title(lang), binomials),
        'missing_language': not getattr(article, 'title_' + lang), 'untranslated': untranslated,
        'subtitle': inline(subtitle, binomials, lang=lang) if subtitle else '', 'summary': plain(subtitle),
        'byline': getattr(article, 'byline_' + lang) or getattr(article, 'byline_' + other),
        'blocks': [html for html, _s, _n in blocks], 'observed': observed,
        'references': reference_list(article, binomials),
        'editorial': inline(getattr(article, 'editorial_' + lang), binomials, lang=lang) if getattr(article, 'editorial_' + lang) else '',
        'body_line_height': '1.7' if lang == 'en' else '1.75',
        'share_image': reverse('observation-photo', args=[figure.pk]) if figure else '',
        'pdf_url': article.pdf_url(lang), 'pdf_other_language': bool(article.pdf_lang(lang) and article.pdf_lang(lang) != lang),
    })
