"""
CosToneService — Context-Sensitive Tone Selection for CoS v2.

Selects and adapts the tone/style of CoS interactions based on:
1. Activity context (work meeting → direct, prayer → gentle)
2. Recent user sentiment (negative streak → extra supportive)
3. Time of day (early morning → gentle, midday → energized)
4. Response style preference (concise/balanced/strategic/deep_dive)
5. User's base coaching style (from UserPreferences)
6. Adaptive coaching mode: SUPPORTIVE / ANALYTICAL / CHALLENGER
   selected based on domain, emotional tone, and trend direction.

Does NOT replace the user's chosen CoachingStyle. Instead, it layers
context-specific tone modifiers on top for CoS-generated prompts.

Design:
- Tone = mood/emotion of the message (encouraging, gentle, direct, etc.)
- Response style = verbosity/depth (from cos_response_style pref)
- Coaching style = base personality (from ai_coaching_style pref)
- Coaching mode = adaptive mode selected per-interaction (SUPPORTIVE/ANALYTICAL/CHALLENGER)
"""

import datetime as dt
import logging
from typing import Dict, Optional

from django.utils import timezone as dj_timezone

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Tone Definitions
# ──────────────────────────────────────────────────────────

# Available tone modifiers
TONES = {
    "encouraging": {
        "label": "Encouraging",
        "instruction": (
            "Use an encouraging, forward-moving tone. "
            "Acknowledge effort briefly, then redirect to the next action. "
            "Build momentum — don't just celebrate, propel."
        ),
    },
    "gentle": {
        "label": "Gentle",
        "instruction": (
            "Use a gentle, calm tone. "
            "Be patient and non-judgmental. Give space for reflection."
        ),
    },
    "direct": {
        "label": "Direct",
        "instruction": (
            "Be clear and direct. Get to the point quickly. "
            "Respect the user's time."
        ),
    },
    "celebratory": {
        "label": "Celebratory",
        "instruction": (
            "Celebrate this accomplishment! Be genuinely enthusiastic. "
            "Acknowledge the win."
        ),
    },
    "empathetic": {
        "label": "Empathetic",
        "instruction": (
            "Be empathetic and understanding. Validate feelings. "
            "Let them know it's okay to struggle."
        ),
    },
    "energized": {
        "label": "Energized",
        "instruction": (
            "Be energetic and motivating. Build excitement. "
            "Help them feel ready to take action."
        ),
    },
    "reflective": {
        "label": "Reflective",
        "instruction": (
            "Encourage thoughtful reflection. Ask open-ended questions. "
            "Help them process their experience."
        ),
    },
    "neutral": {
        "label": "Neutral",
        "instruction": "",  # No modifier — use base style as-is
    },
}

# Activity type → default tone mapping
ACTIVITY_TONE_MAP = {
    "meeting": "direct",
    "appointment": "direct",
    "therapy": "gentle",
    "workout": "energized",
    "bible_study": "reflective",
    "prayer": "gentle",
    "devotional": "gentle",
    "journaling": "reflective",
    "meditation": "gentle",
    "fasting": "encouraging",
    "routine": "encouraging",
    "task": "direct",
    "habit": "encouraging",
    "goal_deadline": "direct",
    "milestone_deadline": "direct",
    "life_event": "encouraging",
    "default": "encouraging",
}

# Time-of-day tone adjustments
# These override the activity default in specific time windows
TIME_TONE_OVERRIDES = {
    # Early morning (5-7am) — gentle regardless of activity
    "early_morning": {"hours": (5, 7), "tone": "gentle"},
    # Late evening (20-23) — reflective wind-down
    "late_evening": {"hours": (20, 23), "tone": "reflective"},
}

# Response style instructions (from cos_response_style preference)
RESPONSE_STYLE_INSTRUCTIONS = {
    "concise": (
        "Keep responses brief — 1-2 sentences max. "
        "No fluff, just what matters."
    ),
    "balanced": (
        "Keep responses moderate — 2-3 sentences. "
        "Include key context but stay focused."
    ),
    "strategic": (
        "Provide actionable guidance — 2-4 sentences. "
        "Include reasoning and next steps."
    ),
    "deep_dive": (
        "Give thorough responses — 3-5 sentences. "
        "Include context, reasoning, and encouragement."
    ),
}

