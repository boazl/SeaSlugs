"""The first rows of the identification-issues table: the mismatches Claude found in a check of the catalogue and the
gallery on 2026-11-17 (identical photos identified as different species, species observed outside their known range,
and classifications that differ from WoRMS / from the source book).

Safe in both environments: observations are found by their transfer_id and species by scientific name, every row has a
fixed transfer_id (so the Mac and the live site get the same rows and the table transfer matches them), a row that
already exists is left alone, and a row whose main species is missing (e.g. an empty test database) is skipped.
How the findings were made:
- identical photos: a perceptual hash (dHash, 256 bits) of every observation's photo compared in pairs; the three
  pairs below differ by 2-5 bits of 256 -- the same frame -- and were checked by eye.
- range: each gallery observation's area compared with the species' range in the catalogue (native_range_en).
- WoRMS: every gallery species and genus matched against the WoRMS REST service (names and authors all agree; the
  remaining notes are status / classification remarks).
"""
import uuid
from datetime import date

from django.db import migrations

NAMESPACE = uuid.UUID('6f1d5c1e-2b8e-4f8a-9d55-1d3f0c9a7e11')
OPENED = date(2026, 11, 17)
REPORTER = 'בדיקת Claude: השוואת תמונות, אזורי תפוצה ו-WoRMS (17/11/2026)'

