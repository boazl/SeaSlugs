"""Regression tests for the new-user notification email sent from observations/views.py's
signup() (see observations/notifications.py). Django's test runner always swaps
EMAIL_BACKEND for the in-memory backend for the duration of the test suite, regardless of
what settings.py configures for real -- so django.core.mail.outbox is what these check,
never a real mailbox."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase, override_settings

from .notifications import notify_new_user_registered


def signup_data(**overrides):
    data = dict(
        username='freshdiver', email='fresh@example.com',
        first_name='Fresh', last_name='Diver',
        password1='really-unusual-password-731', password2='really-unusual-password-731',
    )
    data.update(overrides)
    return data


@override_settings(NEW_USER_NOTIFICATION_EMAIL='admin@seaslugs.org.il')
class SignupNotificationEmailTests(TestCase):
    def test_email_sent_after_successful_signup(self):
        self.assertEqual(len(mail.outbox), 0)
        response = self.client.post('/observations/signup/', signup_data())
        self.assertEqual(response.status_code, 302)  # redirected to profile -- signup succeeded
        self.assertTrue(User.objects.filter(username='freshdiver').exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_recipient_and_subject(self):
        self.client.post('/observations/signup/', signup_data())
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ['admin@seaslugs.org.il'])
        self.assertEqual(sent.subject, 'SeaSlugs - New user registration')

    def test_body_has_registration_details_but_never_the_password(self):
        self.client.post('/observations/signup/', signup_data())
        body = mail.outbox[0].body
        self.assertIn('freshdiver', body)
        self.assertIn('fresh@example.com', body)
        self.assertIn('Fresh Diver', body)
        self.assertNotIn('really-unusual-password-731', body)
        # Belt and braces: no plausible password/auth-data label should appear either, in
        # case the message body is ever restructured to include more fields.
        for label in ('password', 'Password', 'password1', 'password2'):
            self.assertNotIn(label, body)

    def test_signup_still_succeeds_if_the_email_backend_raises(self):
        with patch('observations.notifications.send_mail', side_effect=OSError('smtp unreachable')):
            response = self.client.post('/observations/signup/', signup_data())
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='freshdiver').exists())
        self.assertEqual(len(mail.outbox), 0)  # the raising send_mail is the only one ever called


class NotifyNewUserRegisteredTests(TestCase):
    @override_settings(NEW_USER_NOTIFICATION_EMAIL='')
    def test_no_email_sent_when_no_notification_address_is_configured(self):
        user = User.objects.create_user('quietuser', email='quiet@example.com')
        notify_new_user_registered(user)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(NEW_USER_NOTIFICATION_EMAIL='admin@seaslugs.org.il')
    def test_a_raising_backend_is_logged_not_raised(self):
        user = User.objects.create_user('loudfailure', email='loud@example.com')
        with patch('observations.notifications.send_mail', side_effect=RuntimeError('boom')):
            notify_new_user_registered(user)  # must not raise
        self.assertEqual(len(mail.outbox), 0)
