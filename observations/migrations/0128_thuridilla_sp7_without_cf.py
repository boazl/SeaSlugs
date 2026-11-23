"""Owner's decision (issue #39): the two observations of Thuridilla sp. 7 (Romblon #241, Solomon Islands #471) drop
"cf.". Their notes drop the "uncertain identification (cf.)" opening: #241's note (only part of a rhinophore shows) goes,
#471's keeps why it is not T. ratna; the issue's decision says so. Only the values written by migrations 0126-0127
change. Safe in both environments: found by transfer id."""
from django.db import migrations

ROMBLON, SOLOMON = '51367669-3422-47d7-8a8d-feb01fe2b501', 'f83b17d0-9348-4d7d-af8b-b1ba5955602d'
ISSUE = '7d8eec0e-7c86-5706-8597-36df4ba4ba71'
NOTES = {
    ROMBLON: (('זיהוי לא ודאי (cf.): רק חלק מהמחוש נראה – קצה שחור ופס כתום, כמו Thuridilla sp. 7.', ''),
              ('Uncertain identification (cf.): only part of a rhinophore shows -- a black tip and an orange band, as in '
               'Thuridilla sp. 7.', '')),
    SOLOMON: (('זיהוי לא ודאי (cf.): מחושים לבנים עם פס כתום וקצה שחור, כמו Thuridilla sp. 7; ל־T. ratna, לפי Martín-Hervás '
               'ושותפים (2021), קצה כתום בלי שחור.',
               'מחושים לבנים עם פס כתום וקצה שחור, כמו Thuridilla sp. 7; ל־T. ratna, שבשמו נרשמה התצפית בעבר, לפי Martín-Hervás '
               'ושותפים (2021), קצה כתום בלי שחור.'),
              ('Uncertain identification (cf.): white rhinophores with an orange band and a black tip, as in Thuridilla sp. 7; '
               'in T. ratna, after Martín-Hervás et al. (2021), the tips are orange, without black.',
               'White rhinophores with an orange band and a black tip, as in Thuridilla sp. 7; in T. ratna, the name this '
               'observation was filed under before, after Martín-Hervás et al. (2021), the tips are orange, without black.')),
}
DECISION = [('לפי Martín-Hervás et al. 2021, עם cf. — גם', 'לפי Martín-Hervás et al. 2021 (בלי cf., לפי החלטת הבעלים) — גם'),
            ("'Thuridilla cf. sp. 7'", "'Thuridilla sp. 7'")]


def forwards(apps, schema_editor):
    Sample = apps.get_model('observations', 'Sample')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    for transfer, ((he_old, he_new), (en_old, en_new)) in NOTES.items():
        sample = Sample.objects.filter(transfer_id=transfer).first()
        if sample is None: continue
        changes = {}
        if sample.identification_qualifier == 'cf.': changes['identification_qualifier'] = ''
        if sample.note_he == he_old: changes['note_he'] = he_new
        if sample.note_en == en_old: changes['note_en'] = en_new
        if changes: Sample.objects.filter(pk=sample.pk).update(**changes)
    issue = Issue.objects.filter(transfer_id=ISSUE).first()
    if issue is not None:
        decision = issue.decision
        for old, new in DECISION: decision = decision.replace(old, new)
        if decision != issue.decision:
            issue.decision = decision
            issue.save()


class Migration(migrations.Migration):
    dependencies = [('observations', '0127_thuridilla_paper_numbers_plain')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
