"""Turning a verified PayPal IPN message into SupportContribution / SupportEvent rows.

Rules (docs/SYSTEM.md §7.7, test_support_payments.py):
* Only a message PayPal confirms (VERIFIED) is processed, only for the SeaSlugs account (receiver_id =
  PAYPAL_RECEIVER_ID) and the configured environment (test_ipn only in sandbox).
* A payment belongs to the support project only if PayPal's REST API confirms it: the capture exists for this account
  (payee = PAYPAL_RECEIVER_ID) and its order's item is the support payment link (PAYPAL_SUPPORT_ITEM_ID).
  Amounts, fee and net come from the API (the IPN's own values only where the API has none).
* Each message has an event key (type + status + transaction + case): a message seen before changes nothing.
* Order does not matter: a refund, reversal or dispute that arrives before its payment creates the contribution
  from the API first.
"""
import logging
import re
import urllib.parse
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from . import paypal
from .models import SupportContribution, SupportEvent

logger = logging.getLogger(__name__)
DB = 'support'
MESSAGE_OPTION = 'leave a message'
MAX_MESSAGE = 2000


class NotOurs(Exception):
    """The message is genuine but does not belong to the support project (other account, environment or item)."""


def parse_ipn(raw_body):
    """The IPN form as a dict of str, decoded with the charset PayPal names in it (windows-1255 for Hebrew)."""
    probe = urllib.parse.parse_qs(raw_body.decode('latin-1'), keep_blank_values=True)
    charset = (probe.get('charset') or ['utf-8'])[0] or 'utf-8'
    try:
        ''.encode(charset)
    except LookupError:
        charset = 'utf-8'
    fields = urllib.parse.parse_qs(raw_body.decode('ascii', errors='replace'), keep_blank_values=True,
                                   encoding=charset, errors='replace')
    return {k: v[0] for k, v in fields.items()}


