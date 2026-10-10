"""Catalog fixes after checking the Israeli species list against the species and taxonomy tables.

Every step is conditional and idempotent, so it is harmless on a database that lacks some of the rows.

1. "Okenia pellucida" and "Bermudella pellucida" were two rows of one species. WoRMS: Okenia pellucida is a
   superseded combination, the accepted name is Bermudella pellucida (Burn, 1967). The Okenia row goes (only
   when nothing refers to it), the Bermudella row stays.
2. The genus Cyerce belongs to Caliphyllidae (WoRMS), not Hermaeidae: a Caliphyllidae family row is created in
   the same order / superfamily, the genus moves to it, and every Cyerce species row follows.
3. Legacy species rows with empty order / family / superfamily (or the placeholder order "Not assigned") get
   them from the genus -> family -> order tables.
4. Hebrew names for the listed species (only where the name is empty; Caloria militaris is renamed to the
   name used in the list).
5. is_migrant is switched on for the listed species that also live in tropical regions. Never switched off.
"""
from django.db import migrations

HEBREW_NAMES = {
    'Hexabranchus sanguineus': 'רקדנית ספרדייה',
    'Felimare picta': 'חשופית קשוטה נאה',
    'Chromodoris quadricolor': 'כרומודורית מרובעת-פסים',
    'Hypselodoris pulchella': 'היפסלודורית יפה',
    'Gymnodoris ceylonica': 'שקופית ציילונית',
    'Gymnodoris citrina': 'שקופית צהובה',
    'Phyllidia multifaria': 'פילידיה מנוקדת',
    'Phyllidia varicosa': 'פילידיה וריקוזה',
    'Thecacera pennigera': 'תקצרה אטלנטית',
    'Jorunna rubescens': 'ז\'ורונה אדומה',
    'Flabellina affinis': 'חשופית אונות',
    'Caloria militaris': 'חשופית צבאית',
    'Coryphellina rubrolineata': 'חשופית סגולה',
    'Cratena peregrina': 'חשופית זר-צרובה',
    'Elysia crispata': 'אליסיה ירוקה',
    'Elysia marginata': 'אליסיה שולית',
    'Cyerce elegans': 'צ\'רצ\'ה אלגנטית',
    'Thuridilla bayeri': 'תורידילה באייר',
    'Aplysia dactylomela': 'ארנב ים זריז',
    'Aplysia fasciata': 'ארנב ים שחור',
    'Dolabella auricularia': 'דולברלה מנוקדת',
    'Berthellina citrina': 'תפוזית רעילה',
    'Pleurobranchus grandis': 'משבצון גדול',
    'Pleurobranchus albiguttatus': 'משבצון לבן-טיפות',
    'Pleurobranchus forskalii': 'משבצון פורסקל',
    'Chelidonura livida': 'דו-זנבית סגולה',
    'Chelidonura flavolobata': 'דו-זנבית צהובת-אונות',
    'Odontoglaja mosaica': 'דו-זנבית מרושתת',
    'Scyllaea pelagica': 'חשופית הסרגסום',
}
RENAMED = {'Caloria militaris': 'קלוריה צבאית'}  # old stored name that may be replaced

# Listed species that also occur in tropical regions (Indo-Pacific / Red Sea, or tropical Atlantic).
# Left out on purpose: Cratena peregrina and Flabellina affinis (temperate Atlantic-Mediterranean only,
# per WoRMS) and Bermudella pellucida (no tropical record found yet).
MIGRANTS = [
    'Hexabranchus sanguineus', 'Felimare picta', 'Chromodoris quadricolor', 'Hypselodoris pulchella',
    'Gymnodoris ceylonica', 'Gymnodoris citrina', 'Phyllidia multifaria', 'Phyllidia varicosa',
    'Thecacera pennigera', 'Jorunna rubescens', 'Caloria militaris', 'Coryphellina rubrolineata',
    'Elysia crispata', 'Elysia marginata', 'Cyerce elegans', 'Thuridilla bayeri',
    'Aplysia dactylomela', 'Aplysia fasciata', 'Dolabella auricularia', 'Berthellina citrina',
    'Pleurobranchus grandis', 'Pleurobranchus albiguttatus', 'Pleurobranchus forskalii',
    'Chelidonura livida', 'Chelidonura flavolobata', 'Odontoglaja mosaica', 'Scyllaea pelagica',
    'Goniobranchus pseudodecorus', 'Bursatella leachii',
]

