"""Which observations may be a taxonomy row's defining sample ("דגימה מגדירה"), one level below it.

The defining sample is the photo a taxon page / gallery card falls back to when the taxon has no
observation of its own kind (an order-, family- or genus-kind observation of that taxon):

- a species in an area (SpeciesArea)       -> a species-kind observation of that species in that area
- a genus (TaxonGenus)                       -> a species-kind observation of a species of that genus
- a family (TaxonFamily)                     -> a genus-kind observation of a genus of that family
- an order / sub-order / superfamily row     -> a family-kind observation of a family in it

When the level directly below has no observation with a photo or video, the next level down is
used (an order with no family observation takes genus observations, then species ones).

choices() is the list the admin offers (alphabetical, with a search box); first_choice() is "the first one that
fits" -- the newest published one with a photo or video, else the newest at all -- used to
replace a value that doesn't fit (repair()) and to fill an empty one.
"""
from django.db.models import Q


def _models():
    from . import models
    return models


def _levels(row):
    """The candidate querysets for `row`, from the level directly below it downwards."""
    m = _models(); Sample = m.Sample
    active = Sample.objects.filter(deleted_at__isnull=True).select_related('species', 'trip')
    if isinstance(row, m.SpeciesArea):
        return [active.filter(kind=Sample.Kind.SPECIES, species_id=row.species_id, trip__country_id=row.country_id,
                              trip__region__sea_id=row.sea_id, undetermined_variant=row.undetermined_variant)]
    species_of = lambda genera: active.filter(kind=Sample.Kind.SPECIES, species__genus__in=list(genera))
    if isinstance(row, m.TaxonGenus):
        return [species_of([row.name])]
    if isinstance(row, m.TaxonFamily):
        genera = list(m.TaxonGenus.objects.filter(family_id=row.pk).values_list('name', flat=True))
        return [active.filter(kind=Sample.Kind.GENUS, genus__in=genera), species_of(genera)]
    if isinstance(row, m.TaxonOrder):
        families = families_of_order_row(row)
        genera = list(m.TaxonGenus.objects.filter(family__name__in=families).values_list('name', flat=True))
        return [active.filter(kind=Sample.Kind.FAMILY, family__in=families),
                active.filter(kind=Sample.Kind.GENUS, genus__in=genera), species_of(genera)]
    return []


def _shows_something(qs):
    return qs.filter(status='published').filter(~Q(image='') | ~Q(video_url='')).exists()


def choices(row):
    """The active observations that may define `row`, in alphabetical order (as the admin lists them):
    those of the level directly below it -- and when that level has no observation with a photo or
    video, of the next level down, and so on (an order with no family observation takes genus
    observations, then species ones)."""
    levels = _levels(row)
    if not levels:
        return _models().Sample.objects.none()
    chosen = next((qs for qs in levels if _shows_something(qs)), None) or next((qs for qs in levels if qs.exists()), levels[0])
    # alphabetical by the taxon name the select shows, newest first within one name
    return chosen.order_by('species__scientific_name', 'genus', 'family', '-created_at', '-pk')


def families_of_order_row(row):
    """Names of the families in an order / sub-order / superfamily row."""
    m = _models()
    families = m.TaxonFamily.objects.filter(order__name=row.name)
    if row.sub_order: families = families.filter(order__sub_order=row.sub_order)
    if row.superfamily: families = families.filter(superfamily=row.superfamily)
    return set(families.values_list('name', flat=True))


def first_choice(row):
    candidates = sorted(choices(row), key=lambda s: (s.created_at, s.pk), reverse=True)   # newest first
    shown = [s for s in candidates if _shown(s)]
    return (shown or candidates or [None])[0]


def fits(row, sample):
    return sample is not None and choices(row).filter(pk=sample.pk).exists()


def _shown(sample):
    return sample is not None and sample.status == 'published' and not sample.deleted_at and bool(sample.image or sample.video_url)


def repair(row):
    """Replace a defining sample that doesn't fit `row` -- or a missing one, or one that fits but
    shows nothing while another would -- with the first that fits. True when the row changed."""
    current = row.defining_sample if row.defining_sample_id else None
    current_fits = current is not None and fits(row, current)
    if current_fits and _shown(current): return False
    picked = first_choice(row)
    if current_fits and not _shown(picked): return False
    if (picked.pk if picked else None) == row.defining_sample_id: return False
    type(row).objects.filter(pk=row.pk).update(defining_sample=picked)
    row.defining_sample = picked
    return True


def rows_affected_by(sample):
    """The taxonomy rows whose defining sample may change when `sample` changes."""
    m = _models(); Sample = m.Sample
    rows = []
    for model in (m.TaxonOrder, m.TaxonFamily, m.TaxonGenus, m.SpeciesArea):
        rows += list(model.objects.filter(defining_sample_id=sample.pk))
    # every row above the sample can take it once the levels between are empty
    genus_name = sample.species.genus if sample.kind == Sample.Kind.SPECIES and sample.species_id else sample.genus if sample.kind == Sample.Kind.GENUS else ''
    family_rows = []
    if genus_name:
        genera = list(m.TaxonGenus.objects.filter(name=genus_name).select_related('family', 'family__order'))
        if sample.kind == Sample.Kind.SPECIES: rows += genera
        family_rows = [g.family for g in genera if g.family_id]
    elif sample.kind == Sample.Kind.FAMILY and sample.family:
        family_rows = list(m.TaxonFamily.objects.filter(name=sample.family).select_related('order'))
    if sample.kind in (Sample.Kind.SPECIES, Sample.Kind.GENUS): rows += family_rows
    for family in family_rows:
        if family.order_id:
            rows += [r for r in m.TaxonOrder.objects.filter(name=family.order.name)
                     if (not r.sub_order or r.sub_order == family.order.sub_order) and (not r.superfamily or r.superfamily == family.superfamily)]
    seen, out = set(), []
    for row in rows:
        key = (type(row), row.pk)
        if key not in seen: seen.add(key); out.append(row)
    return out


def own_kind_samples():
    """{(kind, name): newest published, active order/family/genus-kind observation with a photo or
    video} -- what a taxon page shows before falling back to its defining sample."""
    Sample = _models().Sample
    out = {}
    for sample in Sample.objects.filter(kind__in=(Sample.Kind.ORDER, Sample.Kind.FAMILY, Sample.Kind.GENUS), status='published',
                                        deleted_at__isnull=True).order_by('-created_at', '-pk'):
        name = {'order': sample.order, 'family': sample.family, 'genus': sample.genus}[sample.kind]
        if name and (sample.image or sample.video_url): out.setdefault((sample.kind, name), sample)
    return out


def display_sample(row, own=None):
    """The observation whose media a taxon row shows: its own-kind observation, else its defining sample."""
    m = _models()
    own = own_kind_samples() if own is None else own
    if isinstance(row, m.TaxonGenus): key = ('genus', row.name)
    elif isinstance(row, m.TaxonFamily): key = ('family', row.name) if not row.sub_family else None
    elif isinstance(row, m.TaxonOrder): key = ('order', row.name) if not row.sub_order and not row.superfamily else None
    else: key = None
    return own.get(key) if key and own.get(key) else (row.defining_sample if row.defining_sample_id else None)
