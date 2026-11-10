"""The observations forum (/forum/, "פורום תצפיות"): members write criticism, remarks, plans and discussion about the
site's observations.

- **Every discussion belongs to one observation** (a Sample: a species observation, a dive-trip collection, a taxon
  observation...). There is no general discussion.
- **The page:** filters that narrow the observation picker and the discussions shown -- the kind (KIND_FILTERS:
  species observations, dive trips, dive-trip planning, genera, families, orders), the photographer, the country, the
  region, the year and, by kind, the taxon (TAXON_FACETS: genus and species for species observations, the genus /
  family / order of a taxon observation). Each list offers the values found among the observations that match the
  other filters. With an observation chosen (`?obs=<pk>`) the page shows that observation, its whole discussion (oldest
  first) and the writing box (`#write`); without one -- the page a visitor lands on -- it lists the matching
  observations that have a discussion, the most recently active first (DISCUSSIONS_PER_PAGE groups a page): each a row
  (photo, name, place and date, number of messages, the latest message's time and writer; it opens the discussion)
  with its messages open beneath it and a +/- button that folds them. A series of dive trips is one group: the
  summary trip's discussion, then its trips' discussions by date, indented under it; its +/- folds the whole series.
- **Dive-trip planning** (planned_trips.py): its discussion is open until the trip's last day; then it is closed --
  gone from the forum (its owner and the site managers still reach it by its address) and nobody can write in it.
- **The discussion's manager** is the observation's owner (its photographer).
- **Who reads what:** a message for everyone is public -- visitors without an account read it too. A message for the
  discussion's manager only is seen by its writer, the discussion's manager and the site managers. A discussion of an
  observation that is not public (pending or deleted) is seen only by its owner and the site managers.
- **Who writes:** members only. The "add a comment" buttons go to `/forum/new/` (`?obs=<pk>` from an observation's
  page; without it from the home page, then the visitor picks the observation): a visitor who is not signed in goes to
  the login page (which then offers sign-up), and comes back to the forum afterwards.
- **Deleting** marks the message deleted (it disappears from the forum, the row stays): its writer, the discussion's
  manager and the site managers may.
- **Email:** a new message written here emails the observation's owner and the discussion's other writers who ticked
  "email me" on their profile (Profile.forum_email; notifications.notify_forum_message). A manager-only message goes to
  the owner alone. Messages arriving through the transfer send nothing.
- Messages travel between the Mac and the live site with the table transfer (forum_transfer.py).
"""
from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from .i18n import get_lang
from .models import ForumMessage, Sample, full_name_for
from .templatetags.seaslugs_i18n import loc, with_lang

DISCUSSIONS_PER_PAGE = 30
MAX_TEXT = 5000
# The kind filter: key -> (observation kinds, Hebrew label). A new kind of observation (e.g. planned dive trips) is
# added here.
KIND_FILTERS = {
    'species': ((Sample.Kind.SPECIES,), 'תצפיות מין'),
    'collection': ((Sample.Kind.COLLECTION,), 'מסעות צלילה'),
    'planned': ((Sample.Kind.PLANNED,), 'תכנון מסעות צלילה'),
    'genus': ((Sample.Kind.GENUS,), 'תצפיות של סוג'),
    'family': ((Sample.Kind.FAMILY,), 'תצפיות של משפחה'),
    'order': ((Sample.Kind.ORDER,), 'תצפיות של סדרה'),
}
# The taxon filters offered for each kind.
TAXON_FACETS = {'species': ('genus', 'species'), 'genus': ('genus',), 'family': ('family',), 'order': ('order',)}
# filter -> Hebrew label; the order of the filter row.
FACET_LABELS = {'photographer': 'צלם', 'country': 'ארץ', 'region': 'אזור', 'year': 'שנה',
                'order': 'סדרה', 'family': 'משפחה', 'genus': 'סוג', 'species': 'מין'}
