"""Serve the same curated gallery locally and on the static host."""
from django.conf import settings
from django.http import FileResponse, Http404

FILES = {
    'index.html': 'text/html; charset=utf-8',
    'styles.css': 'text/css; charset=utf-8',
    'app.js': 'text/javascript; charset=utf-8',
    'catalog.js': 'text/javascript; charset=utf-8',
    'intro-photo.jpg': 'image/jpeg',
}

def gallery_file(request, filename='index.html'):
    if filename == 'index.html':
        from django.template import engines
        from django.http import HttpResponse
        from observations.models import SiteImage
        has_site_image = SiteImage.objects.filter(key='intro_photo').exclude(image='').exists()
        template = engines['django'].from_string((settings.BASE_DIR / 'dist' / filename).read_text())
        response = HttpResponse(template.render({'has_site_image': has_site_image}, request))
        response['Cache-Control'] = 'private, no-store'
        return response
    if filename == 'catalog.js':
        import json
        from django.http import HttpResponse
        from observations.models import Sample, SpeciesArea, TaxonOrder, TaxonFamily, TaxonGenus, youtube_id

        def sample_out(s, region):
            return {
                'sample_id': s.pk, 'trip_id': s.trip_id,
                'region': str(region.pk), 'site': str(s.site_id) if s.site_id else None,
                'photographer': s.photographer_name, 'year': s.trip.year, 'month': s.trip.month,
                'video_id': youtube_id(s.video_url) if s.video_url else None,
                'image_url': f'/observations/{s.pk}/photo/' if s.image else None,
                'thumbnail': f'/observations/{s.pk}/photo/' if s.image else s.thumbnail,
            }

        # Taxon lookups, keyed by the exact Species.genus/family/order text values, used to
        # resolve each species to its curated TaxonGenus -> TaxonFamily -> TaxonOrder chain.
        # Going through genus (the finest text field) picks up any suborder/subfamily-specific
        # row the family/order was manually reassigned to in admin, not just the auto-built
        # blank-sub_order/sub_family "base" row -- see build_taxonomy_tables.py. A species with
        # no genus match falls back to a family/order match against the base row only, since a
        # bare family/order text value can't identify a specific suborder/subfamily row on its own.
        taxon_genus_by_name = {g.name: g for g in TaxonGenus.objects.select_related('family', 'family__order', 'defining_sample')}
        taxon_family_by_name = {f.name: f for f in TaxonFamily.objects.filter(sub_family='').select_related('order', 'defining_sample')}
        taxon_order_by_name = {o.name: o for o in TaxonOrder.objects.filter(sub_order='').select_related('defining_sample')}

        def resolve_taxon_chain(species):
            # A handful of species have a blank genus column even though their scientific name
            # clearly starts with one (e.g. "Coryphellina iurmanovi" with genus=''). Fall back to
            # that leading word for RESOLUTION only -- it's never written back to Species.genus.
            genus_text = species.genus or (species.scientific_name.split()[0] if species.scientific_name else '')
            genus_obj = taxon_genus_by_name.get(genus_text) if genus_text else None
            family_obj = genus_obj.family if (genus_obj and genus_obj.family_id) else (
                taxon_family_by_name.get(species.family) if species.family else None)
            order_obj = family_obj.order if (family_obj and family_obj.order_id) else (
                taxon_order_by_name.get(species.order) if species.order else None)
            return order_obj, family_obj, genus_obj

        def taxon_rank(value):
            return (1, '') if not value else (0, value)

        def species_sort_key(order_obj, family_obj, genus_obj, species):
            return (
                taxon_rank(order_obj.taxonomic_order if order_obj else ''),
                order_obj.name if order_obj else '', order_obj.sub_order if order_obj else '',
                taxon_rank(family_obj.taxonomic_order if family_obj else ''),
                family_obj.name if family_obj else '', family_obj.sub_family if family_obj else '',
                taxon_rank(genus_obj.taxonomic_order if genus_obj else ''),
                genus_obj.name if genus_obj else '',
                taxon_rank(species.phylogenetic_order),
                species.scientific_name,
            )

        taxa_orders, taxa_families, taxa_genera = {}, {}, {}

        def taxon_media(defining_sample):
            if not defining_sample or defining_sample.status != 'published' or defining_sample.deleted_at:
                return None, None, None
            if not (defining_sample.image or defining_sample.video_url):
                return None, None, None
            thumbnail = f'/observations/{defining_sample.pk}/photo/' if defining_sample.image else defining_sample.thumbnail
            image_url = f'/observations/{defining_sample.pk}/photo/' if defining_sample.image else None
            video_id = youtube_id(defining_sample.video_url) if defining_sample.video_url else None
            return thumbnail, image_url, video_id

        def taxon_label_pair(obj, sub_value):
            # The scientific (Latin) name is always the primary/leading part of the label --
            # the Hebrew or English common name (when set) is added afterwards in parens, the
            # same way species cards show the scientific name first and the common name below.
            suffix = f' ({sub_value})' if sub_value else ''
            latin = obj.name + suffix
            label = latin + (f' ({obj.name_he})' if obj.name_he else '')
            label_en = latin + (f' ({obj.name_en})' if obj.name_en else '')
            return label, label_en

        def register_taxon(dest, obj, sub_value):
            key = str(obj.pk)
            if key not in dest:
                thumbnail, image_url, video_id = taxon_media(obj.defining_sample)
                label, label_en = taxon_label_pair(obj, sub_value)
                dest[key] = {'label': label, 'label_en': label_en, 'thumbnail': thumbnail, 'image_url': image_url, 'video_id': video_id}
                if sub_value is not None:
                    dest[key]['sub_value'] = sub_value
            return key

        areas = SpeciesArea.objects.select_related('species', 'country', 'sea', 'defining_sample')
        species_out, area_labels, region_out, site_out, trip_out = [], {}, {}, {}, {}
        sortable = []
        for area in areas:
            defining = area.defining_sample
            if not defining or defining.status != 'published' or defining.deleted_at or not (defining.image or defining.video_url):
                continue  # a species shows in the gallery only through a valid defining sample
            area_key = f'{area.country_id}-{area.sea_id}'
            area_labels[area_key] = {
                'label': f'{area.country.name} \u00b7 {area.sea.name}',
                'label_en': f'{area.country.name_en or area.country.name} \u00b7 {area.sea.name_en or area.sea.name}',
            }
            samples_qs = Sample.objects.filter(
                kind='species', species_id=area.species_id, status='published', deleted_at__isnull=True,
                trip__country_id=area.country_id, trip__region__sea_id=area.sea_id, trip__year__isnull=False,
                species_other='', site_other='',
            ).select_related('trip', 'trip__region', 'site', 'owner', 'owner__profile').order_by('created_at', 'pk')
            samples = []
            for s in samples_qs:
                region = s.trip.region
                region_out[str(region.pk)] = {'label': region.name, 'label_en': region.name_en or region.name, 'area': area_key}
                if s.site_id:
                    site_out[str(s.site_id)] = {'label': s.site.name, 'label_en': s.site.name_en or s.site.name, 'region': str(region.pk)}
                trip_out[str(s.trip_id)] = {'label': s.trip.title, 'area': area_key}
                samples.append(sample_out(s, region))
            if not samples:
                continue  # area exists but its samples are no longer published/complete
            primary = next((x for x in samples if x['sample_id'] == area.defining_sample_id), samples[0])
            order_obj, family_obj, genus_obj = resolve_taxon_chain(area.species)
            entry = {
                'area_id': area.pk, 'species_id': area.species_id, 'area': area_key,
                'slug': area.slug,
                'title': area.species.scientific_name, 'name_he': area.species.name_he, 'name_en': area.species.name_en,
                'epithet': area.species.species,
                # The genus/family filter+search values are the CURATED names (via genus_obj/
                # family_obj, already resolved above), not the species' raw genus/family text --
                # both fields are blank on many species whose genus is still resolvable (via
                # TaxonGenus, or via the scientific-name fallback in resolve_taxon_chain), which
                # used to make the family filter miss real families entirely (e.g. Myrrhinidae for
                # every observed Phyllodesmium species with family='') and would have hidden those
                # species outright had the family filter been used to select them. Falls back to
                # the raw text only when nothing resolved it, same as the order field above.
                'genus': genus_obj.name if genus_obj else area.species.genus,
                'family': family_obj.name if family_obj else area.species.family,
                # The order filter/search value is the CURATED order name (via order_obj,
                # already resolved above), not the species' raw order text -- Species.order
                # sometimes still carries a legacy synonym (e.g. "Doridida" for Nudibranchia) or
                # a "Not assigned" placeholder, which used to leak into the gallery's order
                # filter as bogus, disconnected options. Falls back to the raw text only when it
                # isn't one of those placeholder values and nothing resolved it, so a species
                # without a matching TaxonOrder row yet doesn't just disappear from the filter.
                'order': order_obj.name if order_obj else (area.species.order if area.species.order not in ('', 'Not assigned') else ''),
                # The family's curated superfamily (blank when not yet classified), for the
                # superfamily filter -- sits between suborder and family in the taxonomic
                # hierarchy the gallery filters by.
                'superfamily': family_obj.superfamily if family_obj else '',
                # Resolved via the TaxonGenus -> TaxonFamily -> TaxonOrder chain above: the
                # suborder this species' order was curated into (blank when none), and the
                # ids used both to filter by suborder and to detect group transitions for the
                # taxonomic-sort panel headings in app.js.
                'sub_order': order_obj.sub_order if order_obj else '',
                'taxon_order_id': str(order_obj.pk) if order_obj else None,
                'taxon_family_id': str(family_obj.pk) if family_obj else None,
                'taxon_genus_id': str(genus_obj.pk) if genus_obj else None,
                'thumbnail': primary['thumbnail'], 'image_url': primary['image_url'], 'video_id': primary['video_id'],
                # Where/when the card's own photo was taken (the defining sample's, not
                # necessarily the whole species-in-area's) -- shown on the card instead of
                # the coarser country+sea area label, e.g. "Anilao, 2017" rather than
                # "Philippines · Indo Pacific".
                'region': primary['region'], 'year': primary['year'],
                'samples': samples,
            }
            if order_obj:
                register_taxon(taxa_orders, order_obj, order_obj.sub_order)
            if family_obj:
                register_taxon(taxa_families, family_obj, family_obj.sub_family)
            if genus_obj:
                register_taxon(taxa_genera, genus_obj, None)
            sortable.append((species_sort_key(order_obj, family_obj, genus_obj, area.species), entry))

        sortable.sort(key=lambda pair: pair[0])
        species_out = [entry for _, entry in sortable]

        collection_rows = Sample.objects.filter(
            status='published', deleted_at__isnull=True, kind='collection', species__isnull=True,
            trip__isnull=False, trip__country__isnull=False, trip__region__isnull=False, trip__year__isnull=False,
            species_other='', site_other='',
        ).select_related('trip', 'trip__region', 'trip__country', 'owner', 'owner__profile').order_by('gallery_order', 'pk')
        collections_out = []
        for item in collection_rows:
            region = item.trip.region
            area_key = f'{item.trip.country_id}-{region.sea_id}'
            region_out[str(region.pk)] = {'label': region.name, 'label_en': region.name_en or region.name, 'area': area_key}
            trip_out[str(item.trip_id)] = {'label': item.trip.title, 'area': area_key}
            collections_out.append({
                'sample_id': item.pk, 'trip_id': item.trip_id, 'title': item.title,
                'photographer': item.photographer_name, 'area': area_key,
                'region': str(region.pk), 'year': item.trip.year, 'month': item.trip.month,
                'video_id': youtube_id(item.video_url) if item.video_url else None,
                'image_url': f'/observations/{item.pk}/photo/' if item.image else None,
                'thumbnail': f'/observations/{item.pk}/photo/' if item.image else item.thumbnail,
                'species_count': item.trip.display_species_count,
            })

        taxa = {'orders': taxa_orders, 'families': taxa_families, 'genera': taxa_genera}
        data = {'species': species_out, 'collections': collections_out, 'areas': area_labels, 'regions': region_out, 'sites': site_out, 'trips': trip_out, 'taxa': taxa}
        response = HttpResponse('window.SEASLUGS = ' + json.dumps(data, ensure_ascii=False).replace('<', '\u003c') + ';', content_type='text/javascript; charset=utf-8')
        response['Cache-Control'] = 'no-store'
        return response

    if filename not in FILES:
        raise Http404
    return FileResponse((settings.BASE_DIR / 'dist' / filename).open('rb'), content_type=FILES[filename])


def health(request):
    from django.http import JsonResponse
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