# key, kind, priority, observation, species, second observation, second species, native range, link, notes
FINDINGS = [
    ('dup-maculosa-aurora', 'duplicate', 1, '616c9a85-5c16-4437-b06f-9228277d47bc', 'Hypselodoris maculosa',
     '36ae91eb-14f6-4fe2-976e-05cf9e71caec', 'Mexichromis aurora', '', '',
     'אותה תמונה בדיוק משמשת לשתי תצפיות שהוגדרו כמינים שונים, ובשני מסעות שונים: #182 Hypselodoris maculosa (מסע H, '
     'אנילאו 2025, ללא סרטון) ו-#88 Mexichromis aurora (מסע V, רומבלון 2026, עם סרטון YouTube; נוצרה קודם).\n'
     'לפי "מינים דומים" בקטלוג, M. aurora מזוהה בכתמים סגולים בין הפסים ובמחושים וזימים כתומים עם פס לבן באמצע — '
     'כך נראית החיה בתמונה. לבדוק: מה הזיהוי הנכון, ומאיזה מסע התמונה (ייתכן שלתצפית ממסע H שויכה תמונה ממסע V).'),
    ('dup-tenellia-a-favorinus-10', 'duplicate', 1, 'eaf4f5a1-ee28-44e6-b32b-f91d5d0433ba', 'Tenellia sp. A',
     'b13837c0-3fea-4e9f-99e9-fe43de13295d', 'Favorinus sp. 10', '', '',
     'אותה תמונה בדיוק בשתי תצפיות מאותו מסע (V, רומבלון 2026): #137 Tenellia sp. A (ללא סרטון) ו-#56 Favorinus sp. 10 '
     '(עם סרטון YouTube; נוצרה קודם). שני סוגים שונים (Trinchesiidae / Facelinidae) — לפחות אחד הזיהויים שגוי.\n'
     'הערה נוספת: בתווית שעל התמונה של Tenellia sp. A מופיע המחבר "A. Costa, 1866" — זה מחבר הסוג; למין sp. אין מחבר.'),
    ('dup-unidentia-tenellia-65', 'duplicate', 1, '7cc463de-4c0c-494c-b79e-f7dfdf1b62d6', 'Unidentia sp.',
     '7b938a0b-049c-42e7-a474-99007310b548', 'Tenellia sp. 65', '', '',
     'אותה תמונה בדיוק בשתי תצפיות משני מסעות: #164 Unidentia sp. (מסע H, אנילאו 2025) ו-#120 Tenellia sp. 65 (מסע V, '
     'רומבלון 2026). שתיהן ללא סרטון ונוצרו ב-15/09/2026. לבדוק את הזיהוי ואת המסע שממנו התמונה.\n'
     'הערה נוספת: בתווית שעל התמונה של Unidentia sp. מופיע המחבר "Millen & Hermosillo, 2012" — מחבר הסוג; למין sp. אין מחבר.'),
    ('range-phyllidia-multifaria-thailand', 'range', 1, '92312e13-7d87-44de-8a34-76c822259a42', 'Phyllidia multifaria',
     None, None, 'Red Sea (endemic)', '',
     'תצפית #539 (מסע Y, תאילנד — מפרץ תאילנד) של מין אנדמי לים סוף. לפי Yonow (2020) המין הדומה במזרח האוקיינוס ההודי '
     'ובמערב האוקיינוס השקט הוא Phyllidia elegans (קיים בקטלוג) — מועמד סביר לזיהוי. התצפית מאילת (#411) תקינה.'),
    ('range-aplysia-dactylomela-australia', 'range', 1, '5a696f42-cd31-497e-b38d-ec1688576d85', 'Aplysia dactylomela',
     None, None, 'Atlantic Ocean (Cape Verde, West Africa, Caribbean); also reached the Mediterranean', '',
     'תצפית #519 (מסע Z1, אוסטרליה — ים האלמוגים) של מין אטלנטי. לפי Alexander & Valdés (2013) האוכלוסיות '
     'ההודו-פסיפיות הן Aplysia argus, וההפרדה מבוססת על מוצא גיאוגרפי ונתונים מולקולריים ולא על דגם הטבעות.\n'
     'שימו לב: באותו מסע כבר יש תצפית #518 Aplysia argus — אם הזיהוי יתוקן יהיו שתי תצפיות של אותו מין באותו מסע '
     '(כלל: תצפית אחת למין במסע), ויש לאחד או להפריד למסע נוסף. התצפית מהים התיכון (#386) תקינה.'),
    ('range-micromelo-undatus-philippines', 'range', 1, '33d8bf52-c4f1-4336-a286-005ef79cec82', 'Micromelo undatus',
     None, None, 'Atlantic (Caribbean; neotype from Jamaica)', '',
     'תצפית #227 (מסע H, אנילאו). לפי הקטלוג, רשומות הודו-פסיפיות שפורסמו בשם זה שייכות כיום למינים קרובים: '
     'Micromelo guamensis, M. scriptus ו-M. barbarae (נבדלים בעיקר גנטית ואנטומית; הגיאוגרפיה היא המדריך הטוב בשטח). '
     'M. guamensis ו-M. scriptus קיימים בקטלוג.'),
    ('range-phyllidia-rueppelii-png', 'range', 2, '16e732cb-7d99-4ac3-b40f-4aa35657f265', 'Phyllidia rueppelii',
     None, None, 'Red Sea and Gulf of Oman', '',
     'תצפית #498 (מסע Z2, פפואה גינאה החדשה — ים ביסמרק). מינים דומים לפי הקטלוג: Phyllidia (Fryeria) guamensis '
     '(צהוב חיוור יותר, בלי חצאי עיגול לבנים ושוליים כתומים), P. bayi, P. schupporum (Brunckhorst 1993; Yonow 2020).'),
    ('range-phyllidia-alyta-png', 'range', 2, '7fcf3c06-5e32-49fe-bca2-8be4dfc00904', 'Phyllidia alyta',
     None, None, 'Western Indian Ocean (e.g. the Maldives and Mauritius)', '',
     'תצפית #502 (מסע Z2, פפואה גינאה החדשה). לפי Yonow (2012) המין הדומה הוא P. varicosa, הנפוץ באזור. '
     'התצפית מהמלדיביים (#529) תקינה.'),
    ('range-hypselodoris-carnea-philippines', 'range', 2, 'dbf76ae2-78de-4079-a994-2349e52fa85d', 'Hypselodoris carnea',
     None, None, 'Western Indian Ocean: Mauritius and the east coast of South Africa; similar animals reported from Oman and western India', '',
     'תצפית #240 (מסע C, אנילאו) רחוקה מאזור התפוצה. מינים דומים לפי הקטלוג: H. capensis ו-H. katherinae '
     '(הפרדה לפי אנטומיה של הרדולה).'),
    ('range-goniodoridella-savignyi-philippines', 'range', 2, 'cdc22204-5e2e-4855-a959-d511dae4ab1b', 'Goniodoridella savignyi',
     'fb8806ad-2c07-45ab-a911-9d30863c99e3', 'Goniodoridella geminae', 'Red Sea (type locality Gulf of Suez); records further east need confirmation', '',
     'תצפית #66 (מסע V, רומבלון). רשומות מחוץ לים סוף טעונות אישור. באותו מסע יש גם #65 G. geminae ו-#67 G. unidonta — '
     'שלושת המינים כמעט זהים חיצונית (זיהוי באנטומיה ו-DNA). לבדוק ששלוש התצפיות הן אכן מינים שונים.'),
    ('range-hypselodoris-melanesica-timor', 'range', 2, '0e28f592-7461-43a0-b0ce-f494b8835264', 'Hypselodoris melanesica',
     None, None, 'Papua New Guinea and the Solomon Islands', '',
     'תצפית #553 (מסע ofTimor26Oct, טימור-לסטה). המין תואר ב-2018 ובעבר בלבל עם H. bullockii (קיים בקטלוג). '
     'התצפית מאיי שלמה (#449) תקינה.'),
    ('range-tambja-kava-philippines', 'range', 2, 'a6ec407e-8915-41e9-a62d-e140a65fb1f7', 'Tambja kava',
     '75dc67e6-e3a3-4142-83d7-31e02482f1fb', None, 'Western Pacific; known with certainty only from Vanuatu', '',
     'תצפית #224 (מסע V, רומבלון, פיליפינים) ותצפית #486 (מסע R, פיג׳י). המין ידוע בוודאות רק מוונואטו (פיג׳י קרובה; '
     'הפיליפינים רחוקים יותר). Tambja amakusana מיפן דומה מאוד (הפרדה אנטומית/מולקולרית).'),
    ('range-elysia-grandifolia-pacific', 'range', 3, '4f7270ae-2961-4762-87f3-ff5c43dc1596', 'Elysia grandifolia',
     'cfbb23a6-81f5-4585-a72f-eb6aea40a3c4', None, 'Indian Ocean (Sri Lanka, southern India) and the Red Sea', '',
     'תצפית #151 (מסע C, אנילאו) ותצפית #556 (מסע ofTimor26Oct, טימור) — מזרחית לאזור התפוצה שבקטלוג. ייתכן שהבעיה '
     'בטקסט אזור התפוצה ולא בזיהוי: לבדוק בספרות אם המין מדווח במערב האוקיינוס השקט, ולעדכן את השדה בהתאם.'),
    ('worms-phestilla-minor-uncertain', 'classification', 2, '3c251fff-22df-4efc-9f3a-4fed48830497', 'Phestilla minor',
     None, None, '', 'https://www.marinespecies.org/aphia.php?p=taxdetails&id=536541',
     'ב-WoRMS המין Phestilla minor Rudman, 1981 מסומן בסטטוס "uncertain" מסיבה "controversed genus allocation" — '
     'השיוך לסוג Phestilla שנוי במחלוקת. כרגע אין שם מקובל חלופי; לעקוב אחר עדכונים.'),
    ('classification-tenellia-sp', 'classification', 3, None, 'Tenellia sp. 65',
     None, None, '', 'https://doi.org/10.1371/journal.pone.0167800',
     'עשרה מיני "Tenellia sp." בגלריה (sp. 17, 18, 29, 34, 39, 65, 71, 81, A, B) נקראים לפי Gosliner, Valdés & Behrens (2018), '
     'שמשתמשים ב-Tenellia במובן הרחב של Cella et al. (2016). WoRMS מקבל את Tenellia אבל לפי Korshunova et al. (2017, '
     'ZooKeys 717, https://doi.org/10.3897/zookeys.717.21885) מינים רבים מ-Tenellia הרחב שייכים ל-Trinchesia, Phestilla, '
     'Catriona ועוד, במשפחת Trinchesiidae. ייתכן שחלק מה-sp. האלה שייכים לסוג אחר לפי WoRMS.'),
    ('classification-family-placeholders', 'classification', 3, 'becdf5ed-656d-4af6-b0ef-54e91f14e486', 'Discodorid sp.',
     '6fd50b52-01a0-4903-b1ef-0965c4dca670', 'Haminoeid sp. 2', '', '',
     'שדה הסוג של "Discodorid sp." ו-"Haminoeid sp. 2" מכיל שם לא פורמלי של משפחה (Discodorididae / Haminoeidae) כפי '
     'שמופיע בספר, ולא סוג של WoRMS — ולכן בגלריה הם מוצגים כאילו "Discodorid" ו-"Haminoeid" הם סוגים. לשקול זיהוי '
     'עד רמת סוג, או הצגה תחת המשפחה בלבד.'),
]