OBSERVATION_RELATED = ('species', 'trip', 'trip__region', 'trip__region__sea', 'trip__country', 'site', 'owner', 'owner__profile')


def is_site_manager(user):
    """The same managers as views.is_manager (staff who may change observations)."""
    return user.is_authenticated and user.is_staff and user.has_perm('observations.change_sample')


def is_live(sample):
    """A public observation: published, not deleted and -- for a dive-trip planning -- not closed yet."""
    return (sample.status == Sample.Status.PUBLISHED and sample.deleted_at is None
            and (sample.kind != Sample.Kind.PLANNED or sample.planning_open))


def can_write(sample):
    """Comments are taken on every observation, except a dive-trip planning whose date has passed."""
    return sample.kind != Sample.Kind.PLANNED or sample.planning_open


def visible_messages(user):
    """The forum messages this user may read (see the module docstring)."""
    rows = ForumMessage.objects.filter(deleted_at__isnull=True)
    if is_site_manager(user):
        return rows
    from .planned_trips import closed_planning_ids
    shown_discussion = (Q(observation__status=Sample.Status.PUBLISHED, observation__deleted_at__isnull=True)
                        & ~Q(observation_id__in=closed_planning_ids()))
    readable = Q(manager_only=False)
    if user.is_authenticated:
        shown_discussion |= Q(observation__owner=user)
        readable |= Q(user=user) | Q(observation__owner=user)
    return rows.filter(shown_discussion).filter(readable)


def can_delete(user, message):
    if not user.is_authenticated:
        return False
    return message.user_id == user.pk or is_site_manager(user) or message.observation.owner_id == user.pk


def forum_counts(user, samples):
    """{sample pk: number of messages this user can read} for the given observations."""
    rows = (visible_messages(user).filter(observation__in=samples).values('observation')
            .annotate(n=Count('id')).values_list('observation', 'n'))
    return dict(rows)


def forum_url(sample=None, lang='he', anchor='', kind=''):
    query = {}
    if kind:
        query['kind'] = kind
    if sample is not None:
        query['obs'] = sample if isinstance(sample, (int, str)) else sample.pk
    url = reverse('forum') + ('?' + urlencode(query) if query else '')
    return with_lang(url, lang) + anchor


def new_comment_url(sample=None, lang='he'):
    """Where an "add a comment" button points (see forum_new)."""
    return with_lang(reverse('forum-new') + (f'?obs={sample.pk}' if sample else ''), lang)


def observation_label(sample, lang):
    """Plain-text name of an observation for the picker: the taxon (or the trip collection's title), place and year."""
    if sample.kind in (Sample.Kind.COLLECTION, Sample.Kind.PLANNED):
        return sample.gallery_title(lang) or str(sample.trip or '')
    parts = [sample.taxon_label]
    if sample.trip_id:
        if sample.trip.region_id:
            parts.append(loc(sample.trip.region, lang))
        if sample.trip.year:
            parts.append(str(sample.trip.year))
    return ' · '.join(p for p in parts if p)


def observation_page_urls(samples, lang):
    """pk -> the public page that shows each observation: the species/taxon page, the dive-trip page of a collection, the
    planning's own page (/planning/<trip code>/) for a dive-trip planning."""
    from .views import gallery_urls
    from .trip_page import trip_collections, trip_page_url
    out = gallery_urls(samples, lang)
    for s in samples:
        if s.kind == Sample.Kind.COLLECTION and is_live(s) and s.trip_id and s in trip_collections(s.trip):
            out[s.pk] = trip_page_url(s.trip, lang)
        elif s.kind == Sample.Kind.PLANNED and is_live(s):
            from .planned_trips import planning_page_url
            out[s.pk] = planning_page_url(s.trip, lang)
    return out


def _kind_filter(request):
    kind = request.GET.get('kind') or ''
    return kind if kind in KIND_FILTERS else ''


