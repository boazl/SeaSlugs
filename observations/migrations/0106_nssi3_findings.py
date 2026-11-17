"""Findings of a comparison of the 2nd (2018) and 3rd (2026) editions of Gosliner, Valdés & Behrens, "Nudibranch & Sea
Slug Identification -- Indo-Pacific", with WoRMS (2026-11-17): rows for the identification-issues table and for the new
"topics for discussion" table.

The site's order of authority: WoRMS first, then the 3rd edition, then the 2nd edition or other publications.
- identification issues: undescribed species ("Genus sp. N") whose number or genus changed between the editions (each
  checked by eye: the same photograph appears in both editions), species described since the 2nd edition, catalogue
  names that WoRMS no longer accepts, 2nd-edition species not found in the 3rd, photos to check, and catalogue gaps.
- topics for discussion: where the 3rd edition departs from WoRMS (its Table 2, pp. 6-7, and species-level names).
Safe in both environments: species found by scientific name, a fixed transfer_id per row, an existing row is left alone,
an issue whose species is missing is skipped, and an empty catalogue (a new or test database) gets nothing.
"""
import uuid
from datetime import date

from django.db import migrations

NAMESPACE = uuid.UUID('3b6f7a52-90d4-4c1e-8a7e-5e2d8c1f4b63')
OPENED = date(2026, 11, 17)
REPORTER = 'השוואת מהדורות 2 ו-3 של Gosliner, Valdés & Behrens מול WoRMS — Claude (17/11/2026)'
BOOK = 'Gosliner, Valdés & Behrens 2026 (מהדורה 3)'
RULE = 'סדר העדיפויות באתר: WoRMS, אחר כך המהדורה השלישית, ולבסוף המהדורה השנייה או פרסומים אחרים.'
RENAME = ('אפשר גם להשאיר את השם של המהדורה השנייה (אין יתרון לאחד המספורים), ובלבד שהמהדורה מצוינת במקור. '
          'שינוי שם מין מפורסם דורש הפניה 301 (species_redirects.py), עדכון התווית שעל התמונה ובדיקה '
          'שהמספר החדש אינו תפוס כבר בקטלוג.')
WORMS = 'https://www.marinespecies.org/aphia.php?p=taxdetails&id='

# key, kind, priority, species, corrected name, link, notes
ISSUES = []

# -- undescribed species renumbered / moved in the 3rd edition (same photograph in both editions) -------------------
for old, p2, new, p3, extra in [
    ('Aegires sp. 8', '68', 'Aegires sp. 13', '28-29', ''),
    ('Atagema sp. 12', '117', 'Atagema sp. 11', '44-45', ''),
    ('Dermatobranchus sp. 6', '234', 'Armina sp. 10', '254-255', 'מעבר לסוג אחר (Armina).'),
    ('Dermatobranchus sp. 17', '240', 'Dermatobranchus sp. 3', '260-261', ''),
    ('Eubranchus sp. 15', '279', 'Eubranchus sp. 17', '320-321',
     'שימו לב: Eubranchus sp. 15 במהדורה השלישית הוא בעל חיים אחר.'),
    ('Eubranchus sp. 17', '279', 'Eubranchus sp. 19', '320-321',
     'שימו לב: Eubranchus sp. 17 במהדורה השלישית הוא ה-sp. 15 של המהדורה השנייה — לעדכן את שני המינים יחד.'),
    ('Eubranchus sp. 23', '281', 'Eubranchus sp. 25', '320-321', ''),
    ('Eubranchus sp. 27', '281', 'Eubranchus sp. 29', '322-323', ''),
    ('Goniobranchus sp. 14', '145', 'Goniobranchus sp. 18', '168-169', ''),
    ('Haminoea sp. 5', '351', 'Liloa sp. 9', '398-399', 'מעבר לסוג אחר (Liloa).'),
    ('Marionia sp. 6', '262', 'Marioniopsis sp. 11', '282-283', 'מעבר לסוג אחר (Marioniopsis).'),
    ('Marionia sp. 24', '266', 'Marioniopsis sp. 22', '284-285', 'מעבר לסוג אחר (Marioniopsis).'),
    ('Phyllidia sp. 1', '212', 'Phyllidia sp. 2', '236-237', ''),
    ('Phyllidiella sp. 2', '219', 'Phyllidiella sp. 5', '244-245',
     'לבדוק את התמונה באתר: ייתכן שהיא מתאימה דווקא ל-Phyllidiella sp. 2 של המהדורה השלישית '
     '(שחור עם פקעות ורודות בטבעות).'),
    ('Tenellia sp. 17', '288', 'Tenellia sp. 15', '328-329',
     'שימו לב: Tenellia sp. 17 במהדורה השלישית הוא בעל חיים אחר.'),
    ('Tenellia sp. 81', '299', 'Tenellia sp. 91', '344-345', ''),
    ('Tritonia sp. 4', '257', 'Marioniopsis sp. 6', '280-281', 'מעבר לסוג אחר (Marioniopsis).'),
]:
    ISSUES.append((f'book3-{old}', 'book_edition', 1, old, new, '',
                   f'במהדורה השנייה: {old} (עמ\' {p2}). במהדורה השלישית אותה תמונה מופיעה בשם {new} (עמ\' {p3}). '
                   f'{extra}\n{RENAME}'.replace('  ', ' ')))

