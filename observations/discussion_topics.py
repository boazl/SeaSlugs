"""/admin/discussion-topics/ -- the "topics for discussion" table (DiscussionTopic): taxonomic questions on which the
sources disagree, above all where the 3rd edition of Gosliner, Valdés & Behrens (2026) departs from WoRMS. Each row
records the book's treatment, WoRMS's, the site's current one and the decision.

The site's order of authority is WoRMS first, then the 3rd edition, then the 2nd edition or other publications; a topic
documents a disagreement and changes nothing in the catalogue by itself (the changes go to the identification-issues
table).
- The list: filters by state (by default the open topics), rank and a free search; sorted by priority, then topic.
  A row's priority and state change right in the list.
- Add / edit form, and a delete page that asks first.
Superusers only, like the other custom admin pages. Per environment until moved with the table transfer (table
`discussions`).
"""
from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import DiscussionTopic

Topic = DiscussionTopic
STATE_FILTERS = [('open', 'פתוחים לדיון'), ('all', 'הכול')] + [c for c in Topic.Status.choices if c[0] != 'open']


def _superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ['topic', 'rank', 'priority', 'status', 'opened_on', 'book_treatment', 'worms_treatment',
                  'site_treatment', 'decision', 'sources', 'worms_link', 'notes']
        area = {'rows': 3, 'cols': 80}
        widgets = {'opened_on': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'topic': forms.TextInput(attrs={'size': 60}),
                   'book_treatment': forms.Textarea(attrs=area), 'worms_treatment': forms.Textarea(attrs=area),
                   'site_treatment': forms.Textarea(attrs=area), 'decision': forms.Textarea(attrs=area),
                   'sources': forms.Textarea(attrs={'rows': 2, 'cols': 80}), 'notes': forms.Textarea(attrs=area),
                   'worms_link': forms.URLInput(attrs={'size': 60, 'dir': 'ltr'})}


def topic_rows(state='open', rank='', q=''):
    """The topics that match the filters, by priority then topic."""
    topics = Topic.objects.all()
    if state != 'all':
        topics = topics.filter(status=state)
    if rank:
        topics = topics.filter(rank=rank)
    if q:
        topics = topics.filter(Q(topic__icontains=q) | Q(book_treatment__icontains=q) | Q(worms_treatment__icontains=q)
                               | Q(site_treatment__icontains=q) | Q(decision__icontains=q) | Q(sources__icontains=q)
                               | Q(notes__icontains=q))
    return list(topics.order_by('priority', 'topic', 'pk'))


def _filters(request):
    state = request.GET.get('state') if request.GET.get('state') in dict(STATE_FILTERS) else 'open'
    rank = request.GET.get('rank') if request.GET.get('rank') in Topic.Rank.values else ''
    return {'state': state, 'rank': rank, 'q': (request.GET.get('q') or '').strip()}


def _back(request):
    back = request.POST.get('back') or request.GET.get('back') or ''
    base = reverse('discussion-topics')
    return f'{base}?{back}' if back and not back.startswith(('/', 'http')) and '//' not in back else base


@staff_member_required
def discussion_topics(request):
    _superuser(request)
    if request.method == 'POST':
        topic = get_object_or_404(Topic, pk=request.POST.get('topic'))
        changed = False
        priorities = {str(value) for value, _ in Topic._meta.get_field('priority').choices}
        if request.POST.get('priority') in priorities and int(request.POST['priority']) != topic.priority:
            topic.priority = int(request.POST['priority']); changed = True
        if request.POST.get('status') in Topic.Status.values and request.POST['status'] != topic.status:
            topic.status = request.POST['status']; changed = True
        if changed:
            topic.updated_at = timezone.now()
            topic.save()
            messages.success(request, f'נושא {topic.pk} עודכן.')
        return redirect(_back(request))
    filters = _filters(request)
    totals = {row['status']: row['n'] for row in Topic.objects.values('status').annotate(n=Count('id'))}
    return render(request, 'observations/discussion_topics.html', {
        'topics': topic_rows(**filters), **filters, 'query': request.GET.urlencode(),
        'state_filters': STATE_FILTERS, 'rank_choices': Topic.Rank.choices,
        'priority_choices': Topic._meta.get_field('priority').choices, 'status_choices': Topic.Status.choices,
        'status_totals': [(label, totals.get(value, 0)) for value, label in Topic.Status.choices],
        'total': sum(totals.values())})


def _form_page(request, topic=None):
    form = TopicForm(request.POST or None, instance=topic or Topic())
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.updated_at = timezone.now()
        saved.save()
        messages.success(request, f'נושא {saved.pk} {"עודכן" if topic else "נוסף"}.')
        return redirect(_back(request))
    return render(request, 'observations/discussion_topic_form.html', {
        'form': form, 'topic': topic, 'back': request.POST.get('back') or request.GET.get('back') or ''})


@staff_member_required
def discussion_topic_new(request):
    _superuser(request)
    return _form_page(request)


@staff_member_required
def discussion_topic_edit(request, pk):
    _superuser(request)
    return _form_page(request, get_object_or_404(Topic, pk=pk))


@staff_member_required
def discussion_topic_delete(request, pk):
    _superuser(request)
    topic = get_object_or_404(Topic, pk=pk)
    if request.method == 'POST':
        number = topic.pk
        topic.delete()
        messages.success(request, f'נושא {number} נמחק.')
        return redirect(_back(request))
    return render(request, 'observations/discussion_topic_delete.html',
                  {'topic': topic, 'back': request.GET.get('back') or ''})