def _chosen(request):
    """The chosen observation (None when none). One that is not public is reachable by its owner and the managers only."""
    value = (request.POST.get('obs') or request.GET.get('obs') or '').strip()
    if not value:
        return None
    if not value.isdigit():
        raise Http404
    sample = Sample.objects.select_related(*OBSERVATION_RELATED).filter(pk=int(value)).first()
    user = request.user
    if not sample or not (is_live(sample) or is_site_manager(user) or (user.is_authenticated and sample.owner_id == user.pk)):
        raise Http404
    return sample


class ForumMessageForm(forms.Form):
    audience = forms.ChoiceField(choices=(('all', 'all'), ('manager', 'manager')), initial='all')
    subject = forms.CharField(max_length=200, required=False)
    text = forms.CharField(max_length=MAX_TEXT, widget=forms.Textarea)

    def clean_text(self):
        text = self.cleaned_data['text'].strip()
        if not text:
            raise forms.ValidationError('יש לכתוב את תוכן ההודעה.')
        return text


def _display_name(user, lang):
    return full_name_for(user, lang) or user.username


def _annotate(messages_, user, lang):
    for m in messages_:
        m.author_name = _display_name(m.user, lang)
        m.local_time = timezone.localtime(m.created_at)
        m.deletable = can_delete(user, m)
    return messages_


def _annotate_observation(sample, lang, page_urls, count=None):
    sample.label = observation_label(sample, lang)
    sample.manager_name = _display_name(sample.owner, lang)
    sample.page_url = page_urls.get(sample.pk, '')
    sample.picture = reverse('observation-photo', args=[sample.pk]) if sample.image else sample.thumbnail
    sample.live = is_live(sample)
    sample.discussion_url = forum_url(sample, lang)
    sample.write_url = forum_url(sample, lang, '#write')
    if count is not None:
        sample.message_count = count
    return sample


def _facet_value(sample, name, lang):
    """(value, label) of one filter for one observation, or None when it has none."""
    trip = sample.trip if sample.trip_id else None
    if name == 'photographer':
        return str(sample.owner_id), _display_name(sample.owner, lang)
    if name == 'country':
        country = trip.country if trip and trip.country_id else (trip.region.country if trip and trip.region_id else None)
        return (str(country.pk), loc(country, lang)) if country else None
    if name == 'region':
        return (str(trip.region_id), loc(trip.region, lang)) if trip and trip.region_id else None
    if name == 'year':
        return (str(trip.year), str(trip.year)) if trip and trip.year else None
    if name == 'species':
        return (str(sample.species_id), sample.species.scientific_name) if sample.species_id else None
    value = getattr(sample, name, '')
    return (value, value) if value else None


def facet_names(kind):
    return ['photographer', 'country', 'region', 'year', *TAXON_FACETS.get(kind, ())]


def observation_filters(request, user, lang):
    """The forum's filters: {kind, chosen: {filter: value}, facets: [(name, label, options, chosen value)], matched:
    the public observations that match them all, active: whether anything is filtered}."""
    kind = _kind_filter(request)
    names = facet_names(kind)
    chosen = {n: (request.GET.get(n) or '').strip() for n in names}
    rows = Sample.objects.filter(status=Sample.Status.PUBLISHED, deleted_at__isnull=True).select_related(
        *OBSERVATION_RELATED, 'trip__region__country')
    if kind:
        rows = rows.filter(kind__in=KIND_FILTERS[kind][0])
    rows = [s for s in rows if is_live(s)]
    values = {s.pk: {n: _facet_value(s, n, lang) for n in names} for s in rows}
    def matches(s, skip=None):
        return all(not v or (values[s.pk][n] or ('',))[0] == v for n, v in chosen.items() if n != skip)
    facets = []
    for name in names:
        options = {}
        for s in rows:
            if matches(s, skip=name) and values[s.pk][name]:
                value, label = values[s.pk][name]
                options[value] = label
        ordered = sorted(options.items(), key=lambda kv: (-int(kv[0]) if name == 'year' else 0, kv[1].lower()))
        facets.append((name, FACET_LABELS[name], ordered, chosen[name]))
    matched = [s for s in rows if matches(s)]
    return {'kind': kind, 'chosen': {n: v for n, v in chosen.items() if v}, 'facets': facets, 'matched': matched,
            'active': bool(kind or any(chosen.values()))}


