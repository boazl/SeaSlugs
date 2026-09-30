"""Send one real email through the configured EMAIL_* settings, without creating a user
or touching the database -- lets an operator confirm real SMTP credentials actually
deliver (locally or on Render) before relying on them for the signup notification.

Usage: python manage.py test_email [recipient]
(recipient defaults to NEW_USER_NOTIFICATION_EMAIL if not given)

Unlike observations.notifications.notify_new_user_registered, this deliberately lets a
send failure raise -- the whole point of running it by hand is to see whether it worked.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Send a test email through the configured EMAIL_* settings, to confirm delivery works.'

    def add_arguments(self, parser):
        parser.add_argument('recipient', nargs='?', help='Defaults to NEW_USER_NOTIFICATION_EMAIL.')

    def handle(self, *args, **options):
        recipient = options['recipient'] or settings.NEW_USER_NOTIFICATION_EMAIL
        if not recipient:
            raise CommandError('No recipient given, and NEW_USER_NOTIFICATION_EMAIL is not set.')
        self.stdout.write(f'Backend: {settings.EMAIL_BACKEND}')
        self.stdout.write(f'Host: {settings.EMAIL_HOST or "(none -- using the console backend, nothing is actually sent)"}')
        self.stdout.write(f'Sending a test email to {recipient} ...')
        send_mail(
            subject='SeaSlugs - test email',
            message=(
                "This is a test email from SeaSlugs's manage.py test_email command, "
                'confirming the configured EMAIL_* settings can deliver mail.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS('Sent.'))
