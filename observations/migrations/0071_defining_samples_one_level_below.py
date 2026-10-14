"""A taxonomy row's defining sample is an observation one level below it (observations/defining.py):

- species in an area -> a species-kind observation of that species in that area
- genus              -> a species-kind observation of a species of the genus
- family             -> a genus-kind observation of a genus of the family
- order / sub-order / superfamily -> a family-kind observation of a family in it

When the level directly below has no observation with a photo or video, the next level down is
used (an order with no family observation takes genus observations, then species ones).

Every row whose current value doesn't fit (or is empty) gets the first that fits: the newest
published, active one with a photo or video, else the newest active one; none if nothing fits.
An order / family / genus page keeps showing its own-kind observation first (defining.display_sample).
"""
from django.db import migrations


def _shown(sample):
    return sample.status == 'published' and (sample.image or sample.video_url)


def fix(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    TaxonGenus = apps.get_model('observations', 'TaxonGenus')
    TaxonFamily = apps.get_model('observations', 'TaxonFamily')
    TaxonOrder = apps.get_model('observations', 'TaxonOrder')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    active = Sample.objects.filter(deleted_at__isnull=True)

    def apply(row, levels):
        # the first level (going down) with an observation that shows something, else the first with any
        lists = [list(qs.order_by('-created_at', '-pk')) for qs in levels]
        chosen = next((l for l in lists if any(_shown(s) for s in l)), None) or next((l for l in lists if l), [])
        if row.defining_sample_id and any(s.pk == row.defining_sample_id and _shown(s) for s in chosen):
            return
        shown = [s for s in chosen if _shown(s)]
        picked = (shown or chosen or [None])[0]
        if row.defining_sample_id and any(s.pk == row.defining_sample_id for s in chosen) and not shown:
            return
        if (picked.pk if picked else None) != row.defining_sample_id:
            type(row).objects.filter(pk=row.pk).update(defining_sample=picked)

    species_of = lambda genera: active.filter(kind='species', species__genus__in=list(genera))
    for area in SpeciesArea.objects.all():
        apply(area, [active.filter(kind='species', species_id=area.species_id, trip__country_id=area.country_id,
                                   trip__region__sea_id=area.sea_id, undetermined_variant=area.undetermined_variant)])
    for genus in TaxonGenus.objects.all():
        apply(genus, [species_of([genus.name])])
    for family in TaxonFamily.objects.all():
        genera = list(TaxonGenus.objects.filter(family_id=family.pk).values_list('name', flat=True))
        apply(family, [active.filter(kind='genus', genus__in=genera), species_of(genera)])
    for row in TaxonOrder.objects.all():
        families = TaxonFamily.objects.filter(order__name=row.name)
        if row.sub_order: families = families.filter(order__sub_order=row.sub_order)
        if row.superfamily: families = families.filter(superfamily=row.superfamily)
        names = list(families.values_list('name', flat=True))
        genera = list(TaxonGenus.objects.filter(family__name__in=names).values_list('name', flat=True))
        apply(row, [active.filter(kind='family', family__in=names), active.filter(kind='genus', genus__in=genera), species_of(genera)])


class Migration(migrations.Migration):
    dependencies = [('observations', '0070_sample_gallery_source')]
    operations = [migrations.RunPython(fix, migrations.RunPython.noop)]
