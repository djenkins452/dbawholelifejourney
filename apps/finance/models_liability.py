# ==============================================================================
# File: apps/finance/models_liability.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Loan terms with field-level provenance. Manual is first-class.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What a debt actually costs — and where each number came from.

Plaid's currently active products give WLJ an account and a balance. They do not give
an APR, a minimum payment, a maturity date or a payoff quote, and **Plaid Liabilities is
not authorised**. Those facts still have to come from somewhere, so the manual path is
not a fallback here — it is a permanent, first-class way to hold a term, and it is
treated with the same seriousness as an imported one.

**Provenance is per FIELD, not per record.** A single loan routinely mixes a balance the
bank supplied this morning with an APR read off a statement in March and a minimum
payment somebody typed in. Recording one `source` for the whole row would make all three
look equally fresh, and the payoff engine would present a projection built on a
six-month-old rate as though the bank had just confirmed it.

**Missing is missing.** Every term is nullable and every absence is reportable. The
payoff engine asks this model what it knows, and a `None` here becomes "I need the APR
before I can answer that" rather than an assumed 7%.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import UserOwnedModel

#: Where a single fact came from. Ordered by how much weight it carries.
SOURCE_PROVIDER = 'provider'
SOURCE_STATEMENT = 'statement'
SOURCE_USER = 'user'
SOURCE_UNAVAILABLE = 'unavailable'
SOURCE_CHOICES = [
    (SOURCE_PROVIDER, 'Imported from the institution'),
    (SOURCE_STATEMENT, 'Read from a statement and confirmed by you'),
    (SOURCE_USER, 'Entered by you'),
    (SOURCE_UNAVAILABLE, 'Not available'),
]

#: Every term whose provenance is tracked. The payoff engine names these when it
#: cannot answer, so the list is the vocabulary of "what WLJ still needs".
TRACKED_TERMS = (
    'current_balance', 'apr', 'interest_method', 'minimum_payment',
    'contractual_payment', 'due_day', 'original_principal', 'origination_date',
    'remaining_term_months', 'maturity_date', 'payoff_amount',
    'payoff_quote_expires', 'promotional_apr', 'promotional_apr_ends',
    'fees', 'prepayment_penalty',
)


