"""/admin/missing-descriptions/ -- gallery species that have no description yet.

Scans every species shown in the gallery (a SpeciesArea whose defining sample is a live, published
observation) and lists those whose description (Species.description_he / description_en, the text under
"תיאור" on the species page) is still empty in Hebrew, in English or in both. Each row shows how many
published observations show the species, when it was first and last observed on the site (so newly
added species stand out), its gallery pages and a link to edit the species. Read-only.
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Min
from django.shortcuts import render

from .models import Sample, SpeciesArea

MISSING_CHOICES = [('any', 'חסר בעברית או באנגלית'), ('both', 'חסר בשתי השפות'), ('he', 'חסר בעברית'), ('en', 'חסר באנגלית')]
SORT_CHOICES = [('new', 'מינים חדשים קודם'), ('name', 'לפי שם מדעי')]


def missing_description_rows(missing='any', sort='new'):
    """One row per gallery species whose description is missing in the language(s) asked for."""
    areas = (SpeciesArea.objects.filter(defining_sample__isnull=False, defining_sample__deleted_at__isnull=True,
                                        defining_sample__status=Sample.Status.PUBLISHED)
             .select_related('species', 'country', 'sea', 'defining_sample').order_by('country__name', 'sea__name', 'undetermined_variant'))
    by_species = {}
    for area in areas:
        by_species.setdefault(area.species_id, (area.species, []))[1].append(area)
    stats = {row['species_id']: row for row in Sample.objects.filter(
        kind=Sample.Kind.SPECIES, status=Sample.Status.PUBLISHED, deleted_at__isnull=True, species_id__in=by_species,
    ).values('species_id').annotate(count=Count('id'), first=Min('created_at'), last=Max('created_at'))}
    rows = []
    for species_id, (species, species_areas) in by_species.items():
        no_he = not (species.description_he or '').strip()
        no_en = not (species.description_en or '').strip()
        wanted = {'any': no_he or no_en, 'both': no_he and no_en, 'he': no_he, 'en': no_en}.get(missing, no_he or no_en)
        if not wanted:
            continue
        stat = stats.get(species_id, {})
        picture = next((a.defining_sample for a in species_areas if a.defining_sample.image), None)
        rows.append({'species': species, 'areas': species_areas, 'no_he': no_he, 'no_en': no_en,
                     'missing_label': 'עברית ואנגלית' if no_he and no_en else 'עברית' if no_he else 'אנגלית',
                     'count': stat.get('count', 0), 'first': stat.get('first'), 'last': stat.get('last'), 'picture': picture})
    if sort == 'name':
        rows.sort(key=lambda r: r['species'].scientific_name.casefold())
    else:
        rows.sort(key=lambda r: (r['first'] is not None, r['first']), reverse=True)
    return rows, len(by_species)


@staff_member_required
def missing_descriptions(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    missing = request.GET.get('missing') if request.GET.get('missing') in dict(MISSING_CHOICES) else 'any'
    sort = request.GET.get('sort') if request.GET.get('sort') in dict(SORT_CHOICES) else 'new'
    rows, gallery_total = missing_description_rows(missing, sort)
    return render(request, 'observations/missing_descriptions.html', {
        'rows': rows, 'gallery_total': gallery_total, 'missing': missing, 'sort': sort,
        'missing_choices': MISSING_CHOICES, 'sort_choices': SORT_CHOICES,
        'both_count': sum(1 for r in rows if r['no_he'] and r['no_en'])})
