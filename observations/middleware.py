"""Blocks ordinary site traffic while a full database replacement is running
(see db_replace.py). Staff accounts always pass through, so an admin can
finish or cancel the replacement; everyone else sees a maintenance page,
except for /admin/ itself (so an admin can still log in) and /healthz
(Render's health check -- if that 503s while locked, Render sees the probe
fail, decides the instance itself has crashed, and restarts it, which is
worse than the maintenance page it was trying to show)."""
from django.http import HttpResponse
from .maintenance import is_locked

PAGE = (
    '<!doctype html><html lang="he" dir="rtl"><head><meta charset="utf-8">'
    '<title>תחזוקה</title></head>'
    '<body style="font-family:system-ui,sans-serif;text-align:center;padding:80px 20px">'
    '<h1>האתר בתחזוקה</h1><p>מתבצע עדכון נתונים. האתר יחזור לפעול בקרוב.</p>'
    '</body></html>'
)


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        exempt = request.path.startswith('/admin/') or request.path == '/healthz'
        if is_locked() and not (request.user.is_authenticated and request.user.is_staff) and not exempt:
            response = HttpResponse(PAGE, content_type='text/html; charset=utf-8', status=503)
            response['Retry-After'] = '300'
            response['Cache-Control'] = 'private, no-store'
            return response
        return self.get_response(request)


class LanguagePreferenceMiddleware:
    """Remembers an explicit ?lang=he/en choice (sent by the bilingual pages'
    language-toggle link) in a cookie, so it stays the default on later visits to
    those pages even without the query parameter."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        lang = request.GET.get('lang')
        if lang in ('he', 'en'):
            response.set_cookie('seaslugs_lang', lang, max_age=60 * 60 * 24 * 365, samesite='Lax')
        return response