# -- described since the 2nd edition (WoRMS first) --------------------------------------------------------------------
ISSUES += [
    ('worms-thecacera-sp-8', 'worms_name', 1, 'Thecacera sp. 8',
     'Thecacera pikachu Pola, Paz-Sedano, Martín, L. Warren, Noble & Martín-Hervás, 2026', WORMS + '1883897',
     'Thecacera sp. 8 של המהדורה השנייה (עמ\' 36) תואר ב-2026; במהדורה השלישית בשם Thecacera pikachu (עמ\' 94-95), '
     'ומקובל ב-WoRMS. המין חסר בקטלוג — יש להוסיף אותו (סוג Thecacera, משפחה Polyceridae) ולהעביר אליו את התצפית.\n'
     'שימו לב: Thecacera sp. 8 במהדורה השלישית הוא בעל חיים אחר.\n' + RENAME),
    ('worms-goniodoridella-sp-8', 'worms_name', 1, 'Goniodoridella sp. 8',
     'Murphydoris cobbi Paz-Sedano, Smirnoff, Candás, Gosliner & Pola, 2022', WORMS + '1568877',
     'Goniodoridella sp. 8 של המהדורה השנייה (עמ\' 51) הוא Murphydoris cobbi במהדורה השלישית (עמ\' 144-145), '
     'מקובל ב-WoRMS. המין כבר קיים בקטלוג — יש לאחד אליו את התצפית ואת עמוד המין.\n' + RENAME),
    ('worms-eubranchus-sp-26', 'worms_name', 1, 'Eubranchus sp. 26',
     'Longibranchus putnami (Fernández-Simón & Moles, 2023)', WORMS + '1832557',
     'Eubranchus sp. 26 של המהדורה השנייה (עמ\' 281) תואר ב-2023. המהדורה השלישית (עמ\' 322-323) קוראת לו '
     'Eubranchus putnami, אבל ב-WoRMS השם המקובל הוא Longibranchus putnami (Martynov & Korshunova, 2025). '
     'לפי כלל האתר — שם WoRMS. הסוג Longibranchus חסר בקטלוג; יש להוסיף אותו ואת המין. ראו גם בנושאים לדיון.\n' + RENAME),
]

