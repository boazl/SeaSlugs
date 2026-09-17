"""Blocks ordinary site traffic while a full database replacement is running
(see db_replace.py). Staff accounts always pass through, so an admin can
finish or cancel the replacement; everyone else sees a maintenance page,
except for /admin/ itself so an admin can still log in."""
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
        if is_locked() and not (request.user.is_authenticated and request.user.is_staff) \
                and not request.path.startswith('/admin/'):
            response = HttpResponse(PAGE, content_type='text/html; charset=utf-8', status=503)
            response['Retry-After'] = '300'
            response['Cache-Control'] = 'private, no-store'
            return response
        return self.get_response(request)
