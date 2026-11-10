"""Dive-trip planning ("תכנון מסע צלילות", Sample.Kind.PLANNED).

- **What:** an observation of a dive trip that has not happened yet: its DiveTrip carries the future date (at least a
  year and a month; DiveTrip.start_date / end_date), the observation has a title and **no media**. Any member adds one
  with the observation form (kind "תכנון מסע צלילות", `/observations/new/?kind=planned`); it publishes itself.
- **Where it shows:** never in the gallery (the gallery, the species/taxon/trip pages, the sitemap and the news log
  all pick their kinds explicitly) -- only in the forum, where the trip is discussed and its owner manages the
  discussion, and in the "תכנון מסעות צלילה" section of the dive trips page.
- **Closing:** once the trip's last day has passed (`Sample.planning_open` is False) the planning is closed: it leaves
  the planning section and the forum, and nobody can write in its discussion any more. Its owner and the site managers
  still see it (in "התצפיות שלי" and in the forum by its address).
- **Becoming a dive trip:** after the trip, its owner (or a manager) edits it, chooses the kind "אוסף מינים / מסע
  צלילה" and adds a video or photo: the same row (same transfer_id, same discussion) is then a regular collection
  observation, under the usual rules (a member's collection waits for a manager's approval).
- Observations with media (species, collections) cannot be added to a trip before it starts (Sample.clean).
- **A series of trips** (DiveTrip.summary_trip): a planning on the summary trip opens a planning -- and so a
  discussion -- for each trip it sums up (sync_sub_plannings: when the series planning is saved, and when a trip joins
  the summary trip in the admin); each has the series planning's owner and its trip's title. The series planning stays
  open until the last of the trips ends; each trip's planning closes with its own trip. The planning section shows the
  trips' plannings inside the series card, and the forum links the series and its trips' discussions to each other.
"""
from datetime import date

from .models import Sample


def planned_samples():
    """Published, not deleted dive-trip plannings (open and closed)."""
    return (Sample.objects.filter(kind=Sample.Kind.PLANNED, status=Sample.Status.PUBLISHED, deleted_at__isnull=True)
            .select_related('trip', 'trip__region', 'trip__country', 'trip__site', 'site', 'owner', 'owner__profile'))


def open_plannings():
    """The open plannings, the soonest first -- without those of trips in a series whose summary trip is being planned
    (they are shown inside the series' card: sub_plannings)."""
    rows = [s for s in planned_samples() if s.planning_open]
    series = {s.trip_id for s in rows}
    rows = [s for s in rows if s.trip.summary_trip_id not in series]
    return sorted(rows, key=lambda s: (s.trip.start_date() or date.max, s.pk))


def sub_plannings(sample):
    """The open plannings of the trips that this planning's trip sums up, the soonest first."""
    if sample.kind != Sample.Kind.PLANNED or not sample.trip_id:
        return []
    rows = [s for s in planned_samples().filter(trip__summary_trip_id=sample.trip_id) if s.planning_open]
    return sorted(rows, key=lambda s: (s.trip.start_date() or date.max, s.pk))


def series_planning(sample):
    """The open planning of the summary trip of this planning's trip, or None."""
    if sample.kind != Sample.Kind.PLANNED or not sample.trip_id or not sample.trip.summary_trip_id:
        return None
    return next((s for s in planned_samples().filter(trip_id=sample.trip.summary_trip_id) if s.planning_open), None)


def sync_sub_plannings(summary_trip):
    """When a summary trip is being planned (an open, published planning on it): a planning for each trip it sums up
    that has none yet and has not ended -- same owner, the trip's title. Returns the plannings created."""
    from django.core.exceptions import ValidationError
    series = next((s for s in planned_samples().filter(trip=summary_trip) if s.planning_open), None)
    if series is None:
        return []
    created = []
    for trip in summary_trip.sub_trips.all():
        if Sample.objects.filter(kind=Sample.Kind.PLANNED, trip=trip, deleted_at__isnull=True).exists():
            continue
        end = trip.end_date()
        if not (trip.year and trip.month) or (end and end < date.today()):
            continue
        sample = Sample(kind=Sample.Kind.PLANNED, trip=trip, owner=series.owner, title=trip.title)
        try:
            sample.save_reviewed()
        except ValidationError:
            continue
        created.append(sample)
    return created


def closed_planning_ids():
    """Ids of every dive-trip planning that is closed (its date has passed) -- deleted or pending ones included."""
    return [s.pk for s in Sample.objects.filter(kind=Sample.Kind.PLANNED).select_related('trip') if not s.planning_open]


