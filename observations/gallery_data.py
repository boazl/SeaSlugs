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
from .models import TaxonGenus, TaxonFamily, TaxonOrder, youtube_id


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
        self.order_by_name = {o.name: o for o in TaxonOrder.objects.filter(sub_order='').select_related('defining_sample')}

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
