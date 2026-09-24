from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Q
from django.http import Http404, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from .models import Sample, Profile, Region, Site, DiveTrip, SiteImage, Species, Country, SpeciesArea, SampleKind, KIND_EN_NAMES
from .forms import SignupForm, SampleForm, ProfileForm, DiveTripForm
from .gallery_data import TaxonResolver, taxon_media
from .i18n import get_lang


def is_manager(user): return user.is_authenticated and user.is_staff and user.has_perm('observations.change_sample')


def trips(request):
    from django.db.models import Prefetch
    published = Sample.objects.filter(status='published', deleted_at__isnull=True, trip__isnull=False,
        trip__country__isnull=False, trip__region__isnull=False, trip__year__isnull=False,
        species_other='', site_other='').filter(Q(kind='collection', species__isnull=True) | Q(kind='species',species__isnull=False)).select_related('species','trip')
    rows = DiveTrip.objects.filter(samples__in=published).distinct().prefetch_related(Prefetch('samples',queryset=published,to_attr='public_samples'))
    return render(request, 'observations/trips.html', {'trips':rows})


def species_page(request, slug):
    """Public, server-rendered, individually-URLed page for one species+area (a species
    observed in a given country+sea -- the same unit the gallery already keys a card on,
    since the same species observed in two different areas gets two different defining
    photos/pages there too). Only reachable once the area has a valid published defining
    sample, same rule the gallery feed itself uses to decide whether to show a card at all."""
    area = get_object_or_404(
        SpeciesArea.objects.select_related('species', 'country', 'sea', 'defining_sample'), slug=slug)
    thumbnail, image_url, video_id = taxon_media(area.defining_sample)
    if not (image_url or video_id):
        raise Http404
    samples = list(Sample.objects.filter(
        kind=Sample.Kind.SPECIES, species_id=area.species_id, status='published', deleted_at__isnull=True,
        trip__country_id=area.country_id, trip__region__sea_id=area.sea_id, trip__year__isnull=False,
        species_other='', site_other='',
    ).select_related('trip', 'trip__region', 'site', 'owner', 'owner__profile').order_by('created_at', 'pk'))
    if not samples:
        raise Http404
    order_obj, family_obj, genus_obj = TaxonResolver().resolve(area.species)
    lang = get_lang(request)

    def taxon_label(obj):
        if not obj:
            return ''
        return (obj.name_en or obj.name) if lang == 'en' else (obj.name_he or obj.name)

    species = area.species
    common_name = (species.name_en or species.name_he) if lang == 'en' else (species.name_he or species.name_en)
    description = (species.description_en or species.description_he) if lang == 'en' else (species.description_he or species.description_en)
    return render(request, 'observations/species_page.html', {
        'area': area, 'species': species, 'samples': samples,
        'image_url': image_url, 'video_id': video_id, 'thumbnail': thumbnail,
        'taxon_order': order_obj, 'taxon_family': family_obj, 'taxon_genus': genus_obj,
        'taxon_order_label': taxon_label(order_obj), 'taxon_family_label': taxon_label(family_obj),
        'taxon_genus_label': taxon_label(genus_obj),
        'common_name': common_name, 'description': description,
        'canonical_url': request.build_absolute_uri(request.path),
    })


def species_article(request, slug):
    """Streams a species' curated article PDF. Production never serves MEDIA_ROOT
    directly (same reason observation-photo/site-image exist as dedicated views rather
    than linking straight to .url) -- this is that view for Species.article_pdf. Keyed by
    the same species+area slug the page itself uses (the file is shared by the species
    across all its areas, but there's no separate species-only slug to key it by)."""
    area = get_object_or_404(SpeciesArea.objects.select_related('species'), slug=slug)
    if not area.species.article_pdf:
        raise Http404
    response = FileResponse(area.species.article_pdf.open('rb'), content_type='application/pdf')
    response['Cache-Control'] = 'public, max-age=3600'
    response['Content-Disposition'] = 'inline; filename="%s.pdf"' % area.species.scientific_name.replace('"', "'")
    return response

