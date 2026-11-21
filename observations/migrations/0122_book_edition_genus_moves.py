"""Five undescribed species that the 3rd edition of Gosliner, Valdés & Behrens (2026) moves to another genus take
their 3rd-edition name (owner's decision on the book-edition issues #19, #26, #27, #28, #33; the site's order of
authority: WoRMS, then the 3rd edition, then the 2nd):

  Dermatobranchus sp. 6 -> Armina sp. 10          Haminoea sp. 5  -> Liloa sp. 9
  Marionia sp. 6        -> Marioniopsis sp. 11    Marionia sp. 24 -> Marioniopsis sp. 22
  Tritonia sp. 4        -> Marioniopsis sp. 6

In place, as in migration 0113: the species row, its observations (same rows, same transfer ids) and its gallery card
keep their rows, and the card keeps its published URL (slug). The name source becomes the 3rd edition; the texts say the
2nd edition's name; the 2nd-edition name stays as the species' name in that publication (SpeciesPublicationName). The
observations' genus follows; the genera's defining samples are repaired (migration 0071's rule). The issues are marked
"decided, waiting for a fix": catalogue done, photo label (and video when there is one) still to fix.
Safe in both environments: found by name, done only where still needed.
"""
import importlib
import re

from django.db import migrations

NSSI2 = 'NSSI-2 Gosliner, Valdés & Behrens, 2018'
NSSI3 = 'NSSI-3 Gosliner, Valdés & Behrens, 2026'
NSSI3_CITATION = ('Gosliner, T. M., Valdés, Á. & Behrens, D. W. (2026). Nudibranch & Sea Slug Identification – '
                  'Indo-Pacific, 3rd ed. New World Publications.')
WORMS = 'https://www.marinespecies.org/aphia.php?p=taxdetails&id={}'

# old name -> (new genus, new epithet, WoRMS id of the new genus, family, issue transfer id)
MOVES = {
    'Dermatobranchus sp. 6': ('Armina', 'sp. 10', 137677, 'Arminidae', '633ecd21-1452-5874-a986-59acbe403d67'),
    'Haminoea sp. 5': ('Liloa', 'sp. 9', 531576, 'Haminoeidae', 'e337d3bc-f74d-5bb0-838b-eea8f4639f71'),
    'Marionia sp. 6': ('Marioniopsis', 'sp. 11', 456341, 'Tritoniidae', 'f246c0fe-ab89-54b4-8578-3d20cfefe311'),
    'Marionia sp. 24': ('Marioniopsis', 'sp. 22', 456341, 'Tritoniidae', '768eff4c-0a69-5668-bb2f-8c460736f91b'),
    'Tritonia sp. 4': ('Marioniopsis', 'sp. 6', 456341, 'Tritoniidae', '03f55dba-8b25-55df-8ddd-07d704f54c67'),
}

DECISION = ('הוחלט (אפשרות א): המין מקבל את שם המהדורה השלישית — {new}; שם המהדורה השנייה ({old}) נשמר כשם בפרסום. '
            'בוצע בקטלוג (מיגרציה 0122): המין, התצפית והכרטיס נשארו באותן שורות ובאותה כתובת. נותר: לתקן את הכיתוב '
            'בתמונה{video}.')


def _texts(sp, old, new, genus, family):
    old_genus = old.split()[0]
    he_head = f'בשם {old}. '
    if he_head in sp.description_he and new not in sp.description_he:
        rest = sp.description_he.split(he_head, 1)[1]
        sp.description_he = (f'מין שטרם תואר רשמית מהסוג {genus} (משפחת {family}), המופיע במהדורה השלישית של ספר ההגדרה של '
                             f'Gosliner, Valdés ו־Behrens (2026) בשם {new}; במהדורה השנייה (2018) הופיע בשם {old}. {rest}')
    en_head = 'Indo-Pacific. '
    if en_head in sp.description_en and new not in sp.description_en.split(en_head, 1)[0]:
        rest = sp.description_en.split(en_head, 1)[1]
        sp.description_en = (f'An undescribed species of {genus} ({family}), listed as {new} in the 3rd edition of Gosliner, '
                             f'Valdés & Behrens (2026), Nudibranch & Sea Slug Identification – Indo-Pacific; the 2nd edition '
                             f'(2018) lists it as {old}. {rest}')
    sp.identification_he = re.sub(r'במהדורה השלישית (הוא )?הועבר לסוג [A-Za-z]+\.', f'במהדורה השנייה הופיע בסוג {old_genus}.',
                                  sp.identification_he)
    sp.identification_en = re.sub(r'The 3rd edition (moves it to|places it in) [A-Za-z]+\.',
                                  f'The 2nd edition placed it in {old_genus}.', sp.identification_en)


def _sources(text, worms_id):
    lines = [l for l in text.splitlines() if l.strip()]
    lines = [WORMS.format(worms_id) if 'marinespecies.org' in l else l for l in lines]
    if not any('3rd ed.' in l for l in lines):
        at = next((i for i, l in enumerate(lines) if '2nd ed.' in l), len(lines))
        lines.insert(at, NSSI3_CITATION)
    return '\n'.join(lines)


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    for old, (genus, epithet, worms_id, family, issue_id) in MOVES.items():
        new = f'{genus} {epithet}'
        sp = Species.objects.filter(scientific_name=old).first()
        if sp is None or Species.objects.filter(scientific_name=new).exists():
            continue
        old_genus = sp.genus
        sp.scientific_name, sp.genus, sp.species = new, genus, epithet
        if sp.accepted_genus == old_genus: sp.accepted_genus = genus
        if sp.accepted_species and sp.accepted_genus == genus: sp.accepted_species = epithet
        if sp.name_source in ('', NSSI2): sp.name_source = NSSI3
        _texts(sp, old, new, genus, family)
        sp.sources = _sources(sp.sources, worms_id)
        sp.save()
        samples = Sample.objects.filter(species_id=sp.pk)
        has_video = samples.exclude(video_url='').exists()
        samples.filter(genus=old_genus).update(genus=genus)
        issue = Issue.objects.filter(transfer_id=issue_id, status__in=('open', 'checking')).first()
        if issue is not None:
            if not issue.decision.strip():
                issue.decision = DECISION.format(new=new, old=old, video=' ובסרטון' if has_video else '')
            issue.status = 'decided'
            issue.action_catalog = 'done'
            issue.action_photo = issue.action_photo or 'needed'
            if has_video: issue.action_video = issue.action_video or 'needed'
            issue.save()
    importlib.import_module('observations.migrations.0071_defining_samples_one_level_below').fix(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [('observations', '0121_issue_order')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
