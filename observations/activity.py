"""The site's activity log and visit counter -- the data behind the /news/ page (views_news.py).

Activity log (ActivityEvent)
  Written by model signals, so it covers every way data changes: the observation form, the Django admin, a table or
  image transfer, a management command. Each environment keeps its own log; nothing here travels between the Mac and
  the live site, so on the live site an observation enters the log when it arrives there.

  * observation_added   an observation (species or trip collection) becomes public for the first time
  * video_added         a public observation gets a (new) YouTube video, including when it is first published
  * species_new         a new gallery card (SpeciesArea): a species in a country+sea, with "new to the site" and
                        "new to this sea" marks so the page can filter new species by area
  * species_changed     a public observation's identification changes (species, cf./aff., variant letter)
  * observation_updated other visible changes of a public observation (photo, notes, site, depth, day, titles,
                        life stage); repeated edits within a day fold into one line, and edits during the first
                        minutes after it was added (the form's own follow-up saves) are part of adding it
  * signup, login       manager-only lines; the owner's own logins are not recorded

Visit counter (VisitCounterMiddleware)
  Counts views of public HTML pages per page per day, and visitors per day by a salted, daily-changing hash of IP and
  browser (no cookie, nothing reversible stored). Not counted: the admin tools, bots, the owner (superusers and
  ACTIVITY_EXCLUDED_USERNAMES) and any browser with the analytics opt-out cookie (/analytics/exclude/).
  Every browser the owner signs in on gets that cookie by itself (VisitCounterMiddleware), so its later visits are
  not counted even signed out -- by this counter or by Google Analytics.
"""
import contextlib
import hashlib
import logging
import re
import threading
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.db import IntegrityError, models, transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)
_state = threading.local()

UPDATE_FOLD = timedelta(hours=24)       # repeated edits of one observation within this window are one log line
ADDING_GRACE = timedelta(minutes=10)    # saves right after an observation was added are part of adding it
TRACKED_FIELDS = ('image_hash', 'note_he', 'note_en', 'site_id', 'day', 'depth', 'title', 'title_en', 'life_stage')
IDENTITY_FIELDS = ('species_id', 'identification_qualifier', 'undetermined_variant')
LOGGED_KINDS = ('species', 'collection')


@contextlib.contextmanager
def suppressed():
    """Writes made inside this block are not logged (e.g. SpeciesArea.rebuild, which recreates every card)."""
    previous = getattr(_state, 'off', False)
    _state.off = True
    try:
        yield
    finally:
        _state.off = previous


def _off():
    return getattr(_state, 'off', False)


def excluded_usernames():
    return tuple(getattr(settings, 'ACTIVITY_EXCLUDED_USERNAMES', ('boazl',)))


def is_excluded_user(user):
    """The site owner: his visits and logins are not counted."""
    return bool(user and getattr(user, 'is_authenticated', False)
                and (user.is_superuser or user.username in excluded_usernames()))


def _video_id(url):
    from .models import youtube_id
    try:
        return youtube_id(url) if url else ''
    except Exception:
        return url or ''


# --- observations ---------------------------------------------------------------------------------------------
def _snapshot(sample):
    data = {field: getattr(sample, field) for field in TRACKED_FIELDS + IDENTITY_FIELDS}
    data['depth'] = str(data['depth']) if data['depth'] is not None else None
    data['live'] = sample.status == 'published' and sample.deleted_at is None
    data['video'] = _video_id(sample.video_url)
    data['label'] = sample.taxon_label
    return data


def _sample_before_save(sender, instance, raw=False, **kwargs):
    instance._activity_before = None
    if raw or _off() or not instance.pk:
        return
    try:
        previous = sender.objects.select_related('species').filter(pk=instance.pk).first()
        instance._activity_before = _snapshot(previous) if previous else None
    except Exception:
        logger.exception('activity log: could not read the observation before saving')


def _sample_saved(sender, instance, created=False, raw=False, **kwargs):
    if raw or _off():
        return
    before = getattr(instance, '_activity_before', None)
    instance._activity_before = None
    if instance.kind not in LOGGED_KINDS:
        return
    try:
        with transaction.atomic():
            _log_sample(before, instance)
    except Exception:
        logger.exception('activity log: could not log an observation change')