# Sentiment → tone override (when recent sentiment is negative)
SENTIMENT_TONE_OVERRIDE = {
    "negative_streak": "empathetic",
    "positive_streak": "celebratory",
}

# ──────────────────────────────────────────────────────────
# Adaptive Coaching Modes (Part 4 — Proactive Intelligence)
# ──────────────────────────────────────────────────────────

COACHING_MODES = {
    "supportive": {
        "label": "Supportive",
        "instruction": (
            "COACHING MODE: SUPPORTIVE. "
            "The user is under strain or showing signs of discouragement. "
            "Be warm. Validate effort. Suggest micro-adjustments, not overhauls. "
            "Frame setbacks as recoverable. Focus on what they did right."
        ),
    },
    "analytical": {
        "label": "Analytical",
        "instruction": (
            "COACHING MODE: ANALYTICAL. "
            "The user is reviewing data or asking about progress. "
            "Be precise and data-driven. Show trends with specific numbers. "
            "Compare periods. Highlight signal over noise. "
            "Let the data speak — no motivational filler."
        ),
    },
    "challenger": {
        "label": "Challenger",
        "instruction": (
            "COACHING MODE: CHALLENGER. "
            "A drift pattern has been detected or long-term identity is at risk. "
            "Be direct. Name the pattern. Clarify the consequence if it continues. "
            "Offer a concrete reset action for today. "
            "If the drifting item is foundational, name that explicitly: "
            "'This is foundational — letting it slide changes who you're becoming.' "
            "Do not soften the message — clarity is kindness here."
        ),
    },
}

# Domain detection keywords for coaching mode selection
DOMAIN_KEYWORDS = {
    "health": [
        "weight", "workout", "exercise", "medication", "meds", "sleep",
        "fasting", "nutrition", "calories", "steps", "heart rate", "bp",
        "blood pressure", "glucose", "fitness",
    ],
    "finance": [
        "budget", "spending", "savings", "money", "income", "expenses",
        "financial", "bills", "debt",
    ],
    "faith": [
        "prayer", "bible", "scripture", "church", "faith", "devotional",
        "spiritual", "fasting",
    ],
    "relationships": [
        "relationship", "family", "friend", "partner", "spouse",
        "connection", "social", "lonely",
    ],
    "productivity": [
        "task", "goal", "habit", "project", "deadline", "schedule",
        "calendar", "priority", "focus",
    ],
}

# Emotional tone keywords
EMOTIONAL_TONE_KEYWORDS = {
    "discouraged": [
        "struggling", "frustrated", "failing", "can't", "giving up",
        "hopeless", "overwhelmed", "tired", "exhausted", "behind",
        "slipping", "disappointed", "hard time",
    ],
    "confident": [
        "great", "amazing", "crushing it", "on track", "proud",
        "consistent", "motivated", "excited", "strong", "progress",
    ],
}


# ──────────────────────────────────────────────────────────
# CosToneService
# ──────────────────────────────────────────────────────────