def money(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None


def ipn_date(value):
    """'07:10:05 Nov 25, 2026 PST' (PayPal's Pacific time) -> aware datetime; None if it does not parse."""
    match = re.match(r'(\d{2}:\d{2}:\d{2}) (\w{3}) (\d{1,2}), (\d{4})', value or '')
    if not match:
        return None
    try:
        naive = datetime.strptime(' '.join(match.groups()), '%H:%M:%S %b %d %Y')
    except ValueError:
        return None
    return naive.replace(tzinfo=ZoneInfo('America/Los_Angeles'))


def ipn_message(fields):
    """The supporter's message: the cart option named "Leave a message" (option_name1_1 / option_selection1_1 ...)."""
    for key, name in fields.items():
        match = re.fullmatch(r'option_name(\d+)_(\d+)', key)
        if match and name.strip().lower() == MESSAGE_OPTION:
            return fields.get(f'option_selection{match.group(1)}_{match.group(2)}', '').strip()[:MAX_MESSAGE]
    for key in ('option_selection1', 'memo'):
        if fields.get(key):
            return fields[key].strip()[:MAX_MESSAGE]
    return ''


def support_item_id():
    configured = getattr(settings, 'PAYPAL_SUPPORT_ITEM_ID', '')
    if configured:
        return configured
    url = getattr(settings, 'PAYPAL_SUPPORT_URL', '') or ''
    return url.rstrip('/').rsplit('/', 1)[-1] if '/ncp/payment/' in url else ''


def classify(fields):
    status = fields.get('payment_status', '')
    txn_type = fields.get('txn_type', '')
    if txn_type in ('new_case', 'adjustment') or fields.get('case_id'):
        return SupportEvent.Kind.DISPUTE
    if status == 'Refunded':
        return SupportEvent.Kind.REFUND
    if status == 'Reversed':
        return SupportEvent.Kind.REVERSAL
    if status == 'Canceled_Reversal':
        return SupportEvent.Kind.REVERSAL_CANCELED
    if status in ('Completed', 'Pending', 'Denied', 'Failed', 'Processed') and not fields.get('parent_txn_id'):
        return SupportEvent.Kind.PAYMENT
    return SupportEvent.Kind.OTHER


def event_key(fields):
    return '|'.join((fields.get('txn_type', ''), fields.get('payment_status', ''), fields.get('txn_id', ''),
                     fields.get('case_id', '')))[:200]


def check_account(fields):
    receiver = getattr(settings, 'PAYPAL_RECEIVER_ID', '')
    if not receiver:
        raise paypal.PayPalNotConfigured('PAYPAL_RECEIVER_ID')
    if fields.get('receiver_id') != receiver:
        raise NotOurs('receiver')
    if (fields.get('test_ipn') == '1') != paypal.is_sandbox():
        raise NotOurs('environment')


def load_from_api(transaction_id):
    """(capture, order) from the REST API after checking they belong to this account and the support link."""
    capture = paypal.get_capture(transaction_id)
    if not capture:
        raise NotOurs('capture not found')
    if (capture.get('payee') or {}).get('merchant_id') != settings.PAYPAL_RECEIVER_ID:
        raise NotOurs('payee')
    order_id = ((capture.get('supplementary_data') or {}).get('related_ids') or {}).get('order_id', '')
    order = paypal.get_order(order_id) if order_id else None
    items = [item for unit in (order or {}).get('purchase_units', []) for item in unit.get('items', [])]
    expected = support_item_id()
    if not expected or not any(item.get('item_id') == expected for item in items):
        raise NotOurs('item')
    return capture, order


def fill_from_api(contribution, capture, order):
    breakdown = capture.get('seller_receivable_breakdown') or {}
    amount = capture.get('amount') or {}
    contribution.currency = amount.get('currency_code') or contribution.currency
    contribution.gross_amount = money(amount.get('value')) if amount.get('value') else contribution.gross_amount
    if (breakdown.get('paypal_fee') or {}).get('value') is not None:
        contribution.fee_amount = money(breakdown['paypal_fee']['value'])
    if (breakdown.get('net_amount') or {}).get('value') is not None:
        contribution.net_amount = money(breakdown['net_amount']['value'])
    contribution.paid_at = parse_datetime(capture.get('create_time') or '') or contribution.paid_at
    contribution.order_id = (order or {}).get('id', contribution.order_id)
    contribution.source_item_id = support_item_id()
    api_status = capture.get('status', '')
    if api_status in ('COMPLETED', 'PARTIALLY_REFUNDED', 'REFUNDED'):
        contribution.payment_status = SupportContribution.PaymentStatus.COMPLETED
    elif api_status == 'PENDING':
        contribution.payment_status = SupportContribution.PaymentStatus.PENDING
    elif api_status in ('DECLINED', 'FAILED'):
        contribution.payment_status = SupportContribution.PaymentStatus.DENIED
    if not contribution.message:
        for unit in (order or {}).get('purchase_units', []):
            for item in unit.get('items', []):
                for option in item.get('item_option_selections', []) or []:
                    if (option.get('name') or '').strip().lower() == MESSAGE_OPTION:
                        contribution.message = (option.get('select') or '').strip()[:MAX_MESSAGE]


def ensure_contribution(transaction_id):
    """The contribution for a payment transaction, created from the API when this is the first message about it."""
    existing = SupportContribution.objects.using(DB).filter(transaction_id=transaction_id).first()
    if existing:
        return existing
    capture, order = load_from_api(transaction_id)
    contribution = SupportContribution(transaction_id=transaction_id)
    fill_from_api(contribution, capture, order)
    contribution.recompute_status()
    contribution.save(using=DB)
    return contribution


def process(raw_body):
    """Process one IPN body that PayPal has already VERIFIED. Returns (outcome, event or None).
    Raises PayPalUnavailable / PayPalNotConfigured when the message must be retried later (nothing is saved then)."""
    fields = parse_ipn(raw_body)
    key = event_key(fields)
    if SupportEvent.objects.using(DB).filter(event_key=key).exists():
        return 'duplicate', None
    kind = classify(fields)
    event = SupportEvent(
        event_key=key, kind=kind, transaction_id=fields.get('txn_id', '')[:64],
        parent_transaction_id=fields.get('parent_txn_id', '')[:64], txn_type=fields.get('txn_type', '')[:40],
        payment_status=fields.get('payment_status', '')[:40], case_id=fields.get('case_id', '')[:64],
        amount=money(fields.get('mc_gross')), fee=money(fields.get('mc_fee')),
        currency=fields.get('mc_currency', '')[:3], test_ipn=fields.get('test_ipn') == '1')
    try:
        check_account(fields)
        if kind == SupportEvent.Kind.OTHER:
            raise NotOurs('unhandled type')
        payment_txn = event.transaction_id if kind == SupportEvent.Kind.PAYMENT else (
            event.parent_transaction_id or event.transaction_id)
        if not payment_txn:
            raise NotOurs('no transaction')
        contribution = ensure_contribution(payment_txn)
    except NotOurs as reason:
        event.outcome = f'ignored: {reason}'[:40]
        with transaction.atomic(using=DB):
            event.save(using=DB)
        logger.warning('PayPal IPN ignored (%s), event %s', reason, kind)
        return 'ignored', event

    with transaction.atomic(using=DB):
        contribution = SupportContribution.objects.using(DB).select_for_update().get(pk=contribution.pk)
        if kind == SupportEvent.Kind.PAYMENT:
            status = fields.get('payment_status')
            if status == 'Completed':
                contribution.payment_status = SupportContribution.PaymentStatus.COMPLETED
            elif status == 'Pending':
                contribution.payment_status = SupportContribution.PaymentStatus.PENDING
            elif status in ('Denied', 'Failed'):
                contribution.payment_status = SupportContribution.PaymentStatus.DENIED
            if contribution.fee_amount is None and event.fee is not None:
                contribution.fee_amount = event.fee
            if contribution.gross_amount is None and event.amount is not None:
                contribution.gross_amount = event.amount
                contribution.currency = contribution.currency or event.currency
            if contribution.net_amount is None and contribution.gross_amount is not None and contribution.fee_amount is not None:
                contribution.net_amount = contribution.gross_amount - contribution.fee_amount
            contribution.paid_at = contribution.paid_at or ipn_date(fields.get('payment_date'))
            contribution.message = ipn_message(fields) or contribution.message
        elif kind == SupportEvent.Kind.REFUND:
            contribution.refunded_amount += abs(event.amount or 0)
            contribution.refunded_fee += abs(event.fee or 0)
        elif kind == SupportEvent.Kind.REVERSAL:
            contribution.reversed_amount = abs(event.amount or 0) or None
        elif kind == SupportEvent.Kind.REVERSAL_CANCELED:
            contribution.reversed_amount = None
        elif kind == SupportEvent.Kind.DISPUTE:
            contribution.dispute_case_id = event.case_id or contribution.dispute_case_id
        if kind != SupportEvent.Kind.PAYMENT and not contribution.message:
            contribution.message = ipn_message(fields)
        contribution.recompute_status()
        contribution.save(using=DB)
        event.contribution = contribution
        event.save(using=DB)
    return 'processed', event


def mark_seen(queryset):
    return queryset.filter(seen=False).update(seen=True, seen_at=timezone.now())
