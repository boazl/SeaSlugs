"""Species/taxonomy resolution logic shared by the public gallery feed (config/views.py's
catalog.js builder) and server-rendered per-entity pages (this app's species/genus/family/
order/trip page views). Kept in one place so they can never disagree about which sample
defines a species+area, or how a species resolves to its curated genus/family/order.

config/views.py's catalog.js builder still has its own inline copy of this logic (written
before this module existed) -- it is deliberately left alone for now to avoid touching that
already-working, already-tested code path while the new per-entity pages are being built one
entity type at a time. Once all entity types have pages, that inline copy should be replaced
with calls into this module too.
"""
from .models import Sample, SpeciesArea, TaxonGenus, TaxonFamily, TaxonOrder, youtube_id


def area_samples(area):
    """The published observations that make up one gallery card / species page: the species'
    samples in the area's country + sea (and with its undetermined-variant letter). The same
    rule the catalog.js builder applies inline, so every page counts observations alike."""
    return Sample.objects.filter(
        kind=Sample.Kind.SPECIES, species_id=area.species_id, status='published', deleted_at__isnull=True,
        trip__country_id=area.country_id, trip__region__sea_id=area.sea_id, trip__year__isnull=False,
        species_other='', site_other='', undetermined_variant=area.undetermined_variant)


UNMARKED_SP_EPITHETS = ('', 'sp', 'sp.', 'spp', 'spp.')


def is_unmarked_sp(area):
    """A bare "Genus sp." with no number or letter (neither in the catalog name, e.g. "sp. 7" / "sp. A", nor as the
    area's undetermined_variant): an unidentified animal, never treated as the same species as another area's."""
    return not area.undetermined_variant and (area.species.species or '').strip() in UNMARKED_SP_EPITHETS


def same_species_areas(area):
    """The other SpeciesArea rows of the same species: the same catalog species and the same undetermined-variant
    letter; none for an unmarked "sp." (is_unmarked_sp). Mirrored by sameSpeciesKey in app.js."""
    if is_unmarked_sp(area):
        return SpeciesArea.objects.none()
    return SpeciesArea.objects.filter(species_id=area.species_id, undetermined_variant=area.undetermined_variant).exclude(pk=area.pk)


def same_species_totals():
    """{(species_id, undetermined_variant): [areas, observations]} over the live gallery cards -- the same numbers
    app.js counts from catalog.js (speciesAreaTotals): a card counts when its defining sample is showable and it
    has published observations of its own; an unmarked "sp." is left out (is_unmarked_sp). One query each."""
    from django.db.models import Count
    counts = {(r['species_id'], r['trip__country_id'], r['trip__region__sea_id'], r['undetermined_variant']): r['n']
              for r in Sample.objects.filter(
                  kind=Sample.Kind.SPECIES, species__isnull=False, status='published', deleted_at__isnull=True,
                  trip__year__isnull=False, species_other='', site_other='')
              .values('species_id', 'trip__country_id', 'trip__region__sea_id', 'undetermined_variant')
              .annotate(n=Count('pk'))}
    totals = {}
    for area in SpeciesArea.objects.select_related('species', 'defining_sample'):
        if is_unmarked_sp(area) or not any(taxon_media(area.defining_sample)[1:]):
            continue
        n = counts.get((area.species_id, area.country_id, area.sea_id, area.undetermined_variant), 0)
        if n:
            t = totals.setdefault((area.species_id, area.undetermined_variant), [0, 0])
            t[0] += 1
            t[1] += n
    return totals


def other_areas_tip(areas, observations, lang):
    """The yellow count's tooltip -- mirrors otherAreasTip in app.js."""
    if lang == 'en':
        return f'This species was observed in {areas} areas, {observations} observations in total'
    return f'המין נצפה ב-{areas} אזורים, {observations} תצפיות בסך הכול'


def annotate_same_species(areas, lang, totals=None):
    """Sets, on each species card (SpeciesArea), other_areas (the number of areas of the same species, 0 when it is
    in this area only) and other_areas_tip -- the card's count then turns yellow (_count_badge.html), as in the
    gallery."""
    totals = same_species_totals() if totals is None else totals
    for area in areas:
        t = None if is_unmarked_sp(area) else totals.get((area.species_id, area.undetermined_variant))
        area.other_areas = t[0] if t and t[0] > 1 else 0
        area.other_areas_tip = other_areas_tip(t[0], t[1], lang) if area.other_areas else ''
    return areas


def area_is_live(area):
    """An area is shown (card, link, page) only when its defining sample is publicly showable AND it still has
    observations of its own -- an area left behind when its trip moved to another country/sea is not."""
    return bool(any(taxon_media(area.defining_sample)[1:]) and area_samples(area).exists())


def annotate_area_cards(area):
    """Sets, on a gallery area shown as a card, what the card's observations contain:
    observation_count (the number the card shows), has_photo and has_video (any observation of the
    area has a photo / a video), so the card can carry both the photo mark and the video mark."""
    media = list(area_samples(area).values_list('image', 'video_url'))
    defining = area.defining_sample
    area.observation_count = len(media)
    area.has_photo = any(image for image, _ in media) or bool(defining and defining.image)
    area.has_video = any(video for _, video in media) or bool(defining and defining.video_url)
    if not (area.has_photo or area.has_video):
        area.has_photo = True


def taxon_media(defining_sample):
    """(thumbnail, image_url, video_id) for a defining_sample, or (None, None, None) if it
    isn't a valid, published, publicly-showable sample. Same rule the gallery feed uses."""
    if not defining_sample or defining_sample.status != 'published' or defining_sample.deleted_at:
        return None, None, None
    if not (defining_sample.image or defining_sample.video_url):
        return None, None, None
    thumbnail = f'/observations/{defining_sample.pk}/photo/' if defining_sample.image else defining_sample.thumbnail
    image_url = f'/observations/{defining_sample.pk}/photo/' if defining_sample.image else None
    video_id = youtube_id(defining_sample.video_url) if defining_sample.video_url else None
    return thumbnail, image_url, video_id


class TaxonResolver:
    """Precomputes the genus/family/order name lookups once, then resolves any Species to its
    curated (TaxonGenus, TaxonFamily, TaxonOrder) chain -- genus (the finest text field on
    Species) first, then family, then order, each falling back to a 'base' (blank sub_*) row
    when no more specific one matches. Build one instance per request/command run and reuse it
    across every species it needs to resolve, rather than re-querying per species."""
    def __init__(self):
        self.genus_by_name = {g.name: g for g in TaxonGenus.objects.select_related('family', 'family__order', 'defining_sample')}
        self.family_by_name = {f.name: f for f in TaxonFamily.objects.filter(sub_family='').select_related('order', 'defining_sample')}
        self.order_by_name = {o.name: o for o in TaxonOrder.objects.filter(sub_order='', superfamily='').select_related('defining_sample')}

    def resolve(self, species):
        # A handful of species have a blank genus column even though their scientific name
        # clearly starts with one (e.g. "Coryphellina iurmanovi" with genus=''). Fall back to
        # that leading word for RESOLUTION only -- it's never written back to Species.genus.
        genus_text = species.genus or (species.scientific_name.split()[0] if species.scientific_name else '')
        genus_obj = self.genus_by_name.get(genus_text) if genus_text else None
        family_obj = genus_obj.family if (genus_obj and genus_obj.family_id) else (
            self.family_by_name.get(species.family) if species.family else None)
        order_obj = family_obj.order if (family_obj and family_obj.order_id) else (
            self.order_by_name.get(species.order) if species.order else None)
        return order_obj, family_obj, genus_obj
