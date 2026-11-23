"""Issues #38 and #39 (owner's decisions), checked against Martín-Hervás et al. 2021 (Cladistics 37: 647-676), pp. 11-12
and fig. 4 -- the paper that numbers Thuridilla sp. 1-10. Its numbers are not the Gosliner et al. book's; where the site
also knows a book number, the paper's carries "(2021)" (the exception).

- Thuridilla sp. 2 (paper): kept; identification texts from the paper.
- Thuridilla sp. 4 (2021): kept, the Romblon observation with cf. (its rhinophores, orange with white longitudinal lines,
  are those the paper gives for sp. 8); identification texts from the paper.
- "Thuridilla sp. 7" (2nd edition of the book) becomes Thuridilla sp. 7 (2021), source the paper: the Romblon
  observation's rhinophore has a black tip and an orange band, the paper's sp. 7 pattern, not the book's light green
  sp. 7; the Solomon Islands observation filed as T. ratna (white rhinophores, orange band, black tip -- in T. ratna the
  tips are orange, without black) moves to it with its card (same rows, transfer ids and slug). Both with cf.
- The two species' sources cite the paper by its real title; the observations get a note on the uncertainty.
The issues become "decided": catalogue and observations done, photo labels to fix -- "(Source: Martín-Hervás et al.,
2021)" on the second line, never an author. Safe in both environments: found by name / transfer id, done once."""
import importlib

from django.db import migrations

PAPER_SLUG = ('a-molecular-phylogeny-of-thuridilla-bergh-1872-sea-slugs-gastropoda-sacoglossa-reveals-a-case-of-flamboyant-'
              'and-cryptic')
SOURCE = 'Martín-Hervás et al., 2021'
WORMS = 'https://www.marinespecies.org/aphia.php?p=taxdetails&id=137929'
CITATION = ('Martín-Hervás, M. R., Carmona, L., Malaquias, M. A. E., Krug, P. J., Gosliner, T. M. & Cervera, J. L. (2021). A '
            'molecular phylogeny of Thuridilla Bergh, 1872 sea slugs (Gastropoda, Sacoglossa) reveals a case of flamboyant '
            'and cryptic radiation in the marine realm. Cladistics 37(6): 647–676. https://doi.org/10.1111/cla.12465')
REF_HE = "(לפי Martín-Hervás ושותפים 2021, עמ' 11-12, איור 4{fig})"
REF_EN = '(after Martín-Hervás et al. 2021, pp. 11-12, fig. 4{fig})'
GENUS_HE = 'סקוגלוסות צבעוניות, לרוב עם קווי אורך דקים; הסוג עבר רביזיה ב־2021 (Martín-Hervás ושותפים).'
GENUS_EN = 'Colourful sacoglossans, usually with fine longitudinal lines; the genus was revised in 2021 (Martín-Hervás et al.).'

