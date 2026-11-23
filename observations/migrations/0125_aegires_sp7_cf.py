"""Issue #37 (owner's decision): the Romblon observation of Aegires sp. 7 (2nd edition of Gosliner, Valdés & Behrens,
p. 67) keeps its species, with "cf." -- seen from other angles it matches, except that its tubercles are white where the
book's are orange. The species gets its 3rd-edition name (Aegires sp. 12, pp. 28-29 -- the 3rd edition's own "Aegires
sp. 7" is another animal), identification texts from both editions, and the 3rd edition in its sources; the observation
gets a note on the difference. The issue becomes "decided": catalogue and observation done, photo label and video to
fix (add cf.). Safe in both environments: found by name / transfer id, done only where still needed."""
from django.db import migrations

SAMPLE = '7363005f-e75b-41a8-9e5d-37cc6a736a48'
ISSUE = 'c1211293-53e6-54f9-a840-f7f5506b5f6a'
NSSI3_SLUG = 'nssi-3-gosliner-valdes-behrens-2026'
NSSI3 = ('Gosliner, T. M., Valdés, Á. & Behrens, D. W. (2026). Nudibranch & Sea Slug Identification – Indo-Pacific, '
         '3rd ed. New World Publications.')
DESC_HE = (' במהדורה השלישית (2026) הוא מופיע בשם Aegires sp. 12; השם Aegires sp. 7 משמש במהדורה השלישית למין אחר '
           '(ירקרק־חום עם רשת קווים לבנים).')
DESC_EN = (' The 3rd edition (2026) lists it as Aegires sp. 12; there, the name Aegires sp. 7 is used for another species '
           '(greenish brown with a network of white lines).')
IDENT_HE = ('ורוד־סגול, עם בליטות גדולות ומעוגלות; קצות האונות שליד הזימים כתומים; המחושים אדומים־סגולים כהים. אורך כ־6 מ״מ. '
            'הפיליפינים ופפואה גינאה החדשה, מים רדודים מתחת לשברי אלמוגים; ניזון מהספוג הגירני הצינורי Pericharax. '
            '(לפי Gosliner, Valdés & Behrens 2026, מהדורה 3, עמ׳ 28-29, בשם Aegires sp. 12; Gosliner, Valdés & Behrens '
            '2018, מהדורה 2, עמ׳ 67, בשם Aegires sp. 7)')
IDENT_EN = ('Pinkish purple with large rounded tubercles; tips of the extrabranchial lobes orange; rhinophores deep purplish '
            'red. About 6 mm. Philippines and Papua New Guinea, shallow water under rubble; feeds on the tubular calcareous '
            'sponge Pericharax. (after Gosliner, Valdés & Behrens 2026, 3rd ed., pp. 28-29, as Aegires sp. 12; Gosliner, '
            'Valdés & Behrens 2018, 2nd ed., p. 67, as Aegires sp. 7)')
NOTE_HE = 'זיהוי לא ודאי (cf.): המבנה תואם את Aegires sp. 7, אבל הבליטות כאן לבנות, ולפי הספר קצות האונות כתומים.'
NOTE_EN = ('Uncertain identification (cf.): the shape matches Aegires sp. 7, but the tubercles here are white, where the '
           'book shows orange lobe tips.')
DECISION = ('הוחלט: התצפית נשארת Aegires sp. 7 (מהדורה 2) עם cf. — מזוויות אחרות היא תואמת, פרט לבליטות לבנות במקום כתומות. '
            'במהדורה השלישית המין נקרא Aegires sp. 12 (עמ׳ 28-29), והשם נוסף לדף המין. בוצע במיגרציה 0125. '
            'נותר: להוסיף cf. לכיתוב בתמונה ובסרטון.')


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    Article = apps.get_model('observations', 'Article')
    Publication = apps.get_model('observations', 'SpeciesPublicationName')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    species = Species.objects.filter(scientific_name='Aegires sp. 7').first()
    if species is None:
        return
    nssi3 = Article.objects.filter(slug=NSSI3_SLUG).first()
    if nssi3 is not None:
        if not Publication.objects.filter(species_id=species.pk, article_id=nssi3.pk).exists():
            Publication.objects.create(species_id=species.pk, article_id=nssi3.pk, name='Aegires sp. 12', pages='28-29')
        species.articles.add(nssi3)
    if 'Aegires sp. 12' not in species.description_he and species.description_he:
        species.description_he += DESC_HE
    if 'Aegires sp. 12' not in species.description_en and species.description_en:
        species.description_en += DESC_EN
    if not species.identification_he: species.identification_he = IDENT_HE
    if not species.identification_en: species.identification_en = IDENT_EN
    if '3rd ed.' not in species.sources:
        lines = [l for l in species.sources.splitlines() if l.strip()]
        at = next((i for i, l in enumerate(lines) if '2nd ed.' in l), len(lines))
        lines.insert(at, NSSI3)
        species.sources = '\n'.join(lines)
    species.save()
    sample = Sample.objects.filter(transfer_id=SAMPLE, species_id=species.pk).first()
    has_video = False
    if sample is not None:
        has_video = bool(sample.video_url)
        changes = {}
        if not sample.identification_qualifier: changes['identification_qualifier'] = 'cf.'
        if not sample.note_he: changes['note_he'] = NOTE_HE
        if not sample.note_en: changes['note_en'] = NOTE_EN
        if changes: Sample.objects.filter(pk=sample.pk).update(**changes)
    issue = Issue.objects.filter(transfer_id=ISSUE, status__in=('open', 'checking')).first()
    if issue is not None:
        if not issue.decision.strip(): issue.decision = DECISION
        issue.status = 'decided'
        issue.action_catalog = issue.action_observation = 'done'
        issue.action_photo = issue.action_photo or 'needed'
        if has_video: issue.action_video = issue.action_video or 'needed'
        issue.save()


class Migration(migrations.Migration):
    dependencies = [('observations', '0124_remove_empty_numbered_rows')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