class LoanTerms(UserOwnedModel):
    """The contractual facts about one debt, each with its own provenance."""

    INTEREST_SIMPLE = 'simple'
    INTEREST_AMORTISED = 'amortised'
    INTEREST_REVOLVING = 'revolving'
    INTEREST_UNKNOWN = 'unknown'
    INTEREST_CHOICES = [
        (INTEREST_SIMPLE, 'Simple interest'),
        (INTEREST_AMORTISED, 'Amortised (a fixed payment schedule)'),
        (INTEREST_REVOLVING, 'Revolving (a credit line)'),
        (INTEREST_UNKNOWN, 'Not known'),
    ]

    account = models.OneToOneField(
        'finance.FinancialAccount', on_delete=models.CASCADE, related_name='loan_terms',
        help_text="The liability these terms describe. The account may be imported or "
                  "created by hand — both are first-class.")

    # -- the terms ---------------------------------------------------------
    apr = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True,
                              help_text="Annual percentage rate, e.g. 6.750")
    interest_method = models.CharField(max_length=16, choices=INTEREST_CHOICES,
                                       default=INTEREST_UNKNOWN)
    minimum_payment = models.DecimalField(max_digits=12, decimal_places=2, null=True,
                                          blank=True)
    contractual_payment = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="The scheduled payment, where that differs from the minimum.")
    due_day = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Day of the month the payment is due.")
    original_principal = models.DecimalField(max_digits=14, decimal_places=2,
                                             null=True, blank=True)
    origination_date = models.DateField(null=True, blank=True)
    remaining_term_months = models.PositiveIntegerField(null=True, blank=True)
    maturity_date = models.DateField(null=True, blank=True)

    payoff_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="A quoted payoff figure. It expires — see payoff_quote_expires.")
    payoff_quote_expires = models.DateField(null=True, blank=True)

    promotional_apr = models.DecimalField(max_digits=6, decimal_places=3, null=True,
                                          blank=True)
    promotional_apr_ends = models.DateField(null=True, blank=True)

    fees = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                               help_text="Recurring servicing or annual fees.")
    prepayment_penalty = models.CharField(max_length=200, blank=True, default='')

    note = models.TextField(blank=True, default='')

    #: {field_name: {"source": ..., "as_of": "YYYY-MM-DD", "note": ...}}
    provenance = models.JSONField(default=dict, blank=True)

    calculation_version = models.CharField(max_length=16, blank=True, default='')

    class Meta:
        verbose_name = "Loan terms"
        verbose_name_plural = "Loan terms"
        indexes = [models.Index(fields=['user', 'status'])]

    def __str__(self):
        return f"Terms for {self.account_id}"

    # -- provenance --------------------------------------------------------
    def record(self, field, value, *, source=SOURCE_USER, as_of=None, note=''):
        """Set a term AND say where it came from. The two are never separable.

        Setting a value without provenance is what produces a payoff projection built
        on a six-month-old rate presented as though the bank confirmed it this morning.
        """
        if field not in TRACKED_TERMS:
            raise ValueError(f"{field} is not a tracked loan term")
        if field != 'current_balance':
            setattr(self, field, value)
        provenance = dict(self.provenance or {})
        provenance[field] = {
            "source": source,
            "as_of": str(as_of or timezone.now().date()),
            "note": note or "",
        }
        self.provenance = provenance
        return self

    def source_of(self, field):
        return (self.provenance or {}).get(field, {}).get("source", SOURCE_UNAVAILABLE)

    def as_of(self, field):
        return (self.provenance or {}).get(field, {}).get("as_of")

    def value_of(self, field):
        """The current value of a term, reading balance from its own authority."""
        if field == 'current_balance':
            return self.account.current_balance if self.account_id else None
        return getattr(self, field, None)

    def known(self, field):
        return self.value_of(field) is not None and self.value_of(field) != ''

    def missing(self, fields=None):
        """Which terms WLJ does not have. This is the guided-input list."""
        return [f for f in (fields or TRACKED_TERMS) if not self.known(f)]

    # -- derived -----------------------------------------------------------
    @property
    def effective_apr(self):
        """The rate in force TODAY, honouring an unexpired promotional rate."""
        today = timezone.now().date()
        if (self.promotional_apr is not None
                and (self.promotional_apr_ends is None
                     or self.promotional_apr_ends >= today)):
            return self.promotional_apr
        return self.apr

    @property
    def payoff_quote_is_current(self):
        if self.payoff_amount is None:
            return False
        if self.payoff_quote_expires is None:
            return False
        return self.payoff_quote_expires >= timezone.now().date()

    @property
    def balance(self):
        """Always the ACCOUNT's balance. Terms never hold a second copy of it."""
        if not self.account_id:
            return None
        raw = self.account.current_balance
        return abs(raw) if raw is not None else None

    def get_context_summary(self):
        apr = f"{self.effective_apr}% APR" if self.effective_apr is not None \
            else "APR unknown"
        payment = (f"{self.minimum_payment} minimum" if self.minimum_payment is not None
                   else "minimum payment unknown")
        return f"{self.account.name if self.account_id else 'loan'}: {apr}, {payment}"


class LoanTermsChange(UserOwnedModel):
    """Append-only record of every term edit. Nothing about a debt is quietly rewritten."""

    terms = models.ForeignKey(LoanTerms, on_delete=models.CASCADE, related_name='changes')
    field = models.CharField(max_length=40)
    old_value = models.CharField(max_length=120, blank=True, default='')
    new_value = models.CharField(max_length=120, blank=True, default='')
    source = models.CharField(max_length=16, choices=SOURCE_CHOICES,
                              default=SOURCE_USER)
    as_of = models.DateField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Loan terms change"
        indexes = [models.Index(fields=['user', 'terms', '-created_at'])]

    def __str__(self):
        return f"{self.field}: {self.old_value} → {self.new_value}"
