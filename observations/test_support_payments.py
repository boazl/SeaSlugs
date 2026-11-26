"""Receiving voluntary support automatically: PayPal IPN -> SupportContribution (contributions app)."""
import urllib.parse
from decimal import Decimal
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from contributions import notify, paypal, processing, summary
from contributions.models import SupportContribution, SupportEvent
from contributions.router import SupportRouter

MERCHANT = 'SJDBY5WBCARSQ'
ITEM = 'A4CQ887BA48WQ'
CONFIG = dict(PAYPAL_WEBHOOK_ENABLED=True, PAYPAL_ENV='sandbox', PAYPAL_RECEIVER_ID=MERCHANT,
              PAYPAL_SUPPORT_ITEM_ID=ITEM, PAYPAL_CLIENT_ID='id', PAYPAL_CLIENT_SECRET='secret',
              SUPPORT_NOTIFICATION_EMAIL='owner@example.com', DEFAULT_FROM_EMAIL='site@example.com')


def ipn(**fields):
    """An IPN body like the ones PayPal sent in the Sandbox test (fake personal fields), windows-1255 encoded."""
    base = {'txn_type': 'cart', 'payment_status': 'Completed', 'txn_id': 'TXN-A', 'mc_gross': '100.00',
            'mc_fee': '4.60', 'mc_currency': 'ILS', 'receiver_id': MERCHANT, 'business': 'seller@example.com',
            'payer_email': 'payer@example.com', 'first_name': 'Payer', 'last_name': 'Person',
            'item_name1': 'Support the SeaSlugs Research Project', 'option_name1_1': 'Leave a message',
            'option_selection1_1': 'בהצלחה בפרויקט', 'payment_date': '07:10:05 Nov 25, 2026 PST',
            'test_ipn': '1', 'charset': 'windows-1255', 'ipn_track_id': 'track1', 'verify_sign': 'sig'}
    base.update(fields)
    return urllib.parse.urlencode({k: v for k, v in base.items() if v is not None}, encoding='windows-1255').encode()


def capture(txn='TXN-A', gross='100.00', fee='4.60', net='95.40', status='COMPLETED', payee=MERCHANT, order='ORD-A'):
    return {'id': txn, 'status': status, 'amount': {'currency_code': 'ILS', 'value': gross},
            'seller_receivable_breakdown': {'gross_amount': {'currency_code': 'ILS', 'value': gross},
                                            'paypal_fee': {'currency_code': 'ILS', 'value': fee},
                                            'net_amount': {'currency_code': 'ILS', 'value': net}},
            'payee': {'merchant_id': payee}, 'supplementary_data': {'related_ids': {'order_id': order}},
            'create_time': '2026-11-25T15:10:05Z'}


def order(order_id='ORD-A', item=ITEM, message='בהצלחה בפרויקט'):
    return {'id': order_id, 'purchase_units': [{'items': [{'item_id': item, 'name': 'Support',
            'item_option_selections': [{'name': 'Leave a message', 'select': message}]}]}]}


class PayPalMock:
    """verify_ipn / get_capture / get_order patched: captures and orders by id."""

    def __init__(self, test, verified=True):
        self.captures, self.orders = {}, {}
        for name, fn in (('verify_ipn', lambda raw: verified), ('get_capture', lambda t: self.captures.get(t)),
                         ('get_order', lambda o: self.orders.get(o))):
            patcher = mock.patch.object(paypal, name, side_effect=fn)
            setattr(self, name, patcher.start())
            test.addCleanup(patcher.stop)

    def add(self, txn='TXN-A', order_id='ORD-A', item=ITEM, **kw):
        self.captures[txn] = capture(txn=txn, order=order_id, **kw)
        self.orders[order_id] = order(order_id, item)


@override_settings(**CONFIG)
class SupportTestBase(TestCase):
    databases = {'default', 'support'}

    def setUp(self):
        self.pp = PayPalMock(self)
        self.pp.add()

    def post(self, body, client=None):
        return (client or self.client).post('/webhooks/paypal/', body, content_type='application/x-www-form-urlencoded')

    def contribution(self, txn='TXN-A'):
        return SupportContribution.objects.using('support').get(transaction_id=txn)