# -- the site's photo or numbering needs checking first ---------------------------------------------------------------
ISSUES += [
    ('check-aegires-sp-7', 'misidentified', 1, 'Aegires sp. 7', 'Aegires sp. 12', '',
     'Aegires sp. 7 של המהדורה השנייה (עמ\' 67, ורוד-סגול עם פקעות גדולות) נקרא במהדורה השלישית Aegires sp. 12 '
     '(עמ\' 28-29); Aegires sp. 7 של המהדורה השלישית הוא בעל חיים אחר (ירקרק-חום עם רשת קווים). '
     'התמונה באתר (חיה בהירה על ספוג אדום) אינה דומה לאף אחת מהשתיים — לבדוק את הזיהוי לפני שינוי השם.'),
    ('check-thuridilla-numbering', 'other', 1, 'Thuridilla sp. 2', '', '',
     'שתי שיטות מספור שונות ל-Thuridilla: התמונות באתר של Thuridilla sp. 2 ו-sp. 4 (2021) מסומנות לפי '
     'Martín-Hervás et al. 2021, ואילו המספרים בספר שונים: sp. 2 של המהדורה השנייה (עמ\' 430) = Thuridilla sp. 5 '
     'במהדורה השלישית (עמ\' 490-491); sp. 4 (עמ\' 431) = sp. 7 (עמ\' 492-493); sp. 7 (עמ\' 432) = sp. 27 (עמ\' 496-497). '
     'לבדוק לאיזו שיטה כל מין באתר שייך, ולמזג את Thuridilla sp. 4 עם Thuridilla sp. 4 (2021) אם זה אותו מין. '
     'ראו גם בנושאים לדיון.'),
    ('check-thuridilla-sp-7', 'misidentified', 1, 'Thuridilla sp. 7', 'Thuridilla sp. 27', '',
     'התמונה באתר (גוף כהה עם קווים) אינה דומה ל-Thuridilla sp. 7 של המהדורה השנייה (עמ\' 432, ירוק בהיר עם שולי פרפודיה בהירים '
     'וקרנפים עם קווים כתומים, שנקרא במהדורה השלישית Thuridilla sp. 27, עמ\' 496-497). ייתכן שהתמונה לפי מספור אחר — לבדוק.'),
    ('check-tritonia-sp-3', 'misidentified', 2, 'Tritonia sp. 3', '', '',
     'Tritonia sp. 3 של המהדורה השנייה (עמ\' 257, כתום-ורוד, על Paralemnalia) לא נמצא במהדורה השלישית, '
     'והתמונה באתר (לבן עם כתמים חומים) אינה דומה לו. לבדוק את הזיהוי ואת שמו במהדורה השלישית '
     '(כנראה בין מיני Marioniopsis).'),
    ('book3-samla-sp-4', 'book_edition', 2, 'Samla sp. 4', 'Samla sp. 1', '',
     'Samla sp. 4 של המהדורה השנייה (עמ\' 275) מתאים לפי התיאור ל-Samla sp. 1 במהדורה השלישית (עמ\' 314-315). '
     'לא אומת לפי תמונה (אין תמונה באתר).'),
]
for name, p2 in [('Atagema sp. 13', '117'), ('Haminoea sp. 2', '350'), ('Sakuraeolis sp. 1', '324'),
                 ('Stiliger sp. 1', '408')]:
    ISSUES.append((f'book3-missing-{name}', 'book_edition', 2, name, '', '',
                   f'{name} של המהדורה השנייה (עמ\' {p2}) לא אותר אוטומטית במהדורה השלישית — לחפש ידנית לפי התמונה '
                   'ולעדכן את השם, או לסמן שהמין הושמט מהמהדורה החדשה.'))

# -- catalogue gaps found on the way ----------------------------------------------------------------------------------
ISSUES += [
    ('catalog-family-coryphellina-sp-1', 'other', 2, 'Coryphellina sp. 1', '', '',
     'למין אין משפחה בקטלוג (Flabellinidae לפי WoRMS לסוג Coryphellina).'),
    ('catalog-family-tenellia-sp-17', 'other', 2, 'Tenellia sp. 17', '', '',
     'למין אין משפחה בקטלוג (Trinchesiidae, כמו שאר מיני Tenellia באתר).'),
    ('catalog-family-phyllidiella-sp-a', 'other', 2, 'Phyllidiella sp. A', '', '',
     'בשדה המשפחה רשום Phyllidioidea, שהיא על-משפחה; המשפחה היא Phyllidiidae. כך גם ב-Phyllidiella sp. B.'),
    ('catalog-authors-sp', 'other', 3, 'Aegires sp. 8', '', '',
     'לכל מיני ה-sp. עם מספר בקטלוג אין מחבר (פרט ל-Phyllidiella sp. 2, שרשום לו 2018). '
     'לפי כלל האתר המקור הוא המהדורה השלישית: "Gosliner, Valdés & Behrens, 2026", '
     'ולמינים שמקורם בפרסום אחר (כמו Thuridilla לפי Martín-Hervás 2021) — המקור שלהם.'),
]

