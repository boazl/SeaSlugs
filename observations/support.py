"""Voluntary financial support for the project (/support/, /support/thank-you/, test_support.py).

The payment itself happens entirely on PayPal's hosted page (settings.PAYPAL_SUPPORT_URL, a PayPal "payment link"
where the payer picks the amount, in ILS). The site stores nothing about supporters or payments: no tables, no
API, no webhooks, no amount field.

* settings.SUPPORT_ENABLED switches the whole feature: the menu and footer links, the support page (404 when off)
  and its sitemap entry. Off by default in production until the owner turns it on; on by default locally.
* The thank-you page is PayPal's auto-return address. It is always reachable (a payer who used a link shared
  before the feature was switched off still lands on a friendly page), is noindex and never in the sitemap, and
  never treats the visit as proof of a payment: no amount, no transaction id, no "verified" message.
* GA4 (the site's existing tag only): support_page_view, support_paypal_click, support_thank_you_view, with
  language / payment_provider / currency -- never a purchase event, never personal data.
"""
from urllib.parse import urlparse

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

# The hosts a payment link may point at -- anything else is treated as "no link" (no button, feature off).
PAYPAL_HOSTS = ('www.paypal.com', 'paypal.com', 'www.paypal.me', 'paypal.me')


def paypal_url():
    """settings.PAYPAL_SUPPORT_URL if it is an https PayPal address, else ''."""
    url = (getattr(settings, 'PAYPAL_SUPPORT_URL', '') or '').strip()
    try:
        parts = urlparse(url)
    except ValueError:
        return ''
    if parts.scheme != 'https' or (parts.hostname or '').lower() not in PAYPAL_HOSTS:
        return ''
    return url


def is_enabled():
    """The support option is on: SUPPORT_ENABLED and a valid PayPal link."""
    return bool(getattr(settings, 'SUPPORT_ENABLED', False)) and bool(paypal_url())


def show_link(request):
    """Whether the menu / footer shows the "support the project" link: the option is on and the page is not one of
    the management tools under /admin/."""
    return is_enabled() and not request.path.startswith('/admin/')


def context(request):
    """Context processor: `support_link` -- the support page's path when the link is shown, else ''."""
    return {'support_link': reverse('support') if show_link(request) else ''}


def _is_nudibranch(resolver, species):
    order = resolver.resolve(species)[0]
    return bool(order and order.name == 'Nudibranchia')


def featured_photo(lang):
    """The picture on the support page, from the site's own photos: the defining photo of a published gallery
    observation in the Mediterranean -- a nudibranch first, Israel first, then the best rated, then the oldest.
    None when there is no such photo (the page then simply has no picture)."""
    from django.db.models import Q
    from .gallery_data import TaxonResolver
    from .models import SpeciesArea
    from .names import name_html
    areas = [a for a in SpeciesArea.objects.filter(
        Q(sea__name='ים התיכון') | Q(sea__name_en__icontains='Mediterranean')).exclude(slug='').select_related(
        'species', 'country', 'defining_sample', 'defining_sample__owner')
        if a.defining_sample and a.defining_sample.image and a.defining_sample.status == 'published'
        and not a.defining_sample.deleted_at]
    if not areas:
        return None
    resolver = TaxonResolver()

    def rank(area):
        sample = area.defining_sample
        return (not _is_nudibranch(resolver, area.species), area.country.name != 'ישראל',
                -(sample.photographer_image_rating or 0), -(sample.audience_image_rating or 0), area.pk)
    area = min(areas, key=rank)
    sample = area.defining_sample
    return {
        'url': f'/observations/{sample.pk}/photo/',
        'name': name_html(area.species.scientific_name),
        'alt': area.species.scientific_name,
        'species_url': reverse('species-page', args=[area.slug]),
        'photographer': sample.photographer_display_name(lang) if sample.owner_id else '',
    }


def support_page(request):
    """/support/: why and how to support the project, one button to PayPal. 404 while the option is off."""
    from .i18n import get_lang
    if not is_enabled():
        raise Http404
    lang = get_lang(request)
    return render(request, 'observations/support.html', {
        'paypal_url': paypal_url(), 'photo': featured_photo(lang)})


def support_thank_you(request):
    """/support/thank-you/: PayPal's auto-return page. A thank-you only -- reaching it proves nothing."""
    response = render(request, 'observations/support_thank_you.html', {})
    response['X-Robots-Tag'] = 'noindex, follow'
    return response
