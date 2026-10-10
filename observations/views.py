from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Q
from django import forms
from django.http import Http404, FileResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from .models import Sample, Profile, Region, Site, DiveTrip, SiteImage, Species, Country, SpeciesArea, SampleKind, KIND_EN_NAMES, TaxonGenus, TaxonFamily, TaxonOrder, full_name_for
from .forms import SiteQuickForm, SpeciesQuickForm, SignupForm, SampleForm, ProfileForm, DiveTripForm, TripQuickForm, taxonomy_for_form, species_name_options
from .notifications import notify_new_user_registered
from . import seo_text
from .gallery_data import TaxonResolver, taxon_media, area_samples
from .i18n import get_lang
from .templatetags.seaslugs_i18n import loc
from .species_redirects import historical_species_redirect


def is_manager(user): return user.is_authenticated and user.is_staff and user.has_perm('observations.change_sample')


def trips(request):
    from django.db.models import Prefetch
    published = Sample.objects.filter(status='published', deleted_at__isnull=True, trip__isnull=False,
        trip__country__isnull=False, trip__region__isnull=False, trip__year__isnull=False,
        species_other='', site_other='').filter(Q(kind='collection', species__isnull=True) | Q(kind='species',species__isnull=False)
        ).filter(Q(image__gt='') | Q(video_url__gt='')   # the public list shows only trips that have media (photo or video)
        ).select_related('species','trip','owner','owner__profile')
    available = DiveTrip.objects.filter(samples__in=published).distinct()
    rows, filters = _trip_list_context(request, available)
    rows = list(rows.select_related('country', 'region', 'site')
                .prefetch_related(Prefetch('samples',queryset=published,to_attr='public_samples')))
    lang = get_lang(request)
    for trip in rows:
        # A trip's title is typed in Hebrew only; in English it is shown as its place and
        # date ("Eilat · Coral Beach 8/2026") built from the localized site/region names.
        if lang == 'en':
            place = (trip.site.name_en or trip.site.name) if trip.site_id else (
                (trip.region.name_en or trip.region.name) if trip.region_id else trip.region_name)
            when = f'{trip.month}/{trip.year}' if trip.year and trip.month else (str(trip.year) if trip.year else '')
            trip.display_title = ' '.join(x for x in (place, when) if x) or trip.title
        else:
            trip.display_title = trip.title
        trip.display_description = (trip.description_en or '') if lang == 'en' else (trip.description_he or '')
        # The free-text reserve/site name is usually typed in Hebrew -- left out in English.
        hebrew = any('\u0590' <= ch <= '\u05ff' for ch in trip.reserve)
        trip.display_reserve = '' if lang == 'en' and hebrew else trip.reserve
        # The table row: one place string, a sortable date key and the two kinds of media.
        trip.display_place = ' · '.join(x for x in (
            loc(trip.country, lang) if trip.country_id else trip.country_name,
            loc(trip.region, lang) if trip.region_id else trip.region_name,
            loc(trip.site, lang) if trip.site_id else trip.display_reserve) if x)
        trip.date_key = (trip.year or 0) * 100 + (trip.month or 0)
        trip.date_text = (f'{trip.month}/{trip.year}' if trip.month else str(trip.year)) if trip.year else ''
        trip.video_cards = [x for x in trip.public_samples if x.kind == 'collection']
        trip.species_samples = [x for x in trip.public_samples if x.kind == 'species']
        trip.species_total = trip.display_species_count
    return render(request, 'observations/trips.html', {'trips':rows, **filters,
        'trips_with_video': [t for t in rows if t.video_cards]})


def sample_edit_url(request, samples):
    """Edit link for the first of these observations the visitor may edit (a manager: any;
    otherwise their own, not deleted -- edit()'s rule); after saving, back to this page."""
    user = request.user
    if not user.is_authenticated:
        return None
    manager = is_manager(user)
    for sample in samples:
        if manager or (sample.owner_id == user.id and not sample.deleted_at):
            return reverse('observation-edit', args=[sample.pk]) + '?' + urlencode({'next': request.get_full_path()})
    return None


