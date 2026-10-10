"""Template filters backing the hand-rolled bilingual UI on the observations
listing and species pages (see observations/i18n.py for the language-detection
side). `t` translates a small, fixed set of Hebrew UI strings written directly
in those templates; `loc` picks the right name off a Country/Region/Site
(or any other model with a name/name_en pair); `get_item` is a plain dict
lookup for the per-item label maps the views build (kind/status)."""
from django import template

register = template.Library()


@register.filter
def with_lang(url, lang):
    """Keep the visitor's language across an internal link: '/x/' -> '/x/?lang=en' on an English
    page, unchanged on a Hebrew one (the default). Used by every navigation link that would
    otherwise drop the language."""
    if lang != 'en' or not url or 'lang=' in str(url):
        return url
    base, sep, fragment = str(url).partition('#')
    return f"{base}{'&' if '?' in base else '?'}lang=en{sep}{fragment}"

# Hebrew UI string -> English equivalent. Only entries actually used by the two
# bilingual templates need to be here; `t` falls back to the Hebrew original for
# anything missing, so a forgotten entry degrades gracefully instead of breaking.
TRANSLATIONS = {
    # observations listing
    'תצפיות': 'Observations',
    'דגימות המינים וסרטוני האוסף שלך. מנהל יכול לראות גם רשומות של משתמשים אחרים.':
        'Species samples and videos from your collection. A manager can also see other users’ records.',
    'סוג הרשומה': 'Record type',
    'סטטוס': 'Status',
    'מדינה': 'Country',
    'אתר': 'Site',
    'כל המדינות': 'All countries',
    'כל האזורים': 'All regions',
    'כל האתרים': 'All sites',
    'כל השנים': 'All years',
    'אזור': 'Region',
    'שנה': 'Year',
    'סדרה': 'Order',
    'משפחה': 'Family',
    'סוג (Genus)': 'Genus',
    'צלם': 'Photographer',
    'משתמש': 'User',
    'רק שלי': 'Only mine',
    'מיון': 'Sort',
    'הכל': 'All',
    'הקלידו לחיפוש': 'Type to search',
    'סינון': 'Filter',
    'איפוס סינון': 'Reset filters',
    'צילום:': 'Photo:',
    'צפייה בסרטון': 'Watch the video',
    'הגדלת התמונה': 'Enlarge photo',
    'סגירה': 'Close',
    'תצפיות נוספות': 'More observations',
    'קהילה ותצפיות': 'Community & observations',
    'SeaSlugs — גלריה': 'SeaSlugs — Gallery',
    'ניהול האתר': 'Site admin',
    'ניהול והעברת תמונות': 'Image management',
    'ניהול משתמשים': 'Users',
    'ניהול גרסאות וגיבויים': 'Releases & backups',
    'העברת טבלאות': 'Table transfer',
    'החלפה מלאה של מסד הנתונים': 'Full database replace',
    'ביטול נעילה — שחרור האתר': 'Unlock the site',
    'הוספת תצפית': 'Add observation',
    'התצפיות שלי': 'My observations',
    'הפרופיל שלי': 'My profile',
    'שותפים למאקרו': 'Macro dive partners',
    'מסעות צלילה': 'Dive trips',
    'סרטוני אוסף ממסעות צלילה, לצד הדגימות המשויכות לכל מסע.': 'Collection videos from dive trips, alongside the species observations from each trip.',
    'מספר מינים בגלריה:': 'Species in the gallery:',
    'צפייה בסרטון המסע ב־YouTube ↗': 'Watch the trip video on YouTube ↗',
    'צפייה בתמונה המלאה ↗': 'View full image ↗',
    'דגימות מינים מהמסע': 'Species observations from this trip',
    'עדיין אין מסעות עם תמונות או סרטונים מפורסמים.': 'No trips with published photos or videos yet.',
    'סרטוני המסעות': 'Trip videos',
    'העתקת כתובת התמונה': 'Copy image address',
    'הכתובת הועתקה': 'Address copied',
    'רשימת המינים במסע': 'Species list of this trip',
    'טבלת המסעות': 'Table of trips',
    'שם המסע': 'Trip',
    'מקום': 'Location',
    'תאריך': 'Date',
    'פתיחה או סגירה של דגימות המסע': 'Show or hide the trip observations',
    'מינים בגלריה': 'Species in the gallery',
    'מינים בסוג זה': 'Species in this genus',
    'תצפיות, תמונות ומידע מאתר SeaSlugs, אתר חינניות הים.': 'Observations, photos and information from SeaSlugs, the sea slugs website.',
    'משפחות': 'Families',
    'סוגים': 'Genera',
    'מינים': 'Species',
    'גודל': 'Size',
    'עומק': 'Depth',
    'תפוצה מקורית': 'Native range',
    'זיהוי': 'Identification',
    'מינים דומים': 'Similar species',
    'בית גידול ותזונה': 'Habitat & diet',
    'בים התיכון': 'In the Mediterranean',
    'תצפית ראשונה': 'First record',
    'תצפית אחרונה מתועדת': 'Latest documented record',
    'מעמד': 'Status',
    'דרך ההגעה': 'Route of arrival',
    'מקורות': 'Sources',
    'מחוקה': 'deleted',
    'צפייה ב־YouTube': 'Watch on YouTube',
    'צפייה בתמונה המלאה': 'View full image',
    'עריכה': 'Edit',
    'הצגה בגלריה': 'Show in gallery',
    'ניהול מסעות': 'Manage trips',
    'הסרה מהאתר': 'Remove from site',
    'בדיקה בניהול': 'Review in admin',
    'עדיין אין תצפיות להצגה. אפשר להוסיף את התצפית הראשונה.':
        'No observations yet. You can add the first one.',
    # species page
    'הגלריה': 'Gallery',
    'מין מהגר': 'Migrant species',
    'תצפיות:': 'Observed:',
    'קישור נוסף ↗': 'More info ↗',
    'מאמר (PDF) ↗': 'Article (PDF) ↗',
    'מפתח זיהוי (PDF) ↗': 'Identification key (PDF) ↗',
    'פתיחת תרשים הזיהוי בגודל מלא': 'Open the identification figure full size',
    'מקור:': 'Source:',
    'חזרה למשפחה': 'Back to family',
    'חזרה לסדרה': 'Back to order',
    'חזרה לסוג': 'Back to genus',
    'חזרה לכל הסדרות': 'Back to all orders',
    'חזרה לגלריה': 'Back to the gallery',
    'תיאור': 'Description',
    'בית גידול': 'Habitat',
    'מזון': 'Food',
    'קישור לשיתוף:': 'Share link:',
    'העתקה': 'Copy',
    'הועתק!': 'Copied!',
    # shared nav / account menu (base.html + account_menu.html)
    'שלום': 'Hello',
    'יציאה': 'Logout',
    'גלריה': 'Gallery',
    'דף הבית': 'Home page',
    'חשבון': 'Account',
    'תפריט חשבון': 'Account menu',
    'עריכת טקסטים בדף הבית': 'Edit home texts',
    'כניסה': 'Login',
    'הרשמה': 'Sign up',
    'חבר/ת הקהילה': 'Community member',
    'הפרופיל נשמר.': 'Profile saved.',
    # signup / profile form field labels and help text (form.html renders these
    # fields manually rather than via form.as_p, precisely so each label/help_text
    # can be run through this filter -- see observations/views.py profile()/signup()).
    'שם משתמש': 'Username',
    'שדה חובה. 150 תווים או פחות. אותיות, ספרות ו-@/./+/-/_ בלבד.':
        'Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.',
    'שם פרטי': 'First name',
    'שם משפחה': 'Last name',
    'דואר אלקטרוני': 'Email',
    'סיסמה': 'Password',
    ('<ul><li>הסיסמה שלך לא יכולה להיות דומה מדי למידע אישי אחר שלך.</li>'
     '<li>הסיסמה שלך חייבת להכיל לפחות 8 תווים.</li>'
     '<li>הסיסמה שלך לא יכולה להיות סיסמה שכיחה.</li>'
     '<li>הסיסמה שלך לא יכולה להכיל רק ספרות.</li></ul>'):
        ("<ul><li>Your password can't be too similar to your other personal information.</li>"
         "<li>Your password must contain at least 8 characters.</li>"
         "<li>Your password can't be a commonly used password.</li>"
         "<li>Your password can't be entirely numeric.</li></ul>"),
    'אימות סיסמה': 'Password confirmation',
    'יש להזין את אותה סיסמה כמו קודם, לאימות.': 'Enter the same password as before, for verification.',
    'שם פרטי באנגלית': 'First name (English)',
    'שם משפחה באנגלית': 'Last name (English)',
    'טלפון': 'Phone',
    'מעוניין במציאת שותפים לצלילת מאקרו': 'Interested in finding macro diving partners',
    'הצגת הפרופיל למשתמשים רשומים': 'Show my profile to other members',
    'מדינות צלילה': 'Diving countries',
    'אזורי צלילה': 'Diving regions',
    'על עצמי': 'About me',
}