# -- catalogue names that WoRMS no longer accepts (both books cover them; no observations on the site) -------------------
UNACCEPTED = [
    ('Berthelinia pseudochloris', 'Edenttellina pseudochloris'), ('Dermatobranchus rubidus', 'Armina rubida'),
    ('Discodoris coerulescens', 'Tayuva coerulescens'), ('Eubranchus virginalis', 'Eubranchopsis virginalis'),
    ('Goniobranchus pruna', 'Chromodoris pruna'), ('Goniodoris felis', 'Pelagella felis'),
    ('Goniodoris joubini', 'Pelagella joubini'), ('Halgerda elegans', 'Halgerda willeyi'),
    ('Marionia elongoviridis', 'Marioniopsis elongoviridis'), ('Marionia hawaiiensis', 'Marioniopsis hawaiiensis'),
    ('Marionia levis', 'Marioniopsis levis'), ('Maxacteon flammeus', 'Punctacteon flammeus'),
    ('Nembrotha yonowae', 'Nembrotha cristata'), ('Okenia hallucigenia', 'Ceratodoris hallucigenia'),
    ('Okenia japonica', 'Bermudella japonica'), ('Okenia kendi', 'Ceratodoris kendi'),
    ('Okenia kondoi', 'Ceratodoris kondoi'), ('Okenia lambat', 'Ceratodoris lambat'),
    ('Okenia liklik', 'Naisdoris liklik'), ('Okenia pilosa', 'Ceratodoris pilosa'),
    ('Okenia plana', 'Ceratodoris plana'), ('Okenia purpurata', 'Bermudella purpurata'),
    ('Okenia purpureolineata', 'Bermudella purpureolineata'), ('Okenia stellata', 'Ceratodoris stellata'),
    ('Okenia virginiae', 'Ceratodoris virginiae'), ('Philine orca', 'Hermania orca'),
    ('Philine rubrata', 'Hermania rubrata'), ('Phyllidiella striata', 'Phyllidiopsis striata'),
    ('Phyllidiopsis monacha', 'Phyllidia monacha'), ('Phyllidiopsis pipeki', 'Phyllidiopsis krempfi'),
    ('Samla rubropurpurata', 'Launsina rubropurpurata'), ('Scaphander japonicus', 'Nipponoscaphander japonicus'),
    ('Smaragdinella fragilis', 'Smaragdinella sieboldi'), ('Tenellia acinosa', 'Trinchesia acinosa'),
    ('Thordisa albomacula', 'Avaldesia albomacula'), ('Thordisa tahala', 'Avaldesia tahala'),
]
for old, valid in UNACCEPTED:
    ISSUES.append((f'worms-unaccepted-{old}', 'worms_name', 3, old, valid, '',
                   f'השם {old} אינו מקובל ב-WoRMS; השם המקובל: {valid}. לשם הישן אין תצפיות באתר — לאחד את רשומת '
                   'הקטלוג לשם המקובל (או להסיר אותה אם השם המקובל כבר קיים בקטלוג).'))
ISSUES.append(('worms-unaccepted-phestilla', 'worms_name', 3, 'Tenellia sibogae', 'Phestilla sibogae', '',
               'בקטלוג קיימים השמות Tenellia arnoldi, T. chaetopterana, T. fuscostriata, T. lugubris, T. melanobrachia, '
               'T. poritophages, T. sibogae, T. subodiosa ו-T. viei, ש-WoRMS רושם כצורה חלופית ("alternative '
               'representation") של מיני Phestilla. בספר הם ב-Tenellia (ראו נושא לדיון Phestilla). לפי כלל האתר — '
               'Phestilla; לבדוק שאין כפילות בקטלוג.'))
