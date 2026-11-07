"""The owner's browsers stay out of the visit statistics even after signing out: every response to a signed-in owner
(a superuser or ACTIVITY_EXCLUDED_USERNAMES) gives that browser the analytics opt-out cookie (exclude_analytics=1,
the same as /analytics/exclude/), so its later signed-out visits are counted neither by the site's counter nor by
Google Analytics. Other members and visitors never get the cookie."""
from django.contrib.auth.models import User
from django.test import TestCase

from .models import DailyPageView, DailyVisitor

UA = 'Mozilla/5.0 (Macintosh) Safari/605'


def sign_out(client):
    # the test client's logout() also forgets every cookie; signing out in a browser only ends the session
    del client.cookies['sessionid']


class OwnerBrowserTests(TestCase):
    def setUp(self):
        User.objects.create_superuser('boss', password='pw-test-12345')
        User.objects.create_user('diver', password='pw-test-12345')

    def test_signing_in_marks_the_browser_and_later_visits_are_not_counted(self):
        self.client.login(username='boss', password='pw-test-12345')
        response = self.client.get('/news/', HTTP_USER_AGENT=UA)
        cookie = response.cookies['exclude_analytics']
        self.assertEqual(cookie.value, '1')
        self.assertTrue(cookie['httponly'])
        self.assertGreater(int(cookie['max-age']), 360 * 24 * 3600)
        sign_out(self.client)
        self.client.get('/news/', HTTP_USER_AGENT=UA)
        self.client.get('/', HTTP_USER_AGENT=UA)
        self.assertFalse(DailyPageView.objects.exists())
        self.assertFalse(DailyVisitor.objects.exists())

    def test_signed_out_owner_page_has_no_google_tag(self):
        self.client.login(username='boss', password='pw-test-12345')
        self.client.get('/news/', HTTP_USER_AGENT=UA)
        sign_out(self.client)
        self.assertNotIn('googletagmanager.com/gtag', self.client.get('/', HTTP_USER_AGENT=UA).content.decode())

    def test_the_cookie_is_set_once(self):
        self.client.login(username='boss', password='pw-test-12345')
        self.assertIn('exclude_analytics', self.client.get('/news/', HTTP_USER_AGENT=UA).cookies)
        self.assertNotIn('exclude_analytics', self.client.get('/news/', HTTP_USER_AGENT=UA).cookies)

    def test_members_and_visitors_are_not_marked_and_are_counted(self):
        self.assertNotIn('exclude_analytics', self.client.get('/news/', HTTP_USER_AGENT=UA).cookies)
        self.client.login(username='diver', password='pw-test-12345')
        self.assertNotIn('exclude_analytics', self.client.get('/news/', HTTP_USER_AGENT=UA).cookies)
        self.assertEqual(DailyPageView.objects.get(path='/news/').views, 2)
