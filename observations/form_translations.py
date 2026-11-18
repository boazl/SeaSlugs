"""English for the observation form (/observations/new/, /observations/<id>/edit/): its labels, help texts, choices and
error messages, the texts its scripts show, and the messages after saving. Merged into the template filter's TRANSLATIONS
(templatetags/seaslugs_i18n.py), so `|t:lang` and SampleForm.localize use the same table. Messages that carry a value
(a name, a size) are matched by FORM_PATTERNS."""
import re

FORM_TRANSLATIONS = {
    # page and links
    'בחרו את סוג הדגימה: מין יחיד, סוג, משפחה, סדרה או אוסף מינים. הסדרה, המשפחה, הסוג והמין משפיעים זה על זה, ורק השדות שמתאימים לסוג הדגימה זמינים. דגימת מין מחייבת מין; אוסף מחייב כותרת, ללא בחירת מין. בשניהם נדרש מסע צלילה (הכולל מדינה, אזור ושנה) ותמונה או סרטון (אפשר גם שניהם). אוספים מתפרסמים במסעות הצלילה לאחר אישור מנהל. ללא העלאת תמונה תוצג התמונה המקדימה של YouTube. מין חדש לאזור מתפרסם מיד אם כל הנתונים מזוהים; אחרת התצפית ממתינה לבדיקה.':
        'Choose the observation type: a single species, a genus, a family, an order or a species collection. The order, family, '
        'genus and species depend on one another, and only the fields that fit the type are available. A species observation '
        'needs a species; a collection needs a title and no species. Both need a dive trip (with its country, region and year) '
        'and a photo or a video (or both). Collections are published on the dive trips after a manager approves them. Without '
        'an uploaded photo the YouTube preview is shown. A species new to its area is published at once when everything is '
        'identified; otherwise the observation waits for review.',
    'מחיקת התצפית מהמין': 'Remove the observation from the species',
    'מחיקת התמונה': 'Delete the photo',
    'מחיקת קישור הסרטון': 'Delete the video link',
    'המין לא ברשימה? הוספת מין חדש לרשימה': 'Species not in the list? Add a new species',
    'הצלם לא ברשימה? הוספת צלם אורח (צלם בלי חשבון באתר)': 'Photographer not in the list? Add a guest photographer (without an account)',
    'המסע או אתר הצלילה לא ברשימה? הוספת מסע חדש (אפשר להוסיף בו גם אתר חדש)':
        'Dive trip or dive site not in the list? Add a new dive trip (a new site can be added there too)',
    # fields
    'סוג הסרטון': 'Observation type',
    'מין יחיד': 'Single species',
    'אוסף מינים / מסע צלילה': 'Species collection / dive trip',
    'כותרת הגלריה': 'Gallery title',
    'כותרת הגלריה באנגלית': 'Gallery title in English',
    'מוצגת כשהאתר באנגלית; כשהשדה ריק מוצגת במקומה כותרת באנגלית שנבנית מהמקום ומהתאריך של המסע.':
        'Shown on the English site; when empty, an English title built from the trip’s place and date is shown instead.',
    'הקלידו לחיפוש…': 'Type to search…',
    'שם המין בלבד, בלי הסוג (הסוג בשדה שלמעלה). אפשר לכלול cf. / sp. 7 וכד׳ כפי שהם רשומים ברשימת המינים.':
        'The species epithet only, without the genus (the genus is in the field above). cf. / sp. 7 etc. may be included as listed in the species list.',
    'השם המדעי המלא (כולל מחבר ותוספות)': 'Full scientific name (with author and qualifiers)',
    'מתעדכן אוטומטית לפי הסדרה/המשפחה/הסוג/המין שנבחרו, סימון הזהות (cf./aff.) ושלב החיים.':
        'Updated automatically from the chosen order / family / genus / species, the identification qualifier (cf./aff.) and the life stage.',
    'סימון זהות לא ודאית': 'Uncertain identification',
    'cf. = דומה ל…, aff. = קרוב ל… — מוצג בין הסוג למין. רק בדגימה מסוג ״מין״. הערכים נשמרים בטבלת העזר.':
        'cf. = compare with…, aff. = close to… — shown between the genus and the species. Species observations only. The values are kept in a reference table.',
    'שלב חיים': 'Life stage',
    'למשל juv. = פרט צעיר — מוצג אחרי השם. הערכים נשמרים בטבלת העזר.':
        'For example juv. = juvenile — shown after the name. The values are kept in a reference table.',
    'ללא': 'None',
    '+ הוספת ערך חדש לרשימה': '+ Add a new value to the list',
    'מין אחר': 'Other species',
    'אם המין לא נמצא ברשימה שלמעלה, אפשר לפרט כאן במקום לבחור מהרשימה.':
        'If the species is not in the list above, describe it here instead of choosing from the list.',
    'אם המסע לא מופיע ניתן להוסיף מסע באזור המסעות ולחזור על התהליך, או להשתמש בנתונים מתצפית זאת ליצירת מסע של צלילה אחת (ואפשר גם להוסיף לו תצפיות). סמנו את התיבה שלמטה ליצירה אוטומטית של מסע מתצפית זו.':
        'If the dive trip is not listed, you can add one in the dive trips section and come back, or use this observation’s '
        'details to create a one-dive trip (more observations can be added to it later). Tick the box below to create the '
        'trip from this observation automatically.',
    'יצירה אוטומטית של מסע מתצפית זו': 'Create a dive trip from this observation',
    'בחירת המסע מהרשימה מושבתת, וייווצר מסע של צלילה אחת לפי האזור, השנה, החודש, האתר והיום של התצפית.':
        'The trip list is disabled, and a one-dive trip is created from the observation’s region, year, month, site and day.',
    'אזור המסע': 'Trip region',
    'שנת הצלילה': 'Dive year',
    'חודש הצלילה': 'Dive month',
    'אתר צלילה': 'Dive site',
    'בחרו…': 'Choose…',
    'אחר...': 'Other...',
    'שם אתר הצלילה החדש בעברית': 'New dive site name in Hebrew',
    'האתר יתווסף לרשימת אתרי הצלילה של האזור של המסע.': 'The site is added to the dive sites of the trip’s region.',
    'שם אתר הצלילה החדש באנגלית (לא חובה)': 'New dive site name in English (optional)',
    'יום': 'Day',
    'עומק במטרים': 'Depth (m)',
    'קישור YouTube': 'YouTube link',
    'אפשר להשאיר ריק כאשר מעלים תמונה. ניתן להוסיף סרטון בהמשך.': 'May be left empty when a photo is uploaded. A video can be added later.',
    'תמונה חלופית (רשות)': 'Alternate photo (optional)',
    'JPEG, PNG או WebP, עד 10MB ועד 25 מיליון פיקסלים. מומלץ צילום רוחבי 1920×1080 ומעלה. נשמור JPEG עד 1920×1080, ללא חיתוך או הגדלת תמונה קטנה. תמונה שהועלתה תשמש כתצוגה מקדימה לסרטון; ללא סרטון תיפתח התמונה המלאה. ללא תמונה נשתמש בתצוגה המקדימה של YouTube. העלו רק תמונות שיש לכם הרשאה לפרסם.':
        'JPEG, PNG or WebP, up to 10MB and 25 megapixels. A landscape photo of 1920×1080 or more is recommended. It is saved as a '
        'JPEG of up to 1920×1080, without cropping or enlarging a small photo. An uploaded photo is the video’s preview; without a '
        'video the full photo opens. Without a photo the YouTube preview is used. Upload only photos you have permission to publish.',
    'או: תמונה קיימת בגלריה': 'Or: an existing gallery photo',
    'במקום להעלות קובץ אפשר להציג תמונה שכבר קיימת בגלריה: הדביקו את כתובת התמונה (כפתור "העתקת כתובת התמונה"), או בחרו מהגלריה. התצפית תצביע על אותו קובץ, בלי להעתיק אותו. רק אחד משני השדות — תמונה חלופית או תמונה קיימת בגלריה — יכול להיות מוגדר. מחיקת הכתובת מבטלת את התמונה הקיימת בגלריה.':
        'Instead of uploading a file you can show a photo already in the gallery: paste its address (the "Copy the photo address" '
        'button), or pick it from the gallery. The observation points at the same file without copying it. Only one of the two '
        'fields — an alternate photo or an existing gallery photo — can be set. Erasing the address removes the gallery photo.',
    ' לתצפית יש תמונה חלופית משלה — כדי לבחור תמונה קיימת יש למחוק אותה קודם.':
        ' The observation has its own alternate photo — delete it first to choose an existing one.',
    'הערה לתצפית (עברית)': 'Observation note (Hebrew)',
    'מוצגת ליד התצפית בעמוד המין. שמות מדעיים מוצגים בנטוי אוטומטית.':
        'Shown with the observation on the species page. Scientific names are set in italics automatically.',
    'הערה לתצפית (אנגלית)': 'Observation note (English)',
    'התצפית נרשמת על שם הצלם. צלם בלי חשבון באתר מסומן "צלם אורח".':
        'The observation is credited to the photographer. A photographer without an account is marked "guest photographer".',
    'לא נדרש לתצפית ברמת סדרה, משפחה או סוג.': 'Not needed for an order, family or genus observation.',
    'שחזור התצפית (ביטול המחיקה)': 'Restore the observation (undo the deletion)',
    'התצפית מחוקה. סמנו כדי להחזיר אותה לאתר אחרי שהשלמתם לה מדיה (תמונה או קישור סרטון). אפשר גם לשנות את המין באותו טופס: השינוי מתבצע באותו מנגנון כמו בכל תצפית. בלי הסימון השמירה משאירה אותה מחוקה.':
        'The observation is deleted. Tick to bring it back once it has media (a photo or a video link). The species can be changed '
        'in the same form, as in any observation. Without the tick, saving leaves it deleted.',
    'להמשיך עם התמונה הקיימת (עליה עדיין כתוב השם הקודם)': 'Keep the current photo (it still shows the previous name)',
    'שינוי המין מחייב תמונה מעודכנת עם שם המין החדש: העלו אותה בשדה התמונה. אם לא — סמנו כאן כדי להמשיך עם התמונה הנוכחית, שתישמר בשם של המין החדש.':
        'Changing the species needs an updated photo with the new species name: upload it in the photo field. Otherwise tick here '
        'to keep the current photo, which is saved under the new species’ name.',
    'כבר קיימת במסע תצפית של המין החדש — מה לעשות?': 'The trip already has an observation of the new species — what should happen?',
    'להחליף את התמונה/הסרטון של התצפית הקיימת במדיה של תצפית זו, ולמחוק את תצפית זו':
        'Replace the existing observation’s photo/video with this one’s media, and delete this observation',
    'למחוק את תצפית זו (כולל המדיה שלה) ולהשאיר את התצפית הקיימת כמות שהיא':
        'Delete this observation (with its media) and leave the existing one as it is',
    'לביטול הפעולה — אל תשמרו, והשאירו את התצפית כפי שהיא.': 'To cancel — don’t save, and leave the observation as it is.',
    # manager-only taxon page fields
    'תיאור בעברית (של הסדרה / המשפחה / הסוג)': 'Description in Hebrew (of the order / family / genus)',
    'תיאור באנגלית (של הסדרה / המשפחה / הסוג)': 'Description in English (of the order / family / genus)',
    'סימני זיהוי בעברית': 'Identification features in Hebrew',
    'סימני זיהוי באנגלית': 'Identification features in English',
    'קישור בכל שורה (אפשר להוסיף טקסט לפני הקישור).': 'One link per line (text may come before the link).',
    'מאמרים של הסדרה / המשפחה / הסוג': 'Articles of the order / family / genus',
    'בחירה מתוך המאמרים שכבר הועלו (Ctrl/Cmd לבחירה של כמה). מאמר חדש מעלים פעם אחת בניהול ← מאמרים.':
        'Choose from the articles already uploaded (Ctrl/Cmd to choose several). A new article is uploaded once in Admin → Articles.',
    'קובץ זיהוי של הסוג בעברית (PDF או תמונה)': 'Genus identification file in Hebrew (PDF or image)',
    'תרשים, לוח תמונות או מפתח לזיהוי המינים בסוג: PDF או תמונה (JPG, PNG, WebP, GIF), עד 20MB.':
        'A diagram, photo plate or key to the genus’ species: PDF or image (JPG, PNG, WebP, GIF), up to 20MB.',
    'עמוד לתצוגה מקדימה (עברית)': 'Preview page (Hebrew)',
    'העמוד ב-PDF שמוצג בריבוע התצוגה המקדימה ושבו הקובץ נפתח.': 'The PDF page shown in the preview box and where the file opens.',
    'קובץ זיהוי של הסוג באנגלית (PDF או תמונה)': 'Genus identification file in English (PDF or image)',
    'מוצג באתר באנגלית (בלעדיו מוצג שם הקובץ העברי), עד 20MB.': 'Shown on the English site (without it the Hebrew file is shown), up to 20MB.',
    'עמוד לתצוגה מקדימה (אנגלית)': 'Preview page (English)',
    'העמוד ב-PDF האנגלי שמוצג בריבוע התצוגה המקדימה ושבו הקובץ נפתח.': 'The English PDF page shown in the preview box and where the file opens.',
    'כיתוב לקובץ הזיהוי': 'Identification file caption',
    'כיתוב לקובץ הזיהוי (אנגלית)': 'Identification file caption (English)',
    'מקור קובץ הזיהוי': 'Identification file source',
    # errors
    'יש לבחור את אזור המסע.': 'Choose the trip’s region.',
    'יש לציין את שנת הצלילה.': 'Enter the dive year.',
    'יש לציין את חודש הצלילה.': 'Enter the dive month.',
    'תאריך לא תקין.': 'Invalid date.',
    'ערך לא תקין.': 'Invalid value.',
    'אתר הצלילה אינו שייך לאזור המסע.': 'The dive site is not in the trip’s region.',
    'יש לכתוב את שם אתר הצלילה בעברית.': 'Enter the dive site’s Hebrew name.',
    'כדי להוסיף אתר צלילה חדש יש לבחור מסע צלילה (שהאזור שלו ידוע) או לסמן יצירת מסע מתצפית זו ולבחור אזור.':
        'To add a new dive site, choose a dive trip (with a known region), or tick “Create a dive trip from this observation” and choose a region.',
    'קבצים אלה מתאימים רק לדגימה מסוג סדרה, משפחה או סוג.': 'These files fit only an order, family or genus observation.',
    'קובץ זיהוי, כיתוב ומקור זמינים רק בסוג.': 'An identification file, caption and source are for a genus only.',
    'לא נמצאה שורה בטבלת הטקסונומיה לסדרה/משפחה/סוג שנבחרו — יש להוסיף אותה בניהול.':
        'The chosen order/family/genus has no row in the taxonomy tables — add it in the admin.',
    'הכתובת אינה כתובת של תמונה קיימת בגלריה. בחרו תמונה מהרשימה, או הדביקו את כתובת התמונה כפי שהועתקה מהאתר.':
        'This is not the address of a gallery photo. Pick a photo from the list, or paste the address as copied from the site.',
    'רק אחד מהשדות יכול להיות מוגדר: תמונה חלופית (העלאת קובץ) או תמונה קיימת בגלריה.':
        'Only one of the fields can be set: an alternate photo (upload) or an existing gallery photo.',
    'זו התמונה של התצפית עצמה.': 'This is the observation’s own photo.',
    'התמונה של תצפית זו מוצגת גם בתצפיות אחרות (כתמונה קיימת בגלריה), ולכן אי אפשר להחליף אותה בתמונה של תצפית אחרת.':
        'This observation’s photo is shown in other observations too (as an existing gallery photo), so it cannot be replaced by another observation’s photo.',
    'לא נמצא מין תואם ברשימה (ביחד עם הסוג שנבחר). יש לבחור מין קיים, או למלא "מין אחר".':
        'No matching species in the list (with the chosen genus). Choose an existing species, or fill in "Other species".',
    'תאריך המסע כבר עבר, ולכן התכנון נסגר. אפשר להפוך אותו למסע צלילה רגיל: בחרו את הסוג "אוסף מינים / מסע צלילה" והוסיפו סרטון או תמונה.':
        'The trip’s date has passed, so the planning is closed. It can become a regular dive trip: choose the type "Species collection / dive trip" and add a video or a photo.',
    'יש לבחור סדרה.': 'Choose an order.',
    'יש לבחור משפחה.': 'Choose a family.',
    'יש לבחור סוג.': 'Choose a genus.',
    'יש לבחור מין או לפרט אחר.': 'Choose a species or describe another one.',
    'יש לספק קישור YouTube או להעלות תמונה, או את שניהם.': 'Give a YouTube link or upload a photo, or both.',
    'המסע עדיין לא התקיים, ולכן אי אפשר להוסיף לו תצפית עם מדיה. לתכנון מסע בחרו את הסוג "תכנון מסע צלילות".':
        'The trip has not taken place yet, so an observation with media cannot be added to it. To plan a trip choose the type "Dive trip planning".',
    'סרטון אוסף אינו משויך למין יחיד. נקה את בחירת המין.': 'A collection is not tied to one species. Clear the species.',
    'יש להזין כותרת לסרטון האוסף.': 'Enter a title for the collection.',
    'יש לבחור מסע צלילה.': 'Choose a dive trip.',
    'למסע הנבחר אין שנה מוגדרת. יש להשלים שנה במסע הצלילה לפני פרסום.': 'The chosen trip has no year. Complete the trip’s year before publishing.',
    'יש לבחור מין מהרשימה או לפרט אחר, לא את שניהם.': 'Choose a species from the list or describe another one, not both.',
    'יש לבחור אתר צלילה מהרשימה או לפרט אחר, לא את שניהם.': 'Choose a dive site from the list or describe another one, not both.',
    'אתר הצלילה אינו שייך לאזור המסע שנבחר.': 'The dive site is not in the chosen trip’s region.',
    'יום מחייב שהוגדר חודש במסע הצלילה.': 'A day needs a month on the dive trip.',
    'תצפית אינה יכולה להציג את התמונה של עצמה.': 'An observation cannot show its own photo.',
    'לתצפית שנבחרה אין תמונה פעילה בגלריה.': 'The chosen observation has no active gallery photo.',
    'לתכנון מסע אין מדיה. אחרי המסע אפשר להפוך אותו למסע צלילה רגיל: בחרו את הסוג "אוסף מינים / מסע צלילה" והוסיפו סרטון או תמונה.':
        'A trip planning has no media. After the trip it can become a regular dive trip: choose the type "Species collection / dive trip" and add a video or a photo.',
    'יש להזין כותרת לתכנון המסע.': 'Enter a title for the trip planning.',
    'למסע מתוכנן יש להגדיר שנה וחודש.': 'A planned trip needs a year and a month.',
    'למסע הזה כבר יש תכנון. אפשר להוסיף תגובות בדיון שלו בפורום.': 'This trip already has a planning. Comments can be added in its forum discussion.',
    # the page's scripts
    'בחירה מתמונות הגלריה': 'Pick from the gallery photos',
    'חיפוש לפי מין, סוג, משפחה, כותרת או מסע': 'Search by species, genus, family, title or trip',
    'רק ממסע זה': 'This trip only',
    'טעינת עוד': 'Load more',
    'טוען…': 'Loading…',
    'לא נמצאו תמונות.': 'No photos found.',
    'שגיאה בטעינת התמונות.': 'Error loading the photos.',
    'שינוי המין: התצפית תעודכן במקומה, והמין הקודם יפסיק להציג אותה. התמונה מכילה את שם המין הקודם — העלו תמונה מעודכנת (עם שם המין החדש על גבי התמונה). הקובץ הקודם יימחק.':
        'Changing the species: the observation is updated in place, and the previous species stops showing it. The photo carries '
        'the previous species name — upload an updated photo (with the new species name on it). The previous file is deleted.',
    'תצפית זו מגדירה את המין.': 'This observation defines the species.',
    'הדגימה הבאה: ': 'Next observation: ',
    'הדגימה הבאה ללא מדיה': 'The next observation has no media',
    'דגימה יחידה': 'Only observation',
    'המין שנבחר מופיע בגלריה.': 'The chosen species appears in the gallery.',
    'המין שנבחר אינו מופיע בגלריה.': 'The chosen species does not appear in the gallery.',
    'אין מסע שמתאים למסננים.': 'No dive trip matches the filters.',
    'מסעות שמתאימים למסננים: ': 'Dive trips matching the filters: ',
    # after saving
    'התצפית פורסמה.': 'The observation was published.',
    'התצפית נשמרה וממתינה להשלמת נתונים ולאישור מנהל.': 'The observation was saved and waits for completion and a manager’s approval.',
    'התצפית שוחזרה והוחזרה לאתר.': 'The observation was restored to the site.',
    'תצפית של מין זה כבר קיימת במסע זה — התמונה/הסרטון עודכנו בתצפית הקיימת במקום יצירת כפילות.':
        'This trip already has an observation of this species — its photo/video was updated instead of creating a duplicate.',
    'אין מדיה להעביר לתצפית הקיימת: העלו תמונה או הזינו קישור סרטון.': 'No media to move to the existing observation: upload a photo or enter a video link.',
    'התצפית הוסרה (כולל המדיה שלה). התצפית הקיימת של המין החדש לא שונתה.':
        'The observation was removed (with its media). The existing observation of the new species was not changed.',
    # the add pages the observation form links to: a dive trip, a dive site, a species, a guest photographer
    'הוספת מסע צלילה': 'Add a dive trip',
    'בחרו מקום, שנה וחודש (ברירת המחדל: החודש הנוכחי) ואפשר להוסיף יום. השם והסימון מוצעים אוטומטית ואפשר לשנות אותם.':
        'Choose a place, a year and a month (the current month by default); a day can be added. The name and the code are '
        'suggested automatically and can be changed. Trip names are written in Hebrew.',
    'הוספת אתר צלילה חדש': 'Add a new dive site',
    'הוספת אתר צלילה': 'Add a dive site',
    'רשימת האתרים מסוננת לפי האזור. בלי אתר השם נבנה לפי האזור.': 'The sites are filtered by the region. Without a site the name is built from the region.',
    'רשימת האתרים מסוננת לפי האזור. בלי אתר השם נבנה לפי האזור. האתר לא ברשימה? לחצו על + כדי להוסיף אותו.':
        'The sites are filtered by the region. Without a site the name is built from the region. Site not in the list? Click + to add it.',
    'מוצע לפי הבחירות. אם תשנו אותו ידנית הוא יפסיק להשתנות לבד.': 'Suggested from your choices. Once you edit it by hand it stops changing by itself.',
    'צלם (אות, אם זה לא בעל האתר) + אזור + שנה + חודש, למשל I26Aug. בלי יום, אלא אם הסימון כבר תפוס.':
        'Photographer (a letter, unless it is the site owner) + region + year + month, e.g. I26Aug. No day unless the code is already taken.',
    'שמירת המסע': 'Save the trip',
    'ביטול': 'Cancel',
    'אתר צלילה (לא חובה)': 'Dive site (optional)',
    'יום (לא חובה)': 'Day (optional)',
    'מספר ימים (לא חובה)': 'Number of days (optional)',
    'שם המסע': 'Trip name',
    'סימון המסע (קוד)': 'Trip code',
    'האתר אינו שייך לאזור שנבחר.': 'The site is not in the chosen region.',
    'חודש בין 1 ל-12.': 'A month between 1 and 12.',
    'בחרו את האזור והקלידו את שם האתר. אתר שכבר קיים באזור לא יתווסף שוב.':
        'Choose the region and type the site’s name. A site that already exists in the region is not added again.',
    'שם האתר': 'Site name (Hebrew)',
    'שם האתר באנגלית (לא חובה)': 'Site name in English (optional)',
    'הוספת האתר': 'Add the site',
    'האתר נוסף': 'Site added',
    'נוסף לרשימת אתרי הצלילה. אפשר לסגור את החלון.': 'was added to the dive sites. You can close this window.',
    'האתר': 'The site',
    'חזרה': 'Back',
    'הוספת צלם אורח': 'Add a guest photographer',
    'צלם אורח הוא צלם שאין לו חשבון באתר: מנהל מוסיף את התצלומים שלו, והם מופיעים באתר עם שמו כצלם. הוא נשמר כמשתמש לא פעיל, בלי סיסמה, ואפשר להפוך אותו בהמשך למשתמש פעיל בניהול המשתמשים. לאחר השמירה תחזרו לטופס התצפית כשהצלם כבר נבחר.':
        'A guest photographer has no account on the site: a manager adds their photos, and they appear with their name as the '
        'photographer. They are kept as an inactive user without a password and can later become an active user in the user '
        'management. After saving you return to the observation form with the photographer already chosen.',
    'שם פרטי': 'First name (Hebrew)',
    'שם משפחה': 'Last name (Hebrew)',
    'שם פרטי באנגלית': 'First name in English',
    'שם משפחה באנגלית': 'Last name in English',
    'דואר אלקטרוני': 'Email',
    'טלפון': 'Phone',
    'הוספת הצלם': 'Add the photographer',
    'כבר קיים משתמש עם כתובת הדואר הזו - אפשר לבחור אותו ברשימת הצלמים.': 'A user with this email already exists — choose them in the photographers list.',
    'מספר טלפון לא תקין.': 'Invalid phone number.',
    'הוספת מין חדש לרשימה': 'Add a new species to the list',
    'המין יתווסף לרשימת המינים ותחזרו לטופס התצפית כשהוא כבר נבחר. כל מין חייב מחבר ושנת תיאור (רק sp. שטרם תואר פטור), ואם הסוג כבר קיים המשפחה והסדרה יתמלאו לבד.':
        'The species is added to the species list and you return to the observation form with it already chosen. Every species '
        'needs an author and year (only an undescribed sp. is exempt); when the genus already exists, the family and order are filled in.',
    'סוג (Genus)': 'Genus',
    'מין (Species)': 'Species',
    'שם המין בלבד, למשל strigata. אפשר גם cf. strigata או sp. 7.': 'The epithet only, e.g. strigata. cf. strigata or sp. 7 also work.',
    'מחבר ושנת תיאור': 'Author and year',
    'למשל Rudman, 1982. חובה לכל מין מלבד sp. שטרם תואר.': 'E.g. Rudman, 1982. Required for every species except an undescribed sp.',
    'משפחה (Family)': 'Family',
    'נשלף אוטומטית כשהסוג כבר קיים. לסוג חדש יש למלא.': 'Filled in when the genus already exists. Required for a new genus.',
    'סדרה (Order)': 'Order',
    'שם בעברית (לא חובה)': 'Hebrew name (optional)',
    'שם באנגלית (לא חובה)': 'English name (optional)',
    'הוספת המין': 'Add the species',
    'הסוג הוא מילה אחת.': 'The genus is one word.',
    'חובה לציין מחבר ושנה (רק sp. שטרם תואר פטור).': 'An author and year are required (only an undescribed sp. is exempt).',
    'הסוג חדש ברשימה — יש לציין את המשפחה.': 'The genus is new to the list — enter its family.',
    'המין כבר קיים ברשימה.': 'The species is already in the list.',
    # the dive trips management page (/observations/trips/manage/)
    'ניהול מסעות צלילה': 'Manage dive trips',
    'בחרו מדינה, אזור, אתר ושנה כדי לסנן מסעות. לחיצה על כותרת עמודה ממיינת; לחיצה נוספת הופכת את הסדר.':
        'Choose a country, region, site and year to filter the trips. Click a column heading to sort; click again to reverse the order.',
    'מסעות': 'trips',
    'סימון': 'Code',
    'פעולות': 'Actions',
    '+ הוספת מסע': '+ Add a trip',
    'אין מסעות לפי המסננים האלה.': 'No trips match these filters.',
}