def _log_sample(before, sample):
    from .models import ActivityEvent as E
    after = _snapshot(sample)
    if not after['live']:
        return
    trip = sample.trip if sample.trip_id else None
    region = trip.region if trip and trip.region_id else None
    common = dict(sample=sample, sample_transfer_id=sample.transfer_id, user_id=sample.owner_id, species_id=sample.species_id,
                  country_id=trip.country_id if trip else None, sea_id=region.sea_id if region else None,
                  name=after['label'][:300])
    events = E.objects.filter(sample_transfer_id=sample.transfer_id)
    if not before or not before['live']:
        if not events.filter(kind=E.Kind.OBSERVATION_ADDED).exists():
            E.objects.create(kind=E.Kind.OBSERVATION_ADDED, **common)
        if after['video'] and not events.filter(kind=E.Kind.VIDEO_ADDED, detail__video=after['video']).exists():
            E.objects.create(kind=E.Kind.VIDEO_ADDED, detail={'video': after['video']}, **common)
        return
    now = timezone.now()
    identity_changed = any(before[f] != after[f] for f in IDENTITY_FIELDS)
    if identity_changed:
        E.objects.create(kind=E.Kind.SPECIES_CHANGED, old_name=before['label'][:300], **common)
    if after['video'] and after['video'] != before['video'] \
            and not events.filter(kind=E.Kind.VIDEO_ADDED, detail__video=after['video']).exists():
        E.objects.create(kind=E.Kind.VIDEO_ADDED, detail={'video': after['video']}, **common)
    changed = [f for f in TRACKED_FIELDS if before[f] != after[f]]
    if identity_changed or not changed:
        return       # a new identification brings its relabelled photo with it: that is one event, not two
    if events.filter(kind=E.Kind.OBSERVATION_ADDED, created_at__gte=now - ADDING_GRACE).exists():
        return
    recent = events.filter(kind=E.Kind.OBSERVATION_UPDATED, created_at__gte=now - UPDATE_FOLD).first()
    if recent:
        recent.detail = {'fields': sorted(set(recent.detail.get('fields', [])) | set(changed))}
        recent.count += 1
        recent.created_at = now
        recent.name = common['name']
        recent.save(update_fields=['detail', 'count', 'created_at', 'name'])
    else:
        E.objects.create(kind=E.Kind.OBSERVATION_UPDATED, detail={'fields': sorted(changed)}, **common)


# --- new gallery cards ------------------------------------------------------------------------------------------
def _area_saved(sender, instance, created=False, raw=False, **kwargs):
    if raw or _off() or not created or not instance.defining_sample_id:
        return
    try:
        with transaction.atomic():
            _log_area(instance)
    except Exception:
        logger.exception('activity log: could not log a new species card')


def _log_area(area):
    from .models import ActivityEvent as E, SpeciesArea
    variant = area.undetermined_variant or ''
    if E.objects.filter(kind=E.Kind.SPECIES_NEW, species_id=area.species_id, country_id=area.country_id,
                        sea_id=area.sea_id, detail__variant=variant).exists():
        return
    others = SpeciesArea.objects.filter(species_id=area.species_id).exclude(pk=area.pk)
    sample = area.defining_sample
    E.objects.create(
        kind=E.Kind.SPECIES_NEW, species_area=area, species_id=area.species_id, country_id=area.country_id, sea_id=area.sea_id,
        sample=sample, sample_transfer_id=sample.transfer_id if sample else None, user_id=sample.owner_id if sample else None,
        name=f'{area.species.scientific_name} {variant}'.strip()[:300],
        detail={'variant': variant, 'new_to_site': not others.exists(),
                'new_to_sea': not others.filter(sea_id=area.sea_id).exists()})


# --- accounts ---------------------------------------------------------------------------------------------------
def _user_saved(sender, instance, created=False, raw=False, **kwargs):
    # A real sign-up only: accounts arriving by table transfer have no usable password, guest photographers are
    # inactive, and the owner is not logged.
    if raw or _off() or not created or not instance.is_active or not instance.has_usable_password() or is_excluded_user(instance):
        return
    from .models import ActivityEvent as E
    try:
        E.objects.create(kind=E.Kind.SIGNUP, public=False, user=instance, name=instance.username[:300])
    except Exception:
        logger.exception('activity log: could not log a sign-up')


