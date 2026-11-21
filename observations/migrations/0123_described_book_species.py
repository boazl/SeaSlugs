"""Three species numbered by the 2nd edition of Gosliner, Valdés & Behrens (2018) that have since been described take
their WoRMS accepted name (owner's decision on issues #34, #35, #36; the photographs match the 3rd edition):

  Thecacera sp. 8       -> Thecacera pikachu Pola, Paz-Sedano, Martín, L. Warren, Noble & Martín-Hervás, 2026
                           (no catalogue row: the species row is renamed in place)
  Goniodoridella sp. 8  -> Murphydoris cobbi Paz-Sedano, Smirnoff, Candás, Gosliner & Pola, 2022 (catalogue row exists)
  Eubranchus sp. 26     -> Longibranchus putnami (Fernández-Simón & Moles, 2023): the catalogue row "Eubranchus putnami"
                           takes the accepted combination, and the genus Longibranchus Martynov & Korshunova, 2025 is
                           added to Eubranchidae

When the accepted name already has a row, the observations and the gallery card move to it (same observation rows and
transfer ids; the card keeps its row and slug, so no redirect), with the numbered row's texts (where the row has none),
its names in the guides (SpeciesPublicationName) and its guides; the numbered row stays, empty. The texts are rewritten
for a described species (who described it and where, the 2nd-edition name), the sources cite WoRMS, the original
description, and both editions. The genera's defining samples are repaired (migration 0071's rule). The issues become
"decided": catalogue and observation done, photo label (and video) to fix.
Safe in both environments: found by name, done only where still needed.
"""
import importlib

from django.db import migrations

NSSI3 = ('Gosliner, T. M., Valdés, Á. & Behrens, D. W. (2026). Nudibranch & Sea Slug Identification – Indo-Pacific, '
         '3rd ed. New World Publications.')
NSSI2 = ('Gosliner, T. M., Valdés, Á. & Behrens, D. W. (2018). Nudibranch & Sea Slug Identification – Indo-Pacific, '
         '2nd ed. New World Publications.')
WORMS = 'https://www.marinespecies.org/aphia.php?p=taxdetails&id={}'

COPY_FIELDS = ['description_he', 'description_en', 'identification_he', 'identification_en', 'similar_species_he',
               'similar_species_en', 'habitat', 'habitat_en', 'food', 'food_en', 'native_range_he', 'native_range_en',
               'distribution', 'size_from', 'size_to', 'size_max', 'depth_min', 'depth_max', 'phylogenetic_order']

