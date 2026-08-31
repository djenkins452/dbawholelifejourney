# ==============================================================================
# File: apps/finance/models_review.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Bulk review batches — so a decision over 40 rows can be undone.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""A bulk decision is only safe if it can be taken back.

Confirming one transaction is a small act. Confirming forty at once is a large one, and
the difference is not the effort — it is that a mistake is now forty mistakes and the
person cannot remember what the rows used to say.

So every bulk application records the rows it touched and **what each one said before**.
Undo restores exactly that, and only that: a row someone edited by hand after the batch
is left alone, because their later decision outranks this record.
"""
from django.db import models
from django.utils import timezone

from apps.core.models import UserOwnedModel


class ReviewBatch(UserOwnedModel):
    """One bulk decision, with everything needed to reverse it."""

    STATUS_APPLIED = 'applied'
    STATUS_UNDONE = 'undone'
    BATCH_STATUS_CHOICES = [
        (STATUS_APPLIED, 'Applied'),
        (STATUS_UNDONE, 'Undone'),
    ]

    decision = models.CharField(
        max_length=32,
        help_text="The economic role applied, or `leave_uncertain` when the user "
                  "deliberately declined to decide.")
    group_key = models.CharField(max_length=200, blank=True, default='')
    group_label = models.CharField(max_length=200, blank=True, default='')

    row_count = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    #: [{"id": pk, "role": prior_role, "source": prior_source, "reason": prior_reason}]
    #: The amounts are NOT stored — the row still holds those, and an undo log does not
    #: need a second copy of the money.
    previous_state = models.JSONField(default=list, blank=True)

    batch_status = models.CharField(max_length=12, choices=BATCH_STATUS_CHOICES,
                                    default=STATUS_APPLIED, db_index=True)
    applied_at = models.DateTimeField(default=timezone.now)
    undone_at = models.DateTimeField(null=True, blank=True)
    created_rule = models.ForeignKey(
        'finance.SpendingClassification', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='review_batches',
        help_text="Set when the user turned this decision into an enduring rule.")

    class Meta:
        ordering = ['-applied_at']
        verbose_name_plural = "Review batches"
        indexes = [models.Index(fields=['user', '-applied_at'])]

    def __str__(self):
        return f"{self.row_count} rows → {self.decision}"

    @property
    def can_undo(self):
        return self.batch_status == self.STATUS_APPLIED and bool(self.previous_state)

    def get_context_summary(self):
        return (f"{self.row_count} transaction(s) set to {self.decision} "
                f"({self.get_batch_status_display().lower()})")
