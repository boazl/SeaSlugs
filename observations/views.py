from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Q
from django.http import Http404, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from .models import Sample, Profile, Region, Site, DiveTrip, SiteImage, Species, Country, SpeciesArea, SampleKind, KIND_EN_NAMES, TaxonGenus, TaxonFamily, TaxonOrder, full_name_for
from .forms import SignupForm, SampleForm, ProfileForm, DiveTripForm, taxonomy_for_form, species_name_options
from .notifications import notify_new_user_registered
from .gallery_data import TaxonResolver, taxon_media, area_samples
from .i18n import get_lang


def is_manager(user): return user.is_authenticated and user.is_staff and user.has_perm('observations.change_sample')


def trips(request):
    from django.db.models import Prefetch
    published = Sample.objects.filter(status='published', deleted_at__isnull=True, trip__isnull=False,
        trip__country__isnull=False, trip__region__isnull=False, trip__year__isnull=False,
        species_other='', site_other='').filter(Q(kind='collection', species__isnull=True) | Q(kind='species',species__isnull=False)).select_related('species','trip','owner','owner__profile')
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
    samples = list(area_samples(area).select_related('species', 'trip', 'trip__region', 'site', 'owner', 'owner__profile').order_by('created_at', 'pk'))
    if not samples:
        raise Http404
    order_obj, family_obj, genus_obj = TaxonResolver().resolve(area.species)
    lang = get_lang(request)

    def taxon_label(obj):
        if not obj:
            return ''
        return (obj.name_en or obj.name) if lang == 'en' else (obj.name_he or obj.name)

    species = area.species
    # Two areas can share one bare catalog species (e.g. "Coryphellina sp.") while the
    # photographer has told them apart with an undetermined_variant letter (see
    # Sample.undetermined_variant / SpeciesArea.undetermined_variant) -- the page's title
    # and headings show that letter too, so the two pages are distinguishable.
    species_label = f'{species.scientific_name} {area.undetermined_variant}'.strip()
    # An observation's own heading only appears when it adds something to the page title
    # (cf./aff./life stage); a plain one would just repeat the h1.
    for s in samples:
        s.show_name = s.taxon_label != species.scientific_name
        s.name_main, s.name_author, s.name_stage = s.taxon_parts()
    # The main observation is the area's defining sample (the one behind the hero photo/
    # video); the observations grid below lists only the other ones.
    main_sample = next((s for s in samples if s.pk == area.defining_sample_id), samples[0])
    other_samples = [s for s in samples if s is not main_sample]
    def pick(he, en):
        # The current language's text, falling back to the other language when it's blank.
        return (en or he) if lang == 'en' else (he or en)

    en = lang == 'en'
    info = {
        'identification': pick(species.identification_he, species.identification_en),
        'similar': pick(species.similar_species_he, species.similar_species_en),
        'habitat': pick(species.habitat, species.habitat_en),
        'food': pick(species.food, species.food_en),
        'native_range': pick(species.native_range_he, species.native_range_en),
        'route': pick(species.introduction_route_he, species.introduction_route_en),
        'status': pick(species.med_status_he, species.med_status_en),
        'first_place': pick(species.first_record_place_he, species.first_record_place_en),
        'last_place': pick(species.last_record_place_he, species.last_record_place_en),
    }
    # Short values for the quick-facts row under the name.
    def num(value):
        return str(int(value)) if value == value.to_integral_value() else str(value.normalize())
    unit = 'mm' if en else 'מ״מ'
    size_short = ''
    if species.size_from is not None and species.size_to is not None:
        size_short = f'\u2066{num(species.size_from)}–{num(species.size_to)}\u2069 {unit}'
    elif species.size_from is not None or species.size_to is not None:
        size_short = f'{num(species.size_from if species.size_from is not None else species.size_to)} {unit}'
    if species.size_max is not None and (species.size_to is None or species.size_max > species.size_to):
        size_short += (' · ' if size_short else '') + (f'max {num(species.size_max)} {unit}' if en else f'עד {num(species.size_max)} {unit}')
    m = 'm' if en else 'מ׳'
    if species.depth_min is not None and species.depth_max is not None:
        depth_short = f'\u2066{species.depth_min}–{species.depth_max}\u2069 {m}'   # LRI..PDI: keep '0–35' in order inside Hebrew text
    elif species.depth_max is not None:
        depth_short = (f'to {species.depth_max} {m}' if en else f'עד {species.depth_max} {m}')
    else:
        depth_short = f'{species.depth_min} {m}' if species.depth_min is not None else ''
    from urllib.parse import urlparse
    sources = []
    for line in species.sources.splitlines():
        line = line.strip()
        if line:
            host = urlparse(line).netloc.removeprefix('www.') if line.startswith('http') else ''
            sources.append({'url': line if host else '', 'label': host or line})
    common_name = (species.name_en or species.name_he) if lang == 'en' else (species.name_he or species.name_en)
    description = (species.description_en or species.description_he) if lang == 'en' else (species.description_he or species.description_en)
    return render(request, 'observations/species_page.html', {
        'area': area, 'species': species, 'species_label': species_label, 'samples': samples,
        'main_sample': main_sample, 'other_samples': other_samples,
        'info': info, 'size_short': size_short, 'depth_short': depth_short, 'sources': sources,
        'image_url': image_url, 'video_id': video_id, 'thumbnail': thumbnail,
        'taxon_order': order_obj, 'taxon_family': family_obj, 'taxon_genus': genus_obj,
        'taxon_order_label': taxon_label(order_obj), 'taxon_family_label': taxon_label(family_obj),
        'taxon_genus_label': taxon_label(genus_obj),
        'common_name': common_name, 'description': description, 'size_text': species.size_text(lang),
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


def genus_page(request, name):
    """Public, server-rendered page for one genus -- the genus-level analogue of
    species_page above, keyed directly by TaxonGenus.name (already unique, and a plain
    single Latin word, so no separate slug field is needed the way SpeciesArea has one).
    Shows every species observed in this genus (across all its areas), each linking to its
    own species page. Only reachable once the genus has a valid defining sample with media,
    the same rule species_page uses."""
    genus = get_object_or_404(
        TaxonGenus.objects.select_related('family', 'family__order', 'defining_sample'), name=name)
    thumbnail, image_url, video_id = taxon_media(genus.defining_sample)
    if not (image_url or video_id):
        raise Http404
    resolver = TaxonResolver()
    areas = []
    for area in SpeciesArea.objects.select_related(
            'species', 'country', 'sea', 'defining_sample', 'defining_sample__trip', 'defining_sample__trip__region'
    ).order_by('species__scientific_name'):
        defining = area.defining_sample
        if not defining or defining.status != 'published' or defining.deleted_at or not (defining.image or defining.video_url):
            continue  # same gate species_page/catalog.js use -- an area only counts once it can actually show something
        _, _, genus_obj = resolver.resolve(area.species)
        if genus_obj and genus_obj.pk == genus.pk:
            area.observation_count = area_samples(area).count()   # same count the gallery card shows
            areas.append(area)
    if not areas:
        raise Http404
    lang = get_lang(request)

    def taxon_label(obj):
        if not obj:
            return ''
        return (obj.name_en or obj.name) if lang == 'en' else (obj.name_he or obj.name)

    taxon_family = genus.family
    taxon_order = taxon_family.order if (taxon_family and taxon_family.order_id) else None
    common_name = (genus.name_en or genus.name_he) if lang == 'en' else (genus.name_he or genus.name_en)
    description = (genus.description_en or genus.description_he) if lang == 'en' else (genus.description_he or genus.description_en)
    return render(request, 'observations/genus_page.html', {
        'genus': genus, 'areas': areas,
        'image_url': image_url, 'video_id': video_id, 'thumbnail': thumbnail,
        'taxon_order': taxon_order, 'taxon_family': taxon_family,
        'taxon_order_label': taxon_label(taxon_order), 'taxon_family_label': taxon_label(taxon_family),
        'common_name': common_name, 'description': description,
        'canonical_url': request.build_absolute_uri(request.path),
    })


def genus_article(request, name):
    """Streams a genus' curated article PDF -- the genus-level analogue of species_article
    above, keyed directly by TaxonGenus.name."""
    genus = get_object_or_404(TaxonGenus, name=name)
    if not genus.article_pdf:
        raise Http404
    response = FileResponse(genus.article_pdf.open('rb'), content_type='application/pdf')
    response['Cache-Control'] = 'public, max-age=3600'
    response['Content-Disposition'] = 'inline; filename="%s.pdf"' % genus.name.replace('"', "'")
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
    rows = visible.select_related('species', 'trip', 'trip__country', 'trip__region', 'site', 'owner', 'owner__profile')
    if request.GET.get('mine') and request.user.is_authenticated:
        rows = rows.filter(owner=request.user)
    get = request.GET
    if get.get('kind') in dict(Sample.Kind.choices):
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
    # keeps a partial or not-quite-exact typed value still useful as a search. A SPECIES-kind
    # sample carries its order/family/genus both through the linked Species row and in its own
    # order/family/genus fields (see Sample.sync_taxonomy); an ORDER/FAMILY/GENUS-kind sample
    # IS the taxon itself and has no linked Species, only those own fields -- so each search
    # matches both, or the sample defining the searched-for taxon would never show up in its
    # own search.
    if get.get('order'):
        rows = rows.filter(Q(species__order__icontains=get['order']) | Q(order__icontains=get['order']))
    if get.get('family'):
        rows = rows.filter(Q(species__family__icontains=get['family']) | Q(family__icontains=get['family']))
    if get.get('genus'):
        rows = rows.filter(Q(species__genus__icontains=get['genus']) |
                            # A handful of species have a blank genus column even though
                            # their scientific name clearly starts with one (e.g. "Cyerce
                            # basi" with genus='') -- see the same fallback in config.views'
                            # resolve_taxon_chain. Without it, a genus search would never
                            # find that species' own sample at all.
                            Q(species__genus='', species__scientific_name__istartswith=get['genus']) |
                            Q(genus__icontains=get['genus']))
    if get.get('photographer'):
        # The photographer of an observation is its owner (see Sample.photographer_name).
        # Match the typed text against owners' Hebrew name, English name or username.
        term = get['photographer'].strip().casefold()
        matching = [u.pk for u in get_user_model().objects.select_related('profile')
                    if term in full_name_for(u, 'he').casefold() or term in full_name_for(u, 'en').casefold()
                    or term in u.get_username().casefold()]
        rows = rows.filter(owner__in=matching)
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

    def photographer_options(page_lang):
        credited = set(visible.order_by().values_list('owner', flat=True))
        users = get_user_model().objects.select_related('profile').filter(pk__in=credited)
        return sorted({name for name in (full_name_for(u, page_lang) for u in users) if name})

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
        'orders': options('order'),
        'families': options('family'),
        'genera': options('genus'),
        'photographers': photographer_options(lang),
    }
    if manager:
        context['owners'] = list(get_user_model().objects.filter(observations__in=visible).distinct().order_by('username').values_list('username', flat=True))
    return render(request, 'observations/list.html', context)


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user=form.save()
        user.groups.add(Group.objects.get_or_create(name='New user')[0])
        Profile.objects.create(user=user)
        notify_new_user_registered(user)
        login(request,user)
        return redirect('profile')
    return render(request,'observations/form.html',{'form':form,'title':'הרשמה / Sign up'})


@login_required
def profile(request):
    lang = get_lang(request)
    item,_=Profile.objects.get_or_create(user=request.user)
    form=ProfileForm(request.POST or None,instance=item,lang=lang)
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
    results = [{'id': str(item.pk), 'label': str(item) + (f' — {item.name_he}' if item.name_he else '')} for item in rows]
    return JsonResponse({'results': results})


@login_required
def species_area_status(request):
    """Whether the sample currently being edited is (or would be) the defining sample
    for the given species in the given trip's country+sea, and whether that species
    already appears in the gallery there through some other sample. Called live from the
    observation form whenever the species or trip field changes, since both together
    determine which SpeciesArea is relevant."""
    from django.http import JsonResponse
    from .models import split_undetermined_variant
    species_text = (request.GET.get('species') or '').strip()
    base_text, variant = split_undetermined_variant(species_text)
    species = Species.find_by_name(base_text)
    trip = DiveTrip.objects.filter(pk=request.GET.get('trip')).select_related('country','region__sea').first()
    if not species or not trip or not trip.country_id or not trip.sea:
        return JsonResponse({'matched': False})
    area = SpeciesArea.objects.filter(species=species, country_id=trip.country_id, sea=trip.sea, undetermined_variant=variant).first()
    sample_id = request.GET.get('sample') or None
    is_defining = bool(area and sample_id and str(area.defining_sample_id) == str(sample_id))
    appears = bool(area and area.defining_sample_id)
    next_info = None
    if is_defining:
        candidate = SpeciesArea.next_candidate(species.pk, trip.country_id, trip.sea, sample_id, variant)
        next_info = {'kind': 'with_media', 'id': candidate['sample'].pk} if candidate['kind'] == 'with_media' else {'kind': candidate['kind']}
    return JsonResponse({'matched': True, 'is_defining': is_defining, 'appears': appears, 'next': next_info})


@staff_member_required
def divetrip_locations(request):
    """Region->country/sea and Site->region mappings, for the DiveTrip admin's cascading
    dropdowns (divetrip_admin.js): narrows the "region" choices to the trip's own
    country/sea, and the "site" choices to the trip's own region. These tables are tiny, so
    the whole mapping is fetched once rather than re-queried per keystroke."""
    from django.http import JsonResponse
    return JsonResponse({
        'regions': list(Region.objects.values('id', 'country_id', 'sea_id')),
        'sites': list(Site.objects.values('id', 'region_id')),
    })


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
    if request.user.is_staff: form.enable_add_links()
    if request.method=='POST' and form.is_valid():
        item=form.save(commit=False)
        def canonical_image_write(source_sample, target_sample=None):
            # Store under the same stable, meaningful name the bulk folder importer and
            # the image manager use (see Sample.canonical_image_name) -- target_sample's
            # own fields decide the name (its own trip/species/kind/title), while
            # source_sample is only where the just-uploaded bytes come from; they differ
            # when a new submission is being folded into an EXISTING observation below.
            from .media_transfer import save_images
            raw=source_sample.image.read();name=(target_sample or source_sample).canonical_image_name()
            save_images({name:raw})
            return name
        # A brand-new SPECIES-kind observation (pk is None -- never one being edited) for a
        # species already observed on this same trip is folded into that existing observation
        # instead of creating a duplicate: whichever of image/video the new submission actually
        # supplies replaces that observation's, rather than piling up a second row for the same
        # species+trip. Sample.clean()'s own species+trip duplicate check (models.py) is what
        # would otherwise reject this outright -- catching it here first turns that rejection
        # into an update. Editing an EXISTING observation into a collision is deliberately not
        # redirected this way -- it still hits that hard validation error, since silently
        # overwriting a different observation than the one being edited would be surprising.
        existing = Sample.objects.filter(
            kind=Sample.Kind.SPECIES, species_id=item.species_id, trip_id=item.trip_id, deleted_at__isnull=True,
            undetermined_variant=item.undetermined_variant,
        ).first() if (item.pk is None and item.kind==Sample.Kind.SPECIES and item.species_id and item.trip_id) else None
        if existing:
            if item.image: existing.image = canonical_image_write(item, existing)
            if item.video_url: existing.video_url = item.video_url
            existing.save_reviewed()
            messages.success(request,'תצפית של מין זה כבר קיימת במסע זה — התמונה/הסרטון עודכנו בתצפית הקיימת במקום יצירת כפילות.')
            return redirect(f'{next_url}#obs-{existing.pk}')
        if 'image' in form.changed_data and item.image:
            item.image = canonical_image_write(item)
        # A brand-new observation (never one being edited) is the message worth the reader's
        # eye first among the run-of-the-mill notices this page and others show (profile
        # saved, trip added, etc.) -- extra_tags carries that distinction through to
        # base.html, which renders it with its own highlighted style.
        is_new_observation = item.pk is None
        item.save_reviewed()
        messages.success(request,'התצפית פורסמה.' if item.status=='published' else 'התצפית נשמרה וממתינה להשלמת נתונים ולאישור מנהל.',
            extra_tags='new-observation' if is_new_observation else '')
        return redirect(f'{next_url}#obs-{item.pk}')
    return render(request,'observations/form.html',{'form':form,'title':'תצפית / Sample','observation_form':True,
        'trip_new_url':reverse('trip-new'),'next':next_url,
        'species_options':species_name_options(),
        'taxonomy':taxonomy_for_form(),
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
    if item.kind == Sample.Kind.SPECIES and item.species_id and item.trip_id and item.trip.country_id and item.trip.sea_id:
        area = SpeciesArea.objects.filter(species_id=item.species_id, country_id=item.trip.country_id, sea=item.trip.sea,
                                           undetermined_variant=item.undetermined_variant).first()
    is_defining = bool(area and area.defining_sample_id == item.pk)

    if action == 'release_species':
        if not is_defining:
            messages.error(request, 'התצפית אינה מגדירה את המין כרגע.')
        else:
            candidate = SpeciesArea.next_candidate(item.species_id, item.trip.country_id, item.trip.sea, item.pk, item.undetermined_variant)
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
            item.image_hash = ''
            item.save(update_fields=['image', 'image_hash', 'updated_at'])
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
