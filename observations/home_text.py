"""Search-facing text of the gallery home page (the title, the description and the short share title),
in both languages. The server renders the one that matches the URL (/ in Hebrew, /?lang=en in English);
app.js reads both from the page so the language button can swap them without a reload.

Wording rules (see the SeaSlugs proposal): "חינניות ים" is the Hebrew umbrella term for Sea slugs;
"חשופיות" means nudibranchs only; the collection is international and must not be described as
mainly Israeli.
"""
HOME_TEXT = {
    'he': {
        'share_title': 'SeaSlugs — חינניות ים',
        'title': 'חינניות ים: מיזם מחקר בים התיכון ואוסף תמונות עולמי | SeaSlugs',
        'description': 'מיזם מחקר ישראלי על חינניות ים (Sea Slugs) וחשופיות (Nudibranchs) בים התיכון, '
                       'עם אוסף תמונות וסרטונים בינלאומי. צלמים וצוללנים מוזמנים לתרום תצפיות.',
    },
    'en': {
        'share_title': 'SeaSlugs — Sea slugs and nudibranchs',
        'title': 'Sea Slugs & Nudibranchs: Mediterranean Research Project and Photo Collection | SeaSlugs',
        'description': 'Israeli research on sea slugs and nudibranchs in the Mediterranean, plus an international '
                       'photo and video collection. Divers and photographers: contribute observations.',
    },
}


def home_lang(request):
    """The home page's language comes from the URL alone: / is Hebrew, /?lang=en is English. (A remembered
    cookie must not turn / into English -- one address, one language -- the button and app.js still
    restore a returning visitor's choice in the browser.)"""
    return 'en' if request.GET.get('lang') == 'en' else 'he'
