"""Ratings and views of an observation's photo and video ("the artistic stage").

Each observation (Sample) has six fields, per medium (photo / video):
  * photographer_<media>_rating -- the photographer's own stars: the observation's owner, signed in, rating it;
  * audience_<media>_rating     -- everyone else's, as a Bayesian average (bayesian below) of their MediaRating rows;
  * <media>_views               -- how many times it was viewed: the photo opened large, the video played.

Who rates: anyone -- a signed-in member as himself, a guest as the random id kept in his browser (RATER_COOKIE).
Each rater has one rating per observation and medium, which he sees whenever he opens it and can change or clear.
Views are not counted for the observation's own photographer, the site owner (activity.is_excluded_user), a browser
with the analytics opt-out cookie, or a bot; the page counts one view per medium per browser tab session.

Everything is written with queryset.update(), so it never changes updated_at, never logs an activity event and never
invalidates a transfer preview. Per environment: ratings and views on the live site and on the Mac are separate and
never transfer. The gallery does not show them but can sort by them (catalog.js, app.js MEDIA_SORTS) -- by the
audience's rating, by the views, and by the visitor's own stars (my_rating_map).

Endpoints (urls: observations/<pk>/rating/ and observations/<pk>/viewed/), JSON:
  GET  rating/                       -> {"image": stars|null, "video": stars|null, "photographer": bool}
  POST rating/  media=image|video stars=1..5 (0 clears) -> the same, after the change
  POST viewed/  media=image|video   -> {"counted": bool}
"""
import re
import uuid

from django.conf import settings
from django.db.models import Count, F, Sum
from django.http import Http404, HttpResponseBadRequest, HttpResponseNotAllowed, JsonResponse

from .models import MediaRating, Sample

MEDIA = ('image', 'video')
# The six per-environment fields on Sample. A transfer that rewrites an observation (sample_transfer.sample_plan
# builds it anew from the file) must carry them over from the target's own row, never reset them.
SAMPLE_FIELDS = ('photographer_image_rating', 'photographer_video_rating', 'audience_image_rating',
                 'audience_video_rating', 'image_views', 'video_views')
# The Bayesian average: as if every observation already had PRIOR_WEIGHT ratings of PRIOR_MEAN stars, so a single
# 5-star rating (4.0) does not outrank forty ratings that average 4.8 (4.6).
PRIOR_MEAN = 3.0
PRIOR_WEIGHT = 3
RATER_COOKIE = 'seaslugs_rater'
RATER_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2
_VISITOR_RE = re.compile(r'[0-9a-f]{32}')


def bayesian(total, count):
    """The audience rating from the sum and number of its ratings; None while nobody has rated."""
    if not count:
        return None
    return round((PRIOR_MEAN * PRIOR_WEIGHT + total) / (PRIOR_WEIGHT + count), 3)


def has_media(sample, media):
    return bool(sample.image) if media == 'image' else bool(sample.video_url)


def is_photographer(request, sample):
    user = getattr(request, 'user', None)
    return bool(user and user.is_authenticated and user.pk == sample.owner_id)


def visitor_id(request):
    value = request.COOKIES.get(RATER_COOKIE, '')
    return value if _VISITOR_RE.fullmatch(value) else ''


def rater_filter(request):
    """The MediaRating lookup of the current rater: his user, else his browser's id ({} for a guest without one)."""
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        return {'user': user}
    visitor = visitor_id(request)
    return {'visitor': visitor} if visitor else {}


def refresh_audience(sample_id, media):
    totals = MediaRating.objects.filter(sample_id=sample_id, media=media).aggregate(total=Sum('stars'), count=Count('id'))
    Sample.objects.filter(pk=sample_id).update(**{f'audience_{media}_rating': bayesian(totals['total'] or 0, totals['count'])})


