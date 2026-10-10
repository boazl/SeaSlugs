"""The default wording of the editable home-page sections, in the markup of home_markup.py. A section edited on
the edit screen (HomeText rows) replaces its default; clearing the text restores the default."""

SECTION_LABELS = {
    'hero': 'פתיחת הדף (כותרת ופסקת פתיחה)',
    'what': 'מה הן חינניות ים?',
    'project': 'המיזם',
    'contribute': 'איך תורמים תצפית?',
    'collection_note': 'שורת האוסף (מעל הגלריה)',
    'footer_invite': 'הזמנה בתחתית הדף',
}

DEFAULTS = {
    'hero': {
        'he': """~ מבעד לעדשה, מתחת לפני הים
# חינניות ים: מידע, תמונות ומיזם מחקר בים התיכון
הבית של חובבי חינניות הים (Sea slugs): אוסף תמונות וסרטונים מרחבי העולם, וקהילה שמתעדת את חינניות הים בים התיכון של ישראל. צילמתם חיננית ים? תרמו תצפית.""",
        'en': """~ Through the lens, beneath the sea
# Sea slugs: information, photos and a Mediterranean research project
A home for sea slug enthusiasts: an international collection of photos and videos, and a community documenting the sea slugs of the Israeli Mediterranean. Photographed a sea slug? Contribute an observation.""",
    },
    'what': {
        'he': """## מה הן חינניות ים?
חינניות ים (Sea slugs) הן חלזונות ים שאין להם קונכייה חיצונית, או שיש להן קונכייה מצומצמת מאוד. רבות מהן קטנות, צבעוניות ובעלות דוגמאות מרשימות. הקבוצה המוכרת ביותר היא החשופיות (Nudibranchs), אך חינניות ים כוללות גם קבוצות נוספות, כמו ארנבות ים.

באתר אפשר לדפדף במינים לפי סדרה, משפחה וסוג, לצפות בסרטונים ובתמונות, ולראות היכן כל מין תועד.""",
        'en': """## What are sea slugs?
Sea slugs are marine gastropods (snails) that have no external shell, or only a very reduced one. Many are small, colorful and strikingly patterned. The best-known group is the nudibranchs, but "sea slugs" also covers other groups, such as sea hares.

On this site you can browse species by order, family and genus, watch videos and view photographs, and find where each species was observed.""",
    },
    'project': {
        'he': """## המיזם: חינניות ים בים התיכון של ישראל
הים התיכון המזרחי מתחמם והופך טרופי יותר. מינים שהגיעו מים סוף דרך תעלת סואץ (הגירה לספסית) מתבססים לאורך חופי ישראל, והרכב המינים משתנה. חינניות ים הן קבוצה טובה לעקוב אחרי השינוי הזה, ותצפיות של צוללנים וצלמים הן הדרך לעקוב אחריו.

[מינים מהגרים](migrant)""",
        'en': """## The project: sea slugs in the Israeli Mediterranean
The eastern Mediterranean is warming and becoming more tropical. Species that entered from the Red Sea through the Suez Canal (Lessepsian migration) are establishing themselves along the Israeli coast, and the mix of species is changing. Sea slugs are a good group for following this change, and observations by divers and photographers are how it is tracked.

[Migrant species](migrant)""",
    },
    'contribute': {
        'he': """## איך תורמים תצפית?
1. **צלמו.** צלמו חיננית ים בצלילה או בשנורקל, תמונה או סרטון. גם כשאינכם בטוחים בזיהוי.
2. **רשמו.** רשמו איפה, מתי ובאיזה עומק ראיתם אותה.
3. **העלו.** הירשמו לאתר (ההרשמה פתוחה לכולם) והעלו את התצפית. נעזור בזיהוי.

[[הוספת תצפית]]""",
        'en': """## How do you contribute an observation?
1. **Photograph.** Take a photo or video of a sea slug while diving or snorkeling. You do not have to be sure of the identification.
2. **Note.** Write down where, when and at what depth you saw it.
3. **Upload.** Sign up (it is open to everyone) and upload the observation. We will help with the identification.

[[Add an observation]]""",
    },
    'collection_note': {
        'he': 'האוסף כולל כרגע {species} מינים ו־{observations} תצפיות, בעיקר מהפיליפינים ומאזורים נוספים בעולם; {israeli} מהמינים תועדו בים התיכון של ישראל. אפשר לחפש ולסנן באוסף שלמטה.',
        'en': 'The collection currently holds {species} species and {observations} observations, mostly from the Philippines and other regions around the world; {israeli} of the species have been recorded in the Israeli Mediterranean. Use the search and filters below to explore it.',
    },
    'footer_invite': {
        'he': 'SeaSlugs – תיעוד ומחקר חינניות ים. יש לכם תמונה של חיננית ים? [תרמו תצפית](contribute)',
        'en': 'SeaSlugs – documenting and researching sea slugs. Have a photo of a sea slug? [Contribute an observation](contribute)',
    },
}