class IpnPaymentTests(SupportTestBase):
    """A verified, completed payment to the SeaSlugs account through the support link is saved once, with gross, fee
    and net from PayPal's API (Decimal), the supporter's Hebrew message (windows-1255) and the payment time, and the
    owner gets one e-mail "SeaSlugs – התקבלה תמיכה כספית חדשה" with the amounts, status, message and admin link."""

    def test_valid_payment(self):
        response = self.post(ipn())
        self.assertEqual(response.status_code, 200)
        c = self.contribution()
        self.assertEqual((c.gross_amount, c.fee_amount, c.net_amount), (Decimal('100.00'), Decimal('4.60'), Decimal('95.40')))
        self.assertEqual(c.currency, 'ILS')
        self.assertEqual(c.status, 'completed')
        self.assertEqual(c.message, 'בהצלחה בפרויקט')
        self.assertEqual(c.order_id, 'ORD-A')
        self.assertEqual(c.source_item_id, ITEM)
        self.assertEqual(c.paid_at.isoformat(), '2026-11-25T15:10:05+00:00')
        self.assertFalse(c.seen)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, 'SeaSlugs – התקבלה תמיכה כספית חדשה')
        self.assertEqual(message.to, ['owner@example.com'])
        for text in ('100.00', 'ILS', '4.60', '95.40', 'הושלם', 'בהצלחה בפרויקט', '/admin/support/', 'TXN-A'):
            self.assertIn(text, message.body)
        self.assertIsNotNone(c.notified_at)

    def test_csrf_is_not_required(self):
        self.assertEqual(self.post(ipn(), client=Client(enforce_csrf_checks=True)).status_code, 200)

    def test_get_is_refused(self):
        self.assertEqual(self.client.get('/webhooks/paypal/').status_code, 405)

    def test_nothing_personal_is_kept(self):
        self.post(ipn())
        stored = [str(v) for row in SupportContribution.objects.using('support').values() for v in row.values()]
        stored += [str(v) for row in SupportEvent.objects.using('support').values() for v in row.values()]
        for personal in ('payer@example.com', 'seller@example.com', 'Payer', 'Person', 'sig'):
            self.assertNotIn(personal, stored)