SORT_OPTIONS = {
    'newest': ('-created_at',),
    'oldest': ('created_at',),
    'trip_desc': ('-trip__year', '-trip__month', '-created_at'),
    'trip_asc': ('trip__year', 'trip__month', 'created_at'),
    'species': ('species__scientific_name', '-created_at'),
}

# (value, {lang: label}) -- ordered as they should appear in the sort dropdown.
SORT_LABELS = [
    ('newest', {'he': 'החדש ביותר', 'en': 'Newest first'}),
    ('oldest', {'he': 'הישן ביותר', 'en': 'Oldest first'}),
    ('trip_desc', {'he': 'תאריך מסע (חדש לישן)', 'en': 'Trip date (newest first)'}),
    ('trip_asc', {'he': 'תאריך מסע (ישן לחדש)', 'en': 'Trip date (oldest first)'}),
    ('species', {'he': 'שם המין (א-ת)', 'en': 'Species name (A–Z)'}),
]

# Sample.Status has no admin-editable bilingual reference table the way Sample.Kind
# does (SampleKind) -- just two fixed values, so a plain dict is enough.
STATUS_LABELS = {
    'pending': {'he': 'ממתינה לאישור', 'en': 'Pending approval'},
    'published': {'he': 'מפורסמת', 'en': 'Published'},
}


@login_required
def listing(request):
    from django.contrib.auth import get_user_model

    def as_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    manager = is_manager(request.user)
    visible = Sample.objects.all() if manager else Sample.objects.filter(deleted_at__isnull=True, owner=request.user)
    rows = visible.select_related('species', 'trip', 'trip__country', 'trip__region', 'site', 'owner')
    if request.GET.get('mine') and request.user.is_authenticated:
        rows = rows.filter(owner=request.user)
    get = request.GET
    if get.get('kind') in ('species', 'collection'):
        rows = rows.filter(kind=get['kind'])
    if get.get('status') in ('pending', 'published'):
        rows = rows.filter(status=get['status'])
    country_id = as_int(get.get('country'))
    if country_id is not None:
        rows = rows.filter(trip__country_id=country_id)
    region_id = as_int(get.get('region'))
    if region_id is not None:
        rows = rows.filter(trip__region_id=region_id)
    year = as_int(get.get('year'))
    if year is not None:
        rows = rows.filter(trip__year=year)
    # order/family/genus/photographer/owner are typed into free-text autocomplete fields
    # (some have hundreds of possible values, so a <select> isn't practical) -- icontains
    # keeps a partial or not-quite-exact typed value still useful as a search.
    if get.get('order'):
        rows = rows.filter(species__order__icontains=get['order'])
    if get.get('family'):
        rows = rows.filter(species__family__icontains=get['family'])
    if get.get('genus'):
        rows = rows.filter(species__genus__icontains=get['genus'])
    if get.get('photographer'):
        rows = rows.filter(trip__photographer__icontains=get['photographer'])
    if manager and get.get('owner'):
        rows = rows.filter(owner__username__icontains=get['owner'])
    sort = get.get('sort') if get.get('sort') in SORT_OPTIONS else 'species'
    rows = rows.order_by(*SORT_OPTIONS[sort])

    def options(field, **extra):
        # .order_by() clears Sample's default Meta.ordering (-created_at) before the
        # values_list/distinct -- otherwise Django silently adds created_at to the
        # SELECT DISTINCT columns (needed to support the implicit ORDER BY), which
        # defeats distinct() and produces duplicate option values in the dropdowns.
        return sorted(v for v in visible.filter(**extra).exclude(**{field: ''}).order_by().values_list(field, flat=True).distinct() if v)

    present_kinds = set(visible.order_by().values_list('kind', flat=True).distinct())
    present_statuses = set(visible.order_by().values_list('status', flat=True).distinct())

    lang = get_lang(request)
    # SampleKind is the admin-editable bilingual reference table for Sample.Kind, but it's
    # only populated once build_taxonomy_tables has run -- fall back to the static
    # KIND_EN_NAMES/TextChoices labels (never the raw code) so a fresh install still shows
    # sensible English text.
    kind_db_labels = {sk.code: sk for sk in SampleKind.objects.all()}
    def kind_label(code, he_label):
        sk = kind_db_labels.get(code)
        if lang == 'en':
            return (sk.name_en if sk and sk.name_en else '') or KIND_EN_NAMES.get(code) or he_label
        return (sk.name if sk and sk.name else '') or he_label
    kind_label_lookup = {code: kind_label(code, he_label) for code, he_label in Sample.Kind.choices}
    status_label_lookup = {code: labels[lang] for code, labels in STATUS_LABELS.items()}

    context = {
        'observations': rows,
        'manager': manager,
        'sort': sort,
        'filters': get,
        'kind_label_lookup': kind_label_lookup,
        'status_label_lookup': status_label_lookup,
        'sort_options': [(v, labels[lang]) for v, labels in SORT_LABELS],
        # A filter whose data holds only zero or one distinct value is never useful --
        # narrowing it can't change the result set -- so each list below is only rendered
        # by the template when it has more than one option (see list.html's length checks).
        'kind_choices': [(v, kind_label_lookup.get(v, label)) for v, label in Sample.Kind.choices if v in present_kinds],
        'status_choices': [(v, status_label_lookup.get(v, label)) for v, label in Sample.Status.choices if v in present_statuses],
        'countries': Country.objects.filter(dive_trips__samples__in=visible).distinct().order_by('name'),
        'regions': Region.objects.filter(dive_trips__samples__in=visible).distinct().order_by('name'),
        'years': sorted((v for v in visible.exclude(trip__year__isnull=True).order_by().values_list('trip__year', flat=True).distinct() if v), reverse=True),
        'orders': options('species__order'),
        'families': options('species__family'),
        'genera': options('species__genus'),
        'photographers': options('trip__photographer'),
    }
    if manager:
        context['owners'] = list(get_user_model().objects.filter(observations__in=visible).distinct().order_by('username').values_list('username', flat=True))
    return render(request, 'observations/list.html', context)


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user=form.save()
        user.groups.add(Group.objects.get_or_create(name='New user')[0])
        Profile.objects.create(user=user,display_name=user.get_full_name() or user.username)
        login(request,user)
        return redirect('profile')
    return render(request,'observations/form.html',{'form':form,'title':'הרשמה / Sign up'})