def _user_logged_in(sender, request, user, **kwargs):
    if _off() or is_excluded_user(user):
        return
    from .models import ActivityEvent as E
    try:
        E.objects.create(kind=E.Kind.LOGIN, public=False, user=user, name=user.username[:300])
    except Exception:
        logger.exception('activity log: could not log a login')


def connect():
    from .models import Sample, SpeciesArea
    models.signals.pre_save.connect(_sample_before_save, sender=Sample, dispatch_uid='activity_sample_before')
    models.signals.post_save.connect(_sample_saved, sender=Sample, dispatch_uid='activity_sample_saved')
    models.signals.post_save.connect(_area_saved, sender=SpeciesArea, dispatch_uid='activity_area_saved')
    models.signals.post_save.connect(_user_saved, sender=settings.AUTH_USER_MODEL, dispatch_uid='activity_user_saved')
    user_logged_in.connect(_user_logged_in, dispatch_uid='activity_user_logged_in')


# --- visit counter ----------------------------------------------------------------------------------------------
BOT_AGENT = re.compile(r'bot|crawl|spider|slurp|facebookexternalhit|whatsapp|telegram|embedly|preview|monitor|uptime|'
                       r'curl|wget|python|httpx|go-http|java/|headless|lighthouse|pingdom|render', re.I)
SKIPPED_PREFIXES = ('/admin/', '/analytics/', '/healthz', '/robots.txt', '/sitemap.xml', '/static/', '/media/',
                    '/observations/species-search/', '/observations/species-area-status/', '/observations/image-search/',
                    '/observations/trips/suggest/')


def should_count(request, response):
    if request.method != 'GET' or response.status_code != 200:
        return False
    if 'text/html' not in response.get('Content-Type', ''):
        return False
    if request.path.startswith(SKIPPED_PREFIXES):
        return False
    if request.COOKIES.get('exclude_analytics') == '1':
        return False
    if is_excluded_user(getattr(request, 'user', None)):
        return False
    agent = request.META.get('HTTP_USER_AGENT', '')
    if not agent or BOT_AGENT.search(agent):
        return False
    if request.headers.get('Purpose') == 'prefetch' or request.headers.get('Sec-Purpose', '').startswith('prefetch'):
        return False
    return True


def client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (forwarded.split(',')[0].strip() if forwarded else '') or request.META.get('REMOTE_ADDR', '')


def record_visit(request):
    from .models import DailyPageView, DailyVisitor
    day = timezone.localdate()
    path = request.path[:300]
    if not DailyPageView.objects.filter(day=day, path=path).update(views=F('views') + 1):
        try:
            with transaction.atomic():
                DailyPageView.objects.create(day=day, path=path, views=1)
        except IntegrityError:
            DailyPageView.objects.filter(day=day, path=path).update(views=F('views') + 1)
    key = hashlib.sha256(f'{settings.SECRET_KEY}|{day}|{client_ip(request)}|{request.META.get("HTTP_USER_AGENT", "")}'
                         .encode()).hexdigest()
    try:
        with transaction.atomic():
            DailyVisitor.objects.get_or_create(day=day, key=key)
    except IntegrityError:
        pass


EXCLUDE_COOKIE = 'exclude_analytics'                 # the same cookie as /analytics/exclude/ (config.views)
EXCLUDE_COOKIE_MAX_AGE = 60 * 60 * 24 * 366


def mark_owner_browser(request, response):
    """The owner's browser keeps the opt-out cookie: set on any response while the owner is signed in, so the
    browser stays uncounted (here and in Google Analytics) after signing out."""
    if request.COOKIES.get(EXCLUDE_COOKIE) == '1' or not is_excluded_user(getattr(request, 'user', None)):
        return
    response.set_cookie(EXCLUDE_COOKIE, '1', max_age=EXCLUDE_COOKIE_MAX_AGE, path='/',
                        secure=settings.PRODUCTION, httponly=True, samesite='Lax')


class VisitCounterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if should_count(request, response):
                record_visit(request)
            mark_owner_browser(request, response)
        except Exception:
            logger.exception('visit counter failed')    # counting must never break a page
        return response


connect()
