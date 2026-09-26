"""Sitemap definitions for the public site (served at /sitemap.xml -- see config/urls.py).

Only ever lists pages that are actually reachable by an anonymous visitor: the homepage and
each species+area's own public page. Admin, login, profile and any other authenticated-only
page are simply never added here -- there is no separate "exclude" step needed for those.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .gallery_data import taxon_media
from .models import Sample, SpeciesArea


class StaticViewSitemap(Sitemap):
    """The one page every visitor starts from."""
    protocol = 'https'
    changefreq = 'daily'
    priority = 0.8

    def items(self):
        return ['gallery']

    def location(self, item):
        return reverse(item)


class SpeciesPageSitemap(Sitemap):
    """Each species+area's dedicated public page (views.species_page) -- only ones that are
    actually live. species_page() 404s when either check below fails, so a stale/incomplete
    SpeciesArea row (a common transient state while data is still being curated -- see the
    Romblon/Anilao region mixup this app has already run into once) never ends up linked from
    the sitemap in the first place."""
    protocol = 'https'
    changefreq = 'weekly'
    priority = 0.6

    def items(self):
        areas = SpeciesArea.objects.exclude(slug='').exclude(slug__isnull=True).select_related(
            'species', 'country', 'sea', 'defining_sample')
        live = []
        for area in areas:
            thumbnail, image_url, video_id = taxon_media(area.defining_sample)
            if not (image_url or video_id):
                continue
            has_a_sample = Sample.objects.filter(
                kind=Sample.Kind.SPECIES, species_id=area.species_id, status=Sample.Status.PUBLISHED,
                deleted_at__isnull=True, trip__country_id=area.country_id, trip__region__sea_id=area.sea_id,
                trip__year__isnull=False, species_other='', site_other='',
            ).exists()
            if has_a_sample:
                live.append(area)
        return live

    def location(self, area):
        return reverse('species-page', args=[area.slug])


SITEMAPS = {
    'static': StaticViewSitemap,
    'species': SpeciesPageSitemap,
}
