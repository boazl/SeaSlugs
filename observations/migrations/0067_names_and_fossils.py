"""Names and fossils (the recommendations of taxonomy_names.xlsx, applied on 2026-10-11).

1. Cylindrobullinidae -- 13 fossil species in four genera that WoRMS (extant marine species only) does not
   know and that have no observations or samples here -- are removed together with their genera and the family.
2. Missing Hebrew / English names of the Nudibranchia sub-orders, the superfamilies, the families and the
   observed genera are filled with the suggested names. Only EMPTY name fields are filled; a name that is
   already there is never changed. The suggestions were written without a source and are meant to be reviewed
   (every one of them is editable in the admin).
"""
from django.db import migrations

SUBORDER_NAMES = {'Cladobranchia': ('קלדוברנכיה (חשופיות זימים מסועפים)', 'Cladobranch nudibranchs'),
 'Doridina': ('דורידינה (חשופיות דוריס)', 'Dorid nudibranchs')}
SUPERFAMILY_HE = {'Acteonoidea': 'קונחינניות – אקטאונואידאה',
 'Akeroidea': 'מגן ראש – אקרואידאה',
 'Aplysioidea': 'ארנבים – אפליסיואידאה',
 'Bathydoridoidea': 'בתידורידואידאה',
 'Bulloidea': 'מגן ראש – בולואידאה',
 'Cylichnoidea': 'מגן ראש – ציליכנואידאה',
 'Doridoxoidea': 'דורידוקסואידאה',
 'Haminoeoidea': 'מגן ראש – המינואואידאה',
 'Heterodoridoidea': 'חשופיות מגן – הטרודורידואידאה',
 'Newnesioidea': 'מגן ראש – ניונסיואידאה',
 'Oxynooidea': 'עלעליות – אוקסינואואידאה',
 'Philinoidea': 'מגן ראש – פילינואידאה',
 'Plakobranchoidea': 'עלעליות – פלקוברנכואידאה',
 'Pleurobranchoidea': 'ימני זים – פלאורוברנכואידאה',
 'Runcinoidea': 'חינניות מקצוע – רונצינואידאה',
 'Umbraculoidea': 'מטריה – אומברקולואידאה'}
SUPERFAMILY_EN = {'Acteonoidea': 'Acteon snails',
 'Aeolidioidea': 'Aeolid nudibranchs',
 'Akeroidea': 'Akera bubble snails',
 'Aplysioidea': 'Sea hares',
 'Arminoidea': 'Armina nudibranchs',
 'Bathydoridoidea': 'Deep-sea dorid nudibranchs',
 'Bulloidea': 'Bubble snails',
 'Chromodoridoidea': 'Chromodorid dorid nudibranchs',
 'Cylichnoidea': 'Barrel bubble snails',
 'Dendronotoidea': 'Dendronotid nudibranchs',
 'Doridoidea': 'Doridid dorid nudibranchs',
 'Doridoxoidea': 'Doridoxa nudibranchs',
 'Embletonioidea': 'Embleton nudibranchs',
 'Fionoidea': 'Fionoid nudibranchs (Flabellina and relatives)',
 'Haminoeoidea': 'Haminoeid bubble snails',
 'Heterodoridoidea': 'Heterodoris nudibranchs',
 'Newnesioidea': 'Newnesia bubble snails',
 'Onchidoridoidea': 'Onchidorid dorid nudibranchs (spiny dorids)',
 'Oxynooidea': 'Oxynoid sap-sucking slugs',
 'Philinoidea': 'Headshield slugs and canoe bubbles',
 'Phyllidioidea': 'Phyllidioid dorid nudibranchs',
 'Plakobranchoidea': 'Sap-sucking sea slugs',
 'Pleurobranchoidea': 'Side-gilled sea slugs',
 'Polyceroidea': 'Polycerid dorid nudibranchs',
 'Proctonotoidea': 'Proctonotid nudibranchs',
 'Runcinoidea': 'Runcinid slugs',
 'Tritonioidea': 'Tritoniid nudibranchs',
 'Umbraculoidea': 'Umbrella slugs'}