TEXTS = {
    'Thuridilla sp. 2': dict(
        identification_he='גוף שחור עם קווי אורך לבנים־צהבהבים לאורך הפרפודיה והמחושים, ושוליים פנימיים כתומים לפרפודיה; '
                          'כתמים בצבע שמנת ליד הרגל. המחושים עם קצה כתום ופס לבן צר מתחתיו. אוסטרליה (Browse, Ashmore '
                          'Reef) והפיליפינים (Cobrador, Lubang). ' + REF_HE.format(fig='b'),
        identification_en='Black body with white-yellowish longitudinal lines along the parapodia and rhinophores and orange '
                          'inner parapodial margins; cream spots near the foot. Rhinophores with orange tips and a narrow '
                          'white subapical band. Australia (Browse Is., Ashmore Reef) and the Philippines (Cobrador, '
                          'Lubang). ' + REF_EN.format(fig='b')),
    'Thuridilla sp. 4 (2021)': dict(
        identification_he='גוף כהה עם קווי אורך צהובים, שוליים פנימיים אדומים־כתומים לפרפודיה, ומעט כתמים בכחול שמיים על '
                          'השוליים החיצוניים ועל הראש; נקודות שחורות ולבנות לסירוגין בשולי הפרפודיה. במחושים הפס הלבן מצטמצם '
                          'לשליש מאורכם, ואחריו פס אדמדם בקצה. פפואה גינאה החדשה (Madang). ' + REF_HE.format(fig='c'),
        identification_en='Dark body with longitudinal yellow lines, red-orange inner parapodial margins and a few sky-blue '
                          'spots on the outer parapodial edge and the head; black and white spots alternate on the parapodial '
                          'margin. On the rhinophores the white band is reduced to a third of their length, followed by a '
                          'reddish band at the tips. Papua New Guinea (Madang). ' + REF_EN.format(fig='c'),
        similar_species_he='T. bayeri: יותר כתמים כחולים, ופס לבן בחצי העליון של המחושים עם פס כתום דק בקצה. Thuridilla sp. 8 '
                           '(2021): כתמים כחולים רבים, ובמחושים קווי אורך לבנים בין האמצע לקצה הכתום, בלי נקודות שחורות '
                           'ולבנות בשולי הפרפודיה. ' + REF_HE.format(fig=''),
        similar_species_en='T. bayeri has more blue spots and a white band on the upper half of the rhinophores with a thin '
                           'orange tip. Thuridilla sp. 8 (2021) has many blue spots and white longitudinal lines between the '
                           'middle and the orange tips of the rhinophores, without black and white spots on the parapodial '
                           'margin. ' + REF_EN.format(fig='')),
    'Thuridilla sp. 7 (2021)': dict(
        description_he='מין שטרם תואר רשמית מהסוג Thuridilla (משפחת Plakobranchidae), המופיע בשם Thuridilla sp. 7 ברביזיה '
                       'של הסוג (Martín-Hervás ושותפים, 2021), אחד המינים במכלול T. gracilis; הסימון (2021) מבדיל אותו '
                       'מ־Thuridilla sp. 7 של ספר ההגדרה של Gosliner, Valdés ו־Behrens (2018), שהוא מין אחר. ' + GENUS_HE,
        description_en='An undescribed species of Thuridilla (Plakobranchidae), listed as Thuridilla sp. 7 in the revision of '
                       'the genus (Martín-Hervás et al., 2021), one of the species of the T. gracilis complex; "(2021)" tells '
                       'it apart from Thuridilla sp. 7 of Gosliner, Valdés & Behrens (2018), another species. ' + GENUS_EN,
        identification_he='גוף שחור עם קווי אורך לבנים־צהבהבים לאורך הפרפודיה והמחושים, ושוליים פנימיים כתומים לפרפודיה. '
                          'קצות המחושים שחורים, ואחריהם פס כתום צר ופס לבן רחב בהרבה. פפואה גינאה החדשה (Siar, Madang). '
                          + REF_HE.format(fig='e'),
        identification_en='Black body with white-yellowish longitudinal lines along the parapodia and rhinophores and orange '
                          'inner parapodial margins. Rhinophore tips black, followed by a narrow orange band and a noticeably '
                          'wider white band. Papua New Guinea (Siar Is., Madang). ' + REF_EN.format(fig='e'),
        similar_species_he='T. ratna: קווי אורך במחושים וקצה כתום, בלי שחור. Thuridilla sp. 6 (2021): קצה שחור, ואחריו פס כתום '
                           'רחב יותר ופס לבן. Thuridilla sp. 2 (2021): קצה כתום ופס לבן צר מתחתיו. ' + REF_HE.format(fig=''),
        similar_species_en='T. ratna: rhinophores with longitudinal lines and orange tips, without black. Thuridilla sp. 6 '
                           '(2021): black tips followed by a wider orange band and a white band. Thuridilla sp. 2 (2021): '
                           'orange tips with a narrow white subapical band. ' + REF_EN.format(fig='')),
}