ISSUES.append(('catalog-missing-book3-species', 'other', 3, None, '', '',
               'מינים מהמהדורה השלישית שמקובלים ב-WoRMS וחסרים בקטלוג: Polycera enesithsaba Toms, Pola, von der Heyden '
               '& Gosliner, 2026; Thecacera pikachu (ראו למעלה); Thecacera sesama H.-Y. Chan & C.-L. Lee, 2026; '
               'Gymnodoris bernardae, G. boiteuxi, G. bricei, G. deniseae, G. fassioae, G. feyae, G. fleuroti, '
               'G. wanaporum De Souza-Canal & Valdés, 2025; Trapania joannotae, T. mechineaui, T. rocherensis, '
               'T. rollandi Lam & A. Valdés, 2026; Hantazuia kimotoi Korshunova, K. Fletcher & Martynov, 2025; '
               'Tenellia pinnifera (Baba, 1949); Cyerce liliuokalaniae, C. trowbridgeae, C. tutela, C. whaapi '
               'K. Moreno, Gosliner, N. G. Wilson, Krug & Á. Valdés, 2025; Pseudunela cornuta (Challis, 1970); '
               'Strubellia paradoxa (Strubell, 1892); ומהפטרופודים Cavolinia tridentata, C. uncinata, Clio pyramidata, '
               'Corolla spectabilis, Cuvierina columnella, Diacria trispinosa. '
               'הרשימה חלקית: היא מבוססת על טקסט ה-OCR, ושמות שנקראו לא נכון לא נבדקו.'))

