"""Identification texts (identification_he / identification_en) for the gallery's undescribed "Genus sp. N" species,
written in Claude's own words from the species accounts of Gosliner, Valdés & Behrens, "Nudibranch & Sea Slug
Identification -- Indo-Pacific" (3rd edition 2026; the 2nd edition 2018 where the 3rd has no matching account), with the
source at the end of each text: the book, its edition, the page and the name the book uses; where the 3rd edition
renamed the species, its 2nd-edition page and name are cited as well. They summarise the book's diagnostic marks; they do not copy its wording.

Where the 3rd edition renumbered or renamed the animal, the text follows its 3rd-edition account and names it (see the
identification-issues rows of migration 0106). Species whose identity is still in question (Aegires sp. 7, the
Thuridilla, Tritonia sp. 3, Coryphellina sp. 1) get nothing here.
Safe in both environments: a species is found by scientific name, and a text is written only where both identification
fields are still empty, so an edited text is never overwritten.
"""
from django.db import migrations

B3 = 'Gosliner, Valdés & Behrens 2026'
B2 = 'Gosliner, Valdés & Behrens 2018'
EDITION = {B3: ('מהדורה 3', '3rd ed.'), B2: ('מהדורה 2', '2nd ed.')}
# The 2nd-edition page of the species whose 3rd-edition name differs: both editions are cited, since a species may
# keep its 2nd-edition name on the site (neither numbering is better) -- the reader must know which one is meant.
SECOND_EDITION_PAGE = {'Aegires sp. 8': '68', 'Atagema sp. 12': '117', 'Dermatobranchus sp. 17': '240', 'Dermatobranchus sp. 6': '234', 'Eubranchus sp. 15': '279', 'Eubranchus sp. 17': '279', 'Eubranchus sp. 23': '281', 'Eubranchus sp. 26': '281', 'Eubranchus sp. 27': '281', 'Goniobranchus sp. 14': '145', 'Goniodoridella sp. 8': '51', 'Haminoea sp. 5': '351', 'Marionia sp. 24': '266', 'Marionia sp. 6': '262', 'Phyllidiella sp. 2': '219', 'Tenellia sp. 17': '288', 'Tenellia sp. 81': '299', 'Thecacera sp. 8': '36', 'Tritonia sp. 4': '257'}