def picker_options(user, lang, rows):
    """The observations offered in the picker: (those with a discussion this user can read, all the others), each
    alphabetical."""
    counts = forum_counts(user, rows)
    for s in rows:
        s.label = observation_label(s, lang)
        s.message_count = counts.get(s.pk, 0)
    rows = sorted(rows, key=lambda s: (s.label.lower(), s.pk))
    return [s for s in rows if s.message_count], [s for s in rows if not s.message_count]


def forum(request):
    lang = get_lang(request)
    user = request.user
    sample = _chosen(request)
    form = ForumMessageForm(request.POST or None)
    if request.method == 'POST':
        if sample is None:
            raise Http404
        if not user.is_authenticated:
            return redirect(login_url(forum_url(sample, lang, '#write'), lang))
        if not can_write(sample):
            messages.error(request, 'הדיון נסגר: תאריך המסע המתוכנן עבר.')
            return redirect(forum_url(sample, lang))
        if form.is_valid():
            message = ForumMessage.objects.create(
                observation=sample, user=user, manager_only=form.cleaned_data['audience'] == 'manager',
                subject=form.cleaned_data['subject'].strip(), text=form.cleaned_data['text'])
            messages.success(request, 'התגובה נשמרה.')
            target = forum_url(sample, lang, f'#m-{message.pk}')
            back = request.POST.get('next') or ''      # e.g. a trip's own discussion page (forum_trip)
            if back and url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                target = back.split('#')[0] + f'#m-{message.pk}'
            from .notifications import notify_forum_message
            notify_forum_message(message, request.build_absolute_uri(forum_url(sample, anchor=f'#m-{message.pk}')))
            return redirect(target)

    filters = observation_filters(request, user, lang)
    kind = filters['kind']
    with_discussion, without_discussion = picker_options(user, lang, filters['matched'])
    query = urlencode({**({'kind': kind} if kind else {}), **filters['chosen']})
    context = {
        'kind': kind, 'kind_filters': [(key, label) for key, (_, label) in KIND_FILTERS.items()],
        'facets': filters['facets'], 'filtered': filters['active'],
        'sample': sample, 'form': form, 'with_discussion': with_discussion, 'without_discussion': without_discussion,
        'all_url': with_lang(reverse('forum'), lang), 'can_write': bool(sample and can_write(sample)),
    }
    rows = visible_messages(user).select_related('user', 'user__profile', 'observation__owner')
    if sample:
        _annotate_observation(sample, lang, observation_page_urls([sample], lang))
        # a series of planned trips (planned_trips.py): the series' discussion and its trips' discussions link each other
        from .planned_trips import series_planning, sub_plannings
        parent = series_planning(sample)
        children = sub_plannings(sample)
        child_counts = forum_counts(user, children)
        for x in ([parent] if parent else []) + children:
            x.label = observation_label(x, lang)
            x.discussion_url = forum_url(x, lang)
            x.message_count = child_counts.get(x.pk, 0)
        context.update({'series_parent': parent, 'series_children': children})
        # a dive trip's or a planning's articles (e.g. a series' schedule)
        if sample.kind in (Sample.Kind.COLLECTION, Sample.Kind.PLANNED) and sample.trip_id:
            from .articles import article_links
            context['trip_articles'] = article_links(sample.trip.articles.all(), lang)
        context.update({
            'messages_list': _annotate(list(rows.filter(observation=sample).order_by('created_at', 'pk')), user, lang),
            'login_url': login_url(forum_url(sample, lang, '#write'), lang),
            'signup_url': signup_url(forum_url(sample, lang, '#write'), lang),
        })
    else:
        if filters['active']:
            rows = rows.filter(observation_id__in=[s.pk for s in filters['matched']])
        latest = list(rows.values('observation').annotate(last=Max('created_at'), n=Count('id')))
        samples = Sample.objects.select_related(*OBSERVATION_RELATED, 'trip__summary_trip').in_bulk([r['observation'] for r in latest])
        groups = discussion_groups(latest, samples)
        page = Paginator(groups, DISCUSSIONS_PER_PAGE).get_page(request.GET.get('page'))
        shown = [row for group in page.object_list for row in group]
        ids = [row['observation'] for row in shown]
        page_urls = observation_page_urls([samples[i] for i in ids], lang)
        messages_by = {i: [] for i in ids}       # each discussion's messages this visitor can read, oldest first
        for m in _annotate(list(rows.filter(observation_id__in=ids).order_by('created_at', 'pk')), user, lang):
            messages_by[m.observation_id].append(m)
        def entry(row):
            s = _annotate_observation(samples[row['observation']], lang, page_urls, row['n'])
            s.thread = messages_by[s.pk]
            m = s.thread[-1]
            s.last_time = timezone.localtime(m.created_at)
            s.last_author = _display_name(m.user, lang)
            # a dive trip's discussion opens on the trip's own page, without the filters and picker (forum_trip)
            if s.kind in (Sample.Kind.PLANNED, Sample.Kind.COLLECTION) and s.trip_id and trip_observation(s.trip) == s:
                s.discussion_url = trip_forum_url(s.trip, lang)
            return s
        discussions = []
        for group in page.object_list:
            head = entry(group[0])
            head.children = [entry(row) for row in group[1:]]
            discussions.append(head)
        context.update({
            'page': page, 'total_discussions': len(latest), 'discussions': discussions,
            'page_query': f'{query}&' if query else '',
        })
    return render(request, 'observations/forum.html', context)


