"""/admin/identification-issues/ -- the identification-issues table: the site manager's worklist of corrections, errors
and disputes about the species identification of observations (IdentificationIssue).

- The list: filters by state (by default the active ones: open + being checked), kind and priority, and a free search
  (species names, notes, corrected name, range, reporter, observation number). Sorted by priority, then newest first
  (or newest / oldest / by species); closed issues always come after the active ones.
  Each row shows the observation(s) with their photo and a link to their page on the site and to their edit form; an
  issue about a species alone shows that species' gallery observation.
- A row's priority and state change right in the list (a small form per row); marking it fixed fills the fix date.
- Add / edit form: observations are given by their number (the id shown on the observation's edit page), species by
  their scientific name from the catalogue (a list of names to pick from). A species left empty follows its
  observation. Kind-specific fields: second observation / species (duplicate), range (range), corrected species
  (misidentified), corrected name (WoRMS; the 3rd edition of Gosliner et al.), research link (classification).
- Delete: a confirmation step, then the row is removed for good.
Superusers only, like the other custom admin pages. Per environment until moved with the table transfer (table
`identissues`).
"""
from django import forms
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import IdentificationIssue, Sample, Species

Issue = IdentificationIssue
STATE_FILTERS = [('active', 'לא טופלו (לבחינה ולתיקון)'), ('review', 'לבחינה (פתוחות ובבדיקה)'), ('tofix', 'לתיקון (הוחלט)'), ('all', 'הכול')] + list(Issue.Status.choices)
ACTIVE = [Issue.Status.OPEN, Issue.Status.CHECKING, Issue.Status.DECIDED]
SORT_CHOICES = [('priority', 'לפי עדיפות'), ('new', 'החדשות קודם'), ('old', 'הישנות קודם'), ('species', 'לפי שם המין')]
# Which kind uses which extra field: the form shows them all, and marks the ones that belong to the chosen kind.
KIND_FIELDS = {
    Issue.Kind.DUPLICATE: ('second_observation', 'second_species'),
    Issue.Kind.RANGE: ('native_range',),
    Issue.Kind.MISIDENTIFIED: ('corrected_species',),
    Issue.Kind.WORMS_NAME: ('corrected_name',),
    Issue.Kind.CLASSIFICATION: ('research_link',),
    Issue.Kind.BOOK_EDITION: ('corrected_name',),
}


def _superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied


class SpeciesNameField(forms.CharField):
    """A species chosen by its scientific name (the catalogue's `scientific_name`), with a list of names to pick from."""
    widget = forms.TextInput(attrs={'list': 'species-names', 'dir': 'ltr', 'size': 34, 'autocomplete': 'off'})

    def prepare_value(self, value):
        if isinstance(value, Species):
            return value.scientific_name
        if isinstance(value, int):
            species = Species.objects.filter(pk=value).first()
            return species.scientific_name if species else ''
        return value

    def clean(self, value):
        value = ' '.join((super().clean(value) or '').split())
        if not value:
            return None
        species = Species.objects.filter(scientific_name=value).first() or Species.objects.filter(scientific_name__iexact=value).first()
        if species is None:
            raise forms.ValidationError(f'המין "{value}" לא נמצא בקטלוג המינים.')
        return species


class ObservationField(forms.ModelChoiceField):
    """An observation given by its number (Sample id); deleted observations count too (an issue may outlive one)."""
    def __init__(self, **kwargs):
        super().__init__(queryset=Sample.objects.all(), required=False,
                         widget=forms.NumberInput(attrs={'min': 1, 'style': 'width:7em'}), **kwargs)
        self.error_messages['invalid_choice'] = 'אין תצפית עם המספר הזה.'