CF = 'זיהוי לא ודאי (cf.): '
NOTES = {
    '450a994b-828f-4eeb-993a-055d62d5d8a3': (
        CF + 'מעט כתמים כחולים, כמו Thuridilla sp. 4 (2021), אבל המחושים כתומים עם קווי אורך לבנים, כמו שהמאמר מתאר ל־Thuridilla sp. 8 (2021).',
        'Uncertain identification (cf.): few blue spots, as in Thuridilla sp. 4 (2021), but the rhinophores are orange with '
        'white longitudinal lines, as the paper describes for Thuridilla sp. 8 (2021).', None),
    '51367669-3422-47d7-8a8d-feb01fe2b501': (
        CF + 'רק חלק מהמחוש נראה – קצה שחור ופס כתום, כמו Thuridilla sp. 7 (2021).',
        'Uncertain identification (cf.): only part of a rhinophore shows -- a black tip and an orange band, as in '
        'Thuridilla sp. 7 (2021).', 'Thuridilla sp. 7'),
    'f83b17d0-9348-4d7d-af8b-b1ba5955602d': (
        CF + 'מחושים לבנים עם פס כתום וקצה שחור, כמו Thuridilla sp. 7 (2021); ל־T. ratna, לפי Martín-Hervás ושותפים (2021), קצה כתום בלי שחור.',
        'Uncertain identification (cf.): white rhinophores with an orange band and a black tip, as in Thuridilla sp. 7 '
        '(2021); in T. ratna, after Martín-Hervás et al. (2021), the tips are orange, without black.', 'Thuridilla ratna'),
}
ISSUES = {
    '4f19052c-d638-52be-8a82-cbdb298aa266': (
        "הוחלט: Thuridilla sp. 2 נשאר (תואם את המאמר). Thuridilla sp. 4 (2021) נשאר, ולתצפית #234 נוסף cf. (המחושים כמו "
        "ב-sp. 8 (2021)). נוספו סימני זיהוי מהמאמר. בוצע במיגרציה 0126. נותר: בכיתוב התמונות, בשורה השנייה, "
        "(Source: Martín-Hervás et al., 2021) במקום מחבר — ב-#173 ('Martín-Herváz, 2021') וב-#234 ('(2021) Bergh, 1872'); "
        "ב-#234 גם cf. בשם.", None),
    '7d8eec0e-7c86-5706-8597-36df4ba4ba71': (
        "הוחלט: Thuridilla sp. 7 (2021) לפי Martín-Hervás et al. 2021, עם cf. — גם לתצפית #241 (רומבלון) וגם לתצפית #471 "
        "(איי שלמה, שתויקה כ-T. ratna). שם המין במקום (מקור: המאמר); #471 והכרטיס שלה עברו אליו באותה כתובת. "
        "בוצע במיגרציה 0126. נותר: כיתוב התמונות — 'Thuridilla cf. sp. 7 (2021)' ובשורה השנייה "
        "(Source: Martín-Hervás et al., 2021).", 'f83b17d0-9348-4d7d-af8b-b1ba5955602d'),
}


def forwards(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    Sample = apps.get_model('observations', 'Sample')
    SpeciesArea = apps.get_model('observations', 'SpeciesArea')
    Article = apps.get_model('observations', 'Article')
    Issue = apps.get_model('observations', 'IdentificationIssue')
    paper = Article.objects.filter(slug=PAPER_SLUG).first()
    renamed = Species.objects.filter(scientific_name='Thuridilla sp. 7 (2021)').first()
    old7 = Species.objects.filter(scientific_name='Thuridilla sp. 7').first()
    if renamed is None and old7 is not None:
        old7.scientific_name, old7.species, old7.name_source = 'Thuridilla sp. 7 (2021)', 'sp. 7 (2021)', SOURCE
        old7.description_he = old7.description_en = ''
        old7.save()
        old7.articles.clear()
        renamed = old7
    if renamed is None:
        return
    for name, texts in TEXTS.items():
        sp = Species.objects.filter(scientific_name=name).first()
        if sp is None: continue
        for field, value in texts.items():
            if not getattr(sp, field): setattr(sp, field, value)
        sp.sources = f'{WORMS}\n{CITATION}'
        sp.name_source = SOURCE
        sp.save()
        if paper is not None: sp.articles.add(paper)
    targets = {'Thuridilla sp. 7': renamed.pk, 'Thuridilla ratna': renamed.pk}
    for transfer, (note_he, note_en, old_name) in NOTES.items():
        sample = Sample.objects.filter(transfer_id=transfer).first()
        if sample is None: continue
        changes = {}
        if not sample.identification_qualifier: changes['identification_qualifier'] = 'cf.'
        if not sample.note_he: changes['note_he'] = note_he
        if not sample.note_en: changes['note_en'] = note_en
        if old_name == 'Thuridilla ratna' and sample.species_id != renamed.pk:
            SpeciesArea.objects.filter(species_id=sample.species_id, defining_sample_id=sample.pk).exclude(
                species_id=renamed.pk).update(species_id=renamed.pk)
            changes['species_id'] = renamed.pk
        if changes: Sample.objects.filter(pk=sample.pk).update(**changes)
    for transfer, (decision, second) in ISSUES.items():
        issue = Issue.objects.filter(transfer_id=transfer, status__in=('open', 'checking')).first()
        if issue is None: continue
        if not issue.decision.strip(): issue.decision = decision
        issue.status = 'decided'
        issue.action_catalog = issue.action_observation = 'done'
        issue.action_photo = issue.action_photo or 'needed'
        if second:
            issue.corrected_species_id = renamed.pk
            obs = Sample.objects.filter(transfer_id=second).first()
            if obs is not None and not issue.second_observation_id: issue.second_observation_id = obs.pk
        issue.save()
    importlib.import_module('observations.migrations.0071_defining_samples_one_level_below').fix(apps, schema_editor)


class Migration(migrations.Migration):
    dependencies = [('observations', '0125_aegires_sp7_cf')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