def rate(request, sample, media, stars):
    """Records (stars 1-5) or clears (0) the current rater's stars; returns the guest id to keep in his cookie
    ('' when none is needed)."""
    if is_photographer(request, sample):
        Sample.objects.filter(pk=sample.pk).update(**{f'photographer_{media}_rating': stars or None})
        return ''
    who = rater_filter(request)
    new_visitor = ''
    if not who:
        if not stars:
            return ''
        new_visitor = uuid.uuid4().hex
        who = {'visitor': new_visitor}
    if stars:
        MediaRating.objects.update_or_create(sample=sample, media=media, **who, defaults={'stars': stars})
    else:
        MediaRating.objects.filter(sample=sample, media=media, **who).delete()
    refresh_audience(sample.pk, media)
    return new_visitor


def my_ratings(request, sample):
    if is_photographer(request, sample):
        return {'image': sample.photographer_image_rating, 'video': sample.photographer_video_rating, 'photographer': True}
    who = rater_filter(request)
    mine = dict(MediaRating.objects.filter(sample=sample, **who).values_list('media', 'stars')) if who else {}
    return {'image': mine.get('image'), 'video': mine.get('video'), 'photographer': False}


def my_rating_map(request):
    """Every rating of the current visitor, for the gallery's "my rating" sorts (catalog.js "my_ratings"):
    {sample id (str): {"image": stars, "video": stars}} -- his MediaRating rows, and for a signed-in member also his
    photographer stars on his own observations. Empty for a guest who never rated."""
    out = {}
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        from django.db.models import Q
        for pk, image, video in Sample.objects.filter(owner=user, deleted_at__isnull=True).filter(
                Q(photographer_image_rating__isnull=False) | Q(photographer_video_rating__isnull=False)
        ).values_list('pk', 'photographer_image_rating', 'photographer_video_rating'):
            entry = out.setdefault(str(pk), {})
            if image: entry['image'] = image
            if video: entry['video'] = video
    who = rater_filter(request)
    if who:
        for sample_id, media, stars in MediaRating.objects.filter(**who).values_list('sample_id', 'media', 'stars'):
            out.setdefault(str(sample_id), {})[media] = stars
    return out


def counts_view(request, sample):
    from .activity import BOT_AGENT, EXCLUDE_COOKIE, is_excluded_user
    if is_photographer(request, sample) or is_excluded_user(getattr(request, 'user', None)):
        return False
    if request.COOKIES.get(EXCLUDE_COOKIE) == '1':
        return False
    agent = request.META.get('HTTP_USER_AGENT', '')
    return bool(agent) and not BOT_AGENT.search(agent)


def _sample(pk):
    sample = Sample.objects.filter(pk=pk, status=Sample.Status.PUBLISHED, deleted_at__isnull=True).first()
    if sample is None:
        raise Http404
    return sample


def _media(request, sample):
    media = request.POST.get('media')
    return media if media in MEDIA and has_media(sample, media) else None


def rating(request, pk):
    sample = _sample(pk)
    if request.method == 'GET':
        response = JsonResponse(my_ratings(request, sample))
    elif request.method == 'POST':
        media = _media(request, sample)
        try:
            stars = int(request.POST.get('stars', ''))
        except ValueError:
            stars = -1
        if media is None or not 0 <= stars <= 5:
            return HttpResponseBadRequest('bad rating')
        new_visitor = rate(request, sample, media, stars)
        sample.refresh_from_db()
        response = JsonResponse(my_ratings(request, sample) if not new_visitor else
                                {**{m: None for m in MEDIA}, media: stars, 'photographer': False})
        if new_visitor:
            response.set_cookie(RATER_COOKIE, new_visitor, max_age=RATER_COOKIE_MAX_AGE, path='/',
                                secure=settings.PRODUCTION, httponly=True, samesite='Lax')
    else:
        return HttpResponseNotAllowed(['GET', 'POST'])
    response['Cache-Control'] = 'private, no-store'
    return response


def viewed(request, pk):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    sample = _sample(pk)
    media = _media(request, sample)
    if media is None:
        return HttpResponseBadRequest('bad media')
    counted = counts_view(request, sample)
    if counted:
        Sample.objects.filter(pk=sample.pk).update(**{f'{media}_views': F(f'{media}_views') + 1})
    response = JsonResponse({'counted': counted})
    response['Cache-Control'] = 'private, no-store'
    return response