FAMILY_HE = {'Abronicidae': 'אברוניצידים',
 'Acteonidae': 'אקטאונידים',
 'Actinocyclidae': 'אקטינוציקלידים',
 'Aegiridae': 'אגירידים',
 'Aeolidiidae': 'אאוליידידים',
 'Aglajidae': 'אגלאידים',
 'Akeridae': 'אקרידים',
 'Akiodorididae': 'אקיודורידידים',
 'Alacuppidae': 'אלקופידים',
 'Antarctophilinidae': 'אנטארקטופילינידים',
 'Apataidae': 'אפטאידים',
 'Aplustridae': 'אפלוסטרידים',
 'Aplysiidae': 'ארנבות ים',
 'Arminidae': 'ארמינידים',
 'Babakinidae': 'בבקינידים',
 'Bathydorididae': 'בתידורידידים',
 'Bornellidae': 'בורנלידים',
 'Bullidae': 'בולידים',
 'Cadlinellidae': 'קדלינלידים',
 'Cadlinidae': 'קדלינידים',
 'Caliphyllidae': 'קליפילידים',
 'Calycidorididae': 'קליצידורידידים',
 'Chromodorididae': 'זריות',
 'Colinatydidae': 'קולינטידידים',
 'Colpodaspididae': 'קולפודספידידים',
 'Corambidae': 'קורמבידים',
 'Costasiellidae': 'קוסטסיילידים',
 'Cumanotidae': 'קומנוטידים',
 'Curnonidae': 'קורנונידים',
 'Cuthonellidae': 'קותונלידים',
 'Cuthonidae': 'קותונידים',
 'Cylichnidae': 'ציליכנידים',
 'Cylindrobullidae': 'ציליינדרובולידים',
 'Dendrodorididae': 'דנדרודורידידים',
 'Dendronotidae': 'דנדרונוטידים',
 'Diaphanidae': 'דיאפנידים',
 'Dironidae': 'דירונידים',
 'Discodorididae': 'דיסקודורידידים',
 'Dorididae': 'דורידידים',
 'Doridomorphidae': 'דורידומורפידים',
 'Doridoxidae': 'דורידוקסידים',
 'Dotidae': 'דוטידים',
 'Embletoniidae': 'אמבלטוניידים',
 'Eoscaphandridae': 'אאוסקפנדרידים',
 'Eubranchidae': 'אאוברנכידים',
 'Facelinidae': 'פצלינידים',
 'Fionidae': 'פיונידים',
 'Flabellinidae': 'פלבלינידים',
 'Flabellinopsidae': 'פלבלינופסידים',
 'Gastropteridae': 'גסטרופטרידים',
 'Glaucidae': 'גלאוקידים',
 'Goniaeolididae': 'גוניאאוליידידים',
 'Goniodorididae': 'גוניודורידידים',
 'Haminoeidae': 'המינואידים',
 'Hancockiidae': 'הנקוקידים',
 'Hermaeidae': 'הרמאידים',
 'Heroidae': 'הרואידים',
 'Heterodorididae': 'הטרודורידידים',
 'Hexabranchidae': 'הקסברנכידים',
 'Ilbiidae': 'אילבידים',
 'Janolidae': 'ינולידים',
 'Juliidae': 'יוליידים',
 'Laonidae': 'לאונידים',
 'Lemindidae': 'למינדידים',
 'Limapontiidae': 'לימפונטידים',
 'Lomanotidae': 'לומנוטידים',
 'Madrellidae': 'מדרלידים',
 'Magallanidae': 'מגלנידים',
 'Mandeliidae': 'מנדלידים',
 'Mnestiidae': 'מנסטידים',
 'Murmaniidae': 'מורמנידים',
 'Myrrhinidae': 'מירינידים',
 'Newnesiidae': 'ניונסידים',
 'Notaeolidiidae': 'נוטאאוליידידים',
 'Notodiaphanidae': 'נוטודיאפנידים',
 'Onchidorididae': 'אונכידורידידים',
 'Oxynoidae': 'אוקסינואידים',
 'Philinidae': 'פילינידים',
 'Philinoglossidae': 'פילינוגלוסידים',
 'Philinorbidae': 'פילינורבידים',
 'Phyllidiidae': 'פילידיידים',
 'Phylliroidae': 'פילירואידים',
 'Pinufiidae': 'פינופידים',
 'Piseinotecidae': 'פיסיינוטציים',
 'Plakobranchidae': 'פלקוברנכידים',
 'Pleurobranchaeidae': 'פלאורוברנכאידים',
 'Pleurobranchidae': 'פלאורוברנכידים',
 'Pleurolidiidae': 'פלאורוליידיים',
 'Polyceridae': 'פוליצרידים',
 'Proctonotidae': 'פרוקטונוטידים',
 'Pseudovermidae': 'פסאודוורמידים',
 'Quijotidae': 'קיחוטידים',
 'Retusidae': 'רטוסידים',
 'Rhizoridae': 'ריזורידים',
 'Runcinidae': 'רונצינידים',
 'Samlidae': 'סמלידים',
 'Scaphandridae': 'סקפנדרידים',
 'Scyllaeidae': 'סקילאידים',
 'Showajidaiidae': 'שואג׳ידאידים',
 'Tergipedidae': 'טרגיפדידים',
 'Tethydidae': 'תטידידים',
 'Tornatinidae': 'טורנטינידים',
 'Trinchesiidae': 'טרינצ׳זידים',
 'Tritoniidae': 'טריטונידים',
 'Tylodinidae': 'טילודינידים',
 'Umbraculidae': 'אומברקולידים',
 'Volvatellidae': 'וולבטלידים',
 'Xenocratenidae': 'קסנוקרטנידים'}