# topic, rank, priority, book, WoRMS, site, sources, WoRMS id
TOPICS = [
    ('Doridida — דרגה', 'order', 2,
     'Doridida הם אחד משני הענפים בתוך Nudibranchia (עם Cladobranchia).',
     'Nudibranchia כוללת רק את Cladobranchia; Doridida (היום Doridina) סדרה נפרדת (Korshunova et al. 2025).',
     'באתר Nudibranchia היא סדרה אחת שכוללת את הדורידים.',
     'Korshunova et al. 2025; ספר מהדורה 3, טבלה 2 ועמ\' 4-5', '1052385'),
    ('Bullinidae', 'family', 3,
     'משפחה נפרדת ל-Bullina.', 'שם נרדף צעיר של Aplustridae (Göbbeler & Klussmann-Kolb 2011; Bouchet et al. 2017).',
     'באתר Bullina ב-Aplustridae (לפי WoRMS).', 'ספר מהדורה 3, טבלה 2', '411860'),
    ('Pleurolidiidae', 'family', 3,
     'לא מוכרת; Pleurolidia ב-Facelinidae.', 'משפחה מקובלת (Carmona et al. 2015).',
     'באתר Pleurolidia ב-Pleurolidiidae (לפי WoRMS).', 'ספר מהדורה 3, טבלה 2', '570853'),
    ('Unidentiidae', 'family', 3,
     'משפחה נפרדת ל-Unidentia.', 'שם נרדף צעיר של Piseinotecidae (Ekimova et al. 2026).',
     'באתר Unidentia ב-Piseinotecidae (לפי WoRMS).', 'ספר מהדורה 3, טבלה 2', '1042367'),
    ('Pinufiidae / Pinufius rebus', 'family', 3,
     'לא מוכרת; המין בשם Tenellia rebus בתוך Fionidae הרחבה.', 'משפחה ומין מקובלים: Pinufius rebus ב-Pinufiidae.',
     'באתר Pinufius ב-Pinufiidae (לפי WoRMS).', 'Fritts-Penniman et al. 2020; Jia et al. 2023', '412592'),
    ('Fionidae במובן הרחב', 'family', 2,
     'Fionidae אחת רחבה שכוללת את Eubranchus, Abronica, Tergipes, Tergiposacca, Fiona ו-Tenellia.',
     'הסוגים מחולקים בין Fionidae, Eubranchidae, Abronicidae, Trinchesiidae ומשפחות נוספות.',
     'באתר לפי WoRMS (Eubranchidae, Abronicidae, Tergipedidae, Fionidae, Trinchesiidae).',
     'Cella et al. 2016; Korshunova et al. 2017, 2025; Ekimova et al. 2026', ''),
    ('Notodoris', 'genus', 2,
     'לא מוכר; המינים ב-Aegires (למשל Aegires minor, A. gardineri).',
     'סוג מקובל (Notodoris minor, N. gardineri), אף שהמקור שמצוטט ברשומה (Fahey & Gosliner 2004) איחד אותו עם Aegires.',
     'באתר Notodoris (לפי WoRMS).', 'Fahey & Gosliner 2004', '531074'),
    ('Martadoris ו-Tyrannodoris', 'genus', 2,
     'לא בשימוש; המינים נשארים ב-Roboastra / Tambja (למשל Tambja amakusana, Roboastra luteolineata, R. nikolasi).',
     'סוגים מקובלים (Martadoris amakusana, Tyrannodoris luteolineata, T. nikolasi).',
     'באתר Martadoris ו-Tyrannodoris (לפי WoRMS).', 'Willan & Chang 2017, 2018', '1036109'),
    ('Phestilla', 'genus', 2,
     'לא בשימוש; מיני האוכלים אלמוגים ב-Tenellia במובן הרחב.',
     'סוג מקובל; בשמות Tenellia של מינים אלה WoRMS רושם "צורה חלופית".',
     'באתר יש גם Phestilla וגם שמות Tenellia של אותם מינים — ראו בטבלת התיקונים.',
     'Cella et al. 2016; Fritts-Penniman et al. 2020; Wang et al. 2020; Mehrotra et al. 2020', '390813'),
    ('Glaucilla', 'genus', 3,
     'לא בשימוש; Glaucus במובן הרחב (Glaucus marginatus ועוד).', 'סוג מקובל (Glaucilla marginata ועוד).',
     'באתר Glaucilla (לפי WoRMS).', 'Churchill et al. 2014', '534055'),
    ('Aglajidae — חלוקה לסוגים', 'genus', 2,
     'חלוקה ישנה: Philinopsis gardineri, P. reticulata, P. orientalis, P. coronata, P. falciphallus, '
     'Aglaja fulvipunctata, Mariaglaja sandrana.',
     'Tubulophilinopsis gardineri / reticulata, Spinoaglaja orientalis, Spinophallus coronatus / falciphallus, '
     'Biuve fulvipunctata, Mariaglaja tsurugensis. WoRMS מסמן את Spinophallus Zamora-Silva & Malaquias, 2017 '
     'כשם לא תקף (הומונים של Spinophallus Riedel, 1962) אך עדיין מציג את המינים בו.',
     'באתר לפי WoRMS (Biuve, Spinoaglaja, Tubulophilinopsis).',
     'Camacho-García et al. 2014; Zamora-Silva & Malaquias 2017, 2018', ''),
    ('Longibranchus putnami / Eubranchus putnami', 'species', 1,
     'Eubranchus putnami Fernández-Simón & Moles, 2023 (היה Eubranchus sp. 26 במהדורה 2).',
     'Longibranchus putnami (Fernández-Simón & Moles, 2023), בסוג Longibranchus Martynov & Korshunova, 2025.',
     'באתר: Eubranchus sp. 26 — ראו בטבלת התיקונים.', '', '1832557'),
    ('Eubranchus rubropunctatus, E. mandapamensis', 'species', 3,
     'שני המינים ב-Eubranchus.', 'Produnga rubropunctata; Annulorhina mandapamensis.',
     '', '', ''),
    ('Marioniopsis distincta, M. pustulosa, M. pambanensis', 'species', 3,
     'שלושת המינים ב-Marioniopsis.', 'Marionia distincta, M. pustulosa, M. pambanensis — מקובלים ב-Marionia.',
     'באתר Marionia distincta (לפי WoRMS).', '', '736332'),
    ('Tayuva murrea, T. fragilis, T. nubilosa', 'species', 3,
     'שלושת המינים ב-Tayuva (Peltodoris murrea של מהדורה 2 עבר ל-Tayuva).',
     'Peltodoris murrea מקובל; השמות ב-Tayuva לא נמצאו ב-WoRMS.', 'באתר Peltodoris murrea (לפי WoRMS).', '', '578708'),
    ('שמות מינים שהספר משתמש בהם ו-WoRMS לא מקבל', 'species', 3,
     'Doris pecten, D. granulosa; Gymnodoris rubropapulosa; Chromodoris versicolor; Goniobranchus naiki; '
     'Glossodoris pullata; Dendrodoris denisoni; Tritoniopsis alba; Marioniopsis fulvicola; Bornella caledonica; '
     'Facelinella semidecora, F. anulifera; Baeolidia palythoae; Smaragdinella viridis; Acteocina hawaiensis; '
     'Pseudophiline acuticauda; Creseis clava; Stiliger subviridis; Petalifera lafonti.',
     'Doriopsis pecten, D. granulosa; Gymnodoris impudica; Hypselodoris versicolor (taxon inquirendum); '
     'Goniobranchus bombayanus; Ardeadoris pullata; Dendrodoris krusensternii; Tritoniopsis elegans; Marioniopsis levis; '
     'Bornella stellifera; Phidiana semidecora, P. anulifera; Aeolidiopsis palythoae; Smaragdinella calyculata; '
     'Truncacteocina hawaiensis; Pseudophiline hayashii; Creseis acicula; Ercolania subviridis; Phyllaplysia lafonti.',
     'באתר לפי WoRMS.', 'בדיקת השמות מול שירות WoRMS (17/11/2026)', ''),
    ('זיהויים שהשתנו בין המהדורות', 'species', 3,
     'אותו תיאור/תמונה של המהדורה השנייה מופיע בשלישית בשם אחר: Doriprismatica sibogae → D. atromarginata; '
     'Gymnodoris okinawae → G. amakusana; Melibe minuta → M. engeli; Scaphander mundus → S. japonicus; '
     'Bornella johnsonorum → Bornella sp. 1; Goniobranchus setoensis → Goniobranchus sp. 43.',
     'כל השמות הישנים מקובלים ב-WoRMS (Scaphander japonicus הוא Nipponoscaphander japonicus).',
     'לשמות האלה אין תצפיות באתר.', 'השוואה אוטומטית של טקסט המהדורות — לאמת לפי התמונות', ''),
    ('מספור Thuridilla', 'species', 1,
     'מספור sp. של הספר (במהדורה 3: sp. 1-27 ומעלה).',
     'אין שמות sp. ב-WoRMS.',
     'באתר חלק מהמינים לפי Martín-Hervás et al. 2021 (Thuridilla sp. 2, sp. 4 (2021)) וחלק לפי הספר — '
     'ראו בטבלת התיקונים.', 'Martín-Hervás et al. 2021; ספר מהדורות 2 ו-3', ''),
]


