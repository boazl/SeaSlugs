"""Owner's decisions on two Phyllidia observations from Papua New Guinea (1998), checked against the 3rd edition of
Gosliner, Valdés & Behrens (2026), pp. 234 and 240:
- Issue #7: observation #498, filed as Phyllidia rueppelii (Red Sea only; yellow-orange mantle margin), is Phyllidia
  picta Pruvot-Fol, 1957 (western Pacific; blue network on black, single gold tubercles, blue crescents along the
  margin, gold rhinophores). The observation moves in place (same row and transfer id) and its card moves with it,
  keeping its slug (as in migration 0123); P. rueppelii stays in the catalogue.
- Issue #8: observation #502 matches Phyllidia alyta (four parallel black lines, white tubercles), but the species is
  known only from the Indian Ocean: it is marked "cf." with a note.
The issues become "decided": observation (and catalogue) done, photo label to fix. Safe in both environments, done once."""
import importlib

from django.db import migrations

PICTA_SAMPLE = '16e732cb-7d99-4ac3-b40f-4aa35657f265'
ALYTA_SAMPLE = '7fcf3c06-5e32-49fe-bca2-8be4dfc00904'
ISSUE_7 = '200e05c7-83ef-5b12-a4f9-a1820d15a33d'
ISSUE_8 = 'a9277a8c-2e9c-5edc-8bd1-62da85faeeda'
NOTE_HE = ('זיהוי לא ודאי (cf.): הדפוס תואם את Phyllidia alyta – ארבעה קווים שחורים מקבילים וגבשושיות לבנות – אבל המין ידוע '
           'רק מהאוקיינוס ההודי, ולא נמצאה רשומה שלו מפפואה גינאה החדשה.')
NOTE_EN = ('Uncertain identification (cf.): the pattern matches Phyllidia alyta – four parallel black lines and white '
           'tubercles – but the species is known only from the Indian Ocean, with no record from Papua New Guinea.')
DECISION_7 = ("הוחלט: #498 היא Phyllidia picta Pruvot-Fol, 1957 (מהדורה 3, עמ' 240). בוצע במיגרציה 0133 (התצפית והכרטיס עברו, "
              "אותה כתובת). נותר: הכיתוב בתמונה – 'Phyllidia picta Pruvot-Fol, 1957'.")
DECISION_8 = ("הוחלט: #502 נשארת Phyllidia alyta עם cf. והערה על התפוצה. בוצע במיגרציה 0133. נותר: הכיתוב בתמונה – "
              "'Phyllidia cf. alyta juv. Yonow, 1996'.")


def _decide(Issue, transfer, decision):
    issue = Issue.objects.filter(transfer_id=transfer, status__in=('open', 'checking')).first()
    if issue is None: return None
    if not issue.decision.strip(): issue.decision = decision
    issue.status = 'decided'
    issue.action_observation = 'done'
    issue.action_photo = issue.action_photo or 'needed'
    return issue


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    picta = Species.objects.filter(scientific_name='Phyllidia picta').first()
    sample = Sample.objects.filter(transfer_id=PICTA_SAMPLE, species__scientific_name='Phyllidia rueppelii').first()
    if picta is not None and sample is not None:
        old = sample.species_id
        area = SpeciesArea.objects.filter(species_id=old, defining_sample_id=sample.pk).first()
        if area is not None and not SpeciesArea.objects.filter(species_id=picta.pk, country_id=area.country_id, sea_id=area.sea_id,
                                                               undetermined_variant=area.undetermined_variant).exists():
            SpeciesArea.objects.filter(pk=area.pk).update(species_id=picta.pk)
        Sample.objects.filter(pk=sample.pk).update(species_id=picta.pk)
        issue = _decide(Issue, ISSUE_7, DECISION_7)
        if issue is not None:
            issue.corrected_species_id = picta.pk
            issue.action_catalog = 'done'
            issue.save()
    alyta = Sample.objects.filter(transfer_id=ALYTA_SAMPLE, identification_qualifier='').first()
    if alyta is not None:
        changes = {'identification_qualifier': 'cf.'}
        if not alyta.note_he: changes['note_he'] = NOTE_HE
        if not alyta.note_en: changes['note_en'] = NOTE_EN
        Sample.objects.filter(pk=alyta.pk).update(**changes)
        issue = _decide(Issue, ISSUE_8, DECISION_8)
        if issue is not None: issue.save()
    importlib.import_module('observations.migrations.0071_defining_samples_one_level_below').fix(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [('observations', '0132_tritonia_sp3_marioniopsis_sp23')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
