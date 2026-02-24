"""
CosGoalSuggestionService — Goal Suggestion Policy for CoS v2.

Manages the lifecycle of CoS goal suggestions:
- Create suggestions from pattern detection evidence
- Monthly throttle per theme (max 1/month)
- Track decline history
- 3-decline opt-out prompt flow
- Never auto-create goals — suggestions only

Policy:
1. Max ~1 suggestion per month per theme
2. Never auto-create goals (always "suggested" status)
3. If declined 3x for same theme → return opt-out prompt
4. If user confirms opt-out → mark theme opted_out
5. Opted-out themes never receive suggestions again

Integration:
- CosPatternService.detect_and_suggest() → this service → user response
- PGE guidance delivery can route through this for tracking
"""

import datetime as dt
import logging
from typing import Dict, List, Optional

from django.utils import timezone as dj_timezone

from apps.cos.models import CosGoalSuggestion

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────

# Monthly throttle: minimum days between suggestions for same theme
THROTTLE_DAYS = 30

# Number of declines before offering opt-out
DECLINE_THRESHOLD = 3

# Opt-out prompt text
OPT_OUT_PROMPT = (
    "You've declined this type of suggestion {} times. "
    "Would you like me to stop suggesting goals about {}?"
)


# ──────────────────────────────────────────────────────────
# CosGoalSuggestionService
# ──────────────────────────────────────────────────────────