class IpnRejectionTests(SupportTestBase):
    """Only what PayPal confirms, for this account, environment and support link, is kept: an unconfirmed message
    is refused (400) and an unreachable PayPal or a missing setting asks PayPal to retry (502 / 503) -- nothing saved;
    a genuine message for another account, item or environment is acknowledged (200) and ignored."""

    def assertNothingSaved(self):
        self.assertFalse(SupportContribution.objects.using('support').exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_invalid_signature(self):
        self.pp.verify_ipn.side_effect = lambda raw: False
        self.assertEqual(self.post(ipn()).status_code, 400)
        self.assertNothingSaved()
        self.assertFalse(SupportEvent.objects.using('support').exists())

    def test_paypal_unreachable(self):
        self.pp.verify_ipn.side_effect = paypal.PayPalUnavailable('timeout')
        self.assertEqual(self.post(ipn()).status_code, 502)
        self.assertNothingSaved()

    def test_api_unreachable_saves_nothing_so_paypal_retries(self):
        self.pp.get_capture.side_effect = paypal.PayPalUnavailable('timeout')
        self.assertEqual(self.post(ipn()).status_code, 502)
        self.assertNothingSaved()
        self.assertFalse(SupportEvent.objects.using('support').exists())

    def test_other_receiver(self):
        self.assertEqual(self.post(ipn(receiver_id='SOMEONEELSE')).status_code, 200)
        self.assertNothingSaved()
        self.assertTrue(SupportEvent.objects.using('support').get().outcome.startswith('ignored'))

    def test_capture_of_another_payee(self):
        self.pp.add(payee='SOMEONEELSE')
        self.assertEqual(self.post(ipn()).status_code, 200)
        self.assertNothingSaved()

    def test_other_item_is_not_the_support_activity(self):
        self.pp.add(item='OTHERLINK')
        self.assertEqual(self.post(ipn()).status_code, 200)
        self.assertNothingSaved()

    def test_unknown_capture(self):
        self.pp.captures.clear()
        self.assertEqual(self.post(ipn()).status_code, 200)
        self.assertNothingSaved()

    @override_settings(PAYPAL_ENV='live')
    def test_sandbox_message_on_the_live_site(self):
        self.assertEqual(self.post(ipn(test_ipn='1')).status_code, 200)
        self.assertNothingSaved()

    @override_settings(PAYPAL_WEBHOOK_ENABLED=False)
    def test_disabled(self):
        self.assertEqual(self.post(ipn()).status_code, 503)
        self.assertNothingSaved()
        self.pp.verify_ipn.assert_not_called()

    @override_settings(PAYPAL_RECEIVER_ID='')
    def test_missing_receiver_setting(self):
        self.assertEqual(self.post(ipn()).status_code, 503)
        self.assertNothingSaved()

    def test_missing_api_credentials(self):
        self.pp.get_capture.side_effect = paypal.PayPalNotConfigured('PAYPAL_CLIENT_ID')
        self.assertEqual(self.post(ipn()).status_code, 503)
        self.assertNothingSaved()

    def test_empty_or_huge_body(self):
        self.assertEqual(self.post(b'').status_code, 400)
        self.assertEqual(self.post(b'a=' + b'x' * 40000).status_code, 400)


class IpnDuplicateAndOrderTests(SupportTestBase):
    """A message PayPal sends again (retry or resend: same type, status, transaction and case) changes nothing and
    sends no second e-mail; messages may arrive in any order -- a refund before its payment creates the contribution
    from the API, and the later payment message completes it without a duplicate."""

    def test_same_message_twice(self):
        body = ipn()
        self.post(body)
        self.assertEqual(self.post(body).status_code, 200)
        self.assertEqual(SupportContribution.objects.using('support').count(), 1)
        self.assertEqual(SupportEvent.objects.using('support').count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_resend_flag_is_still_a_duplicate(self):
        self.post(ipn())
        self.post(ipn(resend='true', ipn_track_id='other'))
        self.assertEqual(SupportEvent.objects.using('support').count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_refund_before_payment(self):
        self.post(ipn(payment_status='Refunded', txn_id='REF-1', parent_txn_id='TXN-A', mc_gross='-30.00',
                      mc_fee='-1.02', txn_type=None, reason_code='refund'))
        c = self.contribution()
        self.assertEqual(c.status, 'partially_refunded')
        self.post(ipn())
        c = self.contribution()
        self.assertEqual(SupportContribution.objects.using('support').count(), 1)
        self.assertEqual(c.status, 'partially_refunded')
        self.assertEqual(c.refunded_amount, Decimal('30.00'))


class IpnRefundReversalTests(SupportTestBase):
    """Refunds (full or partial, PayPal status Refunded linked by parent_txn_id) and reversals (status Reversed,
    e.g. a dispute; Canceled_Reversal undoes it) update the contribution and its net, and each sends the owner an
    e-mail; a dispute (new_case) records its case number."""

    def setUp(self):
        super().setUp()
        self.post(ipn())
        mail.outbox.clear()

    def test_partial_refund(self):
        self.post(ipn(payment_status='Refunded', txn_id='REF-1', parent_txn_id='TXN-A', mc_gross='-30.00',
                      mc_fee='-1.02', txn_type=None, reason_code='refund'))
        c = self.contribution()
        self.assertEqual(c.status, 'partially_refunded')
        self.assertEqual((c.refunded_amount, c.refunded_fee), (Decimal('30.00'), Decimal('1.02')))
        self.assertEqual(c.net_after_refunds, Decimal('66.42'))
        self.assertEqual(mail.outbox[0].subject, 'SeaSlugs – החזר כספי של תמיכה')
        self.assertIn('החזר חלקי', mail.outbox[0].body)

    def test_full_refund(self):
        self.post(ipn(payment_status='Refunded', txn_id='REF-2', parent_txn_id='TXN-A', mc_gross='-100.00',
                      mc_fee='-4.60', txn_type=None))
        c = self.contribution()
        self.assertEqual(c.status, 'refunded')
        self.assertEqual(c.net_after_refunds, Decimal('0.00'))
        self.assertIn('החזר מלא', mail.outbox[0].body)

    def test_reversal_dispute_and_cancel(self):
        self.post(ipn(payment_status='Reversed', txn_id='REV-1', parent_txn_id='TXN-A', mc_gross='-95.40',
                      mc_fee='-4.60', txn_type=None, reason_code='other'))
        c = self.contribution()
        self.assertEqual(c.status, 'reversed')
        self.assertEqual(c.net_after_refunds, Decimal('0.00'))
        self.assertEqual(mail.outbox[0].subject, 'SeaSlugs – ביטול או עיכוב של תמיכה כספית')
        self.post(ipn(txn_type='new_case', payment_status=None, case_id='PP-R-1', case_type='dispute',
                      reason_code='non_receipt', mc_gross=None, mc_fee=None))
        self.assertEqual(self.contribution().dispute_case_id, 'PP-R-1')
        self.post(ipn(payment_status='Canceled_Reversal', txn_id='CR-1', parent_txn_id='TXN-A', mc_gross='95.40',
                      mc_fee='4.60', txn_type=None))
        c = self.contribution()
        self.assertEqual(c.status, 'completed')
        self.assertEqual(c.net_after_refunds, Decimal('95.40'))
        self.assertEqual(len(mail.outbox), 1)


class NotificationFailureTests(SupportTestBase):
    """A failed e-mail never loses the payment: the record stays, the e-mail stays pending and is retried (later
    messages, the admin page, the management command) -- sent once, never twice."""

    def test_mail_failure_then_retry(self):
        with mock.patch('contributions.notify.send_mail', side_effect=OSError('smtp down')):
            self.assertEqual(self.post(ipn()).status_code, 200)
        c = self.contribution()
        self.assertIsNone(c.notified_at)
        self.assertIsNotNone(c.notify_attempted_at)
        self.assertEqual(notify.retry_pending(), 0)          # attempted moments ago: not again yet
        SupportContribution.objects.using('support').update(notify_attempted_at=timezone.now() - notify.RETRY_GAP * 2)
        self.assertEqual(notify.retry_pending(), 1)
        self.assertEqual(notify.retry_pending(), 0)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(SUPPORT_NOTIFICATION_EMAIL='')
    def test_no_address_keeps_it_pending(self):
        self.post(ipn())
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(notify.pending_contributions().count(), 1)

    def test_management_command(self):
        from django.core.management import call_command
        with mock.patch('contributions.notify.send_mail', side_effect=OSError('smtp down')):
            self.post(ipn())
        SupportContribution.objects.using('support').update(notify_attempted_at=None)
        call_command('support_retry_notifications', verbosity=0)
        self.assertEqual(len(mail.outbox), 1)


class TotalsTests(SupportTestBase):
    """Totals are per currency and over completed payments: gross, fees (less fees returned), refunds and net after
    fees, refunds and reversals; a missing fee is counted apart, never guessed."""

    def make(self, txn, currency='ILS', gross='100.00', fee='4.60', net='95.40', **kw):
        return SupportContribution.objects.using('support').create(
            transaction_id=txn, currency=currency, gross_amount=Decimal(gross), fee_amount=Decimal(fee) if fee else None,
            net_amount=Decimal(net) if net else None, payment_status='completed', status='completed',
            paid_at=timezone.now(), **kw)

    def test_totals(self):
        self.make('A')
        self.make('B', gross='70.00', fee='3.58', net='66.42', refunded_amount=Decimal('70.00'), refunded_fee=Decimal('3.58'))
        self.make('C', currency='USD', gross='10.00', fee=None, net=None)
        t = summary.totals(SupportContribution.objects.using('support').all())
        self.assertEqual(list(t), ['ILS', 'USD'])
        self.assertEqual(t['ILS']['count'], 2)
        self.assertEqual(t['ILS']['gross'], Decimal('170.00'))
        self.assertEqual(t['ILS']['fees'], Decimal('4.60'))
        self.assertEqual(t['ILS']['refunds'], Decimal('70.00'))
        self.assertEqual(t['ILS']['net'], Decimal('95.40'))
        self.assertEqual(t['USD']['missing'], 1)
        self.assertEqual(t['USD']['net'], Decimal('0.00'))

    def test_pending_not_counted(self):
        self.make('A')
        SupportContribution.objects.using('support').create(transaction_id='P', currency='ILS', gross_amount=Decimal('5'),
                                                            payment_status='pending', status='pending')
        self.assertEqual(summary.totals(SupportContribution.objects.using('support').all())['ILS']['count'], 1)

    def test_monthly_and_yearly(self):
        self.make('A')
        self.assertEqual(len(summary.by_period(SupportContribution.objects.using('support').all(), 'month')), 1)
        self.assertEqual(len(summary.by_period(SupportContribution.objects.using('support').all(), 'year')), 1)


class OwnerOnlyTests(SupportTestBase):
    """Financial data is for the owner (superuser) only, checked on the server: the news page section, the menu
    count and /admin/support/ (anonymous -> login, staff or member -> 403); opening a page never marks anything
    seen -- only the owner's explicit "seen" / "all seen"; the CSV export opens in Excel with Hebrew (UTF-8 BOM)."""

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.owner = User.objects.create_superuser('owner', password='pw')
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True)
        self.member = User.objects.create_user('member', password='pw')
        self.post(ipn())

    def test_news_section_owner_only(self):
        self.assertNotIn('id="support"', self.client.get('/news/').content.decode())
        for user in (self.member, self.staff):
            self.client.force_login(user)
            self.assertNotIn('id="support"', self.client.get('/news/').content.decode())
        self.client.force_login(self.owner)
        html = self.client.get('/news/').content.decode()
        self.assertIn('id="support"', html)
        self.assertIn('בהצלחה בפרויקט', html)
        self.assertIn('100.00', html)
        self.assertFalse(self.contribution().seen)

    @override_settings(PAYPAL_WEBHOOK_ENABLED=False)
    def test_news_section_hidden_while_off(self):
        self.client.force_login(self.owner)
        self.assertNotIn('id="support"', self.client.get('/news/').content.decode())

    def test_menu_count(self):
        self.client.force_login(self.owner)
        html = self.client.get('/forum/').content.decode()
        self.assertIn('class="nav-count"', html)
        self.assertIn('href="/admin/support/"', html)
        self.client.force_login(self.staff)
        self.assertNotIn('class="nav-count"', self.client.get('/forum/').content.decode())

    def test_admin_page_access(self):
        self.assertEqual(self.client.get('/admin/support/').status_code, 302)
        self.client.force_login(self.member)
        self.assertEqual(self.client.get('/admin/support/').status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get('/admin/support/').status_code, 403)
        self.assertEqual(self.client.get('/admin/support/?format=csv').status_code, 403)
        self.assertEqual(self.client.post('/admin/support/', {'action': 'seen_all'}).status_code, 403)
        self.assertFalse(self.contribution().seen)
        self.client.force_login(self.owner)
        response = self.client.get('/admin/support/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('TXN-A', html)
        self.assertIn('בהצלחה בפרויקט', html)
        self.assertNotIn('googletagmanager.com/gtag/js', html)
        self.assertNotIn('href="/support/"', html)

    def test_filters_and_sorting(self):
        self.pp.add(txn='TXN-B', order_id='ORD-B', gross='20.00', fee='1.88', net='18.12')
        self.post(ipn(txn_id='TXN-B', mc_gross='20.00'))
        self.client.force_login(self.owner)
        html = self.client.get('/admin/support/?sort=amount').content.decode()
        self.assertLess(html.index('TXN-B'), html.index('TXN-A'))
        html = self.client.get('/admin/support/?status=refunded').content.decode()
        self.assertNotIn('TXN-A</td>', html.replace('\n', ''))
        processing.mark_seen(SupportContribution.objects.using('support').filter(transaction_id='TXN-A'))
        html = self.client.get('/admin/support/?new=1').content.decode()
        self.assertIn('TXN-B', html)
        self.assertNotIn('>TXN-A', html)
        html = self.client.get('/admin/support/?from=2030-01-01').content.decode()
        self.assertNotIn('>TXN-B', html)

    def test_mark_seen(self):
        self.client.force_login(self.owner)
        c = self.contribution()
        self.client.get('/admin/support/')
        self.assertFalse(self.contribution().seen)
        self.client.post('/admin/support/', {'action': 'seen', 'pk': c.pk})
        self.assertTrue(self.contribution().seen)
        self.pp.add(txn='TXN-B', order_id='ORD-B')
        self.post(ipn(txn_id='TXN-B'))
        self.client.post('/admin/support/', {'action': 'seen_all', 'next': '/news/#support'})
        self.assertFalse(SupportContribution.objects.using('support').filter(seen=False).exists())

    def test_csv(self):
        self.client.force_login(self.owner)
        response = self.client.get('/admin/support/?format=csv')
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        body = response.content.decode('utf-8')
        self.assertTrue(body.startswith('﻿'))
        self.assertIn('מזהה עסקה', body)
        self.assertIn('TXN-A', body)
        self.assertIn('95.40', body)
        self.assertIn('בהצלחה בפרויקט', body)


class StorageSeparationTests(TestCase):
    """Support data lives in its own database (support.sqlite3): the router sends the contributions app there and
    nothing else; start.sh backs it up and migrates it; a full database replacement ignores its migrations."""
    databases = {'default', 'support'}

    def test_router(self):
        router = SupportRouter()
        self.assertEqual(router.db_for_write(SupportContribution), 'support')
        self.assertIsNone(router.db_for_write(get_user_model()))
        self.assertTrue(router.allow_migrate('support', 'contributions'))
        self.assertFalse(router.allow_migrate('default', 'contributions'))
        self.assertFalse(router.allow_migrate('support', 'observations'))
        self.assertTrue(str(settings.DATABASES['support']['NAME']).endswith('support.sqlite3') or settings.DATABASES['support']['NAME'])

    def test_start_script(self):
        script = (settings.BASE_DIR / 'start.sh').read_text()
        self.assertIn('python manage.py migrate --database support --noinput', script)
        self.assertIn('support-before-deploy-', script)

    def test_db_replace_ignores_contributions_migrations(self):
        import sqlite3, tempfile
        from django.db.migrations.loader import MigrationLoader
        from observations.db_replace import migration_mismatch
        expected = {m for m in MigrationLoader(None, ignore_no_migrations=True).disk_migrations if m[0] != 'contributions'}
        with tempfile.NamedTemporaryFile(suffix='.sqlite3') as f:
            conn = sqlite3.connect(f.name)
            conn.execute('CREATE TABLE django_migrations (id integer primary key, app text, name text, applied text)')
            conn.executemany('INSERT INTO django_migrations (app, name, applied) VALUES (?, ?, "")', sorted(expected))
            conn.commit(); conn.close()
            self.assertIsNone(migration_mismatch(f.name))

    def test_robots_keeps_crawlers_out(self):
        self.assertIn('Disallow: /webhooks/', self.client.get('/robots.txt').content.decode())


class ParsingTests(TestCase):
    """The IPN is decoded with the charset PayPal names (windows-1255 for Hebrew); PayPal's Pacific-time date parses;
    the event key is type + status + transaction + case (ipn_track_id is not unique, so it is not used)."""

    def test_charset(self):
        self.assertEqual(processing.ipn_message(processing.parse_ipn(ipn())), 'בהצלחה בפרויקט')
        utf8 = urllib.parse.urlencode({'charset': 'UTF-8', 'option_name1_1': 'Leave a message',
                                       'option_selection1_1': 'תודה'}).encode()
        self.assertEqual(processing.ipn_message(processing.parse_ipn(utf8)), 'תודה')

    def test_date(self):
        self.assertEqual(processing.ipn_date('07:10:05 Nov 25, 2026 PST').isoformat(), '2026-11-25T07:10:05-08:00')
        self.assertIsNone(processing.ipn_date('nonsense'))

    def test_event_key(self):
        a = processing.event_key(processing.parse_ipn(ipn()))
        b = processing.event_key(processing.parse_ipn(ipn(ipn_track_id='other')))
        self.assertEqual(a, b)
        self.assertNotEqual(a, processing.event_key(processing.parse_ipn(ipn(payment_status='Refunded'))))


@override_settings(**CONFIG)
class SupportDatabaseNotReadyTests(TestCase):
    """Before `migrate --database support` has run, the owner's pages keep working (no count, no section)."""
    databases = {'default', 'support'}

    def test_pages_survive(self):
        from django.db import DatabaseError
        self.client.force_login(get_user_model().objects.create_superuser('owner', password='pw'))
        with mock.patch('contributions.views.summary.news_summary', side_effect=DatabaseError('no such table')), \
                mock.patch.object(SupportContribution.objects, 'using', side_effect=DatabaseError('no such table')):
            response = self.client.get('/news/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('id="support"', response.content.decode())