def gallery_urls(samples, lang):
    """pk -> the public gallery page that shows each of these observations (the species page,
    anchored to the observation, or the genus/family/order page), for those that are actually
    shown there: published, not deleted, and -- for a taxon -- with gallery species under it, so a
    link never leads to a 404."""
    suffix = '?lang=en' if lang == 'en' else ''
    out = {}
    live = [x for x in samples if x.status == Sample.Status.PUBLISHED and not x.deleted_at]
    species_samples = [x for x in live if x.kind == Sample.Kind.SPECIES and x.species_id and x.trip_id and x.trip.year
                       and x.trip.country_id and x.trip.region_id and x.trip.region.sea_id and not x.species_other and not x.site_other]
    if species_samples:
        areas = {(a.species_id, a.country_id, a.sea_id, a.undetermined_variant): a for a in SpeciesArea.objects.filter(
            species_id__in={x.species_id for x in species_samples}).select_related('defining_sample')}
        for x in species_samples:
            area = areas.get((x.species_id, x.trip.country_id, x.trip.region.sea_id, x.undetermined_variant))
            d = area.defining_sample if area else None
            if d and d.status == Sample.Status.PUBLISHED and not d.deleted_at and (d.image or d.video_url):
                out[x.pk] = f'/species/{area.slug}/{suffix}#obs-{x.pk}'
    taxon_samples = [x for x in live if x.kind in (Sample.Kind.GENUS, Sample.Kind.FAMILY, Sample.Kind.ORDER)]
    if taxon_samples:
        areas = gallery_areas()
        genera = {a.taxon_genus.name for a in areas if a.taxon_genus}
        families = {a.taxon_family.name for a in areas if a.taxon_family}
        order_rows = {a.taxon_order.pk: a.taxon_order for a in areas if a.taxon_order}
        for x in taxon_samples:
            if x.kind == Sample.Kind.GENUS and x.genus in genera:
                out[x.pk] = f'/genus/{x.genus}/{suffix}'
            elif x.kind == Sample.Kind.FAMILY and x.family in families:
                out[x.pk] = f'/family/{x.family}/{suffix}'
            elif x.kind == Sample.Kind.ORDER:
                rows = [r for r in order_rows.values() if r.name == x.order]
                row = next((r for r in rows if r.defining_sample_id == x.pk), rows[0] if rows else None)
                if row:
                    out[x.pk] = reverse('order-page', args=[row.pk]) + suffix
    return out


