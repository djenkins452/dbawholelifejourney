"""
Phase 4 — Signal Feedback: Learning from explicit user input only.

Captures user confirmation/rejection of behavioral signals.
The system ONLY learns when the user explicitly responds yes or no.
No inference. No guessing. No auto-learning.

ARCHITECTURAL RULES:
- This model stores feedback only — no decision logic
- No updates to execution truth here
- No side effects beyond storing the record
- Multiple responses per fingerprint are allowed (no dedup yet)
"""

from django.conf import settings
from django.db import models


class SignalFeedback(models.Model):
    """Records explicit user feedback on a behavioral signal.

    Each record captures a single yes/no response to a signal
    presented by the system (via Beth or UI).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signal_feedback",
    )
    signal_type = models.CharField(
        max_length=50,
        help_text="Signal type: possible_completion, effort_signal, etc.",
    )
    domain = models.CharField(
        max_length=50,
        help_text="Domain: faith, health, journal, purpose.",
    )
    item = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Specific item: prayer, workout, journal_entry, etc.",
    )
    fingerprint = models.CharField(
        max_length=255,
        help_text="Unique signal identity: {type}:{domain}:{item}:{date}",
    )
    response = models.CharField(
        max_length=10,
        choices=[
            ("yes", "Yes"),
            ("no", "No"),
        ],
    )
    source = models.CharField(
        max_length=50,
        help_text="Where the signal was detected: journal, workout_notes, etc.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["fingerprint"]),
        ]

    def __str__(self):
        return (
            f"SignalFeedback({self.user_id}, {self.signal_type}, "
            f"{self.domain}, {self.response})"
        )