@login_required
def profile(request):
    item,_=Profile.objects.get_or_create(user=request.user,defaults={'display_name':request.user.username})
    form=ProfileForm(request.POST or None,instance=item)
    if request.method=='POST' and form.is_valid():
        item=form.save()
        group=Group.objects.get_or_create(name='Macro diver')[0]
        if item.macro_diver: request.user.groups.add(group)
        else: request.user.groups.remove(group)
        messages.success(request,'הפרופיל נשמר.')
        return redirect('profile')
    return render(request,'observations/form.html',{'form':form,'title':'הפרופיל שלי / My profile'})


@login_required
def partners(request):
    rows=Profile.objects.filter(macro_diver=True,visible_to_members=True).prefetch_related('regions','countries')
    if request.GET.get('region'): rows=rows.filter(regions__id=request.GET['region'])
    if request.GET.get('country'): rows=rows.filter(countries__id=request.GET['country'])
    from .models import Country
    return render(request,'observations/partners.html',{'profiles':rows.distinct(),'regions':Region.objects.all(),'countries':Country.objects.all()})


@login_required
def species_search(request):
    from django.http import JsonResponse
    q = (request.GET.get('q') or '').strip()
    rows = Species.objects.all()
    if q:
        rows = rows.filter(
            Q(scientific_name__icontains=q) | Q(name_he__icontains=q) | Q(name_en__icontains=q) | Q(genus__icontains=q)
        )
    # An empty q still returns a page of species (rather than nothing) so the species
    # picker on the observation form behaves like an open dropdown you can browse by
    # clicking, not only a search box that stays empty until you type something.
    rows = rows.order_by('scientific_name')[:40]
    results = [{'id': str(item.pk), 'label': item.scientific_name + (f' — {item.name_he}' if item.name_he else '')} for item in rows]
    return JsonResponse({'results': results})