class CosGoalSuggestionService:
    """
    Manages goal suggestion lifecycle:
    create → present → accept/decline → (opt-out?) → throttle
    """

    def __init__(self, user):
        self.user = user

    # ── Create Suggestions ─────────────────────────────────

    def create_suggestion(
        self,
        theme,
        suggestion_text,
        evidence_summary="",
    ):
        """
        Create a new goal suggestion if allowed by throttle/opt-out policy.

        Returns:
            dict with "created": bool, "suggestion": CosGoalSuggestion or None,
            "reason": str if blocked.
        """
        # Check opt-out
        if CosGoalSuggestion.is_theme_opted_out(self.user, theme):
            return {
                "created": False,
                "suggestion": None,
                "reason": "Theme '{}' is opted out.".format(theme),
            }

        # Check monthly throttle
        if not self._passes_throttle(theme):
            return {
                "created": False,
                "suggestion": None,
                "reason": (
                    "Theme '{}' was suggested within the last {} days.".format(
                        theme, THROTTLE_DAYS,
                    )
                ),
            }

        suggestion = CosGoalSuggestion.objects.create(
            user=self.user,
            theme=theme,
            suggestion_text=suggestion_text,
            evidence_summary=evidence_summary,
            status=CosGoalSuggestion.STATUS_SUGGESTED,
        )

        logger.debug(
            "Created goal suggestion: user=%s theme=%s id=%s",
            self.user.id, theme, suggestion.pk,
        )

        return {
            "created": True,
            "suggestion": suggestion,
            "reason": "",
        }

    def create_suggestions_from_patterns(self, pattern_suggestions):
        """
        Batch create suggestions from CosPatternService output.

        Args:
            pattern_suggestions: list of suggestion dicts from
                CosPatternService.generate_suggestions()

        Returns:
            list of result dicts from create_suggestion()
        """
        results = []
        for sug in pattern_suggestions:
            result = self.create_suggestion(
                theme=sug["theme"],
                suggestion_text=sug["text"],
                evidence_summary=sug.get("evidence_summary", ""),
            )
            results.append(result)
        return results

    # ── Response Handling ──────────────────────────────────

    def accept_suggestion(self, suggestion_id):
        """
        User accepts a goal suggestion.

        Does NOT auto-create a goal — just marks as accepted.
        The user or another service creates the goal separately.

        Returns:
            dict with "success": bool, "suggestion": CosGoalSuggestion or None
        """
        suggestion = self._get_suggestion(suggestion_id)
        if not suggestion:
            return {"success": False, "suggestion": None, "error": "Not found"}

        suggestion.status = CosGoalSuggestion.STATUS_ACCEPTED
        suggestion.responded_at = dj_timezone.now()
        suggestion.save(
            update_fields=["status", "responded_at", "updated_at"]
        )

        logger.debug(
            "Suggestion accepted: user=%s theme=%s id=%s",
            self.user.id, suggestion.theme, suggestion.pk,
        )

        return {"success": True, "suggestion": suggestion}

    def decline_suggestion(self, suggestion_id):
        """
        User declines a goal suggestion.

        Tracks the decline and checks if the 3-decline threshold is reached.

        Returns:
            dict with:
            - "success": bool
            - "suggestion": CosGoalSuggestion
            - "offer_opt_out": bool (True if threshold reached)
            - "opt_out_prompt": str (the question to ask if threshold reached)
        """
        suggestion = self._get_suggestion(suggestion_id)
        if not suggestion:
            return {
                "success": False,
                "suggestion": None,
                "offer_opt_out": False,
                "opt_out_prompt": "",
                "error": "Not found",
            }

        suggestion.status = CosGoalSuggestion.STATUS_DECLINED
        suggestion.responded_at = dj_timezone.now()
        suggestion.declined_count = (
            CosGoalSuggestion.get_theme_decline_count(
                self.user, suggestion.theme
            )
            + 1  # Include this decline
        )
        suggestion.save(
            update_fields=[
                "status", "responded_at", "declined_count", "updated_at",
            ]
        )

        logger.debug(
            "Suggestion declined: user=%s theme=%s count=%s",
            self.user.id, suggestion.theme, suggestion.declined_count,
        )

        # Check if we should offer opt-out
        total_declines = CosGoalSuggestion.get_theme_decline_count(
            self.user, suggestion.theme
        )
        offer_opt_out = total_declines >= DECLINE_THRESHOLD
        theme_label = suggestion.theme.replace("_", " ")

        return {
            "success": True,
            "suggestion": suggestion,
            "offer_opt_out": offer_opt_out,
            "opt_out_prompt": (
                OPT_OUT_PROMPT.format(total_declines, theme_label)
                if offer_opt_out else ""
            ),
        }

    def opt_out_theme(self, theme):
        """
        User opts out of future suggestions for a theme.

        Marks all existing suggestions for the theme as opted_out.

        Returns: number of suggestions marked.
        """
        updated = CosGoalSuggestion.objects.filter(
            user=self.user,
            theme=theme,
        ).update(opted_out=True)

        # Also create an opt-out record if none exists
        if not CosGoalSuggestion.objects.filter(
            user=self.user,
            theme=theme,
            status=CosGoalSuggestion.STATUS_OPTED_OUT,
        ).exists():
            CosGoalSuggestion.objects.create(
                user=self.user,
                theme=theme,
                suggestion_text="[Opted out]",
                status=CosGoalSuggestion.STATUS_OPTED_OUT,
                opted_out=True,
                responded_at=dj_timezone.now(),
            )

        logger.debug(
            "Theme opted out: user=%s theme=%s updated=%s",
            self.user.id, theme, updated,
        )

        return updated

    def undo_opt_out(self, theme):
        """
        Re-enable suggestions for an opted-out theme.

        Returns: True if successful, False if theme wasn't opted out.
        """
        updated = CosGoalSuggestion.objects.filter(
            user=self.user,
            theme=theme,
            opted_out=True,
        ).update(opted_out=False)

        return updated > 0

    # ── Query Methods ──────────────────────────────────────

    def get_pending_suggestions(self):
        """Get all unresponded suggestions for the user."""
        return CosGoalSuggestion.objects.filter(
            user=self.user,
            status=CosGoalSuggestion.STATUS_SUGGESTED,
        )

    def get_suggestion_history(self, theme=None, limit=20):
        """Get suggestion history, optionally filtered by theme."""
        qs = CosGoalSuggestion.objects.filter(user=self.user)
        if theme:
            qs = qs.filter(theme=theme)
        return qs[:limit]

    def get_opted_out_themes(self):
        """Get list of themes the user has opted out of."""
        return list(
            CosGoalSuggestion.objects.filter(
                user=self.user,
                opted_out=True,
            )
            .values_list("theme", flat=True)
            .distinct()
        )

    def get_theme_stats(self, theme):
        """
        Get stats for a specific theme.

        Returns: dict with total, accepted, declined, opted_out counts.
        """
        qs = CosGoalSuggestion.objects.filter(
            user=self.user, theme=theme,
        )
        return {
            "total": qs.count(),
            "accepted": qs.filter(
                status=CosGoalSuggestion.STATUS_ACCEPTED
            ).count(),
            "declined": qs.filter(
                status=CosGoalSuggestion.STATUS_DECLINED
            ).count(),
            "opted_out": qs.filter(opted_out=True).exists(),
            "last_suggestion_date": CosGoalSuggestion.last_suggestion_date(
                self.user, theme
            ),
        }

    # ── Full Pipeline ──────────────────────────────────────

    def run_suggestion_pipeline(self, days=30, max_suggestions=3):
        """
        Full pipeline: detect patterns → generate suggestions → store.

        Convenience method combining CosPatternService + this service.

        Returns:
            dict with "patterns", "created", "blocked" lists.
        """
        from apps.cos.services.pattern_service import CosPatternService

        pattern_svc = CosPatternService(self.user)
        result = pattern_svc.detect_and_suggest(
            days=days, max_suggestions=max_suggestions
        )

        created = []
        blocked = []

        for sug in result["suggestions"]:
            creation_result = self.create_suggestion(
                theme=sug["theme"],
                suggestion_text=sug["text"],
                evidence_summary=sug.get("evidence_summary", ""),
            )
            if creation_result["created"]:
                created.append(creation_result["suggestion"])
            else:
                blocked.append({
                    "theme": sug["theme"],
                    "reason": creation_result["reason"],
                })

        return {
            "patterns": result["patterns"],
            "created": created,
            "blocked": blocked,
        }

    # ── Private Helpers ────────────────────────────────────

    def _passes_throttle(self, theme):
        """Check if a theme passes the monthly throttle."""
        last_date = CosGoalSuggestion.last_suggestion_date(
            self.user, theme,
        )
        if not last_date:
            return True

        days_since = (dj_timezone.now().date() - last_date).days
        return days_since >= THROTTLE_DAYS

    def _get_suggestion(self, suggestion_id):
        """Get a suggestion by ID scoped to user."""
        try:
            return CosGoalSuggestion.objects.get(
                pk=suggestion_id, user=self.user,
            )
        except CosGoalSuggestion.DoesNotExist:
            return None