def date_range_text(trip):
    """"12–18/5/2027", "5/2027" -- the trip's dates as far as they are known."""
    if not trip.year:
        return ''
    if trip.month and trip.start_day:
        start, end = trip.start_date(), trip.end_date()
        if end and end != start:
            if (end.year, end.month) == (start.year, start.month):
                return f'⁦{start.day}–{end.day}/{start.month}/{start.year}⁩'
            return f'⁦{start.day}/{start.month}/{start.year}–{end.day}/{end.month}/{end.year}⁩'
        return f'{start.day}/{start.month}/{start.year}'
    return f'{trip.month}/{trip.year}' if trip.month else str(trip.year)


# --- pages: /planning/ (the open plannings) and /planning/<trip code>/ (one planning) ---------------------------------

def planning_page_url(trip, lang='he'):
    """A planning's own address, keyed by its trip's permanent code (like /trip/<code>/)."""
    from django.urls import reverse
    from .templatetags.seaslugs_i18n import with_lang
    return with_lang(reverse('planning-page', args=[trip.code]), lang)


def planning_trip_planning(trip):
    """The trip's planning (not deleted; one per trip -- Sample.clean), or None."""
    return (Sample.objects.filter(kind=Sample.Kind.PLANNED, trip=trip, deleted_at__isnull=True)
            .select_related('trip', 'trip__region', 'trip__country', 'trip__site', 'site', 'owner', 'owner__profile')
            .order_by('pk').first())


def plan_new_url(request):
    """The "plan a new trip" button: the observation form with the planning kind (via the login page when needed)."""
    from django.urls import reverse
    from django.utils.http import urlencode
    url = reverse('observation-new') + '?kind=planned'
    return url if request.user.is_authenticated else reverse('login') + '?' + urlencode({'next': url})


def planning_list(request):
    """/planning/: the open plannings, the soonest first (the same section as on the dive trips page)."""
    from django.shortcuts import render
    from .i18n import get_lang
    from .views import planning_rows
    lang = get_lang(request)
    rows = planning_rows(request, lang)
    return render(request, 'observations/planning_list.html', {
        'plannings': rows, 'plan_new_url': plan_new_url(request), 'planning_page': True})


def planning_page(request, code):
    """/planning/<trip code>/: one planning -- its dates, place, organizer and notes, its articles (a schedule), the
    series it belongs to or the trips it sums up, and its discussion with an "add a comment" button. A closed planning
    is shown to its owner and the site managers only; once it became a dive trip with a page, the address leads there
    (301), so a shared link keeps working."""
    from django.http import Http404, HttpResponsePermanentRedirect
    from django.shortcuts import get_object_or_404, render
    from .articles import article_links
    from .forum import _annotate, can_write, forum_url, is_site_manager, new_comment_url, trip_forum_url, visible_messages
    from .i18n import get_lang
    from .models import DiveTrip, full_name_for
    from .templatetags.seaslugs_i18n import loc
    from .trip_page import trip_collections, trip_page_url
    from .views import sample_edit_url
    trip = get_object_or_404(DiveTrip.objects.select_related('region', 'country', 'site', 'summary_trip'), code=code)
    lang = get_lang(request)
    user = request.user
    sample = planning_trip_planning(trip)
    public = bool(sample and sample.status == Sample.Status.PUBLISHED and sample.planning_open)
    privileged = bool(sample and (is_site_manager(user) or (user.is_authenticated and sample.owner_id == user.pk)))
    if not (public or privileged):
        if trip_collections(trip):
            return HttpResponsePermanentRedirect(trip_page_url(trip, lang))
        raise Http404
    def describe(s):
        t = s.trip
        s.display_title = s.gallery_title(lang) or t.title
        s.date_text = date_range_text(t)
        s.display_place = ' · '.join(x for x in (
            loc(t.region, lang) if t.region_id else (loc(t.country, lang) if t.country_id else t.region_name),
            loc(s.site, lang) if s.site_id else (loc(t.site, lang) if t.site_id else '')) if x)
        s.page_url = planning_page_url(t, lang)
        return s
    describe(sample)
    parent = series_planning(sample)
    children = [describe(x) for x in sub_plannings(sample)]
    note = (sample.note_en or sample.note_he) if lang == 'en' else (sample.note_he or sample.note_en)
    messages_list = _annotate(list(visible_messages(user).filter(observation=sample).select_related('user', 'user__profile', 'observation__owner')
                                   .order_by('created_at', 'pk')), user, lang)
    return render(request, 'observations/planning_page.html', {
        'sample': sample, 'trip': trip, 'note': note, 'organizer': full_name_for(sample.owner, lang) or sample.owner.username,
        'article_links': article_links(trip.articles.all(), lang),
        'parent': describe(parent) if parent else None, 'children': children,
        'messages_list': messages_list, 'can_write': can_write(sample), 'closed': not sample.planning_open,
        'forum_url': forum_url(sample, lang), 'forum_new_url': new_comment_url(sample, lang),
        'trip_forum_url': trip_forum_url(trip, lang),
        'edit_url': sample_edit_url(request, [sample]),
        'meta_description': ' · '.join(x for x in (sample.date_text, sample.display_place, note) if x)[:300],
    })
