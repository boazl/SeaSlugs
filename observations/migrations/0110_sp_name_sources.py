"""The source of the name of every undescribed "sp." species in the gallery (Species.name_source), shown on the site as
"(Source: ...)" where a described species shows its author:
- Thuridilla sp. 2 and Thuridilla sp. 4 (2021): numbered in Martín-Hervás et al. 2021, "A molecular phylogeny of
  Thuridilla ..." (Cladistics), which numbers Thuridilla sp. 1-10 -- not the book's numbering.
- the species whose number is the one of the 3rd edition of Gosliner, Valdés & Behrens (2026): NSSI-3;
- the species whose number is the one of the 2nd edition (2018), renumbered or not found in the 3rd: NSSI-2
  (see migrations 0106 / 0107 for each species's pages in both editions).
Species marked with a letter (sp. A, sp. B) are the owner's own marks and get no source; Thuridilla sp. 7 and
Coryphellina sp. 1 are left empty until their source is checked.
The identification-issues row about the Thuridilla numbering (migration 0106) is corrected accordingly.
Safe in both environments: a species is found by scientific name and a source is written only where it is still empty;
the issue text is replaced only while it is still the original one.
"""
import uuid
from importlib import import_module

from django.db import migrations
from django.utils import timezone

NSSI3 = 'NSSI-3 Gosliner, Valdés & Behrens, 2026'
NSSI2 = 'NSSI-2 Gosliner, Valdés & Behrens, 2018'
MARTIN_HERVAS = 'Martín-Hervás et al., 2021'
SOURCES = {
    **{name: NSSI3 for name in (
        'Eubranchus sp. 2', 'Facelina sp. 4', 'Favorinus sp. 10', 'Haminoeid sp. 2', 'Nembrotha sp. 5', 'Noumeaella sp. 3',
        'Phyllodesmium sp. 4', 'Phyllodesmium sp. 6', 'Tenellia sp. 18', 'Tenellia sp. 29', 'Tenellia sp. 34',
        'Tenellia sp. 39', 'Tenellia sp. 65', 'Tenellia sp. 71')},
    **{name: NSSI2 for name in (
        'Aegires sp. 7', 'Aegires sp. 8', 'Atagema sp. 12', 'Atagema sp. 13', 'Dermatobranchus sp. 17', 'Dermatobranchus sp. 6',
        'Eubranchus sp. 15', 'Eubranchus sp. 17', 'Eubranchus sp. 23', 'Eubranchus sp. 26', 'Eubranchus sp. 27',
        'Goniobranchus sp. 14', 'Goniodoridella sp. 8', 'Haminoea sp. 5', 'Marionia sp. 24', 'Marionia sp. 6',
        'Phyllidiella sp. 2', 'Sakuraeolis sp. 1', 'Stiliger sp. 1', 'Tenellia sp. 17', 'Tenellia sp. 81',
        'Thecacera sp. 8', 'Tritonia sp. 3', 'Tritonia sp. 4')},
    'Thuridilla sp. 2': MARTIN_HERVAS,
    'Thuridilla sp. 4 (2021)': MARTIN_HERVAS,
}

THURIDILLA_ISSUE_KEY = 'check-thuridilla-numbering'
THURIDILLA_NOTES = (
    'Thuridilla sp. 2 ו-Thuridilla sp. 4 (2021) באתר הם מינים שמוספרו במאמר Martín-Hervás et al. 2021 (שממספר את '
    'Thuridilla sp. 1–10), ולא בספר; מקור השם שלהם הוא המאמר, ובאתר מוצג "(Source: Martín-Hervás et al., 2021)" במקום מחבר. '
    'מספרי הספר הם שיטה אחרת ואין להשוות אליהם: sp. 2 של המהדורה השנייה (עמ\' 430) = Thuridilla sp. 5 במהדורה השלישית '
    '(עמ\' 490-491); sp. 4 (עמ\' 431) = sp. 7 (עמ\' 492-493); sp. 7 (עמ\' 432) = sp. 27 (עמ\' 496-497).\n'
    'נשאר לבדוק: Thuridilla sp. 7 באתר — לפי המאמר או לפי הספר (התמונה אינה דומה ל-sp. 7 של הספר); '
    'ואם יש בקטלוג גם Thuridilla sp. 4 לפי הספר — שהוא אינו אותו מין כמו Thuridilla sp. 4 (2021).')


def forward(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    for name, source in SOURCES.items():
        Species.objects.filter(scientific_name=name, name_source='').update(name_source=source)
    findings = import_module('observations.migrations.0106_nssi3_findings')
    original = next((row[6] for row in findings.ISSUES if row[0] == THURIDILLA_ISSUE_KEY), None)
    Issue = apps.get_model('observations', 'IdentificationIssue')
    issue = Issue.objects.filter(transfer_id=uuid.uuid5(findings.NAMESPACE, THURIDILLA_ISSUE_KEY)).first()
    if issue is not None and original is not None and issue.notes == original:
        issue.notes = THURIDILLA_NOTES
        issue.updated_at = timezone.now()
        issue.save(update_fields=['notes', 'updated_at'])


class Migration(migrations.Migration):
    dependencies = [('observations', '0109_species_name_source')]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
