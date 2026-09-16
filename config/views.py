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
        from observations.models import Sample, SpeciesArea, youtube_id
        from django.db.models import Value
        from django.db.models.functions import NullIf

        def sample_out(s, region):
            return {
                'sample_id': s.pk, 'trip_id': s.trip_id,
                'region': str(region.pk), 'site': str(s.site_id) if s.site_id else None,
                'photographer': s.photographer_name, 'year': s.trip.year, 'month': s.trip.month,
                'video_id': youtube_id(s.video_url) if s.video_url else None,
                'image_url': f'/observations/{s.pk}/photo/' if s.image else None,
                'thumbnail': f'/observations/{s.pk}/photo/' if s.image else s.thumbnail,
            }

        areas = SpeciesArea.objects.select_related('species', 'country', 'sea').order_by(
            NullIf('species__phylogenetic_order', Value('')).asc(nulls_last=True), 'species__scientific_name')
        species_out, area_labels, region_out, site_out = [], {}, {}, {}
        for area in areas:
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
                samples.append(sample_out(s, region))
            if not samples:
                continue  # area exists but its samples are no longer published/complete
            primary = next((x for x in samples if x['sample_id'] == area.defining_sample_id), samples[0])
            species_out.append({
                'area_id': area.pk, 'species_id': area.species_id, 'area': area_key,
                'title': area.species.scientific_name, 'name_he': area.species.name_he, 'name_en': area.species.name_en,
                'genus': area.species.genus, 'family': area.species.family, 'order': area.species.order,
                'thumbnail': primary['thumbnail'], 'image_url': primary['image_url'], 'video_id': primary['video_id'],
                'samples': samples,
            })

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
            collections_out.append({
                'sample_id': item.pk, 'trip_id': item.trip_id, 'title': item.title,
                'photographer': item.photographer_name, 'area': area_key,
                'region': str(region.pk), 'year': item.trip.year, 'month': item.trip.month,
                'video_id': youtube_id(item.video_url) if item.video_url else None,
                'image_url': f'/observations/{item.pk}/photo/' if item.image else None,
                'thumbnail': f'/observations/{item.pk}/photo/' if item.image else item.thumbnail,
                'species_count': item.trip.display_species_count,
            })

        data = {'species': species_out, 'collections': collections_out, 'areas': area_labels, 'regions': region_out, 'sites': site_out}
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
