"""Email notifications the app sends -- currently just the admin notice for a brand-new
signup (see observations/views.py's signup()). Kept in its own module so the send's
try/except and logging live next to the one thing that can raise, rather than inline in
the view, and so it's easy to trigger the same send from the test_email management
command without creating a user."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


def notify_new_user_registered(user):
    """Best-effort email to NEW_USER_NOTIFICATION_EMAIL after a successful signup. Never
    raises -- a misconfigured or unreachable mail server must not break registration, so
    any failure here is only logged. Sends nothing if no notification address is
    configured. Deliberately includes only non-sensitive registration details (never the
    password, which isn't even in scope by the time this runs)."""
    recipient = settings.NEW_USER_NOTIFICATION_EMAIL
    if not recipient:
        return
    full_name = f'{user.first_name} {user.last_name}'.strip()
    joined = timezone.localtime(user.date_joined) if user.date_joined else timezone.localtime()
    lines = [
        f'Username: {user.username}',
        f'Email: {user.email}',
    ]
    if full_name:
        lines.append(f'Name: {full_name}')
    lines.append(f'Registered: {joined:%Y-%m-%d %H:%M}')
    lines.append('')
    lines.append('This is an automated notification from SeaSlugs.org.il.')
    try:
        send_mail(
            subject='SeaSlugs - New user registration',
            message='\n'.join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Failed to send new-user notification email for %s', user.username)