def discussion_groups(latest, samples):
    """The landing list's order: groups of discussions, the most recently active group first. A group is one
    discussion -- or a series of dive trips (DiveTrip.summary_trip): the summary trip's discussion followed by those of
    its trips, by date, shown indented under it. A trip whose summary trip has no discussion here stands alone."""
    by_pk = {row['observation']: row for row in latest}
    by_trip = {}
    for row in latest:
        sample = samples[row['observation']]
        if sample.trip_id:
            by_trip.setdefault((sample.trip_id, sample.kind), row)
    children = {}
    for row in latest:
        sample = samples[row['observation']]
        parent = by_trip.get((sample.trip.summary_trip_id, sample.kind)) if sample.trip_id and sample.trip.summary_trip_id else None
        if parent is not None and parent is not row:
            children.setdefault(parent['observation'], []).append(row)
    nested = {row['observation'] for rows in children.values() for row in rows}
    def start(row):
        trip = samples[row['observation']].trip
        return (trip.start_date() or date.max, row['observation'])
    groups = []
    for row in latest:
        if row['observation'] in nested:
            continue
        group = [row] + sorted(children.get(row['observation'], []), key=start)
        groups.append(group)
    groups.sort(key=lambda g: max(r['last'] for r in g), reverse=True)
    return groups


def trip_observation(trip):
    """The observation that holds a dive trip's discussion: its planning, else its collection observation."""
    from .planned_trips import planning_trip_planning
    from .trip_page import trip_collections
    planning = planning_trip_planning(trip)
    if planning is not None:
        return planning
    collections = trip_collections(trip)
    return collections[0] if collections else None


def trip_forum_url(trip, lang='he'):
    return with_lang(reverse('forum-trip', args=[trip.code]), lang)


