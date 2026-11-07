"""The /news/ page ("חדשות ופעילות"): what happened on the site lately, the site's growth since it went live, and,
for managers, visits, sign-ups and logins.

Everything here reads the activity log and visit counter that activity.py writes; this module only selects and
words it. Public lines are shown only while their observation (or gallery card) is still public, so a removed
observation quietly drops out of the page. The new-species list can be filtered by sea, and the whole feed with it.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Min, Q, Sum
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .counts import count_text
from .photographers import PHOTOGRAPHER_GROUP
from .home_markup import render_markup
from .i18n import get_lang
from .models import (ActivityEvent, DailyPageView, DailyVisitor, NewsPost, Sample, Sea, SpeciesArea, full_name_for)
from .templatetags.seaslugs_i18n import loc, t

CHART_W, CHART_H, PAD_X, PAD_Y = 900, 260, 46, 26


def is_manager(user):
    return user.is_authenticated and user.is_staff


def _live_sample(sample):
    return bool(sample and sample.status == 'published' and sample.deleted_at is None)


def _area_slugs(events):
    """{(species, country, sea, variant): slug} for the species pages the lines link to."""
    keys = {(e.sample.species_id, e.sample.trip.country_id, e.sample.trip.region.sea_id, e.sample.undetermined_variant)
            for e in events if e.sample and e.sample.kind == 'species' and e.sample.trip_id and e.sample.trip.region_id}
    species = {k[0] for k in keys}
    return {(a.species_id, a.country_id, a.sea_id, a.undetermined_variant): a.slug
            for a in SpeciesArea.objects.filter(species_id__in=species, defining_sample__isnull=False).exclude(slug__isnull=True)}


def _line(event, lang, slugs):
    sample = event.sample
    trip = sample.trip if sample and sample.trip_id else None
    link = ''
    if event.kind == ActivityEvent.Kind.SPECIES_NEW and event.species_area and event.species_area.slug:
        link = reverse('species-page', args=[event.species_area.slug])
    elif sample and sample.kind == 'species' and trip and trip.region_id:
        slug = slugs.get((sample.species_id, trip.country_id, trip.region.sea_id, sample.undetermined_variant))
        link = reverse('species-page', args=[slug]) if slug else ''
    elif sample and sample.kind == 'collection' and trip:
        link = reverse('dive-trips') + f'#trip-{trip.pk}'
    place = ' · '.join(x for x in (
        loc(event.country, lang) if event.country_id else '',
        loc(trip.region, lang) if trip and trip.region_id else '') if x)
    is_collection = bool(sample and sample.kind == 'collection')
    name = (sample.gallery_title(lang) or event.name) if is_collection else event.name
    return {
        'kind': event.kind, 'sample_id': event.sample_id, 'video_id': event.detail.get('video', ''), 'when': timezone.localtime(event.created_at), 'name': name, 'is_collection': is_collection,
        'old_name': event.old_name, 'link': link, 'place': place, 'count': event.count,
        'photographer': full_name_for(event.user, lang) if event.user_id else '',
        'video_url': sample.video_url if sample and event.kind == ActivityEvent.Kind.VIDEO_ADDED else '',
        'photo': (reverse('observation-photo', args=[sample.pk]) if sample and sample.image else
                  (f'https://i.ytimg.com/vi/{_video(sample.video_url)}/mqdefault.jpg' if sample and sample.video_url else '')),
        'thumb': (f'https://i.ytimg.com/vi/{event.detail.get("video")}/mqdefault.jpg'
                  if event.kind == ActivityEvent.Kind.VIDEO_ADDED and event.detail.get('video') else ''),
        'new_to_site': event.detail.get('new_to_site'), 'species_id': event.species_id, 'new_to_sea': event.detail.get('new_to_sea'),
        'sea': loc(event.sea, lang) if event.sea_id else '',
    }


def _video(url):
    from .models import youtube_id
    try:
        return youtube_id(url)
    except Exception:
        return ''


def public_feed(since, until=None, sea_id=None, lang='he'):
    events = ActivityEvent.objects.filter(public=True, created_at__gte=since)
    if until:
        events = events.filter(created_at__lt=until)
    events = (events
              .select_related('sample', 'sample__trip', 'sample__trip__region', 'user', 'user__profile', 'country', 'sea',
                              'species_area', 'species_area__defining_sample'))
    if sea_id:
        events = events.filter(sea_id=sea_id)
    shown = []
    for event in events:
        if event.kind == ActivityEvent.Kind.SPECIES_NEW:
            if not (event.species_area and _live_sample(event.species_area.defining_sample)):
                continue
        elif not _live_sample(event.sample):
            continue
        shown.append(event)
    slugs = _area_slugs(shown)
    sections = defaultdict(list)
    for event in shown:
        sections[event.kind].append(_line(event, lang, slugs))
    return sections


MONTHS = {'he': ('ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני', 'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר'),
          'en': ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')}
MONTH_NAMES = {'he': MONTHS['he'], 'en': ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
                                         'September', 'October', 'November', 'December')}
# The progress chart: plot area inside the SVG, its y axis from 0 with a faint grid line every Y_STEP (the step
# doubles if the axis would need more than Y_MAX_TICKS lines).
P_W, P_H, P_LEFT, P_RIGHT, P_TOP, P_BOTTOM = 900, 390, 60, 20, 24, 56
Y_STEP, Y_MAX_TICKS = 20, 25
LABEL_GAP = 15                 # px between two y-axis labels
LABEL_MAX_SHIFT = 12           # a y-axis label moved further than this from its line is left out
SPECIES_LABEL_GAP = 15         # px between two species numbers written in the bars


def progress_chart(lang, sea_id=None):
    """Cumulative public observations and species from the first observation to today, as upward bars: one per day
    (the chart keeps its width; the bars get narrower as days are added) showing the running totals at the end of
    that day, the observations bar behind the species bar, both the day's full width with no gap between bars. The
    number of species is written (upright, inside the top of its bar) only on the days it changes. With a sea chosen,
    only that sea's observations and the species first seen there."""
    live = Sample.objects.filter(status='published', deleted_at__isnull=True, kind__in=('species', 'collection'))
    if sea_id:
        live = live.filter(trip__region__sea_id=sea_id)
    dates = [timezone.localtime(d).date() for d in live.values_list('created_at', flat=True)]
    first_seen = [timezone.localtime(d).date() for d in live.filter(kind='species', species__isnull=False)
                  .values('species_id').annotate(first=Min('created_at')).values_list('first', flat=True)]
    if not dates:
        return None
    start, today = min(dates), timezone.localdate()
    per_obs, per_species = Counter(dates), Counter(first_seen)
    buckets = [(start + timedelta(days=i), start + timedelta(days=i + 1)) for i in range((today - start).days + 1)]
    totals, total_o, total_s, day = [], 0, 0, buckets[0][0]
    for first, nxt in buckets:
        while day < nxt and day <= today:
            total_o += per_obs[day]; total_s += per_species[day]
            day += timedelta(days=1)
        totals.append((total_o, total_s))
    peak = max(total_o, total_s, 1)
    low = 0
    step = Y_STEP
    while (peak - low) / step > Y_MAX_TICKS:
        step *= 2
    high = low + step * max(1, -(-(peak - low) // step))
    left, right, top, bottom = P_LEFT, P_W - P_RIGHT, P_TOP, P_H - P_BOTTOM
    domain_start, domain_end = buckets[0][0], buckets[-1][1]
    span = (domain_end - domain_start).days
    x_of = lambda d: left + (right - left) * (d - domain_start).days / span
    y_of = lambda v: bottom - (bottom - top) * (v - low) / (high - low)
    bars, previous_species, last_label_x = [], None, None
    for (first, nxt), (o, sp) in zip(buckets, totals):
        x1, x2 = x_of(first), x_of(nxt)
        centre, width = (x1 + x2) / 2, x2 - x1
        bar = lambda value, share: {'x': round(centre - width * share / 2, 2), 'w': round(width * share + .4, 2),
                                    'y': round(y_of(max(value, low)), 1), 'h': round(bottom - y_of(max(value, low)), 1)}
        species_bar = bar(sp, 1)
        # the number of species, only where it changed, inside the top of the bar (when there is room for it and it
        # would not touch the previous number)
        label = None
        if sp != previous_species and sp > 0 and species_bar['h'] >= 30 \
                and (last_label_x is None or centre - last_label_x >= SPECIES_LABEL_GAP):
            label = {'x': round(centre, 1), 'y': round(species_bar['y'] + 4, 1)}
            last_label_x = centre
        previous_species = sp
        bars.append({'obs': bar(o, 1), 'species': species_bar, 'species_label': label, 'obs_value': o, 'species_value': sp,
                     'start': max(first, start), 'end': min(nxt - timedelta(days=1), today)})
    y_ticks = [{'y': round(y_of(v), 1), 'label': v} for v in range(low, high + 1, step)]
    # The y axis is labelled with every observation total the bars reach (each new value once). The line sits at the
    # exact height; a label that would touch its neighbour is moved just enough to clear it (a short leader joins it
    # to its line). The 20-step lines stay as a faint grid.
    value_ticks = [{'y': round(y_of(v), 1), 'label': v}
                   for v in sorted({b['obs_value'] for b in bars if b['obs_value'] >= low}, reverse=True)]
    kept, previous = [], None
    for tick in value_ticks:                                  # top to bottom: push down to clear the one above,
        tick['label_y'] = tick['y'] if previous is None else max(tick['y'], previous + LABEL_GAP)
        if tick['label_y'] - tick['y'] > LABEL_MAX_SHIFT:     # but a crowd of near values keeps only some of them
            continue
        kept.append(tick)
        previous = tick['label_y']
    value_ticks = kept
    limit = bottom - LABEL_GAP
    for tick in reversed(value_ticks):                        # bottom to top: clear of the axis' starting value
        tick['label_y'] = round(min(tick['label_y'], limit), 1)
        limit = tick['label_y'] - LABEL_GAP
    # x axis: each month's name in the middle of its stretch, the year under all of its months
    months, years, month = [], [], domain_start.replace(day=1)
    while month < domain_end:
        nxt = (month + timedelta(days=32)).replace(day=1)
        x1, x2 = x_of(max(month, domain_start)), x_of(min(nxt, domain_end))
        months.append({'x': round((x1 + x2) / 2, 1), 'start': round(x1, 1), 'label': MONTHS[lang][month.month - 1],
                       'wide': x2 - x1 >= 34})
        if years and years[-1]['year'] == month.year:
            years[-1]['x2'] = x2
        else:
            years.append({'year': month.year, 'x1': x1, 'x2': x2})
        month = nxt
    for y in years:
        y['x'] = round((y['x1'] + y['x2']) / 2, 1)
    return {'w': P_W, 'h': P_H, 'left': left, 'right': right, 'top': top, 'bottom': bottom,
            'plot_w': right - left, 'plot_h': bottom - top + 2,
            'month_y': bottom + 20, 'year_y': bottom + 44, 'year_line_y': bottom + 28,
            'bars': bars, 'obs_total': total_o, 'species_total': total_s, 'start': start,
            'y_ticks': y_ticks, 'value_ticks': value_ticks, 'months': months, 'years': years, 'y_low': low, 'y_step': step}


def manager_data(lang):
    today = timezone.localdate()
    month_ago = today - timedelta(days=29)
    views = dict(DailyPageView.objects.filter(day__gte=month_ago).values('day').annotate(n=Sum('views')).values_list('day', 'n'))
    visitors = dict(DailyVisitor.objects.filter(day__gte=month_ago).values('day').annotate(n=Count('id')).values_list('day', 'n'))
    rows = [{'day': month_ago + timedelta(days=i)} for i in range(30)]
    top = max([views.get(r['day'], 0) for r in rows] + [1])
    bar_w = (CHART_W - 2 * PAD_X) / 30
    for i, r in enumerate(rows):
        r['views'], r['visitors'] = views.get(r['day'], 0), visitors.get(r['day'], 0)
        r['x'] = PAD_X + i * bar_w
        r['w'] = bar_w * .42
        r['x2'] = r['x'] + bar_w * .45
        for key in ('views', 'visitors'):
            r[key + '_h'] = (CHART_H - 2 * PAD_Y) * r[key] / top
            r[key + '_y'] = CHART_H - PAD_Y - r[key + '_h']
        r['label'] = r['day'].strftime('%d/%m') if i % 5 == 0 or i == 29 else ''

    def total(since):
        return {'views': DailyPageView.objects.filter(day__gte=since).aggregate(n=Sum('views'))['n'] or 0,
                'visitors': DailyVisitor.objects.filter(day__gte=since).count()}
    User = get_user_model()
    login_since = timezone.now() - timedelta(days=30)
    logins = dict(ActivityEvent.objects.filter(kind='login', created_at__gte=login_since).values('user_id')
                  .annotate(n=Count('id')).values_list('user_id', 'n'))
    observations = dict(Sample.objects.filter(deleted_at__isnull=True).values('owner_id').annotate(n=Count('id'))
                        .values_list('owner_id', 'n'))
    users = []
    for user in (User.objects.filter(is_active=True).exclude(password__startswith='!').select_related('profile')
                 .order_by('-date_joined')):
        users.append({'name': full_name_for(user, lang) or user.username, 'username': user.username,
                      'joined': timezone.localtime(user.date_joined),
                      'last_login': timezone.localtime(user.last_login) if user.last_login else None,
                      'logins': logins.get(user.pk, 0), 'observations': observations.get(user.pk, 0),
                      'staff': user.is_staff})
    # Photographers: everyone with a published observation on the site (the photographer of an observation is its
    # owner -- Sample.photographer_name -- guest photographers' inactive accounts included), and the potential ones:
    # every registered member and guest photographer (photographers.py) who has not published a photo yet (0).
    # Most observations first.
    published = dict(Sample.objects.filter(status='published', deleted_at__isnull=True).values('owner_id')
                     .annotate(n=Count('id')).values_list('owner_id', 'n'))
    members = User.objects.filter(is_active=True).exclude(password__startswith='!')
    photographers = sorted(
        ({'name': full_name_for(user, lang) or user.username, 'email': user.email,
          'phone': getattr(getattr(user, 'profile', None), 'phone', ''), 'observations': published.get(user.pk, 0),
          'guest': not user.is_active}
         for user in User.objects.filter(Q(pk__in=published) | Q(pk__in=members) | Q(groups__name=PHOTOGRAPHER_GROUP))
         .distinct().select_related('profile')),
        key=lambda p: (-p['observations'], p['name']))
    photographers_active = sum(1 for p in photographers if p['observations'])
    # Visitors by country over the 30 days (DailyVisitor.country, geo.py): a visitor counts once per day, as in the
    # tiles above; '' = unknown (no country database, a private address, or a day before countries were recorded).
    countries = [{'code': r['country'], 'visitors': r['visitors'], 'views': r['views'] or 0}
                 for r in DailyVisitor.objects.filter(day__gte=month_ago).values('country')
                 .annotate(visitors=Count('id'), views=Sum('views')).order_by('-visitors', 'country')]
    most = max([c['visitors'] for c in countries] + [1])
    for c in countries:
        c['bar'] = round(100 * c['visitors'] / most)
    recent_logins = [{'when': timezone.localtime(e.created_at), 'name': full_name_for(e.user, lang) or e.name}
                     for e in ActivityEvent.objects.filter(kind='login').select_related('user', 'user__profile')[:20] if e.user]
    return {
        'visit_rows': rows, 'visit_top': top, 'visit_chart': {'w': CHART_W, 'h': CHART_H, 'pad_x': PAD_X,
                                                              'right': CHART_W - PAD_X, 'bottom': CHART_H - PAD_Y},
        'visits_today': total(today), 'visits_week': total(today - timedelta(days=6)), 'visits_month': total(month_ago),
        'top_pages': DailyPageView.objects.filter(day__gte=month_ago).values('path').annotate(n=Sum('views')).order_by('-n')[:15],
        'users': users, 'recent_logins': recent_logins, 'photographers': photographers, 'countries': countries,
        'photographers_active': photographers_active,
        'country_count': sum(1 for c in countries if c['code']),
        'signups_month': ActivityEvent.objects.filter(kind='signup', created_at__gte=login_since).count(),
    }


def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def activity_years():
    """The years the year list offers: every year with public activity, and the current one, newest first."""
    years = {d.year for d in ActivityEvent.objects.filter(public=True).datetimes('created_at', 'year')}
    years.add(timezone.localdate().year)
    return sorted(years, reverse=True)


def activity_months(year):
    """The months of `year` with public activity: the only ones the month list offers."""
    zone = timezone.get_current_timezone()
    return sorted({d.month for d in ActivityEvent.objects.filter(
        public=True, created_at__gte=datetime(year, 1, 1, tzinfo=zone), created_at__lt=datetime(year + 1, 1, 1, tzinfo=zone)
    ).datetimes('created_at', 'month')})


def chosen_period(request, lang):
    """The feed's period: the last week by default; a chosen year (the whole year), a chosen month (of that year, or
    without a year its latest occurrence up to today), from the month and year lists."""
    year, month = _int(request.GET.get('year')), _int(request.GET.get('month'))
    month = month if 1 <= month <= 12 else 0
    year = year if year in activity_years() else 0          # only the years the list offers
    today = timezone.localdate()
    if month and not year:
        year = today.year if month <= today.month else today.year - 1
    months = activity_months(year or today.year)
    if month not in months:
        month = 0           # a month without activity in that year (e.g. kept from another year): the whole year
    if not year and not month:
        # the last week: the month list shows the current month, so "all months" from there opens the whole year
        return {'since': timezone.now() - timedelta(days=7), 'until': None, 'year': 0, 'month': 0, 'week': True,
                'label': t('השבוע האחרון', lang), 'months': months, 'current_month': today.month}
    zone = timezone.get_current_timezone()
    if month:
        start = datetime(year, month, 1, tzinfo=zone)
        end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=zone)
        label = f'{MONTH_NAMES[lang][month - 1]} {year}'
    else:
        start, end, label = datetime(year, 1, 1, tzinfo=zone), datetime(year + 1, 1, 1, tzinfo=zone), str(year)
    return {'since': start, 'until': end, 'year': year, 'month': month, 'week': False, 'label': label, 'months': months}


def _period_query(request):
    """The page's period and sea, as a query string for the slideshow (and back)."""
    from django.utils.http import urlencode
    params = {k: request.GET[k] for k in ('year', 'month', 'sea', 'lang') if request.GET.get(k)}
    return '?' + urlencode(params) if params else ''


def news_slideshow(request):
    """The new videos of the news page's period and sea, played one after another in a loop -- open to everyone.

    Each video plays from YouTube through its IFrame player API, embedded from www.youtube.com (checked by the owner:
    no ads), moving on when it ends; a video YouTube refuses to embed is skipped. Nothing passes through this server.
    A manager on the Mac plays the offline copy instead wherever there is one on this computer (local_videos.py), so
    the slideshow also works without internet; ?source=youtube makes a manager use YouTube for everything."""
    from .local_videos import STATUS_OK, local_video_url, statuses
    lang = get_lang(request)
    try:
        sea_id = int(request.GET.get('sea') or 0) or None
    except ValueError:
        sea_id = None
    period = chosen_period(request, lang)
    lines, seen = [], set()
    for line in public_feed(period['since'], period['until'], sea_id, lang)['video_added']:
        if line['sample_id'] and line['sample_id'] not in seen:
            seen.add(line['sample_id']); lines.append(line)
    manager = is_manager(request.user)
    force_youtube = request.GET.get('source') == 'youtube'
    found, samples = {}, {}
    if manager and not force_youtube:
        samples = {x.pk: x for x in Sample.objects.filter(pk__in=seen).select_related('trip')}
        found = statuses(list(samples.values()))
    items = []
    for line in reversed(lines):                             # oldest first, in the order they were added
        sample = samples.get(line['sample_id'])
        src = local_video_url(sample) if sample and found.get(sample.pk) == STATUS_OK else ''
        if src or line['video_id']:
            items.append({**line, 'src': src})
    query = _period_query(request)
    local_count = sum(1 for item in items if item['src'])
    switch_url = ''
    if manager and force_youtube:
        switch_url = reverse('news-slideshow') + query                      # back to the Mac copies
    elif manager and local_count:
        switch_url = reverse('news-slideshow') + query + ('&' if query else '?') + 'source=youtube'
    return render(request, 'observations/news_slideshow.html', {
        'items': items, 'period': period, 'missing': len(lines) - len(items), 'local_count': local_count,
        'force_youtube': force_youtube, 'switch_url': switch_url, 'back_url': reverse('news') + query,
    })


def news(request):
    lang = get_lang(request)
    try:
        sea_id = int(request.GET.get('sea') or 0) or None
    except ValueError:
        sea_id = None
    period = chosen_period(request, lang)
    sections = public_feed(period['since'], period['until'], sea_id, lang)
    sea_ids = set(ActivityEvent.objects.filter(public=True, sea__isnull=False).values_list('sea_id', flat=True))
    seas = sorted(Sea.objects.filter(pk__in=sea_ids), key=lambda s: loc(s, lang))
    if sea_id not in sea_ids:
        sea_id = None
    today = timezone.localdate()
    posts = NewsPost.objects.filter(is_published=True, published_on__lte=today)
    planned = (posts.filter(kind=NewsPost.Kind.TRIP).filter(Q(trip_end__gte=today) | Q(trip_end__isnull=True, trip_start__gte=today))
               .order_by('trip_start'))
    contribute = reverse('observation-new') if request.user.is_authenticated else reverse('signup')
    def rendered(post):
        return {'post': post, 'title': post.title(lang), 'kind': post.kind,
                'body': render_markup(post.body(lang), {}, contribute)}
    live_areas = SpeciesArea.objects.filter(defining_sample__status='published', defining_sample__deleted_at__isnull=True)
    # the new-species list: species (species table) new to the site, each once -- not every new species-in-an-area
    species_list, seen = [], set()
    for line in sections['species_new']:
        if line['new_to_site'] and line['species_id'] not in seen:
            seen.add(line['species_id']); species_list.append(line)
    context = {
        'period': period, 'sea_id': sea_id, 'seas': seas,
        'month_options': [(m, MONTH_NAMES[lang][m - 1]) for m in period['months']], 'year_options': activity_years(),
        # new to the site = a species (species table) shown for the first time anywhere; new to an area = every new card
        'new_species_site': len(species_list),
        'species_list': species_list,
        'added': sections['observation_added'], 'videos': sections['video_added'], 'new_species': sections['species_new'],
        'changed': sections['species_changed'], 'updated': sections['observation_updated'],
        'posts': [rendered(p) for p in posts.exclude(kind=NewsPost.Kind.TRIP)[:10]],
        'planned_trips': [rendered(p) for p in planned],
        'chart': progress_chart(lang, sea_id),
        'chart_sea': next((loc(sea, lang) for sea in seas if sea.pk == sea_id), ''),
        'species_total_text': count_text((live_areas.filter(sea_id=sea_id) if sea_id else live_areas)
                                         .values('species_id').distinct().count(), lang),
        'manager': is_manager(request.user),
        'slideshow_url': reverse('news-slideshow') + _period_query(request),
        # section headings in the page's language (passed to the shared list template)
        'h_new': t('מינים חדשים', lang), 'h_added': t('תצפיות חדשות', lang),
        'h_changed': t('שינויים בהגדרת המין', lang), 'h_updated': t('תצפיות שעודכנו', lang),
    }
    if context['manager']:
        context.update(manager_data(lang))
    return render(request, 'observations/news.html', context)
