"""The page of a dive trip's collection observation (/trip/<code>/): the trip's video and photo, as on a species
page (and, for a manager, the local / Google Drive copy of the video), the trip's details, and below them a card for
every species observed on the trip, each linking to that observation on its species page.

The page is keyed by DiveTrip.code (unique, and the same on the Mac and on the live site, unlike the row ids), so
the address never changes. It answers 200 only for a trip with a published collection observation that the gallery
shows (the catalog.js rule: a country, region and year, a photo or a video)."""
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .articles import article_links
from .gallery_data import area_is_live, taxon_media
from .i18n import get_lang
from .models import DiveTrip, Sample, SpeciesArea
from .templatetags.seaslugs_i18n import loc


def trip_collections(trip):
    """The trip's published collection observations the gallery shows as cards, in the gallery's order."""
    return list(Sample.objects.filter(
        trip=trip, status='published', deleted_at__isnull=True, kind=Sample.Kind.COLLECTION, species__isnull=True,
        trip__country__isnull=False, trip__region__isnull=False, trip__year__isnull=False,
        species_other='', site_other='').exclude(image='', video_url='')
        .select_related('trip', 'trip__region', 'trip__country', 'owner', 'owner__profile').order_by('gallery_order', 'pk'))


def trip_title(trip, lang):
    """A trip's title is typed in Hebrew only; in English it is its place and date ("Eilat · Coral Beach 8/2026")
    built from the localized site/region names."""
    if lang != 'en':
        return trip.title
    place = (trip.site.name_en or trip.site.name) if trip.site_id else (
        (trip.region.name_en or trip.region.name) if trip.region_id else trip.region_name)
    when = f'{trip.month}/{trip.year}' if trip.year and trip.month else (str(trip.year) if trip.year else '')
    return ' '.join(x for x in (place, when) if x) or trip.title


def trip_species_areas(trip):
    """The gallery cards (SpeciesArea) of the species observed on the trip, alphabetically. A species is observed at
    most once per trip (Sample.clean: a trip is one sampling -- more dives in the same place are a new trip), so each
    card carries that one observation (card_sample: the card's photo, and the anchor of its link on the species
    page) and shows no observation count, except the yellow "1" of a species also observed in other areas."""
    samples = list(Sample.objects.filter(
        trip=trip, kind=Sample.Kind.SPECIES, species__isnull=False, status='published', deleted_at__isnull=True,
        species_other='', site_other='').order_by('created_at', 'pk'))
    if not samples or not (trip.country_id and trip.region_id and trip.region.sea_id and trip.year):
        return []
    areas = {(a.species_id, a.undetermined_variant): a for a in SpeciesArea.objects.filter(
        species_id__in={s.species_id for s in samples}, country_id=trip.country_id, sea_id=trip.region.sea_id)
        .select_related('species', 'country', 'sea', 'defining_sample')}
    shown = {}
    for sample in samples:
        area = areas.get((sample.species_id, sample.undetermined_variant))
        if not area or not area.slug or area.pk in shown or not area_is_live(area):
            continue
        area.card_sample = sample
        area.observation_count = 1          # the card's count badge is for several observations: never here
        area.has_photo = bool(sample.image) or not sample.video_url
        area.has_video = bool(sample.video_url)
        shown[area.pk] = area
    return sorted(shown.values(), key=lambda a: (a.species.scientific_name.lower(), a.undetermined_variant))


def trip_page(request, code):
    from .views import is_manager, sample_edit_url
    trip = get_object_or_404(DiveTrip.objects.select_related('country', 'region', 'region__sea', 'site'), code=code)
    collections = trip_collections(trip)
    if not collections:
        raise Http404
    main = collections[0]
    thumbnail, image_url, video_id = taxon_media(main)
    lang = get_lang(request)
    manager = is_manager(request.user)
    if manager:
        # The manager's local (Mac) copy of the video, or its Google Drive copy on the live site (local_videos.py).
        from .local_videos import annotate
        annotate([main])
    areas = trip_species_areas(trip)
    from .gallery_data import annotate_same_species
    annotate_same_species(areas, lang)   # a species also observed in other areas: a yellow count (1) with its totals
    if manager and areas:
        from .local_videos import annotate_areas
        annotate_areas(areas)
    title = main.gallery_title(lang) or trip_title(trip, lang)
    # the region's name already starts with its country ("Philippines - Anilao"); the country alone without one
    place = ' · '.join(x for x in (
        loc(trip.region, lang) if trip.region_id else (loc(trip.country, lang) if trip.country_id else trip.country_name),
        loc(trip.site, lang) if trip.site_id else '') if x)
    date_text = (f'{trip.month}/{trip.year}' if trip.month else str(trip.year)) if trip.year else ''
    description = (trip.description_en or trip.description_he) if lang == 'en' else (trip.description_he or trip.description_en)
    return render(request, 'observations/trip_page.html', {
        'trip': trip, 'main_sample': main, 'title': title,
        'place': place, 'date_text': date_text, 'description': description,
        'image_url': image_url, 'video_id': video_id, 'thumbnail': thumbnail,
        'areas': areas, 'article_links': article_links(trip.articles.all(), lang),
        'gallery_trip_url': f'/?sort=alpha&trip={trip.pk}',
        'canonical_url': request.build_absolute_uri(request.path),
        'edit_url': sample_edit_url(request, [main]),
        'can_copy_image': manager,
    })


def trip_page_url(trip, lang='he'):
    return reverse('trip-page', args=[trip.code]) + ('?lang=en' if lang == 'en' else '')
