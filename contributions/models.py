"""Voluntary financial support received through the PayPal payment link (see docs/SYSTEM.md §7.7).

Amounts are Decimal and come only from PayPal (the IPN and the REST API) -- nothing is estimated: a value PayPal did
not send stays empty (shown as "not available"). Nothing personal about the supporter is kept: no name, e-mail,
address or card -- only the transaction, its amounts and the message the supporter chose to leave.
"""
from decimal import Decimal

from django.db import models

ZERO = Decimal('0.00')


class SupportContribution(models.Model):
    class PaymentStatus(models.TextChoices):
        COMPLETED = 'completed', 'הושלם'
        PENDING = 'pending', 'ממתין'
        DENIED = 'denied', 'נדחה'
        UNKNOWN = 'unknown', 'לא ידוע'

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'הושלם'
        PENDING = 'pending', 'ממתין'
        DENIED = 'denied', 'נדחה'
        PARTIALLY_REFUNDED = 'partially_refunded', 'הוחזר חלקית'
        REFUNDED = 'refunded', 'הוחזר במלואו'
        REVERSED = 'reversed', 'בוטל / מעוכב (מחלוקת)'
        UNKNOWN = 'unknown', 'לא ידוע'

    transaction_id = models.CharField('מזהה עסקה ב-PayPal', max_length=64, unique=True)
    order_id = models.CharField('מזהה הזמנה ב-PayPal', max_length=64, blank=True)
    source_item_id = models.CharField('מזהה קישור התשלום', max_length=64, blank=True)
    payment_status = models.CharField('סטטוס התשלום ב-PayPal', max_length=20, choices=PaymentStatus.choices,
                                      default=PaymentStatus.UNKNOWN)
    status = models.CharField('סטטוס', max_length=20, choices=Status.choices, default=Status.UNKNOWN, db_index=True)
    paid_at = models.DateTimeField('מועד התשלום', null=True, blank=True, db_index=True)
    currency = models.CharField('מטבע', max_length=3, blank=True)
    gross_amount = models.DecimalField('סכום ברוטו', max_digits=12, decimal_places=2, null=True, blank=True)
    fee_amount = models.DecimalField('עמלת PayPal', max_digits=12, decimal_places=2, null=True, blank=True)
    net_amount = models.DecimalField('סכום נטו', max_digits=12, decimal_places=2, null=True, blank=True)
    refunded_amount = models.DecimalField('סכום שהוחזר', max_digits=12, decimal_places=2, default=ZERO)
    refunded_fee = models.DecimalField('עמלה שהוחזרה בהחזרים', max_digits=12, decimal_places=2, default=ZERO)
    reversed_amount = models.DecimalField('סכום שבוטל / עוכב', max_digits=12, decimal_places=2, null=True, blank=True)
    dispute_case_id = models.CharField('מספר מחלוקת', max_length=64, blank=True)
    message = models.TextField('הודעת התומך', blank=True)
    seen = models.BooleanField('נצפתה', default=False, db_index=True)
    seen_at = models.DateTimeField('נצפתה בתאריך', null=True, blank=True)
    notified_at = models.DateTimeField('הודעת דוא"ל נשלחה', null=True, blank=True)
    notify_attempted_at = models.DateTimeField('ניסיון שליחה אחרון', null=True, blank=True)
    created_at = models.DateTimeField('נוצרה', auto_now_add=True)
    updated_at = models.DateTimeField('עודכנה', auto_now=True)

    class Meta:
        verbose_name = 'תמיכה כספית'
        verbose_name_plural = 'תמיכות כספיות'
        ordering = ['-paid_at', '-pk']

    def __str__(self):
        return f'{self.transaction_id} {self.gross_amount or ""} {self.currency}'

    @property
    def refund_net_impact(self):
        """What the refunds took from the balance: the amount refunded less the fee PayPal gave back."""
        return self.refunded_amount - self.refunded_fee

    @property
    def net_after_refunds(self):
        """Net after fees, refunds and an active reversal; None when PayPal did not report the net."""
        if self.net_amount is None:
            return None
        return self.net_amount - self.refund_net_impact - (self.reversed_amount or ZERO)

    def recompute_status(self):
        if self.reversed_amount:
            self.status = self.Status.REVERSED
        elif self.refunded_amount and self.gross_amount and self.refunded_amount >= self.gross_amount:
            self.status = self.Status.REFUNDED
        elif self.refunded_amount:
            self.status = self.Status.PARTIALLY_REFUNDED
        else:
            self.status = self.payment_status
        return self.status


class SupportEvent(models.Model):
    """One PayPal notification as received (no personal data). Its event_key makes a repeated notification -- PayPal's
    retries and resends -- a no-op: it is neither recorded nor e-mailed twice."""

    class Kind(models.TextChoices):
        PAYMENT = 'payment', 'תשלום'
        REFUND = 'refund', 'החזר'
        REVERSAL = 'reversal', 'ביטול / עיכוב'
        REVERSAL_CANCELED = 'reversal_canceled', 'ביטול העיכוב'
        DISPUTE = 'dispute', 'מחלוקת'
        OTHER = 'other', 'אחר'

    event_key = models.CharField('מפתח ייחודי', max_length=200, unique=True)
    kind = models.CharField('סוג', max_length=20, choices=Kind.choices)
    outcome = models.CharField('תוצאה', max_length=40, default='processed')
    transaction_id = models.CharField('מזהה עסקה', max_length=64, blank=True)
    parent_transaction_id = models.CharField('מזהה עסקת המקור', max_length=64, blank=True)
    txn_type = models.CharField(max_length=40, blank=True)
    payment_status = models.CharField(max_length=40, blank=True)
    case_id = models.CharField(max_length=64, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    test_ipn = models.BooleanField(default=False)
    contribution = models.ForeignKey(SupportContribution, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name='events')
    received_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField('הודעת דוא"ל נשלחה', null=True, blank=True)
    notify_attempted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'אירוע PayPal'
        verbose_name_plural = 'אירועי PayPal'
        ordering = ['-received_at']

    def __str__(self):
        return self.event_key