def add(apps, schema_editor):
    Issue = apps.get_model('observations', 'IdentificationIssue')
    Topic = apps.get_model('observations', 'DiscussionTopic')
    Species = apps.get_model('observations', 'Species')
    if not Species.objects.exists():
        return  # an empty database (a new install, the test database): nothing to report on
    for key, kind, priority, name, corrected, link, notes in ISSUES:
        transfer_id = uuid.uuid5(NAMESPACE, key)
        if Issue.objects.filter(transfer_id=transfer_id).exists():
            continue
        species = Species.objects.filter(scientific_name=name).first() if name else None
        if name and species is None:
            continue
        valid = ' '.join(corrected.split()[:2]) if corrected else ''  # the binomial, without its author
        corrected_species = (Species.objects.filter(scientific_name=valid).first()
                             if kind in ('worms_name', 'misidentified') and ' sp.' not in corrected else None)
        if corrected_species is not None and corrected_species.pk == getattr(species, 'pk', None):
            corrected_species = None
        Issue.objects.create(transfer_id=transfer_id, kind=kind, priority=priority, status='open', opened_on=OPENED,
                             reporter=REPORTER, species=species, corrected_species=corrected_species,
                             corrected_name=corrected, research_link=link, notes=notes)
    for topic, rank, priority, book, worms, site, sources, aphia in TOPICS:
        transfer_id = uuid.uuid5(NAMESPACE, 'topic-' + topic)
        if Topic.objects.filter(transfer_id=transfer_id).exists():
            continue
        Topic.objects.create(transfer_id=transfer_id, topic=topic, rank=rank, priority=priority, status='open',
                             opened_on=OPENED, book_treatment=book, worms_treatment=worms, site_treatment=site,
                             decision='ברירת המחדל לפי כלל האתר: שם WoRMS.', sources=sources,
                             worms_link=WORMS + aphia if aphia else '', notes=RULE)


def remove(apps, schema_editor):
    apps.get_model('observations', 'IdentificationIssue').objects.filter(
        transfer_id__in=[uuid.uuid5(NAMESPACE, i[0]) for i in ISSUES]).delete()
    apps.get_model('observations', 'DiscussionTopic').objects.filter(
        transfer_id__in=[uuid.uuid5(NAMESPACE, 'topic-' + t[0]) for t in TOPICS]).delete()


class Migration(migrations.Migration):
    dependencies = [('observations', '0105_discussion_topics')]
    operations = [migrations.RunPython(add, remove)]
