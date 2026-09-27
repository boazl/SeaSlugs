from django.test import TestCase
from django.contrib.auth.models import User


class AnalyticsScopeTests(TestCase):
    """The Google tag (gtag.js) belongs on community-facing pages only -- not on
    Boaz's own management tools under /admin/ (image manager, table transfer,
    releases, db-replace, folder import), even though they extend the same
    observations/base.html every public page here extends (see base.html's
    request.path check)."""

    def setUp(self):
        self.user = User.objects.create_superuser('manager', password='test-password')
        self.client.force_login(self.user)

    def test_community_page_gets_the_google_tag(self):
        self.assertContains(self.client.get('/observations/'), 'googletagmanager.com/gtag/js')

    def test_gallery_homepage_gets_the_google_tag(self):
        # dist/index.html -- a separate standalone template from base.html, needs its own check.
        self.assertContains(self.client.get('/'), 'googletagmanager.com/gtag/js')

    def test_image_manager_does_not_get_the_google_tag(self):
        response = self.client.get('/admin/images/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'googletagmanager.com/gtag/js')

    def test_table_transfer_does_not_get_the_google_tag(self):
        response = self.client.get('/admin/table-transfer/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'googletagmanager.com/gtag/js')

    def test_releases_does_not_get_the_google_tag(self):
        response = self.client.get('/admin/releases/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'googletagmanager.com/gtag/js')


class AnalyticsOptOutCookieTests(TestCase):
    """A personal exclude_analytics=1 cookie lets Boaz's own browser skip the gtag.js
    snippet everywhere it's installed (base.html, dist/index.html, species_page.html,
    genus_page.html), set/cleared through the unauthenticated /analytics/exclude/ and
    /analytics/include/ endpoints (config/views.py)."""

    def setUp(self):
        self.user = User.objects.create_superuser('manager', password='test-password')
        self.client.force_login(self.user)

    def test_normal_visitor_without_the_cookie_gets_the_tag(self):
        self.assertContains(self.client.get('/'), 'googletagmanager.com/gtag/js')

    def test_cookie_excludes_analytics_from_the_gallery_homepage(self):
        self.client.cookies['exclude_analytics'] = '1'
        self.assertNotContains(self.client.get('/'), 'googletagmanager.com/gtag/js')

    def test_cookie_excludes_analytics_from_a_base_html_community_page(self):
        self.client.cookies['exclude_analytics'] = '1'
        self.assertNotContains(self.client.get('/observations/'), 'googletagmanager.com/gtag/js')

    def test_admin_tool_has_no_tag_regardless_of_the_cookie(self):
        # /admin/ is already excluded by path alone -- setting the cookie too must not
        # somehow re-enable it or break the combined check in base.html.
        self.client.cookies['exclude_analytics'] = '1'
        response = self.client.get('/admin/table-transfer/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'googletagmanager.com/gtag/js')

    def test_exclude_endpoint_sets_a_year_long_site_wide_cookie(self):
        response = self.client.get('/analytics/exclude/')
        self.assertEqual(response.status_code, 200)
        cookie = response.cookies['exclude_analytics']
        self.assertEqual(cookie.value, '1')
        self.assertEqual(cookie['path'], '/')
        self.assertGreaterEqual(int(cookie['max-age']), 60 * 60 * 24 * 365)
        self.assertTrue(cookie['httponly'])

    def test_exclude_endpoint_actually_stops_the_tag_on_the_next_visit(self):
        self.client.get('/analytics/exclude/')  # test client keeps the returned cookie
        self.assertNotContains(self.client.get('/'), 'googletagmanager.com/gtag/js')

    def test_include_endpoint_clears_the_cookie_and_restores_the_tag(self):
        self.client.get('/analytics/exclude/')
        self.assertNotContains(self.client.get('/'), 'googletagmanager.com/gtag/js')
        response = self.client.get('/analytics/include/')
        self.assertEqual(response.status_code, 200)
        cookie = response.cookies['exclude_analytics']
        self.assertEqual(int(cookie['max-age']), 0)
        self.assertContains(self.client.get('/'), 'googletagmanager.com/gtag/js')
