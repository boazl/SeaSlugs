"""Email notifications the app sends: the admin notice for a brand-new signup (see observations/views.py's
signup()) and the observations forum's new-comment emails (notify_forum_message). Kept in its own module so the send's
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


def forum_message_recipients(message):
    """Who is emailed about a new forum message: the observation's owner (the discussion's manager) and everyone who
    wrote in that discussion -- only those who ticked "email me" on their profile (Profile.forum_email), have an email
    address and an active account, never the writer. A message for the discussion's manager only goes to the owner
    alone (the others may not read it)."""
    from .models import ForumMessage
    users = {message.observation.owner}
    if not message.manager_only:
        writers = ForumMessage.objects.filter(observation_id=message.observation_id, deleted_at__isnull=True).select_related('user', 'user__profile')
        users.update(m.user for m in writers)
    out = []
    for user in users:
        profile = getattr(user, 'profile', None)
        if user.pk != message.user_id and user.is_active and user.email and profile and profile.forum_email:
            out.append(user)
    return sorted(out, key=lambda u: u.pk)


def notify_forum_message(message, link):
    """Best-effort email about a new forum message (forum.forum calls it after saving a message written in the forum;
    messages arriving through the table transfer send nothing). One email per recipient, Hebrew then English, with the
    observation, the writer, the subject and the text, and a link to the message. Never raises."""
    from .forum import observation_label
    from .models import full_name_for
    recipients = forum_message_recipients(message)
    if not recipients:
        return 0
    name_he = full_name_for(message.user, 'he') or message.user.username
    name_en = full_name_for(message.user, 'en') or message.user.username
    label_he = observation_label(message.observation, 'he')
    label_en = observation_label(message.observation, 'en')
    private_he = '\n(ההודעה מיועדת למנהל הדיון בלבד)' if message.manager_only else ''
    private_en = '\n(This message is for the discussion manager only)' if message.manager_only else ''
    subject_line = f' · {message.subject}' if message.subject else ''
    body = '\n'.join([
        f'{name_he} כתב/ה תגובה חדשה בפורום התצפיות על: {label_he}{private_he}',
        '',
        *([message.subject] if message.subject else []),
        message.text,
        '',
        f'לקריאה ולתגובה: {link}',
        '',
        '---',
        f'{name_en} wrote a new comment in the observations forum about: {label_en}{private_en}',
        f'Read and reply: {link}',
        '',
        'קיבלת את ההודעה כי ביקשת זאת בפרופיל שלך באתר; אפשר לבטל שם. / You asked for these emails on your profile; you can turn them off there.',
    ])
    sent = 0
    for user in recipients:
        try:
            send_mail(subject=f'SeaSlugs · תגובה חדשה בפורום / New forum comment · {label_en}{subject_line}',
                      message=body, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[user.email], fail_silently=False)
            sent += 1
        except Exception:
            logger.exception('Failed to send forum notification email to %s', user.username)
    return sent