@register.filter
def t(value, lang):
    # `value` is usually a plain Hebrew string, but callers also run this over
    # objects that stringify to one (e.g. a django.contrib.messages Message,
    # which isn't hashable, so it must go through str() before a dict lookup).
    if lang != 'en':
        return value
    return TRANSLATIONS.get(str(value), value)


@register.filter
def name_html(text):
    """A scientific name with genus and epithet in italics (see observations/names.py)."""
    from ..names import name_html as render
    return render(text)


@register.filter
def loc(obj, lang):
    """Localized name of a Country/Region/Site/etc. (anything with name/name_en)."""
    if not obj:
        return ''
    if lang == 'en':
        return getattr(obj, 'name_en', '') or str(obj)
    return str(obj)


@register.filter
def get_item(mapping, key):
    if not mapping:
        return key
    return mapping.get(key, key)


@register.filter
def account_name(user, lang):
    """The name to greet a logged-in user by (first name only): the Hebrew first
    name on their account in Hebrew mode, their profile's English first name in
    English mode, each falling back to whichever language is actually set. Same
    resolution as the photographer credit (see models.given_name_for), so a
    person's name resolves the same way everywhere it appears."""
    if not user or not getattr(user, 'is_authenticated', False):
        return ''
    from ..models import given_name_for
    return given_name_for(user, lang)


