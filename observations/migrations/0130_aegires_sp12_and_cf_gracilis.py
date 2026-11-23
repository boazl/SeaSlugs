"""Owner's decisions:
- Issue #37: the species "Aegires sp. 7" (2nd edition of Gosliner, Valdés & Behrens) takes its 3rd-edition name, Aegires
  sp. 12 (pp. 28-29), with the 3rd edition as its source; the Romblon observation keeps cf. -- "Aegires cf. sp. 12
  (Source: NSSI-3 Gosliner, Valdés & Behrens, 2026)". Same row; the card keeps its slug. The texts name the 2nd edition's
  number; the 2nd-edition name stays as the species' name in that publication.
- Issue #38: observation #234 is "Thuridilla cf. gracilis".
Safe in both environments: found by name / transfer id, done only where still needed."""
from django.db import migrations

NSSI3 = 'NSSI-3 Gosliner, Valdés & Behrens, 2026'
AEGIRES_SAMPLE = '7363005f-e75b-41a8-9e5d-37cc6a736a48'
GRACILIS_SAMPLE = '450a994b-828f-4eeb-993a-055d62d5d8a3'
ISSUE_37 = 'c1211293-53e6-54f9-a840-f7f5506b5f6a'
ISSUE_38 = '4f19052c-d638-52be-8a82-cbdb298aa266'
DESC_HE = ('מין שטרם תואר רשמית מהסוג Aegires (משפחת Aegiridae), המופיע במהדורה השלישית של ספר ההגדרה של Gosliner, Valdés '
           'ו־Behrens (2026) בשם Aegires sp. 12; במהדורה השנייה (2018) הופיע בשם Aegires sp. 7, שבמהדורה השלישית משמש למין '
           'אחר (ירקרק־חום עם רשת קווים לבנים). חשופיות קטנות שגופן מכוסה בליטות, בלי כיס שאליו הזימים נסוגים.')
DESC_EN = ('An undescribed species of Aegires (Aegiridae), listed as Aegires sp. 12 in the 3rd edition of Gosliner, Valdés & '
           'Behrens (2026), Nudibranch & Sea Slug Identification – Indo-Pacific; the 2nd edition (2018) lists it as Aegires '
           'sp. 7, a name the 3rd edition uses for another species (greenish brown with a network of white lines). Small '
           'nudibranchs with a body covered in knobs and no pocket into which the gills retract.')
NOTES = [('המבנה תואם את Aegires sp. 7,', 'המבנה תואם את Aegires sp. 12,'),
         ('the shape matches Aegires sp. 7,', 'the shape matches Aegires sp. 12,')]
ADDED_37 = ("עדכון (מיגרציה 0130, החלטת הבעלים): המין נקרא עכשיו בשם המהדורה השלישית, Aegires sp. 12. הכיתוב בתמונה "
            "ובסרטון: 'Aegires cf. sp. 12' ובשורה השנייה '(Source: NSSI-3 Gosliner, Valdés & Behrens, 2026)'.")
ADDED_38 = "עדכון (מיגרציה 0130, החלטת הבעלים): #234 היא Thuridilla cf. gracilis; הכיתוב בתמונה: 'Thuridilla cf. gracilis' / '(Risbec, 1928)'."


def _add(issue, text):
    if issue is not None and text not in issue.decision:
        issue.decision = f'{issue.decision}\n{text}'.strip()
        issue.save()


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    sp = Species.objects.filter(scientific_name='Aegires sp. 7', name_source__startswith='NSSI-2').first()
    if sp is not None and not Species.objects.filter(scientific_name='Aegires sp. 12').exists():
        sp.scientific_name, sp.species, sp.name_source = 'Aegires sp. 12', 'sp. 12', NSSI3
        if sp.description_he.startswith('מין שטרם תואר רשמית מהסוג Aegires'): sp.description_he = DESC_HE
        if sp.description_en.startswith('An undescribed species of Aegires'): sp.description_en = DESC_EN
        if sp.full_species_name_with_order: sp.full_species_name_with_order = f'{sp.phylogenetic_order}-Aegires sp. 12  Gosliner, Valdés & Behrens, 2026'
        if sp.reference_author: sp.reference_author = 'Gosliner, Valdés & Behrens, 2026'
        sp.save()
        sample = Sample.objects.filter(transfer_id=AEGIRES_SAMPLE).first()
        if sample is not None:
            Sample.objects.filter(pk=sample.pk).update(note_he=sample.note_he.replace(*NOTES[0]),
                                                       note_en=sample.note_en.replace(*NOTES[1]))
        _add(Issue.objects.filter(transfer_id=ISSUE_37).first(), ADDED_37)
    gracilis = Sample.objects.filter(transfer_id=GRACILIS_SAMPLE, species__scientific_name='Thuridilla gracilis').first()
    if gracilis is not None and not gracilis.identification_qualifier:
        Sample.objects.filter(pk=gracilis.pk).update(identification_qualifier='cf.')
        _add(Issue.objects.filter(transfer_id=ISSUE_38).first(), ADDED_38)


class Migration(migrations.Migration):
    dependencies = [('observations', '0129_thuridilla_234_gracilis')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