MOVES = [
    dict(old='Thecacera sp. 8', row=None, new='Thecacera pikachu', genus='Thecacera', epithet='pikachu',
         author='Pola, Paz-Sedano, Martín, L. Warren, Noble & Martín-Hervás, 2026', worms=1883897,
         issue='7c69d96a-0b29-5049-95be-dd646155fe7c',
         head_he='חשופית ממשפחת Polyceridae שתוארה ב־2026 ממזרח טימור על ידי Pola ועמיתיה; במהדורה השנייה של ספר ההגדרה '
                 'של Gosliner, Valdés ו־Behrens (2018) הופיעה בשם Thecacera sp. 8, ובמהדורה השלישית (2026) בשמה הנוכחי.',
         head_en='A dorid of the family Polyceridae described in 2026 from East Timor by Pola and colleagues; the 2nd '
                 'edition of Gosliner, Valdés & Behrens (2018) lists it as Thecacera sp. 8, the 3rd edition (2026) by its '
                 'present name.',
         drop=['תואר ב־2026 בשם Thecacera pikachu. ', 'Described in 2026 as Thecacera pikachu. '],
         refs=['Pola, M., Paz-Sedano, S., Martín, P. G., Warren, L., Noble, K. & Martín-Hervás, M. D. R. (2026). The most '
               'wanted! Gorgeous, delicate and surprising: description of three new polycerid species (Mollusca, '
               'Heterobranchia) from East Timor. Zootaxa 5793(1): 193–217. https://doi.org/10.11646/zootaxa.5793.1.9']),
    dict(old='Goniodoridella sp. 8', row='Murphydoris cobbi', new='Murphydoris cobbi', genus='Murphydoris',
         epithet='cobbi', author='Paz-Sedano, Smirnoff, Candás, Gosliner & Pola, 2022', worms=1568877,
         issue='4a45d43f-086b-5e32-b814-5f7ae7d26f0c',
         head_he='חשופית זעירה ממשפחת Goniodorididae שתוארה ב־2022 על ידי Paz-Sedano ועמיתיה, במחקר הפילוגנטי הראשון של '
                 'הסוג Murphydoris, שהוסיף לו ארבעה מינים חדשים; במהדורה השנייה של ספר ההגדרה של Gosliner, Valdés '
                 'ו־Behrens (2018) הופיעה בשם Goniodoridella sp. 8.',
         head_en='A tiny dorid of the family Goniodorididae described in 2022 by Paz-Sedano and colleagues, in the first '
                 'phylogeny of the genus Murphydoris, which added four new species to it; the 2nd edition of Gosliner, '
                 'Valdés & Behrens (2018) lists it as Goniodoridella sp. 8.',
         drop=['תואר ב־2022 בשם Murphydoris cobbi. ', 'Described in 2022 as Murphydoris cobbi. '],
         refs=['Paz-Sedano, S., Smirnoff, D., Candás, M., Gosliner, T. M. & Pola, M. (2022). Rediscovering the overlooked '
               'genus Murphydoris (Nudibranchia: Goniodorididae): the first phylogeny and addition of four new species. '
               'Zoological Journal of the Linnean Society. https://doi.org/10.1093/zoolinnean/zlac002']),
    dict(old='Eubranchus sp. 26', row='Eubranchus putnami', new='Longibranchus putnami', genus='Longibranchus',
         epithet='putnami', author='(Fernández-Simón & Moles, 2023)', worms=1832557,
         issue='5b93184e-8fe7-58c8-aedf-a982c1e8c28c',
         head_he='אאולידית ממשפחת Eubranchidae שתוארה ב־2023 מאטול פאפו שבמלדיביים על ידי Fernández-Simón ו־Moles בשם '
                 'Eubranchus putnami, ובשם זה היא מופיעה גם במהדורה השלישית של ספר ההגדרה של Gosliner, Valdés ו־Behrens '
                 '(2026); ב־2025 העבירו אותה Martynov ו־Korshunova לסוג Longibranchus. במהדורה השנייה (2018) הופיעה בשם '
                 'Eubranchus sp. 26.',
         head_en='An aeolid of the family Eubranchidae described in 2023 from Faafu Atoll, Maldives, by Fernández-Simón & '
                 'Moles as Eubranchus putnami, the name the 3rd edition of Gosliner, Valdés & Behrens (2026) also uses; in '
                 '2025 Martynov & Korshunova moved it to Longibranchus. The 2nd edition (2018) lists it as Eubranchus sp. 26.',
         drop=['תואר ב־2023; במהדורה השלישית בשם Eubranchus putnami, וב־WoRMS בשם Longibranchus putnami. ',
               'Described in 2023; the 3rd edition calls it Eubranchus putnami, WoRMS Longibranchus putnami. '],
         refs=['Cunha, T. J., Fernández-Simón, J., Petrula, M., Giribet, G. & Moles, J. (2023). Photographic checklist, DNA '
               'barcoding, and new species of sea slugs and snails from the Faafu Atoll, Maldives (Gastropoda: '
               'Heterobranchia and Vetigastropoda). Diversity 15(2): 219. https://doi.org/10.3390/d15020219',
               'Martynov, A. & Korshunova, T. (2025). Hidden diversity of the North Pacific prompts reorganization of the '
               'taxonomic system. Moscow: Neptune.']),
]
NEW_GENERA = {'Longibranchus': 'Eubranchidae'}