@register.filter
def photographer_name(sample, lang):
    """Language-aware photographer credit for an observation card / species page
    (see Sample.photographer_display_name): prefers a registered photographer's
    English name in English mode, same as the nav greeting. Falls back to the
    plain (language-neutral) property for anything that isn't a Sample."""
    if not sample:
        return ''
    method = getattr(sample, 'photographer_display_name', None)
    if callable(method):
        return method(lang)
    return getattr(sample, 'photographer_name', '')


NAV_ICONS = {
    'add': '<circle cx="12" cy="12" r="10"/><path d="M12 8v8M8 12h8"/>',
    'manage': '<path d="M3 6h18M3 12h18M3 18h18"/><circle cx="8" cy="6" r="2" fill="currentColor"/><circle cx="16" cy="12" r="2" fill="currentColor"/><circle cx="10" cy="18" r="2" fill="currentColor"/>',
    'mine': '<path d="M12 2l3 6.5 7 .9-5.2 4.8 1.4 7-6.2-3.5L5.8 21.2l1.4-7L2 9.4l7-.9z"/>',
    'partners': '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
    'admin': '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>',
    'images': '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 16 5-5 4 4 3-3 6 6"/>',
    'releases': '<path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/>',
    'table': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/>',
    'database': '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>',
    'gallery': '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><rect x="9" y="12" width="6" height="5" rx="1"/>',
    'trips': '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    'observations': '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
    'profile': '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    'edit': '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    'logout': '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    'login': '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><path d="m10 17 5-5-5-5"/><path d="M15 12H3"/>',
    'signup': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/>',
}


@register.simple_tag
def nav_icon(name):
    """A small decorative line icon (inline SVG, drawn in the link's colour) for the main navigation."""
    from django.utils.safestring import mark_safe
    return mark_safe('<svg class="nav-icon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" '
                     f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{NAV_ICONS[name]}</svg>')


@register.simple_tag
def nav_label(hebrew, lang):
    """The label of a navigation item in the page's language, carrying both languages so the home page's
    language button can swap it without a reload (see app.js, setLanguage)."""
    from django.utils.html import format_html
    english = TRANSLATIONS.get(hebrew, hebrew)
    return format_html('<span class="nav-label" data-he="{}" data-en="{}">{}</span>',
                       hebrew, english, english if lang == 'en' else hebrew)
