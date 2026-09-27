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
