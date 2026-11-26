"""E-mails to the owner about support payments, through the site's existing SMTP settings (the same ones the
new-user notice uses) -- addressed to SUPPORT_NOTIFICATION_EMAIL.

* A verified, completed payment: "SeaSlugs – התקבלה תמיכה כספית חדשה". A refund or a reversal: its own e-mail.
* Sending happens after the records are saved, so a mail failure never loses a payment. A failed or skipped send stays
  pending (notified_at empty) and is retried: after each later PayPal message, from the support admin page, and by
  `python manage.py support_retry_notifications`. notified_at is set only after a successful send, and a send
  attempted in the last few minutes is not attempted again, so retries do not duplicate.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import SupportContribution, SupportEvent

logger = logging.getLogger(__name__)
DB = 'support'
RETRY_GAP = timedelta(minutes=5)
NOT_AVAILABLE = 'לא זמין'
SUBJECT_NEW = 'SeaSlugs – התקבלה תמיכה כספית חדשה'
SUBJECT_REFUND = 'SeaSlugs – החזר כספי של תמיכה'
SUBJECT_REVERSAL = 'SeaSlugs – ביטול או עיכוב של תמיכה כספית'


def admin_url():
    from django.contrib.sites.models import Site
    try:
        domain = Site.objects.get_current().domain
    except Exception:
        domain = 'seaslugs.org.il'
    scheme = 'http' if domain.startswith(('127.0.0.1', 'localhost')) else 'https'
    return f'{scheme}://{domain}/admin/support/'


def amount(value, currency=''):
    return NOT_AVAILABLE if value is None else f'{value:,.2f} {currency}'.strip()


def local_time(value):
    return timezone.localtime(value).strftime('%d/%m/%Y %H:%M') if value else NOT_AVAILABLE


def contribution_lines(c):
    return [
        f'סכום התמיכה: {amount(c.gross_amount)}',
        f'מטבע: {c.currency or NOT_AVAILABLE}',
        f'עמלת PayPal: {amount(c.fee_amount, c.currency)}',
        f'סכום נטו: {amount(c.net_amount, c.currency)}',
        f'תאריך ושעת התשלום: {local_time(c.paid_at)}',
        f'סטטוס התשלום: {c.get_status_display()}',
        f'מזהה העסקה ב-PayPal: {c.transaction_id}',
        f'הודעה מהתומך: {c.message}' if c.message else 'הודעה מהתומך: אין',
    ]


def footer():
    return ['', f'לניהול התמיכות: {admin_url()}', '',
            'הודעה אוטומטית מאתר SeaSlugs.org.il. היא אינה קבלה או אישור מס.']


def _due(obj):
    return obj.notified_at is None and (obj.notify_attempted_at is None
                                        or obj.notify_attempted_at < timezone.now() - RETRY_GAP)


def _send(obj, subject, lines):
    recipient = getattr(settings, 'SUPPORT_NOTIFICATION_EMAIL', '')
    if not recipient or not _due(obj):
        return False
    type(obj).objects.using(DB).filter(pk=obj.pk).update(notify_attempted_at=timezone.now())
    try:
        send_mail(subject=subject, message='\n'.join(lines), from_email=settings.DEFAULT_FROM_EMAIL,
                  recipient_list=[recipient], fail_silently=False)
    except Exception:
        logger.exception('Support notification e-mail failed (%s %s)', type(obj).__name__, obj.pk)
        return False
    now = timezone.now()
    type(obj).objects.using(DB).filter(pk=obj.pk, notified_at__isnull=True).update(notified_at=now)
    obj.notified_at = now
    return True


def notify_contribution(c):
    if c.payment_status != SupportContribution.PaymentStatus.COMPLETED:
        return False
    return _send(c, SUBJECT_NEW, ['התקבלה תמיכה כספית חדשה בפרויקט חינניות הים, מאומתת מול PayPal.', ''] +
                 contribution_lines(c) + footer())


def notify_event(event):
    c = event.contribution
    if c is None:
        return False
    if event.kind == SupportEvent.Kind.REFUND:
        full = c.status == SupportContribution.Status.REFUNDED
        intro = [f'בוצע {"החזר מלא" if full else "החזר חלקי"} של תמיכה כספית.',
                 f'סכום ההחזר: {amount(abs(event.amount) if event.amount is not None else None, event.currency)}',
                 f'עמלה שהוחזרה: {amount(abs(event.fee) if event.fee is not None else None, event.currency)}', '']
        return _send(event, SUBJECT_REFUND, intro + contribution_lines(c) + footer())
    if event.kind == SupportEvent.Kind.REVERSAL:
        intro = ['תשלום תמיכה בוטל או עוכב על ידי PayPal (בדרך כלל בעקבות מחלוקת או ביטול של המשלם).',
                 f'סכום שעוכב: {amount(abs(event.amount) if event.amount is not None else None, event.currency)}', '']
        return _send(event, SUBJECT_REVERSAL, intro + contribution_lines(c) + footer())
    return False


def pending_contributions():
    return SupportContribution.objects.using(DB).filter(
        notified_at__isnull=True, payment_status=SupportContribution.PaymentStatus.COMPLETED)


def pending_events():
    return SupportEvent.objects.using(DB).filter(
        notified_at__isnull=True, outcome='processed',
        kind__in=[SupportEvent.Kind.REFUND, SupportEvent.Kind.REVERSAL]).select_related('contribution')


def retry_pending():
    """Send every e-mail still pending. Returns how many were sent."""
    sent = 0
    for c in pending_contributions():
        sent += notify_contribution(c)
    for event in pending_events():
        sent += notify_event(event)
    return sent
