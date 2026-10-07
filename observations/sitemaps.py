"""Sitemap definitions for the public site (served at /sitemap.xml -- see config/urls.py).

Only ever lists pages that are actually reachable by an anonymous visitor: the homepage and
each species+area's own public page. Admin, login, profile and any other authenticated-only
page are simply never added here -- there is no separate "exclude" step needed for those.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .gallery_data import TaxonResolver, taxon_media
from .models import Sample, SpeciesArea, TaxonGenus


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
                trip__year__isnull=False, species_other='', site_other='', undetermined_variant=area.undetermined_variant,
            ).exists()
            if has_a_sample:
                live.append(area)
        return live

    def location(self, area):
        return reverse('species-page', args=[area.slug])


class GenusPageSitemap(Sitemap):
    """Each genus's dedicated public page (views.genus_page) -- only ones that are actually
    live. genus_page() 404s when either check below fails (no defining photo/video of its
    own, or no species actually shown under it), so the sitemap mirrors both."""
    protocol = 'https'
    changefreq = 'weekly'
    priority = 0.5

    def items(self):
        genera = list(TaxonGenus.objects.select_related('defining_sample'))
        live = [g for g in genera if any(taxon_media(g.defining_sample)[1:])]
        if not live:
            return []
        resolver = TaxonResolver()
        genus_ids_with_species = set()
        for area in SpeciesArea.objects.select_related('species', 'defining_sample'):
            defining = area.defining_sample
            if not defining or defining.status != 'published' or defining.deleted_at or not (defining.image or defining.video_url):
                continue
            _, _, genus_obj = resolver.resolve(area.species)
            if genus_obj:
                genus_ids_with_species.add(genus_obj.pk)
        return [g for g in live if g.pk in genus_ids_with_species]

    def location(self, genus):
        return reverse('genus-page', args=[genus.name])


class FamilyPageSitemap(Sitemap):
    """Each family's public page (views.family_page) that has at least one gallery species --
    the same condition under which family_page() answers 200 rather than 404. One entry per
    family name (rare sub_family rows of one family share its page)."""
    protocol = 'https'
    changefreq = 'weekly'
    priority = 0.5

    def items(self):
        from .views import gallery_areas
        return sorted({a.taxon_family.name for a in gallery_areas() if a.taxon_family})

    def location(self, name):
        return reverse('family-page', args=[name])


class OrderPageSitemap(Sitemap):
    """Each order group's public page (views.order_page, keyed by TaxonOrder pk) that has at
    least one gallery species -- order_page() 404s otherwise."""
    protocol = 'https'
    changefreq = 'weekly'
    priority = 0.5

    def items(self):
        from .views import gallery_areas
        return sorted({a.taxon_order.pk for a in gallery_areas() if a.taxon_order})

    def location(self, pk):
        return reverse('order-page', args=[pk])


SITEMAPS = {
    'static': StaticViewSitemap,
    'species': SpeciesPageSitemap,
    'genera': GenusPageSitemap,
    'families': FamilyPageSitemap,
    'orders': OrderPageSitemap,
}
