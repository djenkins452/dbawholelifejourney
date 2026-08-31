# ==============================================================================
# File: apps/finance/models_recurring.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Recurring series — bills, subscriptions, income, debt payments.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What comes back, how often, and how sure WLJ is about it.

Recurrence is the difference between "you spent $14,000 last month" and "you have
$4,400 of commitments before you decide anything". Nearly every useful financial
answer — free cash flow, what can be cancelled, whether an extra debt payment is
affordable — needs it.

**A candidate is not an obligation.** Detection proposes; the person disposes. A
detected series starts as `candidate` and enters no forward-looking total until it is
confirmed, because a wrong bill in a cash-flow forecast is worse than a missing one:
the missing one shows up as an obvious gap, the wrong one silently makes the plan
unachievable.

**Variable is a first-class answer.** A utility bill that lands between $80 and $210 is
not badly detected — it is a variable obligation, and forcing a single expected amount
onto it would be a fabricated number in the one place a household actually plans from.
"""
from decimal import Decimal

from django.db import models

from apps.core.models import UserOwnedModel


class RecurringSeries(UserOwnedModel):
    """A repeating money movement, detected or declared."""

    # -- what kind of commitment -------------------------------------------
    KIND_BILL = 'bill'
    KIND_SUBSCRIPTION = 'subscription'
    KIND_INCOME = 'income'
    KIND_DEBT_PAYMENT = 'debt_payment'
    KIND_TRANSFER = 'transfer'
    KIND_SAVINGS = 'savings_allocation'
    KIND_OTHER = 'other'
    KIND_CHOICES = [
        (KIND_BILL, 'Bill'),
        (KIND_SUBSCRIPTION, 'Subscription'),
        (KIND_INCOME, 'Recurring income'),
        (KIND_DEBT_PAYMENT, 'Debt payment'),
        (KIND_TRANSFER, 'Transfer'),
        (KIND_SAVINGS, 'Savings allocation'),
        (KIND_OTHER, 'Other'),
    ]
    #: Kinds that are a COST the household must fund. A transfer and a savings
    #: allocation recur too, and counting them as bills would double-count money
    #: that is only moving.
    OBLIGATION_KINDS = frozenset({KIND_BILL, KIND_SUBSCRIPTION, KIND_DEBT_PAYMENT})

    # -- how often ---------------------------------------------------------
    FREQ_WEEKLY = 'weekly'
    FREQ_BIWEEKLY = 'biweekly'
    FREQ_SEMIMONTHLY = 'semimonthly'
    FREQ_MONTHLY = 'monthly'
    FREQ_QUARTERLY = 'quarterly'
    FREQ_SEMIANNUAL = 'semiannual'
    FREQ_ANNUAL = 'annual'
    FREQ_IRREGULAR = 'irregular'
    FREQ_CHOICES = [
        (FREQ_WEEKLY, 'Weekly'), (FREQ_BIWEEKLY, 'Every two weeks'),
        (FREQ_SEMIMONTHLY, 'Twice a month'), (FREQ_MONTHLY, 'Monthly'),
        (FREQ_QUARTERLY, 'Quarterly'), (FREQ_SEMIANNUAL, 'Twice a year'),
        (FREQ_ANNUAL, 'Annually'),
        (FREQ_IRREGULAR, 'Irregular — predictable, but not on a schedule'),
    ]
    #: Occurrences per year, for putting everything on a comparable monthly footing.
    PER_YEAR = {
        FREQ_WEEKLY: Decimal("52"), FREQ_BIWEEKLY: Decimal("26"),
        FREQ_SEMIMONTHLY: Decimal("24"), FREQ_MONTHLY: Decimal("12"),
        FREQ_QUARTERLY: Decimal("4"), FREQ_SEMIANNUAL: Decimal("2"),
        FREQ_ANNUAL: Decimal("1"),
    }
    #: Typical days between occurrences, and how far a real-world date may drift.
    EXPECTED_GAP_DAYS = {
        FREQ_WEEKLY: 7, FREQ_BIWEEKLY: 14, FREQ_SEMIMONTHLY: 15, FREQ_MONTHLY: 30,
        FREQ_QUARTERLY: 91, FREQ_SEMIANNUAL: 182, FREQ_ANNUAL: 365,
    }

    # -- review state ------------------------------------------------------
    # Separate from `status` (active/archived/deleted), which is the soft-delete
    # lifecycle. This is the REVIEW lifecycle: has a person looked at it yet?
    REVIEW_CANDIDATE = 'candidate'
    REVIEW_CONFIRMED = 'confirmed'
    REVIEW_IGNORED = 'ignored'
    REVIEW_CHOICES = [
        (REVIEW_CANDIDATE, 'Detected — awaiting your review'),
        (REVIEW_CONFIRMED, 'Confirmed by you'),
        (REVIEW_IGNORED, 'Not a real obligation'),
    ]

    SOURCE_DETECTED = 'detected'
    SOURCE_USER = 'user'
    SOURCE_CHOICES = [(SOURCE_DETECTED, 'Detected by WLJ'),
                      (SOURCE_USER, 'You created it')]

    CONFIDENCE_CHOICES = [('high', 'High'), ('medium', 'Medium'), ('low', 'Low')]

    name = models.CharField(max_length=200)
    payee = models.CharField(max_length=200, blank=True, default='', db_index=True)
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, default=KIND_BILL,
                            db_index=True)
    frequency = models.CharField(max_length=16, choices=FREQ_CHOICES,
                                 default=FREQ_MONTHLY)

    category = models.ForeignKey('finance.TransactionCategory', null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name='recurring')
    account = models.ForeignKey('finance.FinancialAccount', null=True, blank=True,
                                on_delete=models.SET_NULL, related_name='recurring',
                                help_text="Which account it is paid from or into.")
    liability = models.ForeignKey(
        'finance.FinancialAccount', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='recurring_debt_payments',
        help_text="For a debt payment: the liability being serviced.")

    amount_expected = models.DecimalField(max_digits=12, decimal_places=2, null=True,
                                          blank=True)
    amount_min = models.DecimalField(max_digits=12, decimal_places=2, null=True,
                                     blank=True)
    amount_max = models.DecimalField(max_digits=12, decimal_places=2, null=True,
                                     blank=True)
    is_variable = models.BooleanField(
        default=False,
        help_text="The amount genuinely moves. A range is the honest answer; a single "
                  "expected figure would be invented.")

    next_due_date = models.DateField(null=True, blank=True, db_index=True)
    last_seen_date = models.DateField(null=True, blank=True)
    first_seen_date = models.DateField(null=True, blank=True)
    occurrence_count = models.PositiveIntegerField(default=0)

    review_state = models.CharField(max_length=12, choices=REVIEW_CHOICES,
                                    default=REVIEW_CANDIDATE, db_index=True)
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES,
                              default=SOURCE_DETECTED)
    confidence = models.CharField(max_length=8, choices=CONFIDENCE_CHOICES,
                                  default='low')
    detector_version = models.CharField(max_length=16, blank=True, default='')
    evidence = models.JSONField(
        default=dict, blank=True,
        help_text="How the detector reached this: occurrence dates, gap statistics, "
                  "amount spread. Kept so a proposal can be argued with.")
    note = models.TextField(blank=True, default='')

    merged_into = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='merged_from',
        help_text="Set when the user merges two series; the record is kept, not "
                  "deleted, so the history it explains does not disappear.")

    class Meta:
        verbose_name_plural = "Recurring series"
        ordering = ['-confidence', 'name']
        indexes = [
            models.Index(fields=['user', 'review_state', 'status']),
            models.Index(fields=['user', 'kind', 'status']),
            models.Index(fields=['user', 'next_due_date']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'payee', 'frequency', 'kind'],
                condition=models.Q(status='active') & ~models.Q(payee=''),
                name='uniq_active_recurring_per_payee_freq_kind'),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"

    # -- behaviour ---------------------------------------------------------
    @property
    def is_obligation(self):
        """Is this money the household must find, as opposed to money it moves?"""
        return self.kind in self.OBLIGATION_KINDS

    @property
    def is_counted(self):
        """Only a confirmed, live series may enter a forward-looking total."""
        return (self.review_state == self.REVIEW_CONFIRMED
                and self.status == "active" and self.merged_into_id is None)

    def monthly_equivalent(self, *, use='expected'):
        """This series expressed as a monthly figure, or None when unknowable.

        An annual insurance premium is a monthly commitment of a twelfth of itself even
        though it is paid once — a household that ignores that is surprised every year.
        Irregular series return None rather than a guess.
        """
        per_year = self.PER_YEAR.get(self.frequency)
        if per_year is None:
            return None
        amount = {
            'expected': self.amount_expected,
            'min': self.amount_min if self.amount_min is not None else self.amount_expected,
            'max': self.amount_max if self.amount_max is not None else self.amount_expected,
        }.get(use)
        if amount is None:
            return None
        return (abs(amount) * per_year / Decimal("12")).quantize(Decimal("0.01"))

    def get_context_summary(self):
        if self.is_variable and self.amount_min is not None:
            amount = f"{self.amount_min}–{self.amount_max}"
        else:
            amount = str(self.amount_expected) if self.amount_expected else "unknown"
        return (f"{self.name}: {self.get_frequency_display().lower()}, {amount}, "
                f"{self.get_review_state_display().lower()}")
