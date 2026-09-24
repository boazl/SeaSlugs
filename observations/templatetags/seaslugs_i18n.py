"""Template filters backing the hand-rolled bilingual UI on the observations
listing and species pages (see observations/i18n.py for the language-detection
side). `t` translates a small, fixed set of Hebrew UI strings written directly
in those templates; `loc` picks the right name off a Country/Region/Site
(or any other model with a name/name_en pair); `get_item` is a plain dict
lookup for the per-item label maps the views build (kind/status)."""
from django import template

register = template.Library()

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
    'מחוקה': 'deleted',
    'צפייה ב־YouTube': 'Watch on YouTube',
    'צפייה בתמונה המלאה': 'View full image',
    'עריכה': 'Edit',
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
    'תיאור': 'Description',
    'בית גידול': 'Habitat',
    'מזון': 'Food',
    'קישור לשיתוף:': 'Share link:',
    'העתקה': 'Copy',
    'הועתק!': 'Copied!',
    # shared nav / account menu (base.html + account_menu.html)
    'שלום': 'Hi',
    'יציאה': 'Logout',
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
