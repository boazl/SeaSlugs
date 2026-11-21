"""A task in the identification-issues worklist: find in the 3rd edition of Gosliner, Valdés & Behrens (2026) every
gallery species named by the 2nd edition (2018) that has no 3rd-edition name yet (no SpeciesPublicationName of the 3rd
edition) -- by its photograph -- and record what was found. The row lists the species, with the 2nd-edition page where
it is known, at the time the migration runs. Safe in both environments: one row with a fixed transfer_id, written once,
and only when there is such a species.
"""
import uuid
from datetime import date

from django.db import migrations

NSSI2 = 'NSSI-2 Gosliner, Valdés & Behrens, 2018'
NSSI3 = 'NSSI-3 Gosliner, Valdés & Behrens, 2026'
TRANSFER_ID = uuid.uuid5(uuid.UUID('3b6f7a52-90d4-4c1e-8a7e-5e2d8c1f4b63'), 'task-missing-in-3rd-edition')
REPORTER = 'השוואת מהדורות 2 ו-3 של Gosliner, Valdés & Behrens — Claude (21/11/2026)'
STEPS = ('לכל מין: לחפש במהדורה השלישית את אותה תמונה או את אותו בעל חיים (לפי הסוג, הצבע והאזור).\n'
         '- נמצא באותו שם או בשם אחר: בטופס המין, באזור "שם המין בפרסומים", להוסיף את המהדורה השלישית, את השם שבה '
         'ואת העמודים. הקישור למהדורה יופיע אז בדף המין עם השם. אם השם שונה — לפתוח שורת "עדכון שם לפי המהדורה '
         'השלישית" (שינוי מספר בלבד בעדיפות נמוכה).\n'
         '- לא נמצא: לרשום כאן שהמין הושמט מהמהדורה השלישית; המין נשאר לפי המהדורה השנייה.\n'
         'מינים שיש להם כבר שורה משלהם בטבלה (מינים שלא אותרו או שהזיהוי שלהם בבדיקה) מסומנים *.')


def forward(apps, schema_editor):
    Issue = apps.get_model('observations', 'IdentificationIssue')
    Species = apps.get_model('observations', 'Species')
    Article = apps.get_model('observations', 'Article')
    Name = apps.get_model('observations', 'SpeciesPublicationName')
    if Issue.objects.filter(transfer_id=TRANSFER_ID).exists():
        return
    second, third = Article.objects.filter(short_ref=NSSI2).first(), Article.objects.filter(short_ref=NSSI3).first()
    in_third = set(Name.objects.filter(article=third).values_list('species_id', flat=True)) if third else set()
    pages = dict(Name.objects.filter(article=second).values_list('species_id', 'pages')) if second else {}
    own_row = set(Issue.objects.exclude(status__in=('fixed', 'rejected')).filter(
        kind__in=('book_edition', 'misidentified')).values_list('species_id', flat=True))
    missing = [s for s in Species.objects.filter(name_source=NSSI2).order_by('scientific_name') if s.pk not in in_third]
    if not missing:
        return
    lines = [f'- {s.scientific_name}' + (f' (מהדורה 2, עמ\' {pages[s.pk]})' if pages.get(s.pk) else '')
             + (' *' if s.pk in own_row else '') for s in missing]
    Issue.objects.create(
        transfer_id=TRANSFER_ID, kind='other', priority=2, status='open', opened_on=date(2026, 11, 21), reporter=REPORTER,
        notes=f'משימה: לאתר במהדורה השלישית את {len(missing)} המינים באתר שהוגדרו לפי המהדורה השנייה '
              f'ואין להם עדיין שם במהדורה השלישית:\n' + '\n'.join(lines) + '\n\n' + STEPS)


def backward(apps, schema_editor):
    apps.get_model('observations', 'IdentificationIssue').objects.filter(transfer_id=TRANSFER_ID).delete()


class Migration(migrations.Migration):
    dependencies = [('observations', '0119_second_edition_pages')]
    operations = [migrations.RunPython(forward, backward)]
