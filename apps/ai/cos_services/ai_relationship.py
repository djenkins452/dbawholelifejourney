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

AI_RELATIONSHIP_SCHEMA_VERSION = "2.0"  # M1: persona voice + proactivity + boundaries

# Default relationship baseline when the user has not chosen one (not yet a stored
# field; promoted to a real field + UI in a later slice).
DEFAULT_RELATIONSHIP = "chief_of_staff"

# Source markers for provenance / auditability.
SOURCE_USER = "user"        # explicitly stored user configuration
SOURCE_PERSONA = "persona"  # supplied by the selected persona's operational_defaults
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


# ═══════════════════════════════════════════════════════════════════════════════
# M1 — CANONICAL OPERATIONAL PREFERENCE VOCABULARY (Contract 2.1)
# ═══════════════════════════════════════════════════════════════════════════════
# THE single vocabulary. Every entry MUST be delivered into the Executive Context
# Envelope by this projection — `test_personalization_contract.py::T3` fails CI if a
# canonical preference is added here without runtime delivery, and `T4` fails CI if a
# user-editable control exists without an entry here. That pairing is what makes the
# 2026-07-09 class of silent runtime disconnect structurally impossible.
#
#   key            → the envelope path it is delivered at (dotted, under ai_relationship)
#   source         → "prefs" (UserPreferences) | "blueprint" (PersonalOperatingBlueprint)
#   field          → the canonical storage attribute
#   default        → the SYSTEM default (lowest precedence)
#   persona_key    → the key a persona may suggest in `operational_defaults` (None = not
#                    persona-suggestable; consent/boundary truths are never persona-set)
CANONICAL_PREFERENCES = {
    "response_depth": {
        "path": "communication.detail_level", "source": "prefs",
        "field": "cos_response_style", "default": "balanced",
        "persona_key": "response_depth",
    },
    "coaching_style": {
        "path": "communication.coaching_style", "source": "prefs",
        "field": "ai_coaching_style", "default": "supportive", "persona_key": None,
    },
    "accountability": {
        "path": "accountability.level", "source": "blueprint",
        "field": "accountability_style", "default": "standard",
        "persona_key": "accountability",
    },
    "question_frequency": {
        "path": "accountability.question_frequency", "source": "blueprint",
        "field": "question_frequency", "default": "medium",
        "persona_key": "question_frequency",
    },
    "confirm_actions": {
        "path": "action_preferences.confirm_actions", "source": "prefs",
        "field": "assistant_confirm_actions", "default": False, "persona_key": None,
    },
    "event_reflections": {
        "path": "proactivity.event_reflections", "source": "blueprint",
        "field": "event_reflections_enabled", "default": True,
        "persona_key": "event_reflections",
    },
    "relationship_suggestions": {
        "path": "proactivity.relationship_suggestions", "source": "blueprint",
        "field": "relationship_suggestions_enabled", "default": False,
        "persona_key": "relationship_suggestions",
    },
    "knowledge_invitations": {
        "path": "proactivity.knowledge_invitations", "source": "prefs",
        "field": "knowledge_invitations", "default": "occasionally",
        "persona_key": None,
    },
    "sensitivity_topics": {
        "path": "boundaries.sensitivity_topics", "source": "blueprint",
        "field": "sensitivity_tags", "default": [], "persona_key": None,
    },
    "preference_learning": {
        "path": "learning.enabled", "source": "prefs",
        "field": "preference_learning_enabled", "default": True, "persona_key": None,
    },
}

# Sentinel meaning "the user has expressed no explicit choice here".
_UNSET = (None, "")


def _explicit(container, field):
    """The user's EXPLICIT stored value, or None when unset. Never raises."""
    if container is None:
        return None
    try:
        val = getattr(container, field, None)
    except Exception:  # pragma: no cover - defensive
        return None
    if isinstance(val, bool):
        return val                      # False is an explicit choice, not "unset"
    if isinstance(val, (list, tuple)):
        return list(val) if val else None
    return None if val in _UNSET else val


def resolve_persona(user, prefs=None):
    """Resolve the user's PERSONA (Contract 1) — registry row + composed VOICE block.

    Deterministic and resilient. Returns a JSON-safe dict; `instructions` is the
    composed voice the model actually needs (a bare slug is NOT enough — proven
    2026-08-18: the certified runtime received `"texas_rancher"` with no voice at all).
    """
    key = ""
    try:
        key = (getattr(prefs, "ai_coaching_style", "") or "").strip()
    except Exception:  # pragma: no cover - defensive
        key = ""
    try:
        from apps.ai.models import CoachingStyle
        style = CoachingStyle.get_by_key(key) if key else CoachingStyle.get_by_key("")
    except Exception:
        logger.warning("AIRelationship: persona registry unavailable for user=%s",
                       getattr(user, "id", "?"), exc_info=True)
        style = None
    if style is None:
        return {"key": key or None, "name": None, "description": None,
                "category": None, "instructions": "", "source": SOURCE_DEFAULT}
    try:
        instructions = style.composed_instructions()
    except Exception:  # pragma: no cover - defensive
        logger.warning("AIRelationship: persona composition failed", exc_info=True)
        instructions = (style.prompt_instructions or "").strip()
    return {
        "key": style.key,
        "name": style.name,
        "description": style.description,
        "category": style.category or "general",
        "instructions": instructions,
        # `user` only when the stored key actually resolved to THIS persona.
        "source": SOURCE_USER if (key and key == style.key) else SOURCE_DEFAULT,
    }


