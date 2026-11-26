"""Totals for the owner: always per currency (a future payment in another currency is summed apart), counting only
payments that completed. Refunds subtract what they took from the balance (refund less returned fee); a reversal
subtracts what PayPal reversed. A fee or net PayPal did not report is left out and the total says so."""
from collections import OrderedDict
from decimal import Decimal

from django.utils import timezone

from .models import SupportContribution

ZERO = Decimal('0.00')
COUNTED = [SupportContribution.Status.COMPLETED, SupportContribution.Status.PARTIALLY_REFUNDED,
           SupportContribution.Status.REFUNDED, SupportContribution.Status.REVERSED]


def counted(queryset):
    return queryset.filter(payment_status=SupportContribution.PaymentStatus.COMPLETED)


def totals(contributions):
    """{currency: {'count', 'gross', 'fees', 'refunds', 'reversed', 'net', 'missing'}} over completed payments."""
    out = OrderedDict()
    for c in contributions:
        if c.payment_status != SupportContribution.PaymentStatus.COMPLETED:
            continue
        t = out.setdefault(c.currency or '?', {'count': 0, 'gross': ZERO, 'fees': ZERO, 'refunds': ZERO,
                                                'reversed': ZERO, 'net': ZERO, 'missing': 0})
        t['count'] += 1
        t['gross'] += c.gross_amount or ZERO
        t['refunds'] += c.refunded_amount
        t['reversed'] += c.reversed_amount or ZERO
        if c.fee_amount is None or c.net_after_refunds is None:
            t['missing'] += 1
        else:
            t['fees'] += c.fee_amount - c.refunded_fee
            t['net'] += c.net_after_refunds
    return OrderedDict(sorted(out.items()))


def by_period(contributions, period):
    """[(label, totals)] newest first; period 'month' (MM/YYYY) or 'year'."""
    groups = OrderedDict()
    for c in sorted(contributions, key=lambda c: c.paid_at or c.created_at, reverse=True):
        when = timezone.localtime(c.paid_at or c.created_at)
        label = f'{when:%m/%Y}' if period == 'month' else f'{when:%Y}'
        groups.setdefault(label, []).append(c)
    return [(label, totals(items)) for label, items in groups.items()]


def news_summary(queryset):
    """The figures for the news page's manager section."""
    items = list(queryset)
    now = timezone.localtime()
    this_month = [c for c in items if c.paid_at and timezone.localtime(c.paid_at).strftime('%Y%m') == now.strftime('%Y%m')]
    completed = [c for c in items if c.payment_status == SupportContribution.PaymentStatus.COMPLETED]
    return {
        'unseen': sum(1 for c in completed if not c.seen),
        'count': len(completed),
        'totals': totals(items),
        'month_totals': totals(this_month),
        'last_paid_at': max((c.paid_at for c in completed if c.paid_at), default=None),
        'recent': sorted(completed, key=lambda c: c.paid_at or c.created_at, reverse=True)[:5],
    }
