"""Talking to PayPal: verifying an IPN message and reading a transaction back through the REST API.

Only the standard library (urllib), short timeouts, and nothing personal or secret is ever logged. Credentials come
from the environment only (settings.PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET).
"""
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

USER_AGENT = 'SeaSlugs-Support/1.0'
TIMEOUT = 20


class PayPalUnavailable(Exception):
    """PayPal could not be reached or answered with a server error -- the caller asks PayPal to retry later."""


class PayPalNotConfigured(Exception):
    """A setting the feature needs (credentials, receiver id) is missing."""


def is_sandbox():
    return getattr(settings, 'PAYPAL_ENV', 'live') == 'sandbox'


def ipn_verify_url():
    return 'https://ipnpb.sandbox.paypal.com/cgi-bin/webscr' if is_sandbox() else 'https://ipnpb.paypal.com/cgi-bin/webscr'


def api_base():
    return 'https://api-m.sandbox.paypal.com' if is_sandbox() else 'https://api-m.paypal.com'


def _post(url, data, headers):
    request = urllib.request.Request(url, data=data, headers={'User-Agent': USER_AGENT, **headers}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code >= 500:
            raise PayPalUnavailable(f'HTTP {error.code}') from None
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise PayPalUnavailable(type(error).__name__) from None


def verify_ipn(raw_body):
    """Send the message back to PayPal exactly as received (cmd=_notify-validate first). True = VERIFIED,
    False = INVALID; PayPalUnavailable when PayPal cannot be asked."""
    answer = _post(ipn_verify_url(), b'cmd=_notify-validate&' + raw_body,
                   {'Content-Type': 'application/x-www-form-urlencoded'})
    return answer.strip() == b'VERIFIED'


_token = {'value': None, 'expires': 0.0, 'key': None}


def _access_token():
    client_id = getattr(settings, 'PAYPAL_CLIENT_ID', '')
    secret = getattr(settings, 'PAYPAL_CLIENT_SECRET', '')
    if not client_id or not secret:
        raise PayPalNotConfigured('PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET')
    key = (api_base(), client_id)
    if _token['value'] and _token['key'] == key and _token['expires'] > time.time() + 60:
        return _token['value']
    auth = base64.b64encode(f'{client_id}:{secret}'.encode()).decode()
    try:
        body = _post(api_base() + '/v1/oauth2/token', b'grant_type=client_credentials',
                     {'Authorization': f'Basic {auth}', 'Content-Type': 'application/x-www-form-urlencoded'})
    except urllib.error.HTTPError as error:
        raise PayPalNotConfigured(f'token HTTP {error.code}') from None
    data = json.loads(body)
    _token.update(value=data['access_token'], expires=time.time() + int(data.get('expires_in', 300)), key=key)
    return _token['value']


def api_get(path):
    """GET a REST resource as a dict; None when PayPal answers 404 (no such resource for this account)."""
    request = urllib.request.Request(api_base() + path, headers={
        'User-Agent': USER_AGENT, 'Authorization': f'Bearer {_access_token()}', 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code in (403, 404):
            return None
        if error.code == 401:
            _token['value'] = None
            raise PayPalNotConfigured('API HTTP 401') from None
        raise PayPalUnavailable(f'API HTTP {error.code}') from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise PayPalUnavailable(type(error).__name__) from None


def get_capture(transaction_id):
    return api_get('/v2/payments/captures/' + urllib.parse.quote(transaction_id, safe=''))


def get_order(order_id):
    return api_get('/v2/checkout/orders/' + urllib.parse.quote(order_id, safe=''))