# scientific name, Hebrew, English, source (book, page, the name it uses)
TEXTS = [
    ('Aegires sp. 8',
     'חיה זעירה, ורודה כולה, עם גב חלק; זיזים אדומים גדולים סביב הזימים מסתירים אותם כמעט לגמרי. אורך כ־3 מ״מ. '
     'פיליפינים ואינדונזיה, על ספוגים גירניים קטנים בין מושבות של מיתרניים.',
     'A tiny, entirely pink animal with a smooth back; large red processes around the gill all but hide it. About 3 mm. '
     'Philippines and Indonesia, on small calcareous sponges among colonial tunicates.',
     B3, '28-29', 'Aegires sp. 13'),
    ('Atagema sp. 12',
     'לבן אחיד, עם רשת עדינה של בליטות קטנות על הגב; הזימים פונים לאחור ומוגנים בשלוש אונות; המחושים צהבהבים. '
     'אורך כ־35 מ״מ. פיליפינים, שוניות טלאים רדודות בעומק כ־15 מ׳.',
     'Plain white with a fine network of small tubercles over the back; the gill points backwards and is guarded by '
     'three lobes; rhinophores yellowish. About 35 mm. Philippines, shallow patch reefs at about 15 m.',
     B3, '44-45', 'Atagema sp. 11'),
    ('Atagema sp. 13',
     'אפור, עם כתמים כהים יותר בין רכסי הגב; לחלק מהבליטות קצה לבן אטום; שלושה ענפי זימים מוארכים. אורך כ־30 מ״מ. '
     'פיליפינים, שוניות רדודות בעומק כ־15 מ׳.',
     'Grey, with darker spots in the spaces between the dorsal ridges; some tubercles tipped opaque white; three '
     'elongate gill branches. About 30 mm. Philippines, shallow reefs at about 15 m.',
     B2, '117', 'Atagema sp. 13'),
    ('Dermatobranchus sp. 17',
     'גוף לבן עם קווי אורך מקוטעים ונקודות שחורות שמוקפות טבעת בהירה; מחושים שחורים עם כתום. אורך כ־25 מ״מ. '
     'פיליפינים, שוניות בעומק בינוני (כ־22 מ׳).',
     'White body with broken longitudinal lines and black dots each ringed in a paler colour; rhinophores black with '
     'orange. About 25 mm. Philippines, mid-depth reefs (about 22 m).',
     B3, '260-261', 'Dermatobranchus sp. 3'),
    ('Dermatobranchus sp. 6',
     'לבן, עם רכסי אורך לבנים אטומים ושטחים של פיגמנט שחור ביניהם; המחושים בקצוות כתומים; פרגוד הפה כחלחל ושוליו '
     'כתומים־שמנת. אורך כ־15 מ״מ. פיליפינים ואינדונזיה. במהדורה השלישית הוא הועבר לסוג Armina.',
     'White, with opaque white longitudinal ridges and patches of black pigment between them; rhinophores tipped '
     'orange; oral veil bluish with an orange-cream edge. About 15 mm. Philippines and Indonesia. The 3rd edition moves '
     'it to Armina.',
     B3, '254-255', 'Armina sp. 10'),
    ('Eubranchus sp. 15',
     'שקוף־לבן, והאיברים הפנימיים האדומים נראים דרך הגוף; זיזי הגב שקופים עם קצוות לבנים מסועפים, ונראים כמו פוליפים '
     'של הידרואידים. מחושים ארוכים, מחושי פה קצרים ומחודדים. אורך כ־7 מ״מ. אינדונזיה.',
     'Translucent white, the red internal organs showing through; the cerata are clear with branched opaque white tips '
     'and look like hydroid polyps. Long rhinophores, short tapering oral tentacles. About 7 mm. Indonesia.',
     B3, '320-321', 'Eubranchus sp. 17'),
    ('Eubranchus sp. 17',
     'סגול; זיזי הגב שקופים ותפוחים, עם קצה דמוי פטמה ובלוטת עיכול מסועפת מעט; מחושי הפה והמחושים החלקים סגולים. '
     'אורך כ־7 מ״מ. אינדונזיה.',
     'Purple; cerata clear and swollen, each ending in a nipple-like tip, with sparsely branched digestive gland; oral '
     'tentacles and the smooth rhinophores purple. About 7 mm. Indonesia.',
     B3, '320-321', 'Eubranchus sp. 19'),
    ('Eubranchus sp. 2',
     'שקוף, מנוקד בנקודות חומות ולבנות על כל הגוף; זיזי הגב תפוחים, עם צינורות צרים וצהובים של בלוטת העיכול וקצוות '
     'לבנים; מחושים חלקים עם כתמים לבנים וחומים. אורך כ־10 מ״מ. אינדונזיה.',
     'Clear, dotted brown and white all over; cerata swollen, with narrow yellow digestive-gland ducts and white tips; '
     'smooth rhinophores spotted white and brown. About 10 mm. Indonesia.',
     B3, '316-317', 'Eubranchus sp. 2'),
    ('Eubranchus sp. 23',
     'שקוף־לבן, ובלוטת העיכול הצהבהבה נראית דרך הגב; הגב, זיזי הגב, המחושים ומחושי הפה מנוקדים בכתמים שחורים גדולים. '
     'אורך כ־25 מ״מ. מערב האוקיינוס השקט, על הידרואידים מסוג Plumularia במדרונות שונית.',
     'Translucent white with the yellowish digestive gland visible through the back; back, cerata, rhinophores and oral '
     'tentacles all marked with large black spots. About 25 mm. Western Pacific, on plumularian hydroids on reef slopes.',
     B3, '320-321', 'Eubranchus sp. 25'),
    ('Eubranchus sp. 26',
     'חום כהה; בחצי התחתון של זיזי הגב בליטות לבנות, והחלק העליון רחב, חלק ולבנבן, עם טבעת כתומה מתחת לקצה. ניזון '
     'מהידרואיד חום כהה ומוסווה עליו היטב. אורך כ־20 מ״מ. המלדיביים ומערב האוקיינוס השקט. תואר ב־2023; במהדורה השלישית '
     'בשם Eubranchus putnami, וב־WoRMS בשם Longibranchus putnami.',
     'Dark brown; the lower half of each ceras carries white tubercles, the upper part is broad, smooth and whitish with '
     'an orange ring below the tip. Feeds on, and is very well hidden on, a dark brown hydroid. About 20 mm. Maldives '
     'and western Pacific. Described in 2023; the 3rd edition calls it Eubranchus putnami, WoRMS Longibranchus putnami.',
     B3, '322-323', 'Eubranchus putnami'),
    ('Eubranchus sp. 27',
     'חום, עם שולי גב לבנים ופיגמנט לבן צפוף על המחושים; זיזי הגב קצרים ומעוגלים, חומים ומנומרים בלבן. מוסווה מאוד '
     'על ההידרואיד שממנו הוא ניזון. אורך כ־15 מ״מ. אינדונזיה.',
     'Brown, with white edges to the back and dense white on the rhinophores; cerata short and rounded, brown mottled '
     'with white. Very hard to see on the hydroid it eats. About 15 mm. Indonesia.',
     B3, '322-323', 'Eubranchus sp. 29'),
    ('Facelina sp. 4',
     'כתום שקוף עם נקודות לבנות קטנות; זיזי הגב כתומים, מנוקדים בלבן ובעלי קצה לבן; המחושים חלקים, כתומים בבסיסם '
     'ולבנים בקצה; על מחושי הפה הכתומים פס לבן ממש מתחת לקצה. אורך כ־10 מ״מ. פיליפינים, מים רדודים על כתמי שברי '
     'אלמוגים בין שטחי חול.',
     'Translucent orange with small white dots; cerata orange, white-speckled and white-tipped; rhinophores smooth, '
     'orange at the base and white at the tip; the orange oral tentacles have a white band just short of the tip. '
     'About 10 mm. Philippines, shallow rubble patches between sand.',
     B3, '346-347', 'Facelina sp. 4'),
    ('Favorinus sp. 10',
     'לבן שקוף עם נקודות לבנות על הגב ועל זיזי הגב; ענפים צרים וחומים כהים של בלוטת העיכול נראים בתוך זיזי הגב; '
     'מחושים קצרים וחלקים. אורך כ־15 מ״מ. ים סוף ומערב האוקיינוס השקט.',
     'Translucent white with white dots on the back and cerata; narrow dark brown digestive-gland branches show inside '
     'the cerata; rhinophores short and smooth. About 15 mm. Red Sea and western Pacific.',
     B3, '354-355', 'Favorinus sp. 10'),
    ('Goniobranchus sp. 14',
     'תכלת, עם שטח צהוב גדול שעליו עיגולים לבנים, כל אחד במסגרת צהובה כהה; קווים כחולים כהים עד שחורים יוצאים מהצהוב '
     'אל שולי הגוף, ופס שחור עובר סביב הגב מעט פנימה מהשוליים; מחושים וזימים בתכלת וכחול כהה. אורך כ־60 מ״מ. '
     'ראוניון, שוניות סלעיות.',
     'Pale blue, with a large yellow area set with white circles, each ringed darker yellow; dark blue to black lines '
     'run from the yellow out to the body margin, and a black band circles the back just inside it; rhinophores and '
     'gill pale and dark blue. About 60 mm. Réunion, rocky reefs.',
     B3, '168-169', 'Goniobranchus sp. 18'),
    ('Goniodoridella sp. 8',
     'לבן כולו, עם פס רוחב חום כהה עד שחור על הראש מאחורי המחושים, ולעיתים פס שני מאחורי הזימים; נספחי הזימים '
     'ארוכים ודמויי משוט; מחושים חלקים. אורך כ־6 מ״מ. האוקיינוס ההודי ומערב האוקיינוס השקט, מדרונות חול עם שברי '
     'אלמוגים. תואר ב־2022 בשם Murphydoris cobbi.',
     'All white, with a dark brown to black crossband on the head behind the rhinophores and sometimes another behind '
     'the gill; gill appendages long and paddle-shaped; rhinophores smooth. About 6 mm. Indian Ocean and western '
     'Pacific, sandy slopes with coral rubble. Described in 2022 as Murphydoris cobbi.',
     B3, '144-145', 'Murphydoris cobbi'),
    ('Haminoea sp. 5',
     'גוף לבנבן שקוף, צפוף בנקודות לבנות ועם מעט כתמים שחורים גדולים; הקונכייה שקופה וצבע הגוף נראה דרכה. אורך '
     'כ־8 מ״מ. פיליפינים, זוחל בגלוי על מדרונות חול. במהדורה השלישית הועבר לסוג Liloa.',
     'Translucent whitish body crowded with white dots and a few large black spots; the shell is clear, so the body '
     'colour shows through. About 8 mm. Philippines, crawling in the open on sandy slopes. The 3rd edition places it '
     'in Liloa.',
     B3, '398-399', 'Liloa sp. 9'),
    ('Haminoeid sp. 2',
     'זעיר ושקוף, עם פיגמנט לבן וטבעות שחורות אופייניות; לחיה "זנב" ארוך מאוד, פי שניים עד שלושה מאורך שאר הגוף. '
     'אורך כ־3 מ״מ. מערב האוקיינוס השקט, בצד התחתון של שברי אלמוגים; ניזון מכחוליות.',
     'Tiny and clear, with white pigment and distinctive black rings; it has a very long "tail", two to three times '
     'the length of the rest of the body. About 3 mm. Western Pacific, under coral rubble; feeds on cyanobacteria.',
     B3, '406-407', 'Haminoeid sp. 2'),
    ('Marionia sp. 24',
     'לבן־שמנת חיוור, עם זימים משניים מסועפים מעט ונרתיקי מחושים שפיהם רחב. אורך כ־8 מ״מ. פיליפינים, על אלמוגים רכים '
     'בשוניות רדודות (10–15 מ׳). במהדורה השלישית הועבר לסוג Marioniopsis.',
     'Pale off-white, with only slightly branched secondary gills and rhinophore sheaths with a wide opening. About '
     '8 mm. Philippines, on soft corals on shallow reefs (10–15 m). The 3rd edition places it in Marioniopsis.',
     B3, '284-285', 'Marioniopsis sp. 22'),
    ('Marionia sp. 6',
     'ירוק עז עם קווי רוחב לבנים ורשת לבנה בבסיס הזימים המשניים; הזימים ירוקים בהירים, קצרים ומנוצים מאוד; 3–4 זוגות '
     'של מחושי פרגוד, מפוצלים או פשוטים. עד כ־100 מ״מ. מערב האוקיינוס השקט, טבלאות שונית רדודות מתחת לשברי אלמוגים; '
     'פעיל בלילה וניזון מאלמוג רך מהסוג Lemnalia. במהדורה השלישית הועבר לסוג Marioniopsis.',
     'Bright green with white crosslines and a white network at the bases of the secondary gills, which are light '
     'green, short and densely pinnate; 3–4 pairs of simple or divided velar tentacles. Up to about 100 mm. Western '
     'Pacific, shallow reef flats under rubble; active at night, feeding on the soft coral Lemnalia. The 3rd edition '
     'places it in Marioniopsis.',
     B3, '282-283', 'Marioniopsis sp. 11'),
    ('Nembrotha sp. 5',
     'ירקרק כולו, עם שורות אורך של נקודות וקווים לבנים וכתמים לבנים על הראש ובבסיס הזימים; בסיסי הזימים והמחושים '
     'סגולים וקצותיהם אדומים. אורך כ־30 מ״מ. אינדונזיה, שוניות סלעיות רדודות.',
     'Greenish all over, with lengthwise rows of white dots and lines and white patches on the head and at the gill '
     'base; gill and rhinophores purple at the base, red at the tips. About 30 mm. Indonesia, shallow rocky reefs.',
     B3, '106-107', 'Nembrotha sp. 5'),
    ('Noumeaella sp. 3',
     'לבן שקוף, מכוסה רובו בשכבה לבנה אטומה ועם אזורים שקופים; זיזי הגב מעוקלים פנימה ובאותו דגם צבע; מחושים בעלי '
     'פטמות ומחושי פה בגוון חום עם לבן. אורך כ־10 מ״מ. מערב האוקיינוס השקט; נמצא בצד התחתון של הספוג Phyllospongia '
     'lamellosa, ניזון מהידרואידים קטנים.',
     'Translucent white, mostly covered in an opaque white crust with some clear patches; inward-curving cerata in the '
     'same pattern; papillate rhinophores and the oral tentacles brown with white. About 10 mm. Western Pacific; found '
     'under the sponge Phyllospongia lamellosa, feeding on small hydroids.',
     B3, '356-357', 'Noumeaella sp. 3'),
    ('Phyllidiella sp. 2',
     'לבן עם רשת של קווים שחורים על הגב, ובליטות גדולות וחרוטיות בקבוצות של 2–5; מחושים שחורים. אורך כ־45 מ״מ. ים '
     'סוף (ערב הסעודית), שוניות טלאים סלעיות בלגונות מוגנות, כ־20 מ׳.',
     'White with a network of black lines over the back, and large conical tubercles grouped in twos to fives; '
     'rhinophores black. About 45 mm. Red Sea (Saudi Arabia), rocky patch reefs in sheltered lagoons, about 20 m.',
     B3, '244-245', 'Phyllidiella sp. 5'),
    ('Phyllodesmium sp. 4',
     'לבנבן־חום שקוף; זיזי הגב חומים וחסרי פיגמנט נוסף. דומה מבחוץ ל־Phyllodesmium magnum, אבל האנטומיה הפנימית שונה '
     'לגמרי. אורך כ־65 מ״מ. מערב האוקיינוס ההודי, מתחת לשברי אלמוגים.',
     'Translucent whitish brown; cerata brownish with no other pigment. Looks like Phyllodesmium magnum outside but is '
     'very different internally. About 65 mm. Western Indian Ocean, under coral rubble.',
     B3, '374-375', 'Phyllodesmium sp. 4'),
    ('Phyllodesmium sp. 6',
     'בצבע שמנת אחיד; על המחושים פטמות שבקושי נראות; זיזי הגב צפופים ומכוסים פטמות רבות, חלקן עם קצה חום. אורך '
     'כ־45 מ״מ. קניה.',
     'Uniform cream; rhinophores with barely visible papillae; cerata closely packed and covered in many papillae, some '
     'tipped brown. About 45 mm. Kenya.',
     B3, '376-377', 'Phyllodesmium sp. 6'),
    ('Sakuraeolis sp. 1',
     'לבן אטום, עם שני כתמים צהובים־כתומים גדולים בצידי הראש; המחושים חומים שקופים עם קצה צהוב; זיזי הגב חומים '
     'ומנוקדים בלבן. אורך כ־18 מ״מ. אינדונזיה.',
     'Opaque white, with two large yellow-orange patches on the sides of the head; rhinophores clear brown with yellow '
     'tips; cerata brown with white dots. About 18 mm. Indonesia.',
     B2, '324', 'Sakuraeolis sp. 1'),
    ('Stiliger sp. 1',
     'כחלחל, עם צהוב וכחול על זיזי הגב ובלוטת עיכול כהה. בעבר שויך לסוג Costasiella כי העיניים קרובות זו לזו, אבל '
     'לפי הספר זהו מין לא מתואר של Stiliger. אורך כ־8 מ״מ. מערב ומרכז האוקיינוס השקט.',
     'Bluish, with yellow and blue on the cerata and a dark digestive gland. Once placed in Costasiella because the '
     'eyes are close together, but the book treats it as an undescribed Stiliger. About 8 mm. Western and central '
     'Pacific.',
     B2, '408', 'Stiliger sp. 1'),
    ('Tenellia sp. 17',
     'גוף חום כהה עם סימנים לבנים סביב המחושים; לכל זיז גב קצה כחול ומתחתיו טבעות צהובה, כחולה ולבנה. אורך כ־10 מ״מ. '
     'איחוד האמירויות.',
     'Deep brown body with white marks around the rhinophores; each ceras has a blue tip with yellow, blue and white '
     'rings below it. About 10 mm. United Arab Emirates.',
     B3, '328-329', 'Tenellia sp. 15'),
    ('Tenellia sp. 18',
     'כתום עם הרבה לבן אטום; צידם הקדמי של זיזי הגב לבן, האחורי בצבע שמנת, והקצוות כחולים; המחושים ומחושי הפה לבנים '
     'עם מחצית עליונה כתומה. אורך כ־8 מ״מ. פפואה גינאה החדשה ומלזיה, מתחת לשברי אלמוגים בשוניות מחסום (8–15 מ׳).',
     'Orange with plenty of opaque white; the cerata are white in front, cream behind and blue at the tips; rhinophores '
     'and oral tentacles white with orange upper halves. About 8 mm. Papua New Guinea and Malaysia, under rubble on '
     'barrier reefs (8–15 m).',
     B3, '328-329', 'Tenellia sp. 18'),
    ('Tenellia sp. 29',
     'רוב הגב מכוסה לבן אטום, פרט למחושים ולמחושי הפה; זיזי הגב אדומים עם מעט נקודות לבנות. אורך כ־9 מ״מ. אינדונזיה.',
     'Most of the back covered in opaque white, except the rhinophores and oral tentacles; cerata red with a few white '
     'dots. About 9 mm. Indonesia.',
     B3, '330-331', 'Tenellia sp. 29'),
    ('Tenellia sp. 34',
     'כתום שקוף עם ראש ורוד; מחושי הפה והמחושים כתומים; לבסיס זיזי הגב ברק כחלחל וקצותיהם כתומים. אורך כ־7 מ״מ. '
     'האוקיינוס ההודי ומערב האוקיינוס השקט, בצד התחתון של שברי אלמוגים (1–10 מ׳).',
     'Translucent orange with a pink head; oral tentacles and rhinophores orange; cerata with a bluish sheen at the base '
     'and orange tips. About 7 mm. Indian Ocean and western Pacific, under rubble (1–10 m).',
     B3, '332-333', 'Tenellia sp. 34'),
    ('Tenellia sp. 39',
     'לבן שקוף מכוסה בצפיפות בלבן אטום; גם זיזי הגב לבנים, עם קטעים שקופים ופס צהוב עז מתחת לקצה; למחושים ולמחושי '
     'הפה פסים צהובים ואדומים. אורך כ־8 מ״מ. מערב האוקיינוס השקט, שוניות טלאים מתחת לשברי אלמוגים (5–10 מ׳).',
     'Translucent white thickly coated in opaque white; the cerata are white too, with clear sections and a bright '
     'yellow band below the tip; rhinophores and oral tentacles banded yellow and red. About 8 mm. Western Pacific, '
     'patch reefs under rubble (5–10 m).',
     B3, '332-333', 'Tenellia sp. 39'),
    ('Tenellia sp. 65',
     'לבן שקוף כולו, ובלוטת העיכול הלבנה נראית דרך הגוף וזיזי הגב; המחושים בצבע שמנת־לבן; מחושי הפה שקופים עם קצה '
     'לבן. אורך כ־9 מ״מ. פיליפינים, מתחת לשברי אלמוגים בשוניות רדודות.',
     'Translucent white throughout, with the white digestive gland visible through body and cerata; rhinophores '
     'cream-white; oral tentacles clear with white tips. About 9 mm. Philippines, under rubble on shallow reefs.',
     B3, '336-337', 'Tenellia sp. 65'),
    ('Tenellia sp. 71',
     'לבן שקוף עם כתמים לבנים גדולים; המחושים ומחושי הפה חומים־אדמדמים עם קצה לבן; זיזי הגב שקופים, ורואים בהם את '
     'ענפי בלוטת העיכול החומים ואת שקי הצורבים הלבנים; עליהם כתמים שחורים גדולים וקצה לבן. אורך כ־7 מ״מ. פיליפינים.',
     'Translucent white with large white spots; rhinophores and oral tentacles reddish brown with white tips; the clear '
     'cerata show brown digestive-gland branches and white cnidosacs, and carry large black spots and white tips. About '
     '7 mm. Philippines.',
     B3, '338-339', 'Tenellia sp. 71'),
    ('Tenellia sp. 81',
     'חום בהיר עם קווי רוחב לאורך הגוף; מוסווה מאוד על האלמוג המאכסן שלו, Gardineroseris planulata. אורך כ־18 מ״מ. '
     'פיליפינים, שוניות רדודות (1–10 מ׳).',
     'Pale brown with crosswise lines along the body; very hard to see on its host coral, Gardineroseris planulata. '
     'About 18 mm. Philippines, shallow reefs (1–10 m).',
     B3, '344-345', 'Tenellia sp. 91'),
    ('Thecacera sp. 8',
     'כתום עם סימנים סגולים עד שחורים; הזיזים שליד המחושים מצויצים בקצותיהם. נבדל מקרובו הדומה במחושים שקצותיהם '
     'תמיד שחורים ובסידור אחר של הכתמים. אורך כ־40 מ״מ. מלזיה, אינדונזיה, פיליפינים ויפן, שוניות רדודות. תואר '
     'ב־2026 בשם Thecacera pikachu.',
     'Orange with purple to black markings; the processes beside the rhinophores are fringed. Told apart from its close '
     'look-alike by rhinophores that always have black tips and a different pattern of spots. About 40 mm. Malaysia, '
     'Indonesia, Philippines and Japan, shallow reefs. Described in 2026 as Thecacera pikachu.',
     B3, '94-95', 'Thecacera pikachu'),
    ('Tritonia sp. 4',
     'לבן אטום עם מעט ירוק; ענפי הזימים קצרים ומסולסלים, ונראים כמו אלמוגים רכים ממשפחת Xeniidae כשהם מכווצים; מחושי '
     'הפרגוד פשוטים, קצרים ומעוגלים. אורך כ־15 מ״מ. פפואה גינאה החדשה, שוניות רדודות (כ־15 מ׳) ליד מושבות של '
     'Anthelia. במהדורה השלישית הועבר לסוג Marioniopsis.',
     'Opaque white with a little green; the gill branches are short and curled, like contracted xeniid soft corals; '
     'velar tentacles simple, short and rounded. About 15 mm. Papua New Guinea, shallow reefs (about 15 m) near '
     'colonies of Anthelia. The 3rd edition places it in Marioniopsis.',
     B3, '280-281', 'Marioniopsis sp. 6'),
]