def add_findings(apps, schema_editor):
    Issue = apps.get_model('observations', 'IdentificationIssue')
    Sample = apps.get_model('observations', 'Sample')
    Species = apps.get_model('observations', 'Species')

    def sample(key):
        return Sample.objects.filter(transfer_id=uuid.UUID(key)).first() if key else None

    def species(name):
        return Species.objects.filter(scientific_name=name).first() if name else None

    for key, kind, priority, obs, name, obs2, name2, native_range, link, notes in FINDINGS:
        transfer_id = uuid.uuid5(NAMESPACE, key)
        main = species(name)
        if main is None or Issue.objects.filter(transfer_id=transfer_id).exists():
            continue
        first, second = sample(obs), sample(obs2)
        Issue.objects.create(
            transfer_id=transfer_id, kind=kind, priority=priority, status='open', opened_on=OPENED, reporter=REPORTER,
            observation=first, species=main, second_observation=second,
            second_species=species(name2) or (Species.objects.filter(pk=second.species_id).first() if second else None),
            native_range=native_range, research_link=link, notes=notes)


def remove_findings(apps, schema_editor):
    Issue = apps.get_model('observations', 'IdentificationIssue')
    Issue.objects.filter(transfer_id__in=[uuid.uuid5(NAMESPACE, f[0]) for f in FINDINGS]).delete()


class Migration(migrations.Migration):
    dependencies = [('observations', '0103_identification_issues')]
    operations = [migrations.RunPython(add_findings, remove_findings)]
