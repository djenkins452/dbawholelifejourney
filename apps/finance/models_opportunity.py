# ==============================================================================
# File: apps/finance/models_opportunity.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Savings opportunities and the plans they become.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Things the household could actually do, and whether doing them worked.

An opportunity is a claim about the future, so it carries the evidence for itself:
which transactions it was derived from, what calculation produced the figure, and how
confident WLJ is. A recommendation that cannot show its working is indistinguishable
from a guess, and the household has no way to tell which one it received.

**Projected is not realized.** The two are separate fields and they are never conflated.
"You could save $47 a month" and "you have saved $47 a month" are different sentences,
and a system that blurs them will eventually congratulate someone for a saving they
never made.

**WLJ never acts outside itself.** No cancellation, no negotiation, no payment. An
accepted opportunity becomes a PLAN — a thing the person intends to do — and WLJ then
watches the transactions to see whether it happened.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import UserOwnedModel


class SavingsOpportunity(UserOwnedModel):
    """One specific, evidenced thing that could reduce what the household spends."""

    KIND_CANCEL = 'cancel'
    KIND_DOWNGRADE = 'downgrade'
    KIND_NEGOTIATE = 'negotiate'
    KIND_REDUCE_FREQUENCY = 'reduce_frequency'
    KIND_REDUCE_CATEGORY = 'reduce_category'
    KIND_MOVE_TO_ENTITY = 'move_to_entity'
    KIND_ELIMINATE_DUPLICATE = 'eliminate_duplicate'
    KIND_CORRECT_CLASSIFICATION = 'correct_classification'
    KIND_CHOICES = [
        (KIND_CANCEL, 'Cancel it'),
        (KIND_DOWNGRADE, 'Move to a cheaper tier'),
        (KIND_NEGOTIATE, 'Ask for a better price'),
        (KIND_REDUCE_FREQUENCY, 'Buy it less often'),
        (KIND_REDUCE_CATEGORY, 'Spend less in this category'),
        (KIND_MOVE_TO_ENTITY, 'Charge it to the entity that benefits'),
        (KIND_ELIMINATE_DUPLICATE, 'You are paying for this twice'),
        (KIND_CORRECT_CLASSIFICATION, 'This looks miscategorised'),
    ]
    #: Kinds that do NOT reduce household spending — they move who pays, or fix a
    #: record. Counted separately so a "you could save $400" total never quietly
    #: includes money that is still being spent.
    NON_REDUCING_KINDS = frozenset({KIND_MOVE_TO_ENTITY, KIND_CORRECT_CLASSIFICATION})

    # The lifecycle, in the order it actually happens. `decision` is what the PERSON
    # said; `outcome` is what the WORLD did. Keeping them in one field is how a system
    # ends up congratulating someone for a saving they never made.
    STATUS_PROPOSED = 'proposed'
    STATUS_ACCEPTED = 'accepted'
    STATUS_REJECTED = 'rejected'
    STATUS_SNOOZED = 'snoozed'
    STATUS_PLANNED = 'planned'
    STATUS_DONE = 'done'
    STATUS_ABANDONED = 'abandoned'
    DECISION_CHOICES = [
        (STATUS_PROPOSED, 'Suggested'), (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_REJECTED, 'Not for me'), (STATUS_SNOOZED, 'Later'),
        (STATUS_PLANNED, 'In the plan'),
        (STATUS_DONE, 'I have done this'), (STATUS_ABANDONED, 'Gave up on it'),
    ]

    #: What actually happened, observed from transactions. Deliberately separate from
    #: the decision: "I accepted it" and "it worked" are different claims.
    OUTCOME_PENDING = 'pending'
    OUTCOME_TOO_EARLY = 'too_early'
    OUTCOME_ACHIEVED = 'achieved'
    OUTCOME_PARTIAL = 'partially_achieved'
    OUTCOME_NOT_ACHIEVED = 'not_achieved'
    OUTCOME_UNMEASURABLE = 'unmeasurable'
    OUTCOME_CHOICES = [
        (OUTCOME_PENDING, 'Not yet looked at'),
        (OUTCOME_TOO_EARLY, 'Too early to tell'),
        (OUTCOME_ACHIEVED, 'Achieved'),
        (OUTCOME_PARTIAL, 'Partly achieved'),
        (OUTCOME_NOT_ACHIEVED, 'Did not happen'),
        (OUTCOME_UNMEASURABLE, 'Cannot be measured from transactions'),
    ]

    EFFORT_CHOICES = [('low', 'A few minutes'), ('medium', 'A phone call'),
                      ('high', 'A real project')]
    DISRUPTION_CHOICES = [('low', 'Nobody notices'), ('medium', 'Some change'),
                          ('high', 'A real sacrifice')]
    CONFIDENCE_CHOICES = [('high', 'High'), ('medium', 'Medium'), ('low', 'Low')]

    kind = models.CharField(max_length=32, choices=KIND_CHOICES, db_index=True)
    title = models.CharField(max_length=200)
    rationale = models.TextField(blank=True, default='')

    series = models.ForeignKey('finance.RecurringSeries', null=True, blank=True,
                               on_delete=models.CASCADE, related_name='opportunities')
    category = models.ForeignKey('finance.TransactionCategory', null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name='opportunities')
    payee = models.CharField(max_length=200, blank=True, default='')

    projected_monthly_savings = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="What WLJ calculates could be saved. NOT what has been saved.")
    realized_monthly_savings = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="What actually happened, observed from transactions after the fact.")
    observed_from = models.DateField(null=True, blank=True)

    confidence = models.CharField(max_length=8, choices=CONFIDENCE_CHOICES,
                                  default='low')
    effort = models.CharField(max_length=8, choices=EFFORT_CHOICES, default='medium')
    disruption = models.CharField(max_length=8, choices=DISRUPTION_CHOICES,
                                  default='medium')

    decision = models.CharField(max_length=12, choices=DECISION_CHOICES,
                                default=STATUS_PROPOSED, db_index=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.CharField(max_length=300, blank=True, default='')
    snooze_until = models.DateField(null=True, blank=True)

    outcome = models.CharField(max_length=24, choices=OUTCOME_CHOICES,
                               default=OUTCOME_PENDING, db_index=True)
    outcome_checked_at = models.DateTimeField(null=True, blank=True)
    started_on = models.DateField(
        null=True, blank=True,
        help_text="When the change was supposed to take effect. Measurement starts here.")
    observation_days = models.PositiveIntegerField(
        default=60,
        help_text="How long WLJ watches before it will say whether it worked.")
    outcome_evidence = models.JSONField(default=dict, blank=True)
    abandoned_reason = models.CharField(max_length=300, blank=True, default='')

    target_debt = models.ForeignKey(
        'finance.FinancialAccount', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='directed_savings',
        help_text="Where the freed money is meant to go. A direction, never a payment "
                  "— WLJ moves no money.")
    target_goal = models.ForeignKey(
        'finance.FinancialGoal', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='directed_savings')

    evidence = models.JSONField(
        default=dict, blank=True,
        help_text="Transaction ids and the calculation behind the figure. An "
                  "opportunity that cannot show its working is a guess.")
    engine_version = models.CharField(max_length=16, blank=True, default='')

    class Meta:
        verbose_name_plural = "Savings opportunities"
        ordering = ['-projected_monthly_savings']
        indexes = [
            models.Index(fields=['user', 'decision', 'status']),
            models.Index(fields=['user', '-projected_monthly_savings']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'kind', 'series'],
                condition=models.Q(status='active') & models.Q(series__isnull=False),
                name='uniq_active_opportunity_per_series_kind'),
        ]

    def __str__(self):
        return f"{self.title} (~{self.projected_monthly_savings}/mo)"

    @property
    def reduces_spending(self):
        return self.kind not in self.NON_REDUCING_KINDS

    @property
    def is_open(self):
        """Still awaiting a decision — a snooze that has expired is open again."""
        if self.decision == self.STATUS_SNOOZED:
            return bool(self.snooze_until and self.snooze_until <= timezone.now().date())
        return self.decision == self.STATUS_PROPOSED

    @property
    def variance(self):
        """Realized minus projected. None until something has actually been observed."""
        if self.realized_monthly_savings is None:
            return None
        return self.realized_monthly_savings - self.projected_monthly_savings

    @property
    def is_measurable(self):
        """Can WLJ see whether this happened at all?

        Only a series-backed opportunity is: the saving shows up as that series
        stopping or shrinking. A category-level intention has no single row to watch,
        and claiming to have measured it would be a fabrication.
        """
        return self.series_id is not None

    @property
    def is_being_tracked(self):
        return (self.decision in (self.STATUS_ACCEPTED, self.STATUS_PLANNED,
                                 self.STATUS_DONE)
                and self.started_on is not None)

    def decide(self, decision, *, reason='', snooze_until=None):
        self.decision = decision
        self.decision_reason = reason
        self.snooze_until = snooze_until
        self.decided_at = timezone.now()
        return self

    def get_context_summary(self):
        return (f"{self.title}: about {self.projected_monthly_savings} a month "
                f"({self.get_confidence_display().lower()} confidence, "
                f"{self.get_decision_display().lower()})")