def forum_trip(request, code):
    """/forum/trip/<trip code>/: one dive trip's discussion on a page of its own, to send to people -- without the
    forum's filters and picker. A summary trip's page holds the series: its discussion, then each of its trips'
    discussions by date, indented, every one with its messages open (+/- folds them) -- and one writing box with a
    choice of the trip the message is about. The discussion is the trip's planning (planned_trips.py), else its
    collection observation; the usual reading rules apply (forum.visible_messages)."""
    from .models import DiveTrip
    lang = get_lang(request)
    user = request.user
    trip = get_object_or_404(DiveTrip.objects.select_related('summary_trip'), code=code)
    head = trip_observation(trip)
    if head is None or not (is_live(head) or is_site_manager(user) or (user.is_authenticated and head.owner_id == user.pk)):
        raise Http404
    members = [head]
    for sub in trip.sub_trips.all():
        sample = trip_observation(sub)
        if sample is not None and is_live(sample):
            members.append(sample)
    samples = Sample.objects.select_related(*OBSERVATION_RELATED).in_bulk([s.pk for s in members])
    members = [samples[s.pk] for s in members]
    page_urls = observation_page_urls(members, lang)
    rows = visible_messages(user).select_related('user', 'user__profile', 'observation__owner')
    threads = {s.pk: [] for s in members}
    for m in _annotate(list(rows.filter(observation_id__in=threads).order_by('created_at', 'pk')), user, lang):
        threads[m.observation_id].append(m)
    def entry(s):
        _annotate_observation(s, lang, page_urls, len(threads[s.pk]))
        s.discussion_url = trip_forum_url(s.trip, lang)
        s.thread = threads[s.pk]
        if s.thread:
            s.last_time = timezone.localtime(s.thread[-1].created_at)
            s.last_author = _display_name(s.thread[-1].user, lang)
        s.label = observation_label(s, lang)
        return s
    head = entry(members[0])
    head.children = sorted((entry(s) for s in members[1:]), key=lambda s: (s.trip.start_date() or date.max, s.pk))
    writable = [s for s in [head, *head.children] if can_write(s)]
    here = trip_forum_url(trip, lang)
    from .articles import article_links
    return render(request, 'observations/forum_trip.html', {
        'head': head, 'trip': trip, 'writable': writable, 'here': here, 'form': ForumMessageForm(),
        'article_links': article_links(trip.articles.all(), lang),
        'summary_url': trip_forum_url(trip.summary_trip, lang) if trip.summary_trip_id and trip_observation(trip.summary_trip) else '',
        'login_url': login_url(here + '#write', lang), 'signup_url': signup_url(here + '#write', lang),
    })


def login_url(next_url, lang):
    return with_lang(reverse('login') + '?' + urlencode({'next': next_url}), lang)


def signup_url(next_url, lang):
    return with_lang(reverse('signup') + '?' + urlencode({'next': next_url}), lang)


def forum_new(request):
    """The "add a comment" buttons: to the writing box of that observation's discussion, or -- from the home page,
    without an observation -- to the forum's observation picker. A visitor who is not signed in goes to the login page
    first and comes back there afterwards."""
    lang = get_lang(request)
    sample = _chosen(request)
    target = forum_url(sample, lang, '#write') if sample else forum_url(None, lang, '#choose')
    if not request.user.is_authenticated:
        return redirect(login_url(target, lang))
    return redirect(target)


@login_required
@require_POST
def forum_delete(request, pk):
    lang = get_lang(request)
    message = get_object_or_404(ForumMessage.objects.select_related('observation'), pk=pk, deleted_at__isnull=True)
    if not can_delete(request.user, message):
        raise Http404
    message.deleted_at = timezone.now()
    message.deleted_by = request.user
    message.save(update_fields=['deleted_at', 'deleted_by'])
    messages.success(request, 'ההודעה נמחקה.')
    back = request.POST.get('next') or ''
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        back = forum_url(message.observation_id, lang)
    return redirect(back)
