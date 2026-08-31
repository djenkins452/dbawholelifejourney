# ==============================================================================
# File: apps/finance/models_networth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Net-worth snapshots — observed history, never invented history.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""What the household was worth, on days WLJ could actually see.

**History starts when observation starts.** WLJ holds today's account balances and
today's asset valuations; it does not hold what a car was worth in March. Back-filling a
trend line from today's numbers would produce a chart that looks like history and is
fiction, and a person would make decisions from it.

So a snapshot records what was true on the day it was taken, and the series begins with
the first trustworthy one. Where a value CAN be defensibly reconstructed from records
WLJ already holds, it is labelled `reconstructed` and never mixed silently with
`observed`.

Idempotent by construction: one snapshot per user per day, updated in place if the day
is re-run, so a scheduled job and a manual click cannot produce two versions of the same
Tuesday.
"""
from decimal import Decimal

from django.db import models

from apps.core.models import UserOwnedModel


class NetWorthSnapshot(UserOwnedModel):
    """One day's position, with its composition and its gaps."""

    BASIS_OBSERVED = 'observed'
    BASIS_RECONSTRUCTED = 'reconstructed'
    BASIS_CHOICES = [
        (BASIS_OBSERVED, 'Observed — the values WLJ held that day'),
        (BASIS_RECONSTRUCTED, 'Reconstructed from records, and labelled as such'),
    ]

    as_of = models.DateField(db_index=True)
    basis = models.CharField(max_length=16, choices=BASIS_CHOICES,
                             default=BASIS_OBSERVED)

    cash_and_financial = models.DecimalField(max_digits=16, decimal_places=2,
                                             default=Decimal("0.00"))
    investments = models.DecimalField(max_digits=16, decimal_places=2,
                                      default=Decimal("0.00"))
    tangible_assets = models.DecimalField(max_digits=16, decimal_places=2,
                                          default=Decimal("0.00"))
    liabilities = models.DecimalField(max_digits=16, decimal_places=2,
                                      default=Decimal("0.00"))
    net_worth = models.DecimalField(max_digits=16, decimal_places=2,
                                    default=Decimal("0.00"))

    #: Counted separately, never folded into a total. An asset nobody has valued is
    #: not worth zero — it is worth an unknown amount, and the difference matters when
    #: the asset is a house.
    unvalued_asset_count = models.PositiveIntegerField(default=0)
    excluded_asset_count = models.PositiveIntegerField(default=0)
    stale_valuation_count = models.PositiveIntegerField(default=0)

    calculation_version = models.CharField(max_length=16, blank=True, default='')
    composition = models.JSONField(
        default=dict, blank=True,
        help_text="Per-account and per-asset contributions, so every total can be "
                  "opened rather than trusted.")
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-as_of']
        verbose_name = "Net worth snapshot"
        indexes = [models.Index(fields=['user', '-as_of'])]
        constraints = [
            # One per user per day. A scheduled run and a manual click on the same
            # Tuesday must not produce two versions of that Tuesday.
            models.UniqueConstraint(
                fields=['user', 'as_of'], condition=models.Q(status='active'),
                name='uniq_active_networth_snapshot_per_day'),
        ]

    def __str__(self):
        return f"{self.as_of}: {self.net_worth}"

    @property
    def gross_assets(self):
        return self.cash_and_financial + self.investments + self.tangible_assets

    @property
    def is_complete(self):
        """A snapshot with unvalued assets is a real figure with a stated hole in it."""
        return self.unvalued_asset_count == 0

    def get_context_summary(self):
        gaps = []
        if self.unvalued_asset_count:
            gaps.append(f"{self.unvalued_asset_count} unvalued asset(s)")
        if self.stale_valuation_count:
            gaps.append(f"{self.stale_valuation_count} stale valuation(s)")
        tail = f" ({'; '.join(gaps)})" if gaps else ""
        return f"Net worth {self.net_worth} on {self.as_of}{tail}"
