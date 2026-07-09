# ==============================================================================
# File: apps/ai/cos_services/ai_relationship.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: AIRelationshipService — projects the user's AI Relationship (Pillar 3)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
AIRelationshipService — Pillar 3 of the WLJ ↔ conversational-model interface
============================================================================

AI Relationship is an **owned deterministic area of WLJ** — how this user wants to
work with their AI (AI Name, Default Relationship, Communication Style, Personality,
Trust & Accuracy, Formatting, Learning). WLJ owns it; the interface only *projects*
it at runtime for the conversational model to consume.

Governing docs:
* docs/WLJ_MODEL_INTERFACE_DESIGN.md  (Pillar 3; §9 ownership)
* docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md §5

Design rules honored (following the existing cos_services pattern):
* REUSE / EXPOSE, do not invent — this slice is a pure read-only PROJECTION over
  data that already exists (`UserPreferences`, `PersonalOperatingBlueprint`). No new
  tables, no schema change, no reasoning, no LLM call.
* DETERMINISTIC + READ-ONLY. The model consumes this; it never originates it.
* Every field is tagged with a source (`user` = explicitly configured, `default` =
  not yet configurable / falling back to a safe default) so learned-vs-selected-vs-
  default is auditable (a later slice adds persisted fields + learned preferences).
* JSON-safe output, wrappable later by an HTTP endpoint / tool with zero logic change.

Not yet persisted (safe defaults here; a later slice adds the fields + UI + learning):
    default_relationship · personality_overlay · preference_learning_enabled ·
    learned_preferences[]

IMPORTANT: `learning.enabled` here is the *preference-learning* toggle. It is NOT the
same as `PersonalOperatingBlueprint.cos_learning_mode_active` (that is "Learning Mode",
a UAIO action-suppression concept). They must not be conflated.

Public API:
    get_ai_relationship(user) -> dict
"""

import logging

logger = logging.getLogger(__name__)

AI_RELATIONSHIP_SCHEMA_VERSION = "1.0"

# Default relationship baseline when the user has not chosen one (not yet a stored
# field; promoted to a real field + UI in a later slice).
DEFAULT_RELATIONSHIP = "chief_of_staff"

# Source markers for provenance / auditability.
SOURCE_USER = "user"        # explicitly stored user configuration
SOURCE_DEFAULT = "default"  # safe fallback; not yet user-configurable or unset


def _safe_get_preferences(user):
    """Return the user's UserPreferences, or None (never raise)."""
    try:
        return user.preferences
    except Exception:  # pragma: no cover - defensive; preferences normally exist
        logger.warning("AIRelationship: no preferences for user=%s", getattr(user, "id", "?"))
        return None


def _safe_get_blueprint(user):
    """Return the user's PersonalOperatingBlueprint (get-or-create), or None."""
    try:
        from apps.core.blueprint.engine import get_blueprint
        return get_blueprint(user)
    except Exception:  # pragma: no cover - defensive
        logger.warning("AIRelationship: no blueprint for user=%s", getattr(user, "id", "?"))
        return None


def _load_learned_preferences(user) -> list:
    """Return the user's ACTIVE learned communication preferences (never raise)."""
    try:
        from apps.ai.models import LearnedCommunicationPreference
        rows = LearnedCommunicationPreference.objects.filter(
            user=user, active=True
        ).order_by("category", "key")
        return [
            {
                "category": r.category,
                "key": r.key,
                "value": r.value,
                "source": r.source,
                "confidence": r.confidence,
                "evidence_count": r.evidence_count,
                "last_evidence_at": (
                    r.last_evidence_at.isoformat() if r.last_evidence_at else None
                ),
            }
            for r in rows
        ]
    except Exception:  # pragma: no cover - defensive
        logger.warning(
            "AIRelationship: could not load learned prefs for user=%s",
            getattr(user, "id", "?"),
        )
        return []