DECISION = ('הוחלט: {new} (השם המקובל ב־WoRMS; התמונה תואמת את המהדורה השלישית). בוצע בקטלוג ובתצפיות (מיגרציה 0123): '
            'אותן שורות תצפית ואותה כתובת לכרטיס. נותר: לתקן את הכיתוב בתמונה{video}.')


def _rest(text, marker):
    return text.split(marker, 1)[1] if marker in text else ''


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    Publication = apps.get_model('observations', 'SpeciesPublicationName')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    TaxonGenus = apps.get_model('observations', 'TaxonGenus')
    TaxonFamily = apps.get_model('observations', 'TaxonFamily')
    for name, family in NEW_GENERA.items():
        fam = TaxonFamily.objects.filter(name=family).first()
        if fam and not TaxonGenus.objects.filter(name=name).exists():
            sibling = TaxonGenus.objects.filter(family=fam).exclude(taxonomic_order='').first()
            TaxonGenus.objects.create(name=name, family=fam, taxonomic_order=sibling.taxonomic_order if sibling else '')
    for m in MOVES:
        old = Species.objects.filter(scientific_name=m['old']).first()
        if old is None or not Sample.objects.filter(species_id=old.pk).exists():
            continue
        target = old
        if m['row']:
            target = (Species.objects.filter(scientific_name=m['new']).first()
                      or Species.objects.filter(scientific_name=m['row']).first())
            if target is None:
                continue
        old_genus = old.genus
        desc_rest_he = _rest(old.description_he, f'בשם {m["old"]}. ')
        desc_rest_en = _rest(old.description_en, 'Indo-Pacific. ')
        for field in COPY_FIELDS:
            if target.pk != old.pk and getattr(target, field) in (None, '') and getattr(old, field) not in (None, ''):
                setattr(target, field, getattr(old, field))
        target.scientific_name, target.genus, target.species = m['new'], m['genus'], m['epithet']
        target.accepted_genus, target.accepted_species = m['genus'], m['epithet']
        target.author, target.name_source = m['author'], ''
        target.description_he = f'{m["head_he"]} {desc_rest_he}'.strip()
        target.description_en = f'{m["head_en"]} {desc_rest_en}'.strip()
        for phrase in m['drop']:
            target.identification_he = target.identification_he.replace(phrase, '')
            target.identification_en = target.identification_en.replace(phrase, '')
        target.sources = '\n'.join([WORMS.format(m['worms'])] + m['refs'] + [NSSI3, NSSI2])
        target.save()
        if target.pk != old.pk:
            for pub in Publication.objects.filter(species_id=old.pk):
                if not Publication.objects.filter(species_id=target.pk, article_id=pub.article_id).exists():
                    pub.species_id = target.pk
                    pub.save()
            target.articles.add(*old.articles.all())
            SpeciesArea.objects.filter(species_id=old.pk).update(species_id=target.pk)
        samples = Sample.objects.filter(species_id=old.pk)
        has_video = samples.exclude(video_url='').exists()
        Sample.objects.filter(species_id=old.pk, genus=old_genus).update(genus=m['genus'])
        samples.update(species_id=target.pk)
        issue = Issue.objects.filter(transfer_id=m['issue'], status__in=('open', 'checking')).first()
        if issue is not None:
            if not issue.decision.strip():
                issue.decision = DECISION.format(new=f'{m["new"]} {m["author"]}', video=' ובסרטון' if has_video else '')
            issue.status = 'decided'
            issue.corrected_species_id = target.pk
            issue.action_catalog = 'done'
            issue.action_observation = 'done'
            issue.action_photo = issue.action_photo or 'needed'
            if has_video: issue.action_video = issue.action_video or 'needed'
            issue.save()
    importlib.import_module('observations.migrations.0071_defining_samples_one_level_below').fix(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [('observations', '0122_book_edition_genus_moves')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