FAMILY_EN = {'Acteonidae': 'Acteon snails',
 'Aegiridae': 'Aegires dorids',
 'Aeolidiidae': 'Aeolid nudibranchs',
 'Aglajidae': 'Aglajid headshield slugs',
 'Akeridae': 'Akera bubble snails',
 'Aplustridae': 'Aplustrid bubble snails',
 'Aplysiidae': 'Sea hares',
 'Arminidae': 'Armina nudibranchs',
 'Babakinidae': 'Babakina nudibranchs',
 'Bathydorididae': 'Deep-sea dorids',
 'Bornellidae': 'Bornellid nudibranchs',
 'Bullidae': 'Bubble snails',
 'Cadlinellidae': 'Cadlinella nudibranchs',
 'Cadlinidae': 'Cadlina nudibranchs',
 'Caliphyllidae': 'Caliphyllid sap-sucking slugs',
 'Chromodorididae': 'Chromodorid nudibranchs',
 'Colpodaspididae': 'Colpodaspid bubble snails',
 'Corambidae': 'Corambid dorids',
 'Costasiellidae': 'Costasiellid sap-sucking slugs',
 'Cuthonidae': 'Cuthonid nudibranchs',
 'Cylichnidae': 'Barrel bubble snails',
 'Cylindrobullidae': 'Cylindrobulla sap-sucking slugs',
 'Dendrodorididae': 'Dendrodorid nudibranchs',
 'Dendronotidae': 'Dendronotid nudibranchs',
 'Diaphanidae': 'Diaphanid bubble snails',
 'Discodorididae': 'Discodorid nudibranchs',
 'Dorididae': 'Doridid nudibranchs',
 'Dotidae': 'Doto nudibranchs',
 'Embletoniidae': 'Embleton nudibranchs',
 'Eubranchidae': 'Eubranchid nudibranchs',
 'Facelinidae': 'Facelinid nudibranchs',
 'Fionidae': 'Fionid nudibranchs',
 'Flabellinidae': 'Flabellinid nudibranchs',
 'Gastropteridae': 'Gastropterid sea slugs',
 'Glaucidae': 'Blue dragons and sea swallows',
 'Goniodorididae': 'Goniodorid nudibranchs',
 'Haminoeidae': 'Haminoeid bubble snails',
 'Hermaeidae': 'Hermaeid sap-sucking slugs',
 'Hexabranchidae': 'Spanish dancers',
 'Janolidae': 'Janolid nudibranchs',
 'Juliidae': 'Bivalved sea slugs',
 'Limapontiidae': 'Limapontiid sap-sucking slugs',
 'Myrrhinidae': 'Myrrhinid nudibranchs',
 'Onchidorididae': 'Onchidorid dorids (spiny dorids)',
 'Oxynoidae': 'Oxynoid sap-sucking slugs',
 'Philinidae': 'Philinid headshield slugs',
 'Phyllidiidae': 'Phyllidiid nudibranchs',
 'Phylliroidae': 'Phylliroid sea slugs',
 'Piseinotecidae': 'Piseinotecid nudibranchs',
 'Plakobranchidae': 'Plakobranchid sap-sucking slugs',
 'Pleurobranchaeidae': 'Pleurobranchaeid sea slugs',
 'Pleurobranchidae': 'Side-gilled sea slugs',
 'Polyceridae': 'Polycerid nudibranchs',
 'Retusidae': 'Retusid bubble snails',
 'Runcinidae': 'Runcinid slugs',
 'Samlidae': 'Samlid nudibranchs',
 'Scaphandridae': 'Scaphandrid bubble snails',
 'Scyllaeidae': 'Scyllaeid nudibranchs',
 'Tergipedidae': 'Tergipedid nudibranchs',
 'Tethydidae': 'Tethydid nudibranchs',
 'Tornatinidae': 'Tornatinid bubble snails',
 'Trinchesiidae': 'Trinchesiid nudibranchs',
 'Tritoniidae': 'Tritoniid nudibranchs',
 'Tylodinidae': 'Tylodinid sea slugs',
 'Umbraculidae': 'Umbrella slugs',
 'Volvatellidae': 'Volvatellid sap-sucking slugs'}