def get_ai_relationship(user) -> dict:
    """
    Project the user's AI Relationship into one compact, JSON-safe object.

    This is a deterministic READ-ONLY projection over existing preference data.
    It performs no reasoning and never calls an LLM.
    """
    prefs = _safe_get_preferences(user)
    blueprint = _safe_get_blueprint(user)

    sources: dict[str, str] = {}

    def _tag(key: str, value, source: str):
        sources[key] = source
        return value

    # --- Assistant identity + relationship ------------------------------------
    # Display name: get_cos_name() resolves a blank name to 'Chief of Staff'.
    raw_name = (getattr(prefs, "cos_display_name", "") or "").strip() if prefs else ""
    display_name = raw_name or "Chief of Staff"
    # default_relationship: blank stored value = not chosen → Chief of Staff baseline.
    raw_rel = (getattr(prefs, "default_relationship", "") or "").strip() if prefs else ""
    assistant = {
        "display_name": _tag(
            "assistant.display_name", display_name,
            SOURCE_USER if raw_name else SOURCE_DEFAULT,
        ),
        "default_relationship": _tag(
            "assistant.default_relationship", raw_rel or DEFAULT_RELATIONSHIP,
            SOURCE_USER if raw_rel else SOURCE_DEFAULT,
        ),
    }

    # --- Communication style ---------------------------------------------------
    detail_level = getattr(prefs, "cos_response_style", None) if prefs else None
    coaching_style = getattr(prefs, "ai_coaching_style", None) if prefs else None
    communication = {
        "detail_level": _tag(
            "communication.detail_level", detail_level or "balanced",
            SOURCE_USER if detail_level else SOURCE_DEFAULT,
        ),
        "coaching_style": _tag(
            "communication.coaching_style", coaching_style or "supportive",
            SOURCE_USER if coaching_style else SOURCE_DEFAULT,
        ),
    }

    # --- Personality overlay (tone/flavor only) --------------------------------
    raw_overlay = (getattr(prefs, "personality_overlay", "") or "").strip() if prefs else ""
    personality_overlay = {
        "name": _tag(
            "personality_overlay.name", raw_overlay or None,
            SOURCE_USER if raw_overlay else SOURCE_DEFAULT,
        ),
    }

    # --- Accountability (firmness / question cadence) --------------------------
    accountability_level = getattr(blueprint, "accountability_style", None) if blueprint else None
    question_frequency = getattr(blueprint, "question_frequency", None) if blueprint else None
    accountability = {
        "level": _tag(
            "accountability.level", accountability_level or "standard",
            SOURCE_USER if accountability_level else SOURCE_DEFAULT,
        ),
        "question_frequency": _tag(
            "accountability.question_frequency", question_frequency or "medium",
            SOURCE_USER if question_frequency else SOURCE_DEFAULT,
        ),
    }

    # --- Truth & evidence preferences (strict safe defaults; constants) --------
    # `may_invent_facts` is ALWAYS False and is NOT user-settable — surfaced here as
    # data for the model to read, never as a toggle.
    truth_preferences = {
        "authoritative_source": "WLJ",
        "may_invent_facts": False,
        "may_derive_conclusions": True,
        "may_state_hypotheses": True,
    }
    sources["truth_preferences"] = SOURCE_DEFAULT

    # --- Action preferences ----------------------------------------------------
    confirm_actions = bool(getattr(prefs, "assistant_confirm_actions", False)) if prefs else False
    action_preferences = {
        "confirm_actions": _tag(
            "action_preferences.confirm_actions", confirm_actions,
            SOURCE_USER if prefs is not None else SOURCE_DEFAULT,
        ),
    }

    # --- Learning (preference-learning toggle; NOT Learning Mode) --------------
    # Distinct from cos_learning_mode_active (Learning Mode / UAIO suppression).
    if prefs is not None and hasattr(prefs, "preference_learning_enabled"):
        learning = {
            "enabled": _tag(
                "learning.enabled", bool(prefs.preference_learning_enabled), SOURCE_USER,
            ),
        }
    else:
        learning = {"enabled": _tag("learning.enabled", True, SOURCE_DEFAULT)}

    # --- Learned communication preferences (active rows only) ------------------
    learned_preferences = _load_learned_preferences(user)

    return {
        "schema_version": AI_RELATIONSHIP_SCHEMA_VERSION,
        "assistant": assistant,
        "communication": communication,
        "personality_overlay": personality_overlay,
        "accountability": accountability,
        "truth_preferences": truth_preferences,
        "action_preferences": action_preferences,
        "learning": learning,
        "learned_preferences": learned_preferences,
        "_sources": sources,
    }