# Messages that carry a value: (Hebrew pattern, English with {0}, {1}... for its groups)
FORM_PATTERNS = [(re.compile(he), en) for he, en in (
    (r'הקובץ גדול מדי \(עד (\d+)MB\)\.', 'The file is too large (up to {0}MB).'),
    (r'הסוג (.+) שייך למשפחה (.+), לא ל(.*)\.', 'The genus {0} belongs to the family {1}, not {2}.'),
    (r'הסוג (.+) שייך לסדרה (.+), לא ל(.*)\.', 'The genus {0} belongs to the order {1}, not {2}.'),
    (r'המשפחה (.+) שייכת לסדרה (.+), לא ל(.*)\.', 'The family {0} belongs to the order {1}, not {2}.'),
    (r'הערך "(.*)" אינו קיים בטבלת העזר\. אפשר להוסיף אותו שם\.', 'The value "{0}" is not in the reference table. It can be added there.'),
    (r'מין זה כבר נקלט למסע זה בתצפית קיימת \((.*)\)\. אי אפשר לקלוט אותו מין פעמיים באותו מסע\.',
     'This species is already on this trip in an existing observation ({0}). A species cannot be entered twice on one trip.'),
    (r'התמונה הזו כבר קיימת בתצפית אחרת \((.*)\)\. לא ניתן להעלות את אותה תמונה פעמיים — כדי להציג אותה גם כאן, בחרו אותה בשדה "תמונה קיימת בגלריה"\.',
     'This photo is already in another observation ({0}). The same photo cannot be uploaded twice — to show it here too, choose it in the "existing gallery photo" field.'),
    (r'הסרטון הזה כבר קיים בתצפית אחרת \((.*)\)\. לא ניתן להשתמש באותו סרטון פעמיים\.',
     'This video is already in another observation ({0}). The same video cannot be used twice.'),
    (r'המין החדש כבר קיים במסע זה בתצפית אחרת \((.*)\)\. בחרו מה לעשות בשתי התצפיות\.',
     'The new species is already on this trip in another observation ({0}). Choose what happens to the two observations.'),
    (r'אתר הצלילה נוסף: (.*)\.', 'Dive site added: {0}.'),
    (r'נוצר מסע צלילה מהתצפית: (.*) \((.*)\)\.', 'A dive trip was created from the observation: {0} ({1}).'),
    (r'המין בתצפית שונה ל־(.*)\. התצפית עודכנה במקומה: המין הקודם כבר אינו מציג אותה, והתמונה נשמרה בשם של המין החדש\.',
     'The observation’s species was changed to {0}. It was updated in place: the previous species no longer shows it, and the photo was saved under the new species’ name.'),
    (r'המדיה של התצפית הקיימת של (.*) במסע זה הוחלפה, והתצפית הקודמת הוסרה \(כולל המדיה שלה\)\.',
     'The media of the existing {0} observation on this trip was replaced, and the previous observation was removed (with its media).'),
    (r'התמונה של תצפית זו מוצגת גם בתצפיות אחרות כתמונה קיימת בגלריה \((.*)\)\. יש להסיר אותה מהן קודם\.',
     'This observation’s photo is shown in other observations as an existing gallery photo ({0}). Remove it from them first.'),
    (r'(.+) \(צלם אורח\)', '{0} (guest photographer)'),
    (r'האתר "(.*)" כבר קיים באזור הזה\. בחרו אותו מרשימת האתרים\.', 'The site "{0}" already exists in this region. Choose it from the dive sites list.'),
    (r'המסע נוסף: (.*) \((.*)\)\.', 'Dive trip added: {0} ({1}).'),
    (r'הצלם נוסף: (.*)\. אפשר להוסיף תצפיות על שמו\.', 'Photographer added: {0}. Observations can now be added under their name.'),
    (r'המין נוסף לרשימה: (.*)\.', 'Species added to the list: {0}.'),
)]


def translate_pattern(text):
    """English for a message that carries a value, or None."""
    for pattern, english in FORM_PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return english.format(*match.groups())
    return None