def species_page(request, slug):
    """Public, server-rendered, individually-URLed page for one species+area (a species
    observed in a given country+sea -- the same unit the gallery already keys a card on,
    since the same species observed in two different areas gets two different defining
    photos/pages there too). Only reachable once the area has a valid published defining
    sample, same rule the gallery feed itself uses to decide whether to show a card at all."""
    try:
        area = get_object_or_404(
            SpeciesArea.objects.select_related('species', 'country', 'sea', 'defining_sample'), slug=slug)
        thumbnail, image_url, video_id = taxon_media(area.defining_sample)
        if not (image_url or video_id):
            raise Http404
        samples = list(area_samples(area).select_related('species', 'trip', 'trip__region', 'site', 'owner', 'owner__profile').order_by('created_at', 'pk'))
        if not samples:
            raise Http404
    except Http404:
        response = historical_species_redirect(request, slug)
        if response is not None:
            return response
        raise
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
    sources = parse_sources(species.sources)
    # A common name is shown only in its own language (no Hebrew name in the English view).
    common_name = species.name_en if lang == 'en' else species.name_he
    description = (species.description_en or species.description_he) if lang == 'en' else (species.description_he or species.description_en)
    place = seo_text.area_label(area, lang, seo_text.multi_sea_country_ids())
    meta_title = seo_text.species_title(species_label, common_name, place)
    meta_description = (description or seo_text.species_description(
        species_label, common_name, taxon_label(family_obj), taxon_label(order_obj), len(samples), place, lang,
        migrant=species.is_migrant and seo_text.is_mediterranean(area), migrant_year=species.first_observed_year))
    return render(request, 'observations/species_page.html', {
        'can_copy_image': is_manager(request.user),
        'meta_title': meta_title, 'meta_description': meta_description, 'place_label': place,
        'area': area, 'species': species, 'species_label': species_label, 'samples': samples,
        'main_sample': main_sample, 'other_samples': other_samples,
        'info': info, 'size_short': size_short, 'depth_short': depth_short, 'sources': sources,
        'image_url': image_url, 'video_id': video_id, 'thumbnail': thumbnail,
        'taxon_order': order_obj, 'taxon_family': family_obj, 'taxon_genus': genus_obj,
        'taxon_order_label': taxon_label(order_obj), 'taxon_family_label': taxon_label(family_obj),
        'taxon_genus_label': taxon_label(genus_obj),
        'common_name': common_name, 'description': description, 'size_text': species.size_text(lang),
        'canonical_url': request.build_absolute_uri(request.path),
        'edit_url': sample_edit_url(request, [main_sample] + other_samples),
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


def parse_sources(text):
    """One entry per non-empty line of a "sources" text field: a link (labelled by its host)
    when the line is a URL, otherwise plain text -- shared by the species and genus pages."""
    from urllib.parse import urlparse
    sources = []
    for line in (text or '').splitlines():
        line = line.strip()
        if line:
            host = urlparse(line).netloc.removeprefix('www.') if line.startswith('http') else ''
            sources.append({'url': line if host else '', 'label': host or line})
    return sources


def genus_page(request, name):
    """Public, server-rendered page for one genus -- the genus-level analogue of
    species_page above, keyed directly by TaxonGenus.name (already unique, and a plain
    single Latin word, so no separate slug field is needed the way SpeciesArea has one).
    Shows every species observed in this genus (across all its areas), each linking to its
    own species page. Only reachable once the genus has a valid defining sample with media,
    the same rule species_page uses."""
    genus = get_object_or_404(
        TaxonGenus.objects.select_related('family', 'family__order', 'defining_sample'), name=name)
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
    thumbnail, image_url, video_id = taxon_hero_media(genus.defining_sample, areas)
    lang = get_lang(request)

    def taxon_label(obj):
        if not obj:
            return ''
        return (obj.name_en or obj.name) if lang == 'en' else (obj.name_he or obj.name)

    taxon_family = genus.family
    taxon_order = taxon_family.order if (taxon_family and taxon_family.order_id) else None
    common_name = genus.name_en if lang == 'en' else genus.name_he
    description = (genus.description_en or genus.description_he) if lang == 'en' else (genus.description_he or genus.description_en)
    return render(request, 'observations/genus_page.html', {
        'genus': genus, 'areas': areas,
        'image_url': image_url, 'video_id': video_id, 'thumbnail': thumbnail,
        'taxon_order': taxon_order, 'taxon_family': taxon_family,
        'taxon_order_label': taxon_label(taxon_order), 'taxon_family_label': taxon_label(taxon_family),
        'common_name': common_name, 'description': description,
        'identification': (genus.identification_en or genus.identification_he) if lang == 'en' else (genus.identification_he or genus.identification_en),
        'identification_caption': (genus.identification_caption_en or genus.identification_caption) if lang == 'en' else (genus.identification_caption or genus.identification_caption_en),
        'sources': parse_sources(genus.sources),
        'canonical_url': request.build_absolute_uri(request.path),
        'edit_url': taxon_edit_url(request, Sample.Kind.GENUS, genus),
    })


def taxon_hero_media(defining_sample, areas):
    """(thumbnail, image_url, video_id) for a taxon page's hero: the taxon's own defining
    sample when it has a photo/video, otherwise the first of its species' defining samples
    that does -- so a genus/family/order page never 404s just for lacking its own media."""
    media = taxon_media(defining_sample)
    if media[1] or media[2]:
        return media
    for area in areas:
        media = taxon_media(area.defining_sample)
        if media[1] or media[2]:
            return media
    return '', '', ''


def gallery_areas():
    """Every SpeciesArea the gallery shows (published defining sample with a photo or video),
    each with its resolved (order, family, genus) and observation count attached -- shared by
    the order and family pages."""
    resolver = TaxonResolver()
    out = []
    for area in SpeciesArea.objects.select_related(
            'species', 'country', 'sea', 'defining_sample', 'defining_sample__trip', 'defining_sample__trip__region'
    ).order_by('species__scientific_name'):
        defining = area.defining_sample
        if not defining or defining.status != 'published' or defining.deleted_at or not (defining.image or defining.video_url):
            continue
        area.taxon_order, area.taxon_family, area.taxon_genus = resolver.resolve(area.species)
        area.observation_count = area_samples(area).count()
        out.append(area)
    return out


def taxon_edit_url(request, kind, taxon):
    """Link to the edit page of the order/family/genus observation behind this taxon page, for
    a visitor who may edit it -- a manager (any observation) or the observation's own owner
    (not deleted), exactly edit()'s rule. The taxon's defining sample comes first, then the
    newest other observation of that kind and name; failing that, for a manager, a new observation of
    that kind and name. None otherwise. After saving, the edit page returns to this page."""
    user = request.user
    if not user.is_authenticated:
        return None
    field = {Sample.Kind.ORDER: 'order', Sample.Kind.FAMILY: 'family', Sample.Kind.GENUS: 'genus'}[kind]
    candidates = [taxon.defining_sample] if taxon.defining_sample_id else []
    candidates += list(Sample.objects.filter(kind=kind, deleted_at__isnull=True, **{field: taxon.name}).order_by('-created_at', '-pk'))
    manager = is_manager(user)
    for sample in candidates:
        if sample.kind == kind and getattr(sample, field) == taxon.name and (manager or (sample.owner_id == user.id and not sample.deleted_at)):
            return reverse('observation-edit', args=[sample.pk]) + '?' + urlencode({'next': request.get_full_path()})
    # No observation of this taxon yet: a manager gets a new one with its kind and name filled in
    # (its picture, until it has its own, is borrowed from an observation one level below).
    if manager:
        return reverse('observation-new') + '?' + urlencode({'kind': kind, 'name': taxon.name, 'next': request.get_full_path()})
    return None


def _taxon_page(request, rank, obj, areas, children, parent, parent_url):
    lang = get_lang(request)
    pick = lambda he, en: (en or he) if lang == 'en' else (he or en)
    thumbnail, image_url, video_id = taxon_hero_media(obj.defining_sample, areas)
    sub = getattr(obj, 'sub_order', '') or getattr(obj, 'sub_family', '')
    return render(request, 'observations/taxon_page.html', {
        'rank': rank, 'taxon': obj, 'latin_name': f'{obj.name} — {sub}' if sub else obj.name,
        # Names only in the page's own language; otherwise the Latin name stands alone.
        'common_name': obj.name_en if lang == 'en' else obj.name_he,
        'description': pick(obj.description_he, obj.description_en),
        'identification': pick(obj.identification_he, obj.identification_en),
        'sources': [line.strip() for line in obj.sources.splitlines() if line.strip()],
        'areas': areas, 'children': children,
        'parent_label': ((parent.name_en if lang == 'en' else parent.name_he) or parent.name) if parent else '',
        'parent_url': parent_url,
        'image_url': image_url, 'video_id': video_id, 'thumbnail': thumbnail,
        'canonical_url': request.build_absolute_uri(request.path),
        'edit_url': taxon_edit_url(request, getattr(Sample.Kind, rank.upper()), obj),
    })


def _child_list(areas, attr, url_name, lang):
    """[{label, latin, url, count}] for the distinct families/genera under a taxon, in
    taxonomic order, each with the number of species cards it holds."""
    seen = {}
    for area in areas:
        child = getattr(area, attr)
        if child is None:
            continue
        entry = seen.setdefault(child.pk, {'obj': child, 'count': 0})
        entry['count'] += 1
    out = []
    for entry in sorted(seen.values(), key=lambda e: ((e['obj'].taxonomic_order or '~'), e['obj'].name)):
        obj = entry['obj']
        common = (obj.name_en if lang == 'en' else obj.name_he) or ''
        out.append({'latin': obj.name, 'common': common, 'count': entry['count'],
                    'url': reverse(url_name, args=[obj.name])})
    return out


def order_page(request, pk):
    """Public page for one order group (TaxonOrder row -- keyed by pk, since one order name
    such as Nudibranchia has several rows): its description and identification, the
    families it holds and every gallery species in it."""
    order = get_object_or_404(TaxonOrder.objects.select_related('defining_sample'), pk=pk)
    areas = [a for a in gallery_areas() if a.taxon_order and a.taxon_order.pk == order.pk]
    if not areas:
        raise Http404
    children = _child_list(areas, 'taxon_family', 'family-page', get_lang(request))
    return _taxon_page(request, 'order', order, areas, children, None, '')


def family_page(request, name):
    """Public page for one family, keyed by name (the rare sub_family rows of one family are
    shown together): description, identification, its genera and every gallery species."""
    families = list(TaxonFamily.objects.select_related('order', 'defining_sample').filter(name=name))
    if not families:
        raise Http404
    ids = {f.pk for f in families}
    areas = [a for a in gallery_areas() if a.taxon_family and a.taxon_family.pk in ids]
    if not areas:
        raise Http404
    family = next((f for f in families if not f.sub_family), families[0])
    children = _child_list(areas, 'taxon_genus', 'genus-page', get_lang(request))
    order = family.order or areas[0].taxon_order
    return _taxon_page(request, 'family', family, areas, children, order,
                       reverse('order-page', args=[order.pk]) if order else '')


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

def family_article(request, name):
    """Streams a family's article PDF (the family page's own row -- see family_page)."""
    families = list(TaxonFamily.objects.filter(name=name))
    family = next((f for f in families if not f.sub_family), families[0] if families else None)
    if family is None or not family.article_pdf:
        raise Http404
    response = FileResponse(family.article_pdf.open('rb'), content_type='application/pdf')
    response['Cache-Control'] = 'public, max-age=3600'
    response['Content-Disposition'] = 'inline; filename="%s.pdf"' % family.name.replace('"', "'")
    return response


def order_article(request, pk):
    """Streams an order group's article PDF."""
    order = get_object_or_404(TaxonOrder, pk=pk)
    if not order.article_pdf:
        raise Http404
    response = FileResponse(order.article_pdf.open('rb'), content_type='application/pdf')
    response['Cache-Control'] = 'public, max-age=3600'
    response['Content-Disposition'] = 'inline; filename="%s.pdf"' % order.name.replace('"', "'")
    return response


def genus_identification(request, name):
    """Streams a genus' identification file (a PDF or an image -- see TaxonGenus.
    identification_file), inline, with the content type its extension implies."""
    import mimetypes
    genus = get_object_or_404(TaxonGenus, name=name)
    if not genus.identification_file:
        raise Http404
    content_type = mimetypes.guess_type(genus.identification_file.name)[0] or 'application/octet-stream'
    response = FileResponse(genus.identification_file.open('rb'), content_type=content_type)
    response['Cache-Control'] = 'public, max-age=3600'
    extension = genus.identification_file.name.rsplit('.', 1)[-1].lower()
    response['Content-Disposition'] = 'inline; filename="%s-identification.%s"' % (genus.name.replace('"', "'"), extension)
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

    rows = list(rows.select_related('trip', 'trip__region'))
    by_pk = {r.pk: r for r in rows}
    for pk_, url_ in gallery_urls(rows, lang).items():
        by_pk[pk_].gallery_url = url_

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
        # Every record type is always offered (family/order records are new and may not
        # exist yet), unlike the other filters below that list only values present.
        'kind_choices': [(v, kind_label_lookup.get(v, label)) for v, label in Sample.Kind.choices],
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


def trip_picker_data():
    """What the observation form's trip filters (country / region / site / year) need: every trip's
    place and year, and the names of the places that have a trip, so the browser can narrow the long
    trip list without a round trip. Also keeps the region->site mapping the site field already uses."""
    trips = list(DiveTrip.objects.values('id', 'region_id', 'country_id', 'site_id', 'year'))
    used = lambda key: {t[key] for t in trips if t[key]}
    return {
        'trips': trips,
        'sites': list(Site.objects.values('id', 'region_id')),
        'filters': {
            'countries': [{'id': c.pk, 'name': str(c)} for c in Country.objects.filter(pk__in=used('country_id')).order_by('name')],
            'regions': [{'id': r.pk, 'name': str(r), 'country_id': r.country_id} for r in Region.objects.filter(pk__in=used('region_id')).order_by('name')],
            'sites': [{'id': x.pk, 'name': str(x), 'region_id': x.region_id} for x in Site.objects.filter(pk__in=used('site_id')).order_by('name')],
            'years': sorted(used('year'), reverse=True),
        },
    }


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
    # Back from "add a new species": the species just added is already chosen.
    added=Species.objects.filter(pk=_int(request.GET.get('new_species'))).first() if request.method!='POST' and not pk else None
    if added: initial.update(genus=added.genus,species=added.species,family=added.family,order=added.order)
    # Opened from a taxon page that has no observation of its own yet: a new order/family/genus
    # observation with its kind and name filled in (managers -- they are the ones who edit taxon pages).
    kind_param=request.GET.get('kind')
    if not pk and request.method!='POST' and is_manager(request.user) and kind_param in ('order','family','genus'):
        initial['kind']=kind_param
        initial[kind_param]=request.GET.get('name','')[:150]
    # Where to return to after saving -- normally the observations list URL the user
    # followed the "עריכה" link from, filters/sort/page and all, carried through the
    # POST as a hidden field (see form.html) since it isn't otherwise part of this URL.
    # Validated against open-redirect abuse since it's attacker-influenceable input.
    requested_next=request.POST.get('next') or request.GET.get('next')
    if requested_next and url_has_allowed_host_and_scheme(requested_next,allowed_hosts={request.get_host()},require_https=request.is_secure()):
        next_url=requested_next
    else:
        next_url=reverse('observations')
    old_image_name=item.image.name if item.pk and item.image else ''
    form=SampleForm(request.POST or None,request.FILES or None,instance=item,initial=initial)
    manager=is_manager(request.user)
    if not manager:
        del form.fields['existing_image']      # re-using a gallery image is for managers only
    if manager and not item.species_other:
        # A manager adds the species to the catalog (link below the species field) instead of typing a free-text "other species".
        form.fields['species_other'].widget=forms.HiddenInput()
    if request.user.is_staff: form.enable_add_links()
    if is_manager(request.user): form.enable_taxon_files()
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
            if getattr(item,'_shared_image',False):
                existing.image = item.image.name; existing._shared_image = True   # the chosen gallery image itself, not a copy
            elif item.image: existing.image = canonical_image_write(item, existing)
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
        if getattr(item,'_shared_image',False) and old_image_name and old_image_name!=item.image.name:
            from .media_transfer import delete_image_if_unused
            delete_image_if_unused(old_image_name)        # the file this observation used to have, if nothing else uses it
        form.save_taxon_files(item)
        messages.success(request,'התצפית פורסמה.' if item.status=='published' else 'התצפית נשמרה וממתינה להשלמת נתונים ולאישור מנהל.',
            extra_tags='new-observation' if is_new_observation else '')
        return redirect(f'{next_url}#obs-{item.pk}')
    return render(request,'observations/form.html',{'form':form,'title':'תצפית / Observation','observation_form':True,
        'trip_new_url':reverse('trip-new'),'trip_add_url':reverse('trip-add'),'species_add_url':reverse('species-new') if manager else '','next':next_url,
        'species_options':species_name_options(),
        'taxonomy':taxonomy_for_form(),
        'locations':trip_picker_data()})


@login_required
def image_search(request):
    """Published observations that have an image, for the picker on the observation form (JSON). `q` matches the
    species / taxon name, title or trip (every word must match); `trip` limits it to one trip. 48 per page."""
    if not is_manager(request.user):
        raise Http404
    q = (request.GET.get('q') or '').strip()
    offset = max(_int(request.GET.get('offset')) or 0, 0)
    rows = Sample.objects.filter(status=Sample.Status.PUBLISHED, deleted_at__isnull=True).exclude(image='').select_related('species', 'trip')
    if _int(request.GET.get('trip')):
        rows = rows.filter(trip_id=_int(request.GET.get('trip')))
    for term in q.split()[:5]:
        rows = rows.filter(Q(species__scientific_name__icontains=term) | Q(species_other__icontains=term) | Q(genus__icontains=term)
            | Q(family__icontains=term) | Q(order__icontains=term) | Q(title__icontains=term)
            | Q(trip__title__icontains=term) | Q(trip__code__icontains=term))
    page = list(rows.order_by('-created_at', '-pk')[offset:offset + 49])
    return JsonResponse({'results': [{'id': x.pk, 'url': reverse('observation-photo', args=[x.pk]), 'label': x.taxon_label,
                                      'trip': x.trip.title if x.trip_id else ''} for x in page[:48]],
                         'next': offset + 48 if len(page) > 48 else None})


@login_required
def site_new(request):
    """Add a dive site that is not in the list. Opened from the trip form's "+" in a small window (popup=1): on
    success it tells the opener which site was created and closes itself; otherwise it returns to `next`."""
    popup = bool(request.GET.get('popup') or request.POST.get('popup'))
    next_url = request.POST.get('next') or request.GET.get('next') or reverse('trip-add')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = reverse('trip-add')
    form = SiteQuickForm(request.POST or None, initial={'region': _int(request.GET.get('region'))})
    if request.method == 'POST' and form.is_valid():
        site = form.save()
        if popup:
            return render(request, 'observations/site_added.html', {'site': {'id': site.pk, 'name': site.name, 'region_id': site.region_id}, 'next': next_url})
        messages.success(request, f'אתר הצלילה נוסף: {site.name}.')
        return redirect(next_url)
    return render(request, 'observations/site_add.html', {'form': form, 'popup': popup, 'next': next_url})


@login_required
def species_new(request):
    """A manager adds a species that is not in the catalog (genus, species, author, family...), then
    returns to the observation form with it already chosen."""
    if not is_manager(request.user):
        raise Http404
    next_url = request.POST.get('next') or request.GET.get('next') or reverse('observation-new')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = reverse('observation-new')
    form = SpeciesQuickForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        species = form.save()
        messages.success(request, f'המין נוסף לרשימה: {species.full_name}.')
        return redirect(next_url + ('&' if '?' in next_url else '?') + urlencode({'new_species': species.pk}))
    return render(request, 'observations/species_add.html', {'form': form, 'next': next_url, 'taxonomy': taxonomy_for_form()})


@login_required
def home_text_edit(request):
    """Manager-only screen for the wording of the home page's text sections (and the Google title and
    description), in both languages. A section left empty, or equal to the default, uses the default."""
    if not is_manager(request.user):
        raise Http404
    from .home_defaults import DEFAULTS, SECTION_LABELS
    from .home_content import overrides
    from .home_text import HOME_TEXT
    from .models import HomeText
    items = [(key, label, DEFAULTS[key], 'text') for key, label in SECTION_LABELS.items()]
    items += [('meta_title', 'כותרת הדף בגוגל (title)', {l: HOME_TEXT[l]['title'] for l in ('he', 'en')}, 'line'),
              ('meta_description', 'תיאור הדף בגוגל (description)', {l: HOME_TEXT[l]['description'] for l in ('he', 'en')}, 'text')]
    if request.method == 'POST':
        errors = []
        for key, label, defaults, kind in items:
            for lang in ('he', 'en'):
                value = request.POST.get(f'{key}__{lang}', '').replace('\r\n', '\n').strip()
                if len(value) > 6000:
                    errors.append(f'{label} ({lang}): הטקסט ארוך מדי.')
                    continue
                if not value or value == defaults[lang].strip():
                    HomeText.objects.filter(key=key, lang=lang).delete()
                else:
                    HomeText.objects.update_or_create(key=key, lang=lang, defaults={'content': value})
        for error in errors:
            messages.error(request, error)
        if not errors:
            messages.success(request, 'הטקסטים נשמרו. אפשר לראות אותם בדף הבית.')
        return redirect('home-text-edit')
    edited = overrides()
    rows = []
    for key, label, defaults, kind in items:
        rows.append({'key': key, 'label': label, 'kind': kind, 'fields': [
            {'lang': lang, 'name': f'{key}__{lang}', 'value': edited.get((key, lang)) or defaults[lang],
             'default': defaults[lang], 'is_default': not edited.get((key, lang))}
            for lang in ('he', 'en')]})
    return render(request, 'observations/home_text_edit.html', {'rows': rows})


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


def _int(value):
    try: return int(value)
    except (TypeError, ValueError): return None


def _trip_filters(params):
    """region / site / year picked on the trips page (GET), as objects; a site implies its region."""
    site = Site.objects.select_related('region').filter(pk=_int(params.get('site'))).first()
    region = site.region if site else Region.objects.select_related('country', 'sea').filter(pk=_int(params.get('region'))).first()
    return region, site, _int(params.get('year'))


def _trip_list_context(request, available, management=False):
    """Shared, validated location filters and allow-listed sorting for both trip pages."""
    from datetime import date
    region, site, year = _trip_filters(request.GET)
    country = Country.objects.filter(pk=_int(request.GET.get('country'))).first()
    if country and region and region.country_id != country.pk:
        region = site = None
    if not country and region:
        country = region.country
    rows = available
    if country: rows = rows.filter(country=country)
    if region: rows = rows.filter(region=region)
    if site: rows = rows.filter(site=site)
    if year: rows = rows.filter(year=year)
    sorts = {
        'code': ('code',), 'title': ('title',),
        'place': ('country__name', 'region__name', 'site__name', 'region_name'),
        'date': ('year', 'month', 'start_day'),
    }
    if management: sorts['count'] = ('sample_count',)
    sort = request.GET.get('sort', '-date')
    key = sort.lstrip('-')
    if key not in sorts or sort not in (key, '-' + key):
        sort, key = '-date', 'date'
    rows = rows.order_by(*[('-' if sort.startswith('-') else '') + f for f in sorts[key]], 'title', 'pk')
    query = {k: v for k, v in (('country', country.pk if country and request.GET.get('country') else ''),
        ('region', region.pk if region else ''), ('site', site.pk if site else ''), ('year', year or '')) if v}
    if request.GET.get('lang') in ('en', 'he'): query['lang'] = request.GET['lang']
    headers = []
    for field, label in [('code', 'סימון'), ('title', 'שם המסע'), ('place', 'מקום'), ('date', 'תאריך'), ('count', 'תצפיות')]:
        if field not in sorts: continue
        active = key == field
        target = field if active and sort.startswith('-') else '-' + field if active else field
        headers.append({'label': label, 'url': '?' + urlencode({**query, 'sort': target}),
            'aria': ('descending' if sort.startswith('-') else 'ascending') if active else 'none',
            'arrow': (' ↓' if sort.startswith('-') else ' ↑') if active else ''})
    years = {y for y in available.exclude(year__isnull=True).values_list('year', flat=True)}
    if management: years.add(date.today().year)
    # Management can create a trip in a location which has no trips yet.
    countries = Country.objects.all() if management else Country.objects.filter(dive_trips__in=available).distinct()
    regions = Region.objects.all() if management else Region.objects.filter(dive_trips__in=available).distinct()
    sites = Site.objects.all() if management else Site.objects.filter(dive_trips__in=available).distinct()
    return rows, {'countries': countries.order_by('name'), 'regions': regions.select_related('country').order_by('name'),
        'sites': sites.select_related('region').order_by('name'), 'years': sorted(years, reverse=True),
        'country': country, 'region': region, 'site': site, 'year': year, 'sort': sort,
        'sort_headers': headers, 'reset_url': reverse('trips-manage' if management else 'dive-trips') +
            ('?' + urlencode({'lang': query['lang']}) if 'lang' in query else ''),
        'add_url': reverse('trip-add') + ('?' + urlencode(query) if query else '')}


@login_required
def trips_manage(request):
    """Every dive trip with filters (region/site, year) and an add button that carries the filters
    into the add form, which suggests the trip's name and code from them."""
    from django.db.models import Count
    rows = DiveTrip.objects.select_related('country', 'region', 'site').annotate(
        sample_count=Count('samples', filter=Q(samples__deleted_at__isnull=True), distinct=True))
    rows, filters = _trip_list_context(request, rows, management=True)
    return render(request, 'observations/trips_manage.html', {
        'trips': rows, **filters, 'manager': is_manager(request.user), 'trip_management': True})


@login_required
def trip_add(request):
    """Quick dive-trip form. Opened from the trips page with the page's filters as the starting point;
    year and month default to now; name and code are suggested and can be overwritten."""
    from datetime import date
    next_url = request.POST.get('next') or request.GET.get('next') or reverse('trips-manage')
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        next_url = reverse('trips-manage')
    # Coming from the observation form: go back to it with the new trip already selected.
    select_trip = bool(request.POST.get('select_trip') or request.GET.get('select_trip'))
    if request.method == 'POST':
        form = TripQuickForm(request.POST, user=request.user)
        if form.is_valid():
            trip = form.save()
            messages.success(request, f'המסע נוסף: {trip.title} ({trip.code}).')
            if select_trip:
                next_url += ('&' if '?' in next_url else '?') + urlencode({'trip': trip.pk})
            return redirect(next_url)
    else:
        region, site, year = _trip_filters(request.GET)
        today = date.today()
        form = TripQuickForm(user=request.user, initial={'region': region, 'site': site, 'year': year or today.year,
            'month': today.month, 'photographer': request.user})
    return render(request, 'observations/trip_add.html', {'form': form, 'next': next_url, 'select_trip': select_trip,
        'site_regions': {s.pk: s.region_id for s in Site.objects.all()}})


@login_required
def trip_suggest(request):
    """The suggested name and code for the add form's current choices (JSON), so they follow the
    form as it changes -- the same rules the server applies on save."""
    from .trip_naming import suggest_title, suggest_code
    region, site, year = _trip_filters(request.GET)
    month, day = _int(request.GET.get('month')), _int(request.GET.get('day'))
    if not (region and year and month and 1 <= month <= 12):
        return JsonResponse({'title': '', 'code': ''})
    user = get_user_model().objects.filter(pk=_int(request.GET.get('photographer'))).first() if is_manager(request.user) else None
    user = user or request.user
    if day is not None and not 1 <= day <= 31: day = None
    return JsonResponse({'title': suggest_title(user, region, site, year, month, day), 'code': suggest_code(user, region, year, month, day)})


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