@login_required
def species_area_status(request):
    """Whether the sample currently being edited is (or would be) the defining sample
    for the given species in the given trip's country+sea, and whether that species
    already appears in the gallery there through some other sample. Called live from the
    observation form whenever the species or trip field changes, since both together
    determine which SpeciesArea is relevant."""
    from django.http import JsonResponse
    species_text = (request.GET.get('species') or '').strip()
    species = Species.objects.filter(scientific_name__iexact=species_text).first() if species_text else None
    trip = DiveTrip.objects.filter(pk=request.GET.get('trip')).select_related('country','region__sea').first()
    if not species or not trip or not trip.country_id or not trip.sea:
        return JsonResponse({'matched': False})
    area = SpeciesArea.objects.filter(species=species, country_id=trip.country_id, sea=trip.sea).first()
    sample_id = request.GET.get('sample') or None
    is_defining = bool(area and sample_id and str(area.defining_sample_id) == str(sample_id))
    appears = bool(area and area.defining_sample_id)
    next_info = None
    if is_defining:
        candidate = SpeciesArea.next_candidate(species.pk, trip.country_id, trip.sea, sample_id)
        next_info = {'kind': 'with_media', 'id': candidate['sample'].pk} if candidate['kind'] == 'with_media' else {'kind': candidate['kind']}
    return JsonResponse({'matched': True, 'is_defining': is_defining, 'appears': appears, 'next': next_info})


@login_required
def edit(request,pk=None):
    if pk:
        item=get_object_or_404(Sample,pk=pk)
        # A manager (e.g. from the image manager's "which observations use this file" list,
        # which can point at a soft-deleted sample too) can open and edit any observation --
        # everyone else is limited to their own, not-deleted samples, exactly like remove().
        if not is_manager(request.user) and (item.owner_id!=request.user.id or item.deleted_at): raise Http404
    else:
        item=Sample(owner=request.user)
    initial={}
    trip_param=request.GET.get('trip')
    if trip_param and request.method!='POST': initial['trip']=trip_param
    # Where to return to after saving -- normally the observations list URL the user
    # followed the "עריכה" link from, filters/sort/page and all, carried through the
    # POST as a hidden field (see form.html) since it isn't otherwise part of this URL.
    # Validated against open-redirect abuse since it's attacker-influenceable input.
    requested_next=request.POST.get('next') or request.GET.get('next')
    if requested_next and url_has_allowed_host_and_scheme(requested_next,allowed_hosts={request.get_host()},require_https=request.is_secure()):
        next_url=requested_next
    else:
        next_url=reverse('observations')
    form=SampleForm(request.POST or None,request.FILES or None,instance=item,initial=initial)
    if request.method=='POST' and form.is_valid():
        item=form.save(commit=False)
        if 'image' in form.changed_data and item.image:
            # Store by content hash, exactly like the bulk folder importer and the
            # image manager, so the same photo always resolves to the same image
            # reference whether it was uploaded here or arrived through a transfer.
            import hashlib
            from .media_transfer import save_images
            raw=item.image.read();name='observations/transfer/'+hashlib.sha256(raw).hexdigest()+'.jpg'
            save_images({name:raw});item.image=name
        item.save_reviewed()
        messages.success(request,'התצפית פורסמה.' if item.status=='published' else 'התצפית נשמרה וממתינה להשלמת נתונים ולאישור מנהל.')
        return redirect(f'{next_url}#obs-{item.pk}')
    return render(request,'observations/form.html',{'form':form,'title':'תצפית / Sample','observation_form':True,
        'trip_new_url':reverse('trip-new'),'next':next_url,
        'species_options':Species.objects.order_by('scientific_name').values_list('scientific_name',flat=True),
        'locations':{'trips':list(DiveTrip.objects.values('id','region_id')),'sites':list(Site.objects.values('id','region_id'))}})


