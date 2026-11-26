"""The PayPal IPN listener (/webhooks/paypal/), the owner's support page (/admin/support/) and the figures for the
news page's manager section. Financial data is shown to superusers only, checked on the server."""
import csv
import logging
from datetime import datetime, time

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import notify, paypal, processing, summary
from .models import SupportContribution

logger = logging.getLogger(__name__)
DB = 'support'
MAX_BODY = 32 * 1024


def enabled():
    return bool(getattr(settings, 'PAYPAL_WEBHOOK_ENABLED', False))


def is_owner(user):
    return bool(getattr(user, 'is_authenticated', False) and user.is_superuser)


def context(request):
    """Context processor: the superuser's link to the support page and the number of contributions not yet seen."""
    if not enabled() or not is_owner(getattr(request, 'user', None)):
        return {}
    try:
        unseen = SupportContribution.objects.using(DB).filter(
            seen=False, payment_status=SupportContribution.PaymentStatus.COMPLETED).count()
    except DatabaseError:
        # support.sqlite3 not migrated yet (`python manage.py migrate --database support`): never break the pages.
        logger.warning('Support database not ready')
        return {'support_admin': True, 'support_unseen': 0}
    return {'support_admin': True, 'support_unseen': unseen}


@csrf_exempt
@require_POST
def paypal_ipn(request):
    """PayPal's IPN. Answers 200 to anything handled (processed, ignored or a repeat) so PayPal stops sending; 400 to
    a message PayPal does not confirm; 503 while the option is off or misconfigured and 502 when PayPal cannot be
    reached -- PayPal then sends the message again later, for days."""
    if not enabled():
        return HttpResponse('disabled', status=503, content_type='text/plain')
    raw = request.body
    if not raw or len(raw) > MAX_BODY:
        return HttpResponse('bad request', status=400, content_type='text/plain')
    try:
        if not paypal.verify_ipn(raw):
            logger.warning('PayPal IPN rejected: not verified by PayPal')
            return HttpResponse('invalid', status=400, content_type='text/plain')
        outcome, event = processing.process(raw)
    except paypal.PayPalNotConfigured as missing:
        logger.error('PayPal IPN not processed: configuration missing (%s)', missing)
        return HttpResponse('not configured', status=503, content_type='text/plain')
    except paypal.PayPalUnavailable as error:
        logger.warning('PayPal IPN deferred: PayPal unavailable (%s)', error)
        return HttpResponse('retry', status=502, content_type='text/plain')
    if outcome == 'processed':
        try:
            notify.retry_pending()
        except Exception:
            logger.exception('Support notifications failed after an IPN')
    return HttpResponse('ok', content_type='text/plain')


SORTS = {'date': ('paid_at', 'pk'), '-date': ('-paid_at', '-pk'), 'amount': ('gross_amount', 'pk'),
         '-amount': ('-gross_amount', '-pk')}


def _date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def filtered(request):
    qs = SupportContribution.objects.using(DB).all()
    date_from, date_to = _date(request.GET.get('from')), _date(request.GET.get('to'))
    tz = timezone.get_current_timezone()
    if date_from:
        qs = qs.filter(paid_at__gte=timezone.make_aware(datetime.combine(date_from, time.min), tz))
    if date_to:
        qs = qs.filter(paid_at__lte=timezone.make_aware(datetime.combine(date_to, time.max), tz))
    status = request.GET.get('status', '')
    if status in SupportContribution.Status.values:
        qs = qs.filter(status=status)
    if request.GET.get('new') == '1':
        qs = qs.filter(seen=False)
    sort = request.GET.get('sort') if request.GET.get('sort') in SORTS else '-date'
    return qs.order_by(*SORTS[sort]), {'from': date_from, 'to': date_to, 'status': status,
                                         'new': request.GET.get('new') == '1', 'sort': sort}


def _csv_amount(value):
    return '' if value is None else f'{value:.2f}'


def csv_response(rows):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="seaslugs-support-{timezone.localdate():%Y%m%d}.csv"'
    response['Cache-Control'] = 'private, no-store'
    response.write('﻿')    # BOM: Excel opens the Hebrew correctly
    writer = csv.writer(response)
    writer.writerow(['תאריך ושעה', 'מזהה עסקה', 'מזהה הזמנה', 'סטטוס', 'מטבע', 'ברוטו', 'עמלה', 'נטו',
                     'הוחזר', 'עמלה שהוחזרה', 'בוטל / עוכב', 'נטו אחרי החזרים', 'מספר מחלוקת', 'הודעת התומך',
                     'נצפתה'])
    for c in rows:
        writer.writerow([timezone.localtime(c.paid_at).strftime('%Y-%m-%d %H:%M') if c.paid_at else '',
                         c.transaction_id, c.order_id, c.get_status_display(), c.currency,
                         _csv_amount(c.gross_amount), _csv_amount(c.fee_amount), _csv_amount(c.net_amount),
                         _csv_amount(c.refunded_amount), _csv_amount(c.refunded_fee), _csv_amount(c.reversed_amount),
                         _csv_amount(c.net_after_refunds), c.dispute_case_id, c.message, 'כן' if c.seen else 'לא'])
    return response


@staff_member_required
def support_admin(request):
    """/admin/support/: every contribution with filters, sorting, monthly / yearly totals, CSV export and the
    "seen" marks. No refunds or receipts from here -- money is handled in PayPal itself."""
    if not request.user.is_superuser:
        raise PermissionDenied
    if request.method == 'POST':
        action = request.POST.get('action')
        qs = SupportContribution.objects.using(DB)
        if action == 'seen':
            processing.mark_seen(qs.filter(pk=request.POST.get('pk')))
        elif action == 'seen_all':
            count = processing.mark_seen(qs.all())
            messages.success(request, f'{count} תמיכות סומנו כנצפו.')
        elif action == 'retry':
            sent = notify.retry_pending()
            messages.success(request, f'נשלחו {sent} הודעות דוא"ל שהמתינו.')
        back = request.POST.get('next', '')
        return redirect(back if back.startswith('/') and not back.startswith('//') else 'support-admin')
    rows, chosen = filtered(request)
    if request.GET.get('format') == 'csv':
        return csv_response(rows)
    items = list(rows)
    all_items = list(SupportContribution.objects.using(DB).all())
    response = render(request, 'contributions/support_admin.html', {
        'rows': items, 'chosen': chosen, 'statuses': SupportContribution.Status.choices,
        'totals': summary.totals(items), 'monthly': summary.by_period(all_items, 'month'),
        'yearly': summary.by_period(all_items, 'year'),
        'pending_mail': notify.pending_contributions().count() + notify.pending_events().count(),
        'mail_configured': bool(settings.SUPPORT_NOTIFICATION_EMAIL), 'enabled': enabled(),
        'query': request.GET.urlencode(),
    })
    response['Cache-Control'] = 'private, no-store'
    return response


def news_section(request):
    """The news page's support section: superusers only, while receiving is on; None otherwise."""
    if not enabled() or not is_owner(request.user):
        return None
    try:
        return summary.news_summary(SupportContribution.objects.using(DB).all())
    except DatabaseError:
        logger.warning('Support database not ready')
        return None
