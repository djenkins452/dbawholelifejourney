# ==============================================================================
# File: apps/finance/models_controllability.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The controllability taxonomy — what a person can actually change.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Which costs can this household actually do something about?

`net_spending` answers "what did it cost". It cannot answer "what can I change", and
the difference is the entire point of the savings work: a mortgage and a streaming
subscription are both spending, and only one of them is a decision this month.

**Three axes, not one enum.** The obvious modelling mistake is a single
`controllability` field with ten choices, because the ten are not alternatives:

* **Necessity** — essential or discretionary. *Do I have to buy this at all?*
* **Variability** — fixed or variable. *Does the amount move?*
* **Levers** — cancellable, negotiable, reducible, avoidable, deferrable. *What could
  I actually DO?* These genuinely co-occur: a phone plan is usually negotiable AND
  reducible, and forcing a choice between them loses a real option.

Every axis defaults to UNKNOWN and stays there until something says otherwise. An
unclassified cost is not a controllable one, and it is not an uncontrollable one
either — pretending to know is how a savings engine invents opportunities.

**Precedence is by specificity, then by authority.** A classification on one
transaction beats one on its recurring series, which beats its payee, which beats a
rule, which beats its category. Within a scope, a decision the user made beats one WLJ
inferred. See `resolve_controllability`.
"""
from django.db import models
from django.utils import timezone

from apps.core.models import UserOwnedModel


class SpendingClassification(UserOwnedModel):
    """One person's judgement about what a cost is, at one level of specificity."""

    # -- necessity ---------------------------------------------------------
    NECESSITY_ESSENTIAL = 'essential'
    NECESSITY_DISCRETIONARY = 'discretionary'
    NECESSITY_UNKNOWN = 'unknown'
    NECESSITY_CHOICES = [
        (NECESSITY_ESSENTIAL, 'Essential — I have to pay this'),
        (NECESSITY_DISCRETIONARY, 'Discretionary — this is a choice'),
        (NECESSITY_UNKNOWN, 'Not yet decided'),
    ]

    # -- variability -------------------------------------------------------
    VARIABILITY_FIXED = 'fixed'
    VARIABILITY_VARIABLE = 'variable'
    VARIABILITY_UNKNOWN = 'unknown'
    VARIABILITY_CHOICES = [
        (VARIABILITY_FIXED, 'Fixed — the same every time'),
        (VARIABILITY_VARIABLE, 'Variable — the amount moves'),
        (VARIABILITY_UNKNOWN, 'Not yet decided'),
    ]

    # -- levers ------------------------------------------------------------
    LEVER_CANCELLABLE = 'cancellable'
    LEVER_NEGOTIABLE = 'negotiable'
    LEVER_REDUCIBLE = 'reducible'
    LEVER_AVOIDABLE = 'avoidable'
    LEVER_DEFERRABLE = 'deferrable'
    LEVER_CHOICES = [
        (LEVER_CANCELLABLE, 'Cancellable — I could stop it'),
        (LEVER_NEGOTIABLE, 'Negotiable — I could ask for a better price'),
        (LEVER_REDUCIBLE, 'Reducible — I could spend less on it'),
        (LEVER_AVOIDABLE, 'Avoidable — I could go without'),
        (LEVER_DEFERRABLE, 'Deferrable — I could put it off'),
    ]
    ALL_LEVERS = frozenset(k for k, _ in LEVER_CHOICES)

    # -- scope -------------------------------------------------------------
    # Ordered least to most specific; `PRECEDENCE` gives the resolution weight.
    SCOPE_CATEGORY = 'category'
    SCOPE_RULE = 'rule'
    SCOPE_PAYEE = 'payee'
    SCOPE_SERIES = 'recurring_series'
    SCOPE_TRANSACTION = 'transaction'
    SCOPE_CHOICES = [
        (SCOPE_CATEGORY, 'A whole category'),
        (SCOPE_RULE, 'Anything matching a rule'),
        (SCOPE_PAYEE, 'One payee or merchant'),
        (SCOPE_SERIES, 'One recurring series'),
        (SCOPE_TRANSACTION, 'One transaction'),
    ]
    PRECEDENCE = {
        SCOPE_TRANSACTION: 100,
        SCOPE_SERIES: 80,
        SCOPE_PAYEE: 60,
        SCOPE_RULE: 40,
        SCOPE_CATEGORY: 20,
    }

    SOURCE_USER = 'user'
    SOURCE_INFERRED = 'inferred'
    SOURCE_PROVIDER = 'provider'
    SOURCE_CHOICES = [
        (SOURCE_USER, 'You decided this'),
        (SOURCE_INFERRED, 'WLJ inferred it'),
        (SOURCE_PROVIDER, 'The bank suggested it'),
    ]
    #: A person outranks a derivation. Never reorder this to make a number nicer.
    SOURCE_AUTHORITY = {SOURCE_USER: 3, SOURCE_PROVIDER: 2, SOURCE_INFERRED: 1}

    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, db_index=True)

    transaction = models.ForeignKey(
        'finance.Transaction', on_delete=models.CASCADE, null=True, blank=True,
        related_name='controllability_classifications')
    category = models.ForeignKey(
        'finance.TransactionCategory', on_delete=models.CASCADE, null=True, blank=True,
        related_name='controllability_classifications')
    payee = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Normalised payee/merchant name this classification applies to.")
    match_contains = models.CharField(
        max_length=200, blank=True, default='',
        help_text="For a rule: a case-insensitive fragment of the description.")

    necessity = models.CharField(max_length=16, choices=NECESSITY_CHOICES,
                                 default=NECESSITY_UNKNOWN)
    variability = models.CharField(max_length=16, choices=VARIABILITY_CHOICES,
                                   default=VARIABILITY_UNKNOWN)
    levers = models.JSONField(
        default=list, blank=True,
        help_text="Zero or more of cancellable/negotiable/reducible/avoidable/"
                  "deferrable. They co-occur, so this is a list, not a choice.")

    source = models.CharField(max_length=12, choices=SOURCE_CHOICES,
                              default=SOURCE_USER, db_index=True)
    note = models.TextField(blank=True, default='')
    decided_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Spending classification"
        indexes = [
            models.Index(fields=['user', 'scope', 'status']),
            models.Index(fields=['user', 'payee']),
        ]
        constraints = [
            # One live decision per (user, scope, target). Archived and deleted rows
            # are excluded so a restored history never blocks a new decision — the same
            # active-row predicate the transaction duplicate constraint uses.
            models.UniqueConstraint(
                fields=['user', 'transaction'], condition=models.Q(status='active'),
                name='uniq_active_controllability_per_transaction'),
            models.UniqueConstraint(
                fields=['user', 'category'], condition=models.Q(status='active'),
                name='uniq_active_controllability_per_category'),
            models.UniqueConstraint(
                fields=['user', 'payee'],
                condition=models.Q(status='active') & ~models.Q(payee=''),
                name='uniq_active_controllability_per_payee'),
        ]

    def __str__(self):
        return f"{self.get_scope_display()}: {self.necessity}/{self.variability}"

    # -- behaviour ---------------------------------------------------------
    @property
    def precedence(self):
        return self.PRECEDENCE.get(self.scope, 0)

    @property
    def authority(self):
        return self.SOURCE_AUTHORITY.get(self.source, 0)

    @property
    def is_controllable(self):
        """Controllable means there is a LEVER — something the person could do.

        Deliberately not "discretionary". A cost can be essential and still negotiable
        (insurance), and calling that uncontrollable would hide one of the largest
        genuine savings a household has.
        """
        return bool(self.clean_levers())

    def clean_levers(self):
        """Only recognised levers, de-duplicated, in a stable order."""
        seen = [lv for lv in (self.levers or []) if lv in self.ALL_LEVERS]
        return [lv for lv in (k for k, _ in self.LEVER_CHOICES) if lv in seen]

    def save(self, *args, **kwargs):
        self.levers = self.clean_levers()
        if self.payee:
            self.payee = self.payee.strip()
        return super().save(*args, **kwargs)

    def get_context_summary(self):
        target = (self.payee or (self.category and self.category.name)
                  or self.match_contains or "one transaction")
        levers = ", ".join(self.clean_levers()) or "no lever recorded"
        return (f"{target}: {self.get_necessity_display()}, "
                f"{self.get_variability_display()} — {levers}")
