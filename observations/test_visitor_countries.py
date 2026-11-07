"""Visitors by country on the /news/ page (managers only).

Rules:
- Each counted visitor-day keeps its two-letter country code (never the address) and how many pages it viewed
  (DailyVisitor.country / .views). The country is looked up once, on the day's first page.
- geo.country_of: an edge-network country header (CF-IPCountry) first, else the DB-IP country database
  (geoip/country.mmdb); unknown ('') for private addresses, "XX"/"T1", or without the database.
- build.sh downloads the database on every deploy (scripts/fetch_geoip.py: this month's edition, else last month's;
  never fails the build); the file is not in git.
- The manager section lists the 30 days' visitors and views per country, most visitors first, with an
  "unknown" row and DB-IP's attribution; country names and flags are drawn in the page's language by the browser.
"""
import datetime
import importlib.util
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.utils import timezone

from . import geo
from .models import DailyVisitor

UA = 'Mozilla/5.0 (Macintosh) Safari/605'
BASE = Path(settings.BASE_DIR)


class FakeReader:
    def get(self, ip):
        return {'132.64.0.1': {'country': {'iso_code': 'IL'}}, '8.8.8.8': {'country': {'iso_code': 'US'}}}.get(ip)


class CountryOfTests(SimpleTestCase):
    def country(self, ip, **meta):
        return geo.country_of(RequestFactory().get('/', **meta), ip)

    def test_edge_header_wins(self):
        with mock.patch.object(geo, '_open_reader', return_value=FakeReader()):
            self.assertEqual(self.country('8.8.8.8', HTTP_CF_IPCOUNTRY='il'), 'IL')
            self.assertEqual(self.country('8.8.8.8', HTTP_CF_IPCOUNTRY='XX'), 'US')   # unknown header: the database
            self.assertEqual(self.country('8.8.8.8', HTTP_CF_IPCOUNTRY='T1'), 'US')

    def test_database_lookup(self):
        with mock.patch.object(geo, '_open_reader', return_value=FakeReader()):
            self.assertEqual(self.country('132.64.0.1'), 'IL')
            self.assertEqual(self.country('1.2.3.4'), '')          # not in the database

    def test_private_or_bad_addresses_and_no_database_are_unknown(self):
        with mock.patch.object(geo, '_open_reader', return_value=FakeReader()):
            for ip in ('127.0.0.1', '10.0.0.5', '192.168.1.2', '', 'not-an-ip'):
                self.assertEqual(self.country(ip), '')
        with mock.patch.object(geo, '_open_reader', return_value=None):
            self.assertEqual(self.country('132.64.0.1'), '')


class RecordCountryTests(TestCase):
    def test_country_is_kept_once_and_views_are_counted(self):
        with mock.patch.object(geo, '_open_reader', return_value=FakeReader()) as reader:
            for _ in range(3):
                self.client.get('/news/', HTTP_USER_AGENT=UA, REMOTE_ADDR='132.64.0.1')
            self.assertEqual(reader.call_count, 1)                   # looked up on the day's first page only
        visitor = DailyVisitor.objects.get()
        self.assertEqual((visitor.country, visitor.views), ('IL', 3))
        self.assertEqual(len(visitor.key), 64)                       # the address itself is never stored
        self.assertNotIn('132.64', str(DailyVisitor.objects.values().get()))


class NewsCountriesTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        DailyVisitor.objects.create(day=today, key='a', country='IL', views=5)
        DailyVisitor.objects.create(day=today, key='b', country='IL', views=2)
        DailyVisitor.objects.create(day=today - datetime.timedelta(days=3), key='c', country='US', views=1)
        DailyVisitor.objects.create(day=today, key='d', country='', views=1)
        DailyVisitor.objects.create(day=today - datetime.timedelta(days=40), key='e', country='FR', views=9)   # too old
        self.manager = User.objects.create_superuser('boss', password='pw-test-12345')

    def section(self, lang='he'):
        html = self.client.get('/news/', {'lang': lang}).content.decode()
        start = html.index('id="countries"')
        return html[start:html.index('</script>', start)]

    def test_manager_sees_visitors_by_country(self):
        self.client.force_login(self.manager)
        section = self.section()
        self.assertIn('מבקרים לפי מדינה (30 יום) · 2 מדינות', section)
        rows = section.split('<tr>')[2:]
        self.assertIn('data-country="IL"', rows[0])
        self.assertIn('<td class="num">2</td><td class="num">7</td>', rows[0])
        self.assertIn('data-country="US"', section)
        self.assertIn('לא ידוע', section)
        self.assertNotIn('data-country="FR"', section)
        self.assertIn('https://db-ip.com', section)
        self.assertIn('Intl.DisplayNames', section)

    def test_english(self):
        self.client.force_login(self.manager)
        section = self.section('en')
        self.assertIn('Visitors by country (30 days) · 2 countries', section)
        self.assertIn('Unknown', section)

    def test_not_shown_to_visitors(self):
        self.assertNotIn('id="countries"', self.client.get('/news/').content.decode())


class FetchDatabaseTests(SimpleTestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location('fetch_geoip', BASE / 'scripts' / 'fetch_geoip.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_this_month_then_last_month(self):
        urls = self.load().editions(datetime.date(2027, 1, 15))
        self.assertEqual(urls, ['https://download.db-ip.com/free/dbip-country-lite-2027-01.mmdb.gz',
                                'https://download.db-ip.com/free/dbip-country-lite-2026-12.mmdb.gz'])

    def test_a_failed_download_never_fails_the_build(self):
        module = self.load()
        with mock.patch('urllib.request.urlopen', side_effect=OSError('offline')), \
                mock.patch.object(module, 'TARGET', Path('/nonexistent-dir-for-test/geoip/country.mmdb')), \
                mock.patch.object(Path, 'mkdir'):
            self.assertEqual(module.main(), 0)

    def test_wired_into_the_build_and_kept_out_of_git(self):
        self.assertIn('python scripts/fetch_geoip.py || true', (BASE / 'build.sh').read_text())
        self.assertIn('maxminddb==', (BASE / 'requirements.txt').read_text())
        self.assertIn('\ngeoip/\n', (BASE / '.gitignore').read_text())
