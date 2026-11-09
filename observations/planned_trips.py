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
"""
from datetime import date

from .models import Sample


def planned_samples():
    """Published, not deleted dive-trip plannings (open and closed)."""
    return (Sample.objects.filter(kind=Sample.Kind.PLANNED, status=Sample.Status.PUBLISHED, deleted_at__isnull=True)
            .select_related('trip', 'trip__region', 'trip__country', 'trip__site', 'site', 'owner', 'owner__profile'))


def open_plannings():
    """The plannings whose trip has not ended yet, the soonest first."""
    rows = [s for s in planned_samples() if s.planning_open]
    return sorted(rows, key=lambda s: (s.trip.start_date() or date.max, s.pk))


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
