"""
SAE — State Awareness Engine Models.

UserState stores a structured JSON snapshot of each user's current
life state. This is a OneToOneField per user — one row per user.
"""

from django.conf import settings
from django.db import models


class UserState(models.Model):
    """
    Persistent user state snapshot.

    Contains a structured JSON blob with current values for each
    domain module (health, goals, habits, faith, journal).
    Updated incrementally after every successful action.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sae_state",
    )
    state_data = models.JSONField(
        default=dict,
        help_text="Structured state snapshot keyed by module.",
    )

    # Phase 10 — Schedule instability (rolling 7-day total)
    schedule_instability_score = models.IntegerField(
        default=0,
        help_text="Rolling 7-day schedule instability points total.",
    )
    schedule_instability_last_updated = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When schedule_instability_score was last recalculated.",
    )

    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "core"
        db_table = "core_user_state"
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["last_updated"]),
        ]
        verbose_name = "User State"
        verbose_name_plural = "User States"

    def __str__(self):
        modules = list(self.state_data.keys()) if self.state_data else []
        return f"State for {self.user} ({', '.join(modules) or 'empty'})"

    def get_module(self, module):
        """Get state data for a specific module."""
        return self.state_data.get(module, {})

    def set_module(self, module, data):
        """Set state data for a specific module."""
        self.state_data[module] = data