def resolve_operational_preferences(user, prefs=None, blueprint=None, persona=None):
    """Resolve every canonical Operational Preference under the LOCKED invariant:

        explicit user setting  >  persona default  >  system default

    Returns ``(values, provenance)`` keyed by canonical preference name. A persona may
    SUGGEST a default; it may never override an explicit user choice.
    """
    persona_defaults = {}
    if persona and persona.get("key"):
        try:
            from apps.ai.models import CoachingStyle
            row = CoachingStyle.get_by_key(persona["key"])
            raw = getattr(row, "operational_defaults", None) if row else None
            if isinstance(raw, dict):
                persona_defaults = raw
        except Exception:  # pragma: no cover - defensive
            logger.warning("AIRelationship: persona defaults unavailable", exc_info=True)

    values, provenance = {}, {}
    for name, spec in CANONICAL_PREFERENCES.items():
        container = prefs if spec["source"] == "prefs" else blueprint
        explicit = _explicit(container, spec["field"])
        if explicit is not None:
            values[name], provenance[name] = explicit, SOURCE_USER
            continue
        pkey = spec.get("persona_key")
        if pkey and pkey in persona_defaults and persona_defaults[pkey] not in _UNSET:
            values[name], provenance[name] = persona_defaults[pkey], SOURCE_PERSONA
            continue
        values[name], provenance[name] = spec["default"], SOURCE_DEFAULT
    return values, provenance


def get_ai_relationship(user) -> dict:
    """
    Project the user's AI Relationship into one compact, JSON-safe object.

    This is a deterministic READ-ONLY projection over existing preference data.
    It performs no reasoning and never calls an LLM.
    """
    prefs = _safe_get_preferences(user)
    blueprint = _safe_get_blueprint(user)

    # PERSONA (Contract 1) + the LOCKED precedence resolution (Contract 1.4).
    persona = resolve_persona(user, prefs)
    values, provenance = resolve_operational_preferences(
        user, prefs=prefs, blueprint=blueprint, persona=persona)

    # Provenance is exposed under BOTH the canonical preference name and the envelope
    # PATH, so the UI can honestly explain a conflict ("Texas Rancher usually asks a lot -
    # you've set Low, which wins") whichever key a caller already uses.
    sources = dict(provenance)
    for _name, _spec in CANONICAL_PREFERENCES.items():
        sources[_spec["path"]] = provenance[_name]

    # --- Assistant identity + persona ------------------------------------------
    raw_name = (getattr(prefs, "cos_display_name", "") or "").strip() if prefs else ""
    display_name = raw_name or "Chief of Staff"
    raw_rel = (getattr(prefs, "default_relationship", "") or "").strip() if prefs else ""
    sources["assistant.display_name"] = SOURCE_USER if raw_name else SOURCE_DEFAULT
    sources["assistant.default_relationship"] = SOURCE_USER if raw_rel else SOURCE_DEFAULT
    sources["assistant.persona"] = persona.get("source", SOURCE_DEFAULT)
    assistant = {
        "display_name": display_name,
        "default_relationship": raw_rel or DEFAULT_RELATIONSHIP,
        "persona": {k: persona.get(k) for k in ("key", "name", "description", "category")},
    }

    # --- Communication ---------------------------------------------------------
    communication = {
        "detail_level": values["response_depth"],
        "coaching_style": values["coaching_style"],
    }

    # --- Accountability (firmness / question cadence) --------------------------
    accountability = {
        "level": values["accountability"],
        "question_frequency": values["question_frequency"],
    }

    # --- Proactivity (M1: these had NO certified-runtime consumer before) ------
    proactivity = {
        "event_reflections": bool(values["event_reflections"]),
        "relationship_suggestions": bool(values["relationship_suggestions"]),
        # Configuration + delivery only. The invitations that CONSUME this are M4.
        "knowledge_invitations": values["knowledge_invitations"],
    }

    # --- Boundaries (M1: sensitivity_tags had NO certified-runtime consumer) ---
    topics = values["sensitivity_topics"] or []
    if not isinstance(topics, (list, tuple)):
        topics = [topics]
    boundaries = {
        "sensitivity_topics": [str(t).strip() for t in topics if str(t).strip()],
    }

    # --- Truth & evidence preferences (strict safe defaults; constants) --------
    # `may_invent_facts` is ALWAYS False and is NOT user-settable - surfaced here as
    # data for the model to read, never as a toggle. A persona can never relax this.
    truth_preferences = {
        "authoritative_source": "WLJ",
        "may_invent_facts": False,
        "may_derive_conclusions": True,
        "may_state_hypotheses": True,
    }
    sources["truth_preferences"] = SOURCE_DEFAULT

    action_preferences = {"confirm_actions": bool(values["confirm_actions"])}

    # --- Learning (preference-learning toggle; NOT Learning Mode) --------------
    # Distinct from cos_learning_mode_active (Learning Mode / UAIO suppression).
    learning = {"enabled": bool(values["preference_learning"])}

    # --- Learned communication preferences (active rows only) ------------------
    learned_preferences = _load_learned_preferences(user)

    return {
        "schema_version": AI_RELATIONSHIP_SCHEMA_VERSION,
        "assistant": assistant,
        # The composed persona VOICE the model must actually adopt (Contract 1.6).
        "persona_instructions": persona.get("instructions") or "",
        "communication": communication,
        "accountability": accountability,
        "proactivity": proactivity,
        "boundaries": boundaries,
        "truth_preferences": truth_preferences,
        "action_preferences": action_preferences,
        "learning": learning,
        "learned_preferences": learned_preferences,
        "_sources": sources,
    }