def _pages(page, lang):
    return (f'עמ׳ {page}' if lang == 'he' else f"{'pp.' if '-' in page else 'p.'} {page}")


def source(name, book, page, as_name, lang):
    """The source at the end of a text: the book with its edition, page and the name it uses there; for a species whose
    3rd-edition name differs from the site's (2nd-edition) name, the 2nd edition too."""
    he = lang == 'he'
    edition = EDITION[book][0 if he else 1]
    parts = [f"{book}, {edition}, {_pages(page, lang)}, {'בשם' if he else 'as'} {as_name}"]
    if book == B3 and as_name != name and name in SECOND_EDITION_PAGE:
        parts.append(f"{B2}, {EDITION[B2][0 if he else 1]}, {_pages(SECOND_EDITION_PAGE[name], lang)}, "
                     f"{'בשם' if he else 'as'} {name}")
    return (' (לפי ' if he else ' (after ') + '; '.join(parts) + ')'


def add(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    for name, he, en, book, page, as_name in TEXTS:
        species = Species.objects.filter(scientific_name=name).first()
        if species is None or (species.identification_he or '').strip() or (species.identification_en or '').strip():
            continue
        species.identification_he = he + source(name, book, page, as_name, 'he')
        species.identification_en = en + source(name, book, page, as_name, 'en')
        species.save(update_fields=['identification_he', 'identification_en'])


def remove(apps, schema_editor):
    Species = apps.get_model('observations', 'Species')
    for name, he, en, book, page, as_name in TEXTS:
        Species.objects.filter(scientific_name=name, identification_he=he + source(name, book, page, as_name, 'he')).update(
            identification_he='', identification_en='')


class Migration(migrations.Migration):
    dependencies = [('observations', '0106_nssi3_findings')]
    operations = [migrations.RunPython(add, remove)]