class IssueForm(forms.ModelForm):
    observation = ObservationField(label='מזהה תצפית')
    second_observation = ObservationField(label='מזהה התצפית השנייה')
    species = SpeciesNameField(label='מין', required=False, help_text='ריק = המין של התצפית.')
    second_species = SpeciesNameField(label='מין שני', required=False, help_text='ריק = המין של התצפית השנייה.')
    corrected_species = SpeciesNameField(label='מזהה מין מתוקן', required=False)

    class Meta:
        model = Issue
        fields = ['kind', 'priority', 'status', 'opened_on', 'fixed_on', 'reporter', 'observation', 'species',
                  'second_observation', 'second_species', 'native_range', 'corrected_species', 'corrected_name',
                  'research_link', 'notes', 'recommendation', 'decision'] + list(Issue.ACTION_FIELDS)
        widgets = {'opened_on': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'fixed_on': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'notes': forms.Textarea(attrs={'rows': 6, 'cols': 80}),
                   'recommendation': forms.Textarea(attrs={'rows': 8, 'cols': 80}),
                   'decision': forms.Textarea(attrs={'rows': 4, 'cols': 80}),
                   'native_range': forms.TextInput(attrs={'size': 60}),
                   'corrected_name': forms.TextInput(attrs={'size': 40, 'dir': 'ltr'}),
                   'research_link': forms.URLInput(attrs={'size': 60, 'dir': 'ltr'}),
                   'reporter': forms.TextInput(attrs={'size': 40})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('species', 'second_species', 'corrected_species'):
            value = getattr(self.instance, f'{name}_id', None)
            if value and not self.is_bound:
                self.initial[name] = value

    def clean(self):
        data = super().clean()
        if not (data.get('observation') or data.get('species') or (data.get('notes') or '').strip()):
            raise forms.ValidationError('יש לציין תצפית, מין או הערה.')
        return data


def _filters(request):
    state = request.GET.get('state') if request.GET.get('state') in dict(STATE_FILTERS) else 'active'
    kind = request.GET.get('kind') if request.GET.get('kind') in Issue.Kind.values else ''
    priority = request.GET.get('priority') if request.GET.get('priority') in {str(v) for v in Issue.Priority.values} else ''
    sort = request.GET.get('sort') if request.GET.get('sort') in dict(SORT_CHOICES) else 'priority'
    return {'state': state, 'kind': kind, 'priority': priority, 'sort': sort, 'q': (request.GET.get('q') or '').strip()}


def issue_rows(state='active', kind='', priority='', q='', sort='priority'):
    """The issues that match the filters, in the asked order."""
    issues = Issue.objects.select_related('observation__trip__region__sea', 'observation__trip__country', 'observation__species',
                                          'second_observation__trip__region__sea', 'second_observation__trip__country',
                                          'second_observation__species', 'species', 'second_species', 'corrected_species')
    if state == 'active':
        issues = issues.filter(status__in=ACTIVE)
    elif state == 'review':
        issues = issues.filter(status__in=[Issue.Status.OPEN, Issue.Status.CHECKING])
    elif state == 'tofix':
        issues = issues.filter(status=Issue.Status.DECIDED)
    elif state != 'all':
        issues = issues.filter(status=state)
    if kind:
        issues = issues.filter(kind=kind)
    if priority:
        issues = issues.filter(priority=int(priority))
    if q:
        match = (Q(species__scientific_name__icontains=q) | Q(second_species__scientific_name__icontains=q)
                 | Q(corrected_species__scientific_name__icontains=q) | Q(corrected_name__icontains=q)
                 | Q(notes__icontains=q) | Q(recommendation__icontains=q) | Q(decision__icontains=q) | Q(native_range__icontains=q) | Q(reporter__icontains=q)
                 | Q(observation__species__scientific_name__icontains=q))
        if q.isdigit():
            match |= Q(observation_id=int(q)) | Q(second_observation_id=int(q)) | Q(pk=int(q))
        issues = issues.filter(match)
    order = {'priority': ['priority', '-opened_on', '-pk'], 'new': ['-opened_on', '-pk'], 'old': ['opened_on', 'pk'],
             'species': ['species__scientific_name', 'priority', '-pk']}[sort]
    # closed issues (fixed / rejected) after the active ones, whatever the order
    return sorted(issues.order_by(*order), key=lambda issue: not issue.is_active)


def _species_samples(issues):
    """An issue about a species with no observation of its own (e.g. a catalogue name to update) shows the species'
    gallery observation instead -- its area's defining observation, else its newest published one with a photo --
    so the row still has a photo and links (`issue.species_sample`, None when the species has none)."""
    from .models import SpeciesArea
    wanted = {i.species_id for i in issues if not i.observation_id and i.species_id}
    found = {}
    for area in SpeciesArea.objects.filter(species_id__in=wanted, defining_sample__deleted_at__isnull=True,
                                           defining_sample__status=Sample.Status.PUBLISHED).select_related(
            'defining_sample__trip__country', 'defining_sample__trip__region__sea', 'defining_sample__species').order_by('pk'):
        found.setdefault(area.species_id, area.defining_sample)
    rest = wanted - set(found)
    if rest:
        for sample in Sample.objects.filter(species_id__in=rest, deleted_at__isnull=True, status=Sample.Status.PUBLISHED
                                            ).exclude(image='').select_related(
                'trip__country', 'trip__region__sea', 'species').order_by('-pk'):
            found.setdefault(sample.species_id, sample)
    for issue in issues:
        issue.species_sample = None if issue.observation_id else found.get(issue.species_id)


def _page_urls(issues):
    from .forum import observation_page_urls
    samples = {s.pk: s for i in issues for s in (i.observation, i.second_observation, getattr(i, 'species_sample', None))
               if s is not None}
    return observation_page_urls(list(samples.values()), 'he') if samples else {}


def _back(request):
    """The list with the filters it was opened with (kept in ?back=)."""
    back = request.POST.get('back') or request.GET.get('back') or ''
    base = reverse('identification-issues')
    return f'{base}?{back}' if back and not back.startswith(('/', 'http')) and '//' not in back else base


@staff_member_required
def identification_issues(request):
    _superuser(request)
    if request.method == 'POST':
        # the quick change of one row's priority / state from the list
        issue = get_object_or_404(Issue, pk=request.POST.get('issue'))
        changed = []
        if request.POST.get('priority') in {str(v) for v in Issue.Priority.values} and int(request.POST['priority']) != issue.priority:
            issue.priority = int(request.POST['priority']); changed.append('priority')
        if request.POST.get('status') in Issue.Status.values and request.POST['status'] != issue.status:
            if request.POST['status'] == Issue.Status.FIXED and issue.actions_pending:
                messages.error(request, f'רשומה {issue.pk}: לפני סימון "טופלה" יש לסמן כבוצעו: ' + ', '.join(issue.actions_pending))
                return redirect(_back(request))
            issue.status = request.POST['status']; changed.append('status')
        if changed:
            issue.updated_at = timezone.now()
            issue.save()
            messages.success(request, f'רשומה {issue.pk} עודכנה.')
        return redirect(_back(request))
    filters = _filters(request)
    issues = issue_rows(**filters)
    _species_samples(issues)
    page_urls = _page_urls(issues)
    for issue in issues:
        issue.page_url = page_urls.get(issue.observation_id)
        issue.second_page_url = page_urls.get(issue.second_observation_id)
        issue.species_page_url = page_urls.get(getattr(issue.species_sample, 'pk', None))
    totals = {row['status']: row['n'] for row in Issue.objects.values('status').annotate(n=Count('id'))}
    active = Issue.objects.filter(status__in=ACTIVE)
    by_kind = {row['kind']: row['n'] for row in active.values('kind').annotate(n=Count('id'))}
    return render(request, 'observations/identification_issues.html', {
        'issues': issues, **filters, 'query': request.GET.urlencode(),
        'state_filters': STATE_FILTERS, 'sort_choices': SORT_CHOICES, 'kind_choices': Issue.Kind.choices,
        'priority_choices': Issue.Priority.choices, 'status_choices': Issue.Status.choices,
        'status_totals': [(label, totals.get(value, 0)) for value, label in Issue.Status.choices],
        'kind_totals': [(value, label, by_kind.get(value, 0)) for value, label in Issue.Kind.choices],
        'total': sum(totals.values())})


def _form_page(request, issue=None):
    form = IssueForm(request.POST or None, instance=issue or Issue())
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.updated_at = timezone.now()
        saved.save()
        messages.success(request, f'רשומה {saved.pk} {"עודכנה" if issue else "נוספה"}.')
        return redirect(_back(request))
    if issue is None and request.method == 'GET':
        # "?observation=<id>" (and "&kind=") opens the form for that observation, e.g. from an observation's page
        if (request.GET.get('observation') or '').isdigit():
            form.initial['observation'] = int(request.GET['observation'])
        if request.GET.get('kind') in Issue.Kind.values:
            form.initial['kind'] = request.GET['kind']
    instance = form.instance
    observations = [s for s in (instance.observation if instance.observation_id else None,
                                instance.second_observation if instance.second_observation_id else None) if s]
    page_urls = _page_urls([instance]) if observations else {}
    return render(request, 'observations/identification_issue_form.html', {
        'form': form, 'issue': issue, 'back': request.POST.get('back') or request.GET.get('back') or '',
        'kind_fields': {k: list(v) for k, v in KIND_FIELDS.items()},
        'kind_field_names': sorted({f for v in KIND_FIELDS.values() for f in v}),
        'observations': [(s, page_urls.get(s.pk)) for s in observations],
        'species_names': Species.objects.order_by('scientific_name').values_list('scientific_name', flat=True)})


@staff_member_required
def identification_issue_new(request):
    _superuser(request)
    return _form_page(request)


@staff_member_required
def identification_issue_edit(request, pk):
    _superuser(request)
    return _form_page(request, get_object_or_404(Issue, pk=pk))


@staff_member_required
def identification_issue_delete(request, pk):
    _superuser(request)
    issue = get_object_or_404(Issue, pk=pk)
    if request.method == 'POST':
        number = issue.pk
        issue.delete()
        messages.success(request, f'רשומה {number} נמחקה.')
        return redirect(_back(request))
    return render(request, 'observations/identification_issue_delete.html',
                  {'issue': issue, 'back': request.GET.get('back') or ''})
