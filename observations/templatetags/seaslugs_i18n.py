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
}


@register.filter
def t(value, lang):
    if lang != 'en':
        return value
    return TRANSLATIONS.get(value, value)


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
