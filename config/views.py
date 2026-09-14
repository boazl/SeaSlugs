"""Serve the same curated gallery locally and on the static host."""
from django.conf import settings
from django.http import FileResponse, Http404

FILES = {
    'index.html': 'text/html; charset=utf-8',
    'styles.css': 'text/css; charset=utf-8',
    'app.js': 'text/javascript; charset=utf-8',
    'catalog.js': 'text/javascript; charset=utf-8',
}

def gallery_file(request, filename='index.html'):
    if filename == 'index.html':
        from django.template import engines
        from django.http import HttpResponse
        template = engines['django'].from_string((settings.BASE_DIR / 'dist' / filename).read_text())
        response = HttpResponse(template.render({}, request))
        response['Cache-Control'] = 'private, no-store'
        return response
    if filename == 'catalog.js':
        import json
        from django.http import HttpResponse
        from observations.models import Sample, youtube_id
        from django.db.models import Q, Value
        from django.db.models.functions import NullIf
        rows = Sample.objects.filter(status='published', deleted_at__isnull=True, region__isnull=False, country__isnull=False, year__isnull=False).filter(Q(kind='species',species__isnull=False) | Q(kind='collection',species__isnull=True,trip__isnull=False)).select_related('species', 'region', 'country', 'trip', 'owner', 'owner__profile').order_by(NullIf('species__phylogenetic_order', Value('')).asc(nulls_last=True), 'species__scientific_name', 'gallery_order', 'pk')
        data = {'videos': [], 'collections': [], 'regions': {}, 'regions_en': {}}
        for item in rows:
            if any(getattr(item, field + '_other') for field in ('species', 'country', 'region', 'site')):
                continue
            key = str(item.region_id)
            data['regions'][key] = f'{item.region.name} · {item.country.name}'
            data['regions_en'][key] = f'{item.region.name_en or item.region.name} · {item.country.name_en or item.country.name}'
            video = {'id': youtube_id(item.video_url) if item.video_url else None, 'image_url': f'/observations/{item.pk}/photo/' if item.image else None, 'trip_id': item.trip_id, 'photographer': item.photographer_name, 'sample_id': item.pk, 'kind': item.kind, 'title': item.title or (item.species.scientific_name if item.species else ''), 'region': key, 'year': item.year, 'month': item.month, 'thumbnail': f'/observations/{item.pk}/photo/' if item.image else item.thumbnail}
            if item.kind == 'collection':
                video.update(species_count=item.trip.display_species_count, month=item.month or item.trip.month, year=item.year or item.trip.year)
            data['collections' if item.kind == 'collection' else 'videos'].append(video)
        response = HttpResponse('window.SEASLUGS = ' + json.dumps(data, ensure_ascii=False).replace('<', '\\u003c') + ';', content_type='text/javascript; charset=utf-8')
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
