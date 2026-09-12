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
    if filename not in FILES:
        raise Http404
    return FileResponse((settings.BASE_DIR / 'dist' / filename).open('rb'), content_type=FILES[filename])


def health(request):
    from django.http import JsonResponse
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})
