# ==============================================================================
# File: apps/finance/models_reserves.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Sinking funds and reserve floors — money already spoken for.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Cash you have is not cash you can use.

A balance of $8,000 with a $6,000 emergency floor and $900 set aside for the December
insurance premium is $1,100 of actual freedom. A forecast that reports $8,000 of "free
cash" is arithmetically correct and practically a lie, and the household finds out in
December.

Two kinds of claim on the same money:

* a **reserve** is a floor you do not go below — an emergency fund;
* a **sinking fund** is an accumulation towards a known future cost — the annual
  premium, the tyres, the property tax.

Both reduce free cash flow, and both are the user's declaration. WLJ does not invent
either: no reserve target is assumed, and a household with none configured is told that
its free-cash figure has no floor under it rather than being given a made-up one.
"""
from decimal import Decimal

from django.db import models

from apps.core.models import UserOwnedModel


class CashReserve(UserOwnedModel):
    """A claim on cash that is not a transaction: a floor, or a fund being built."""

    KIND_RESERVE = 'reserve'
    KIND_SINKING = 'sinking_fund'
    KIND_CHOICES = [
        (KIND_RESERVE, 'Reserve floor — do not go below this'),
        (KIND_SINKING, 'Sinking fund — building towards a known cost'),
    ]

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES,
                            default=KIND_SINKING, db_index=True)

    target_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="What it should reach. Null means you have not decided, and WLJ "
                  "will not decide for you.")
    current_amount = models.DecimalField(max_digits=14, decimal_places=2,
                                         default=Decimal("0.00"))
    monthly_contribution = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="What you intend to put in each month. Committed cash in a forecast.")

    due_date = models.DateField(
        null=True, blank=True,
        help_text="When the cost lands, for a sinking fund.")

    account = models.ForeignKey(
        'finance.FinancialAccount', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reserves',
        help_text="Where it is held, when it is held somewhere specific.")
    goal = models.ForeignKey(
        'finance.FinancialGoal', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='reserves',
        help_text="An existing goal this reserve represents — the Emergency Fund goal "
                  "is the usual case. Linked, never duplicated.")

    note = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['kind', 'name']
        verbose_name = "Cash reserve"
        indexes = [models.Index(fields=['user', 'kind', 'status'])]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'name'], condition=models.Q(status='active'),
                name='uniq_active_reserve_per_name'),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    @property
    def effective_balance(self):
        """What is actually in it. A linked goal or account is the authority.

        Never a stored second copy: a copy is stale the moment the balance moves, and
        the difference shows up as a reserve that looks funded and is not.
        """
        if self.goal_id is not None:
            return self.goal.current_value
        if self.account_id is not None and self.account.current_balance is not None:
            return self.account.current_balance
        return self.current_amount

    @property
    def shortfall(self):
        """How far short it is, or None when no target has been set."""
        if self.target_amount is None:
            return None
        gap = self.target_amount - self.effective_balance
        return gap if gap > Decimal("0.00") else Decimal("0.00")

    @property
    def is_funded(self):
        return self.target_amount is not None and self.shortfall == Decimal("0.00")

    def get_context_summary(self):
        target = (f" of {self.target_amount}" if self.target_amount is not None
                  else " (no target set)")
        return f"{self.name}: {self.effective_balance}{target}"