LISTED = sorted(set(HEBREW_NAMES) | set(MIGRANTS))


def unify_pellucida(apps):
    Species = apps.get_model('observations', 'Species')
    keep = Species.objects.filter(scientific_name='Bermudella pellucida').first()
    old = Species.objects.filter(scientific_name='Okenia pellucida').first()
    if not keep or not old or keep.pk == old.pk:
        return
    if any(rel.related_model.objects.filter(**{rel.field.name: old}).exists() for rel in old._meta.related_objects):
        return
    # Anything the old row knew that the kept row lacks is carried over before it goes.
    for field in ('name_he', 'name_en', 'distribution', 'habitat', 'food', 'description_he', 'description_en', 'link'):
        if not getattr(keep, field) and getattr(old, field):
            setattr(keep, field, getattr(old, field))
    keep.save()
    old.delete()


def move_cyerce_to_caliphyllidae(apps):
    Family = apps.get_model('observations', 'TaxonFamily')
    Genus = apps.get_model('observations', 'TaxonGenus')
    Species = apps.get_model('observations', 'Species')
    genus = Genus.objects.filter(name='Cyerce').select_related('family').first()
    if not genus:
        return
    family = Family.objects.filter(name='Caliphyllidae', sub_family='').first()
    if not family:
        source = genus.family
        if not source or source.name != 'Hermaeidae':
            return
        family = Family.objects.create(
            name='Caliphyllidae', order_id=source.order_id, superfamily=source.superfamily,
            taxonomic_order=source.taxonomic_order)
    if genus.family_id != family.pk:
        genus.family = family
        genus.save()
    Species.objects.filter(genus='Cyerce').exclude(family='Caliphyllidae').update(family='Caliphyllidae')


def fill_taxonomy(apps):
    Species = apps.get_model('observations', 'Species')
    Genus = apps.get_model('observations', 'TaxonGenus')
    for sp in Species.objects.filter(scientific_name__in=LISTED):
        genus = Genus.objects.filter(name=sp.genus).select_related('family', 'family__order').first()
        family = genus.family if genus else None
        if not family:
            continue
        changed = []
        if not sp.family:
            sp.family = family.name; changed.append('family')
        if not sp.superfamily and family.superfamily:
            sp.superfamily = family.superfamily; changed.append('superfamily')
        if family.order_id and sp.order in ('', 'Not assigned'):
            sp.order = family.order.name; changed.append('order')
        if changed:
            sp.save(update_fields=changed)


def set_hebrew_names(apps):
    Species = apps.get_model('observations', 'Species')
    for name, hebrew in HEBREW_NAMES.items():
        qs = Species.objects.filter(scientific_name=name)
        qs.filter(name_he='').update(name_he=hebrew)
        if name in RENAMED:
            qs.filter(name_he=RENAMED[name]).update(name_he=hebrew)


def mark_migrants(apps):
    apps.get_model('observations', 'Species').objects.filter(scientific_name__in=MIGRANTS).update(is_migrant=True)


def forwards(apps, schema_editor):
    unify_pellucida(apps)
    move_cyerce_to_caliphyllidae(apps)
    fill_taxonomy(apps)
    set_hebrew_names(apps)
    mark_migrants(apps)


class Migration(migrations.Migration):
    dependencies = [('observations', '0063_home_text')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
