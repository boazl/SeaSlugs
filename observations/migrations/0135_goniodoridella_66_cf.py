"""Owner's decision (issue #10): the Romblon observation #66 of Goniodoridella savignyi stays in the species complex as
"Goniodoridella cf. savignyi", with a note. After Paz-Sedano et al. 2023 (J. Molluscan Studies 89: eyad020) the complex
holds near-identical species (geminae, unidonta, serrata); G. savignyi in the strict sense is known from the Red Sea, and
its extrabranchial papillae are much larger than the gill branches -- in #66 they are of similar size, as in G. geminae.
The issue is decided: observation done, photo label to fix. Safe in both environments, done once."""
from django.db import migrations

SAMPLE = 'cdc22204-5e2e-4855-a959-d511dae4ab1b'
ISSUE = '9276cf08-a237-5697-a825-a27d38922d0c'
NOTE_HE = ('זיהוי לא ודאי (cf.): G. savignyi הוא מכלול של מינים כמעט זהים (Paz-Sedano ושותפים, 2023). במובן הצר הוא ידוע '
           'מים סוף, והבליטות שמאחורי הזימים שלו גדולות בהרבה מענפי הזימים; כאן הן בגודל דומה להם, כמו ב־G. geminae.')
NOTE_EN = ('Uncertain identification (cf.): G. savignyi is a complex of near-identical species (Paz-Sedano et al., 2023). In '
           'the strict sense it is known from the Red Sea, with extrabranchial papillae much larger than the gill branches; '
           'here they are of similar size, as in G. geminae.')
DECISION = ("הוחלט (אפשרות ב): #66 נשארת במכלול, Goniodoridella cf. savignyi, עם הערה. בוצע במיגרציה 0135. נותר: הכיתוב "
            "בתמונה – 'Goniodoridella cf. savignyi (Pruvot-Fol, 1933)'.")


def forwards(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    sample = Sample.objects.filter(transfer_id=SAMPLE, identification_qualifier='').first()
    if sample is None:
        return
    changes = {'identification_qualifier': 'cf.'}
    if not sample.note_he: changes['note_he'] = NOTE_HE
    if not sample.note_en: changes['note_en'] = NOTE_EN
    Sample.objects.filter(pk=sample.pk).update(**changes)
    issue = Issue.objects.filter(transfer_id=ISSUE, status__in=('open', 'checking')).first()
    if issue is not None:
        if not issue.decision.strip(): issue.decision = DECISION
        issue.status = 'decided'
        issue.action_observation = 'done'
        issue.action_photo = issue.action_photo or 'needed'
        issue.save()


class Migration(migrations.Migration):
    dependencies = [('observations', '0134_hypselodoris_240_skyleri')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
