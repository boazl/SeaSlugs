"""Suggested name and code for a new dive trip, from the choices made on the trips page.

Name  : [photographer] [site, or the region when no single site is chosen] [year]
        [month -- only when that place already has a trip that year]
        [day   -- only when it already has one that month too, and a day was given]
Code  : [photographer letter -- left out for the site owner] [region code] [YY] [Mon]
        e.g. I26Aug. No day by default; a taken code gets the day, then -2, -3...

Region codes live on Region.trip_code and photographer letters on Profile.trip_code (both editable
in the admin); a missing one is derived here the first time it is needed.
"""
import re
from django.conf import settings
from .models import DiveTrip, Profile, Region

MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MONTHS_HE = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']
# The letters the old trip codes already used for these two places.
LEGACY_REGION_CODES = {'Akhziv': 'I', 'Eilat': 'J'}
ISRAEL_MED_PREFIX = 'I'


def default_photographer_username():
    return getattr(settings, 'TRIP_DEFAULT_PHOTOGRAPHER', 'boazl')


def _letters(text):
    return re.sub(r'[^A-Za-z]', '', text or '')


def region_code_for(name_en, name, israel_mediterranean, taken):
    """A short code for a region that is not in `taken` (a set of codes already in use).
    Israel's Mediterranean regions share the old letter I as a prefix (IA..., IC...); every
    other region starts from its own first letter and grows by one letter on a clash."""
    base = _letters(name_en) or _letters(name) or 'X'
    if name_en in LEGACY_REGION_CODES and LEGACY_REGION_CODES[name_en] not in taken:
        return LEGACY_REGION_CODES[name_en]
    prefix = ISRAEL_MED_PREFIX if israel_mediterranean else ''
    for length in range(1, len(base) + 1):
        candidate = prefix + base[:length].capitalize()
        if candidate not in taken and candidate not in LEGACY_REGION_CODES.values():
            return candidate
    number = 2
    while f'{prefix}{base.capitalize()}{number}' in taken:
        number += 1
    return f'{prefix}{base.capitalize()}{number}'


def is_israel_mediterranean(region):
    return (region.country.name_en or '').strip() == 'Israel' and 'Mediterranean' in (region.sea.name_en or '')


def region_code(region, persist=False):
    if region.trip_code:
        return region.trip_code
    taken = set(Region.objects.exclude(trip_code='').values_list('trip_code', flat=True))
    code = region_code_for(region.name_en, region.name, is_israel_mediterranean(region), taken)
    if persist:
        Region.objects.filter(pk=region.pk).update(trip_code=code)
        region.trip_code = code
    return code


def photographer_letter_for(first_name_en, username, taken):
    base = (_letters(first_name_en) or _letters(username) or 'x').lower()
    for length in range(1, len(base) + 1):
        if base[:length] not in taken:
            return base[:length]
    number = 2
    while f'{base}{number}' in taken:
        number += 1
    return f'{base}{number}'


def photographer_letter(user, persist=False):
    """'' for the site owner (their trips carry no photographer letter), else the user's letter."""
    if user is None or user.username == default_photographer_username():
        return ''
    profile = Profile.objects.filter(user=user).first()
    if profile and profile.trip_code:
        return profile.trip_code
    taken = set(Profile.objects.exclude(trip_code='').values_list('trip_code', flat=True))
    letter = photographer_letter_for(profile.first_name_en if profile else '', user.username, taken)
    if persist:
        profile = profile or Profile.objects.create(user=user)
        profile.trip_code = letter
        profile.save(update_fields=['trip_code'])
    return letter


def _same_place(trips, region, site):
    return trips.filter(site=site) if site else trips.filter(region=region)


def suggest_title(photographer, region, site, year, month=None, day=None, exclude_pk=None):
    from .models import full_name_for
    place = (site.name if site else region.name) if (site or region) else ''
    parts = [full_name_for(photographer, 'he') if photographer else '', place, str(year) if year else '']
    if region and year and month:
        others = _same_place(DiveTrip.objects.filter(year=year).exclude(pk=exclude_pk), region, site)
        if others.exists():
            parts.append(MONTHS_HE[month - 1])
            if day and others.filter(month=month).exists():
                parts.append(str(day))
    return ' '.join(p for p in parts if p)


def suggest_code(photographer, region, year, month, day=None, exclude_pk=None, persist=False):
    base = f'{photographer_letter(photographer, persist)}{region_code(region, persist)}{year % 100:02d}{MONTHS_EN[month - 1]}'
    taken = lambda code: DiveTrip.objects.filter(code=code).exclude(pk=exclude_pk).exists()
    if not taken(base):
        return base
    if day and not taken(f'{base}{day:02d}'):
        return f'{base}{day:02d}'
    number = 2
    while taken(f'{base}-{number}'):
        number += 1
    return f'{base}-{number}'
