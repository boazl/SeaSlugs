"""A temporary password a manager set (Profile.must_change_password) must be replaced at the next login."""
from django.contrib.auth.models import User
from django.test import TestCase

from .models import Profile


class PasswordChangeRequiredTests(TestCase):
    """A member with a temporary password is sent to the password change page from every page (logging out still
    works) until they choose their own; then the mark is cleared and they go on to where they were headed. Any member
    can change their password from the profile page; the manager sets the mark on the user's admin page."""

    def setUp(self):
        self.user = User.objects.create_user('ofer', password='12345678')
        Profile.objects.create(user=self.user, must_change_password=True)
        self.client.force_login(self.user)

    def test_redirected_until_changed(self):
        response = self.client.get('/forum/')
        self.assertEqual(response['Location'], '/observations/password/?next=%2Fforum%2F')
        self.assertContains(self.client.get('/observations/password/'), 'הסיסמה שקיבלת היא זמנית')
        self.assertEqual(self.client.post('/observations/logout/').status_code, 302)

    def test_change_clears_the_mark(self):
        response = self.client.post('/observations/password/', {
            'old_password': '12345678', 'new_password1': 'Nudibranch-2027!', 'new_password2': 'Nudibranch-2027!', 'next': '/forum/'})
        self.assertEqual(response['Location'], '/forum/')
        self.assertFalse(Profile.objects.get(user=self.user).must_change_password)
        self.assertEqual(self.client.get('/forum/').status_code, 200)       # still logged in, no redirect
        self.assertTrue(User.objects.get(pk=self.user.pk).check_password('Nudibranch-2027!'))

    def test_weak_password_refused(self):
        self.client.post('/observations/password/', {'old_password': '12345678', 'new_password1': '87654321', 'new_password2': '87654321'})
        self.assertTrue(Profile.objects.get(user=self.user).must_change_password)

    def test_profile_link_and_admin_field(self):
        Profile.objects.filter(user=self.user).update(must_change_password=False)
        self.assertContains(self.client.get('/observations/profile/'), 'href="/observations/password/"')
        admin = User.objects.create_superuser('boss', 'b@example.org', 'a-valid-password-927')
        self.client.force_login(admin)
        self.assertContains(self.client.get(f'/admin/auth/user/{self.user.pk}/change/'), 'must_change_password')