@login_required
def trip_new(request):
    next_url=request.POST.get('next') or request.GET.get('next') or reverse('observation-new')
    form=DiveTripForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        trip=form.save()
        messages.success(request,'מסע הצלילה נוסף.')
        sep='&' if '?' in next_url else '?'
        return redirect(f'{next_url}{sep}trip={trip.pk}')
    return render(request,'observations/form.html',{'form':form,'title':'מסע צלילה חדש / New dive trip','trip_form':True,'next':next_url,
        'locations':{'regions':list(Region.objects.values('id','country_id'))}})


@login_required
@require_POST
def remove(request,pk):
    item=get_object_or_404(Sample,pk=pk,owner=request.user,deleted_at__isnull=True)
    item.soft_delete(request.user)
    messages.success(request,'התצפית הוסרה מהאתר. מנהל יכול לשחזר אותה.')
    return redirect('observations')


@login_required
@require_POST
def observation_action(request, pk):
    """Three destructive-ish actions available from the observation edit form, all scoped
    to the owner's own non-deleted sample: releasing it from the species it currently
    defines in the gallery (with the vacated spot handed to next_candidate's pick, exactly
    like the live preview on the form promised), and deleting its image or video link --
    which is only ever blocked while this sample is the one defining its species, since
    that would silently drop the species from the gallery instead of going through the
    explicit release action above."""
    item = get_object_or_404(Sample, pk=pk, owner=request.user, deleted_at__isnull=True)
    action = request.POST.get('action')
    area = None
    if item.kind == Sample.Kind.SPECIES and item.species_id and item.trip_id and item.trip.country_id and item.trip.region_id:
        area = SpeciesArea.objects.filter(species_id=item.species_id, country_id=item.trip.country_id, sea=item.trip.region.sea).first()
    is_defining = bool(area and area.defining_sample_id == item.pk)

    if action == 'release_species':
        if not is_defining:
            messages.error(request, 'התצפית אינה מגדירה את המין כרגע.')
        else:
            candidate = SpeciesArea.next_candidate(item.species_id, item.trip.country_id, item.trip.region.sea, item.pk)
            area.defining_sample = candidate['sample'] if candidate['kind'] == 'with_media' else None
            area.save(update_fields=['defining_sample'])
            messages.success(request, 'המין שנבחר מופיע בגלריה.' if area.defining_sample_id else 'המין שנבחר אינו מופיע בגלריה.')
    elif action == 'delete_image':
        if is_defining:
            messages.error(request, 'לא ניתן למחוק את התמונה כאשר התצפית מגדירה את המין. יש להסיר קודם את התצפית מהמין.')
        elif not item.image:
            messages.error(request, 'לתצפית זו אין תמונה.')
        else:
            from .media_transfer import delete_image_if_unused
            old_name = item.image.name
            item.image = ''
            item.save(update_fields=['image', 'updated_at'])
            delete_image_if_unused(old_name)
            messages.success(request, 'התמונה נמחקה.')
    elif action == 'delete_video':
        if is_defining:
            messages.error(request, 'לא ניתן למחוק את קישור הסרטון כאשר התצפית מגדירה את המין. יש להסיר קודם את התצפית מהמין.')
        elif not item.video_url:
            messages.error(request, 'לתצפית זו אין קישור סרטון.')
        else:
            item.video_url = ''
            item.save(update_fields=['video_url', 'updated_at'])
            messages.success(request, 'קישור הסרטון נמחק.')
    else:
        messages.error(request, 'פעולה לא מוכרת.')
    return redirect('observation-edit', pk=item.pk)


def site_image(request,key):
    item=get_object_or_404(SiteImage,key=key)
    if not item.image: raise Http404
    response=FileResponse(item.image.open('rb'),content_type='image/jpeg')
    response['Cache-Control']='public, max-age=600'
    return response


def photo(request,pk):
    item=get_object_or_404(Sample,pk=pk)
    if not (is_manager(request.user) or (not item.deleted_at and (item.status=='published' or item.owner_id==getattr(request.user,'id',None)))): raise Http404
    if not item.image: raise Http404
    response=FileResponse(item.image.open('rb'),content_type='image/jpeg')
    response['Cache-Control']='private, no-store'
    return response
