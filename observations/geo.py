"""The country of a visitor, for the visit counter's per-country numbers (activity.record_visit, the /news/ page).

Only the two-letter country code is ever kept -- never the address. It comes from:
  1. a country header set by the hosting's edge network (Cloudflare's CF-IPCountry), when there is one;
  2. otherwise the free DB-IP "IP to Country Lite" database (CC BY 4.0, https://db-ip.com), downloaded by build.sh on
     every deploy to geoip/country.mmdb (not in git). Without the file (e.g. on the Mac) the country is unknown ('').
"""
import ipaddress
import logging
import re
import threading

from django.conf import settings

logger = logging.getLogger(__name__)
COUNTRY_HEADERS = ('HTTP_CF_IPCOUNTRY',)
NOT_A_COUNTRY = {'XX', 'T1', 'ZZ'}          # Cloudflare's "unknown" and "Tor"
_lock = threading.Lock()
_reader = None
_reader_path = None


def database_path():
    return getattr(settings, 'GEOIP_COUNTRY_DB', settings.BASE_DIR / 'geoip' / 'country.mmdb')


def _open_reader():
    global _reader, _reader_path
    path = database_path()
    with _lock:
        if _reader_path != path:
            _reader_path, _reader = path, None
            try:
                if path.exists():
                    import maxminddb
                    _reader = maxminddb.open_database(str(path))
            except Exception:
                logger.exception('could not open the country database %s', path)
        return _reader


def _valid(code):
    code = (code or '').strip().upper()
    return code if re.fullmatch(r'[A-Z]{2}', code) and code not in NOT_A_COUNTRY else ''


def country_of(request, ip):
    """The visitor's two-letter country code, or '' when unknown."""
    for header in COUNTRY_HEADERS:
        code = _valid(request.META.get(header))
        if code:
            return code
    try:
        address = ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return ''
    if not address.is_global:
        return ''
    reader = _open_reader()
    if reader is None:
        return ''
    try:
        record = reader.get(str(address)) or {}
    except Exception:
        return ''
    return _valid((record.get('country') or {}).get('iso_code'))