GENUS_HE = {'Biuve': 'ביובה',
 'Bornella': 'בורנלה',
 'Colpodaspis': 'קולפודספיס',
 'Cyerce': 'קיירקה',
 'Dendrodoris': 'מתנת עץ',
 'Diniatys': 'דיניאטיס',
 'Doridomorpha': 'דורידומורפה',
 'Ercolania': 'ארקולניה',
 'Facelina': 'פצלינה',
 'Haminoea': 'המינואה',
 'Kabeiro': 'קבירו',
 'Kaloplocamus': 'תלתל יפה',
 'Lamprohaminoea': 'המינואה זוהרת',
 'Marioniopsis': 'דמוית מריוניה',
 'Micromelo': 'מיקרומלו',
 'Murphydoris': 'מרפידוריס',
 'Noumeaella': 'נומיאלה',
 'Phanerophthalmus': 'עין גלויה',
 'Phestilla': 'פסטילה',
 'Phyllidia': 'עלויה',
 'Stiliger': 'סטיליגר',
 'Stylocheilus': 'סטילוכיילוס'}


def fill(queryset_for, mapping, field):
    for name, value in mapping.items():
        row = queryset_for(name)
        if row is not None and not getattr(row, field):
            setattr(row, field, value)
            row.save(update_fields=[field])


def forwards(apps, schema_editor):
    Order = apps.get_model('observations', 'TaxonOrder')
    Family = apps.get_model('observations', 'TaxonFamily')
    Genus = apps.get_model('observations', 'TaxonGenus')
    Species = apps.get_model('observations', 'Species')
    Superfamily = apps.get_model('observations', 'TaxonSuperfamily')

    family = Family.objects.filter(name='Cylindrobullinidae', sub_family='').first()
    if family is not None:
        genera = Genus.objects.filter(family=family)
        names = list(genera.values_list('name', flat=True))
        fossils = Species.objects.filter(genus__in=names, family='Cylindrobullinidae', areas__isnull=True, sample__isnull=True)
        fossils.delete()
        if not Species.objects.filter(genus__in=names).exists():
            genera.delete()
            family.delete()

    for sub, (he, en) in SUBORDER_NAMES.items():
        row = Order.objects.filter(name='Nudibranchia', sub_order=sub).first()
        if row is not None:
            if not row.name_he: row.name_he = he
            if not row.name_en: row.name_en = en
            row.save(update_fields=['name_he', 'name_en'])
    sf = lambda n: Superfamily.objects.filter(name=n).first()
    fam = lambda n: Family.objects.filter(name=n, sub_family='').first()
    gen = lambda n: Genus.objects.filter(name=n).first()
    fill(sf, SUPERFAMILY_HE, 'name_he')
    fill(sf, SUPERFAMILY_EN, 'name_en')
    fill(fam, FAMILY_HE, 'name_he')
    fill(fam, FAMILY_EN, 'name_en')
    fill(gen, GENUS_HE, 'name_he')


class Migration(migrations.Migration):

    dependencies = [
        ('observations', '0066_worms_family_cleanup'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