class CosToneService:
    """
    Selects context-appropriate tone for CoS interactions.

    Usage:
        svc = CosToneService(user)
        tone = svc.select_tone(activity_type="workout")
        instruction = svc.get_tone_instruction(tone)
        full_prefix = svc.build_prompt_modifier(activity_type="workout")
    """

    def __init__(self, user):
        self.user = user

    # ── Tone Selection ─────────────────────────────────────

    def select_tone(
        self,
        activity_type="default",
        reference_time=None,
        sentiment_context=None,
    ):
        """
        Select the best tone for a given context.

        Priority (highest to lowest):
        1. Sentiment override (negative streak → empathetic)
        2. Time-of-day override (early morning → gentle)
        3. Activity type default

        Args:
            activity_type: The type of activity (workout, prayer, etc.)
            reference_time: When the prompt will be delivered (defaults to now)
            sentiment_context: Optional dict with recent sentiment info
                {"recent_sentiment": "negative", "streak_days": 3}

        Returns:
            Tone key string (e.g. "encouraging", "gentle", "direct")
        """
        # 1. Check sentiment override
        if sentiment_context:
            recent = sentiment_context.get("recent_sentiment", "")
            streak_days = sentiment_context.get("streak_days", 0)
            if recent == "negative" and streak_days >= 2:
                return SENTIMENT_TONE_OVERRIDE["negative_streak"]
            if recent == "positive" and streak_days >= 3:
                return SENTIMENT_TONE_OVERRIDE["positive_streak"]

        # 2. Check time-of-day override
        now = reference_time or dj_timezone.now()
        hour = now.hour
        for window in TIME_TONE_OVERRIDES.values():
            start_h, end_h = window["hours"]
            if start_h <= hour <= end_h:
                return window["tone"]

        # 3. Activity type default
        return ACTIVITY_TONE_MAP.get(activity_type, ACTIVITY_TONE_MAP["default"])

    def get_tone_instruction(self, tone_key):
        """
        Get the instruction text for a tone modifier.

        Returns empty string for "neutral" or unknown tones.
        """
        tone_def = TONES.get(tone_key)
        if not tone_def:
            return ""
        return tone_def.get("instruction", "")

    def get_response_style_instruction(self):
        """
        Get the response style instruction based on user preference.

        Returns the instruction for the user's cos_response_style setting.
        """
        style = getattr(
            getattr(self.user, "preferences", None),
            "cos_response_style",
            "balanced",
        )
        return RESPONSE_STYLE_INSTRUCTIONS.get(
            style, RESPONSE_STYLE_INSTRUCTIONS["balanced"]
        )

    # ── Sentiment-Aware Selection ──────────────────────────

    def get_sentiment_context(self, days=7):
        """
        Build sentiment context from recent reflections.

        Returns dict suitable for passing to select_tone():
            {"recent_sentiment": "negative"|"positive"|"neutral",
             "streak_days": int}
        """
        try:
            from apps.cos.services.reflection_service import CosReflectionService

            svc = CosReflectionService(self.user)
            trend = svc.get_sentiment_trend(days=days)

            if not trend:
                return None

            direction = trend.get("direction", "stable")
            if direction == "declining":
                return {
                    "recent_sentiment": "negative",
                    "streak_days": trend.get("negative_count", 0),
                }
            elif direction == "improving":
                return {
                    "recent_sentiment": "positive",
                    "streak_days": trend.get("positive_count", 0),
                }
            return None
        except Exception as e:
            logger.debug("Could not get sentiment context: %s", e)
            return None

    # ── Full Prompt Modifier ───────────────────────────────

    def build_prompt_modifier(
        self,
        activity_type="default",
        reference_time=None,
        include_sentiment=True,
        include_response_style=True,
    ):
        """
        Build the complete tone/style modifier for a CoS prompt.

        Combines:
        1. Tone instruction (context-sensitive)
        2. Response style instruction (user preference)

        Returns a string that can be prepended to prompt text.
        Returns empty string if no modifiers apply.
        """
        parts = []

        # Get sentiment context if requested
        sentiment_context = None
        if include_sentiment:
            sentiment_context = self.get_sentiment_context()

        # Select tone
        tone = self.select_tone(
            activity_type=activity_type,
            reference_time=reference_time,
            sentiment_context=sentiment_context,
        )

        # Add tone instruction
        tone_instruction = self.get_tone_instruction(tone)
        if tone_instruction:
            parts.append(tone_instruction)

        # Add response style
        if include_response_style:
            style_instruction = self.get_response_style_instruction()
            if style_instruction:
                parts.append(style_instruction)

        return " ".join(parts) if parts else ""

    def select_tone_for_prompt(self, prompt):
        """
        Select tone for a specific CosPromptSchedule instance.

        Convenience method that extracts activity_type and scheduled_for
        from the prompt object.

        Returns: (tone_key, tone_instruction) tuple
        """
        activity_type = getattr(prompt, "activity_type", "default") or "default"
        reference_time = getattr(prompt, "scheduled_for", None)

        sentiment_context = self.get_sentiment_context()

        tone = self.select_tone(
            activity_type=activity_type,
            reference_time=reference_time,
            sentiment_context=sentiment_context,
        )
        instruction = self.get_tone_instruction(tone)
        return tone, instruction

    # ── Adaptive Coaching Mode Selection ──────────────────

    def select_coaching_mode(
        self,
        user_message="",
        cos_context=None,
    ):
        """
        Select the adaptive coaching mode based on domain, emotional tone,
        and trend direction.

        Priority:
        1. If drift/consistency patterns detected → CHALLENGER
        2. If user emotional tone is discouraged → SUPPORTIVE
        3. If reviewing data or neutral tone → ANALYTICAL
        4. Default → ANALYTICAL

        Args:
            user_message: The user's current message text.
            cos_context: The full CoS context dict (from build_cos_context).

        Returns:
            str — coaching mode key ("supportive", "analytical", "challenger")
        """
        cos_context = cos_context or {}
        msg_lower = (user_message or "").lower()

        # 1. Check for drift/consistency patterns → CHALLENGER
        drift_score = cos_context.get("drift_score", 0)
        if drift_score >= 30:
            return "challenger"

        # Check active patterns for warnings
        insights = cos_context.get("active_insights", [])
        for insight in insights:
            severity = insight.get("severity", "")
            if severity in ("warning", "critical"):
                pattern_type = insight.get("pattern_type", "")
                if pattern_type in (
                    "negative_streak", "consistency_drop",
                    "activity_gap", "fatigue",
                ):
                    return "challenger"

        # Check medication adherence
        med = cos_context.get("medication_adherence_state", {})
        adherence_pct = med.get("adherence_pct")
        if adherence_pct is not None and adherence_pct < 70:
            return "challenger"

        # 2. Check emotional tone from message → SUPPORTIVE
        for keyword in EMOTIONAL_TONE_KEYWORDS.get("discouraged", []):
            if keyword in msg_lower:
                return "supportive"

        # Check mood trend from context
        mood = cos_context.get("mood_status", {})
        mood_trend = mood.get("trend", "stable")
        if mood_trend in ("declining", "decreasing"):
            return "supportive"

        # Check sentiment context
        sentiment_ctx = self.get_sentiment_context(days=7)
        if sentiment_ctx and sentiment_ctx.get("recent_sentiment") == "negative":
            if sentiment_ctx.get("streak_days", 0) >= 2:
                return "supportive"

        # 3. Check for confident/data-review tone → ANALYTICAL
        for keyword in EMOTIONAL_TONE_KEYWORDS.get("confident", []):
            if keyword in msg_lower:
                return "analytical"

        # Default to ANALYTICAL (data-driven)
        return "analytical"

    def get_coaching_mode_instruction(self, mode_key):
        """
        Get the instruction text for a coaching mode.

        Returns empty string for unknown modes.
        """
        mode_def = COACHING_MODES.get(mode_key)
        if not mode_def:
            return ""
        return mode_def.get("instruction", "")

    def build_coaching_mode_injection(
        self,
        user_message="",
        cos_context=None,
    ):
        """
        Build the coaching mode injection string for the system prompt.

        Detects the appropriate coaching mode and returns the instruction
        text ready for injection into the LLM system prompt.

        Returns:
            str — coaching mode instruction, or "" if no mode selected.
        """
        mode = self.select_coaching_mode(
            user_message=user_message,
            cos_context=cos_context,
        )
        instruction = self.get_coaching_mode_instruction(mode)
        return instruction

    def detect_domain(self, user_message=""):
        """
        Detect the primary domain from the user's message.

        Returns:
            str — domain key (health, finance, faith, relationships,
                  productivity) or "general".
        """
        msg_lower = (user_message or "").lower()
        scores = {}
        for domain, keywords in DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in msg_lower)
            if score > 0:
                scores[domain] = score
        if scores:
            return max(scores, key=scores.get)
        return "general"

    # ── Available Tones (for UI/API) ───────────────────────

    @staticmethod
    def get_available_tones():
        """Return list of available tones with labels."""
        return [
            {"key": key, "label": tone["label"]}
            for key, tone in TONES.items()
            if key != "neutral"
        ]

    @staticmethod
    def get_activity_tone_defaults():
        """Return the default tone mapping for all activity types."""
        return dict(ACTIVITY_TONE_MAP)

    @staticmethod
    def get_available_coaching_modes():
        """Return list of available coaching modes with labels."""
        return [
            {"key": key, "label": mode["label"]}
            for key, mode in COACHING_MODES.items()
        ]
