# ==============================================================================
# File: apps/ai/cos_services/personal_truth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Personal Truth — the canonical PROJECTION of durable, cross-module,
#   explicitly-stored user facts the Chief of Staff reasons FROM every turn.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-17
# ==============================================================================
"""
Personal Truth (Slice 1 — Explicit Durable Facts)
=================================================

A deterministic, cross-domain, READ-ONLY projection of the durable user facts that
transcend any one module — goals/targets, conditions, medications, relationship, and
declared priorities — so the model reasons FROM "who this user is" instead of generic
knowledge (the personalization defect, 2026-07-17).

CONTRACT (what Personal Truth IS): deterministic · cross-domain · read-only · composed
from module-owned AUTHORITATIVE facts · provenance-bearing · available in standing
context AND through a targeted tool.

CONTRACT (what it is NOT): a new source of authority · a replacement for DomainTruth or
module entity/history surfaces · an LLM-generated profile · a reasoning/recommendation
engine · a place to duplicate module data · a key-value dumping ground.

Modules retain ownership. This layer READS and PROJECTS their facts — it never owns,
stores authority, or resolves a contradiction with AI. ONE composer feeds BOTH the
standing-context view and the get_user_truth tool (no duplicate retrieval logic).

SLICE 1 = EXPLICITLY STORED facts only. NO behavioral derivations (favorite foods,
preferred shake, inferred routines) — those are a later derived-fact slice with their
own provenance/confidence/freshness/invalidation rules.

Request-path safety: composition is a bounded handful of small per-user reads, each
wrapped so ONE failing module never erases the others; the result is cache-first
(slow TTL — durable facts change slowly). Missing facts are stated, never invented.
"""
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

PERSONAL_TRUTH_SCHEMA_VERSION = "1.0"
_TTL = 600  # seconds — durable facts change slowly; cache-first, TTL refresh
_PROVENANCE_EXPLICIT = "explicit"

# Sensitivity classification (introduced here — WLJ had no formal one). Conservative:
# medical facts are the sensitive class; everything else is standard.
_SENS_MEDICAL = "medical"
_SENS_STANDARD = "standard"

# Standing-context caps — keep the always-on profile bounded (must not inflate prompts).
_CAP_CONDITIONS = 6
_CAP_MEDICATIONS = 10
_CAP_GOALS = 3
_CAP_PRIORITIES = 3


def _key(uid):
    return f"wlj:personal_truth:v1:{uid}"


def _fact(key, value, *, module, source, unit=None, updated_at=None,
          sensitivity=_SENS_STANDARD, standing=True):
    """Build one data-contract fact. Every fact carries its owning module, its
    authoritative source model/surface, explicit provenance, an optional last-updated
    timestamp, a sensitivity class, and whether it belongs in standing context.
    Ownership/provenance are never flattened away."""
    out = {
        "key": key,
        "value": value,
        "module": module,
        "source": source,
        "provenance": _PROVENANCE_EXPLICIT,
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat")
        else updated_at,
        "sensitivity": sensitivity,
        "standing": standing,
    }
    if unit is not None:
        out["unit"] = unit
    return out


# ── per-source projectors (each RESILIENT — never raises) ────────────────────
def _relationship_section(user):
    try:
        from apps.ai.cos_services.ai_relationship import get_ai_relationship
        rel = get_ai_relationship(user) or {}
        assistant = rel.get("assistant") or {}
        comm = rel.get("communication") or {}
        facts = []

        def _val(tag):
            # get_ai_relationship returns {"value":..., "source":...} tags.
            return tag.get("value") if isinstance(tag, dict) else tag

        name = _val(assistant.get("display_name"))
        mode = _val(assistant.get("default_relationship"))
        coaching = _val(comm.get("coaching_style"))
        detail = _val(comm.get("detail_level"))
        if name:
            facts.append(_fact("relationship.assistant_name", name,
                               module="ai_relationship", source="cos_services.ai_relationship"))
        if mode:
            facts.append(_fact("relationship.mode", mode,
                               module="ai_relationship", source="cos_services.ai_relationship"))
        if coaching:
            facts.append(_fact("relationship.coaching_style", coaching,
                               module="ai_relationship", source="cos_services.ai_relationship"))
        if detail:
            facts.append(_fact("relationship.communication_style", detail,
                               module="ai_relationship", source="cos_services.ai_relationship"))
        return {"status": "ready" if facts else "empty", "facts": facts}
    except Exception:
        logger.warning("personal_truth: relationship section failed", exc_info=True)
        return {"status": "error", "facts": []}


def _active_nutrition_goals(user):
    """The currently-effective NutritionGoals row (canonical target authority — the
    source get_foundational_health_facts derives from), or None."""
    from apps.health.models import NutritionGoals
    from apps.core.utils import get_user_today
    from datetime import date as _date
    today = get_user_today(user) or _date.today()
    qs = (NutritionGoals.objects.filter(user=user, status="active",
                                        effective_from__lte=today)
          .order_by("-effective_from"))
    for g in qs:
        if g.effective_until is None or g.effective_until >= today:
            return g
    return qs.first()


def _nutrition_section(user):
    try:
        g = _active_nutrition_goals(user)
        facts, contradictions = [], []
        if g is not None:
            src = "health.NutritionGoals"
            for key, attr, unit in (
                ("nutrition.calorie_target", "daily_calorie_target", "kcal"),
                ("nutrition.protein_target", "daily_protein_target_g", "g"),
                ("nutrition.carb_target", "daily_carb_target_g", "g"),
                ("nutrition.fat_target", "daily_fat_target_g", "g"),
            ):
                v = getattr(g, attr, None)
                if v is not None:
                    facts.append(_fact(key, float(v), module="nutrition", source=src,
                                       unit=unit, updated_at=g.updated_at))
            restr = _clean_list(getattr(g, "dietary_preferences", None))
            if restr:
                facts.append(_fact("nutrition.dietary_restrictions", restr,
                                   module="nutrition", source=src, updated_at=g.updated_at))
            allergies = _clean_list(getattr(g, "allergies", None))
            if allergies:
                facts.append(_fact("nutrition.allergies", allergies, module="nutrition",
                                   source=src, updated_at=g.updated_at,
                                   sensitivity=_SENS_MEDICAL))
        # CONFLICT POLICY — targets ALSO live in meals.DietaryProfile. NutritionGoals is
        # canonical (feeds foundational facts). Never silently choose between authorities:
        # if the secondary store disagrees, represent it as a CONTRADICTION, not a pick.
        contradictions = _nutrition_target_contradictions(user, g)
        return {"status": "ready" if facts else "empty", "facts": facts,
                "contradictions": contradictions}
    except Exception:
        logger.warning("personal_truth: nutrition section failed", exc_info=True)
        return {"status": "error", "facts": [], "contradictions": []}


def _nutrition_target_contradictions(user, goals):
    """Compare NutritionGoals (canonical) with meals.DietaryProfile (secondary) for the
    SAME target. Equal or missing → no conflict. Different → an explicit contradiction."""
    out = []
    try:
        from apps.meals.models import DietaryProfile
        dp = DietaryProfile.objects.filter(user=user, status="active").order_by("-updated_at").first()
        if dp is None or goals is None:
            return out
        pairs = (
            ("nutrition.calorie_target", "daily_calorie_target", "calorie_target"),
            ("nutrition.protein_target", "daily_protein_target_g", "protein_target_daily"),
            ("nutrition.carb_target", "daily_carb_target_g", "carb_limit_daily"),
            ("nutrition.fat_target", "daily_fat_target_g", "fat_limit_daily"),
        )
        for key, g_attr, d_attr in pairs:
            gv, dv = getattr(goals, g_attr, None), getattr(dp, d_attr, None)
            if gv is not None and dv is not None and float(gv) != float(dv):
                out.append({
                    "key": key,
                    "canonical": {"source": "health.NutritionGoals", "value": float(gv)},
                    "conflicting": {"source": "meals.DietaryProfile", "value": float(dv)},
                    "resolution": "canonical_module_wins",  # deterministic; NOT AI-resolved
                    "note": ("Two stores disagree; NutritionGoals is authoritative. "
                             "Surfaced as a contradiction, not silently chosen."),
                })
    except Exception:
        logger.warning("personal_truth: nutrition contradiction check failed", exc_info=True)
    return out


def _health_section(user):
    """Active medical conditions + active medications (referenced from the authoritative
    medicine surface — not re-derived here)."""
    facts = []
    try:
        from apps.health.models import MedicalCondition
        conds = (MedicalCondition.objects.filter(user=user, status="active",
                                                 condition_status="active_condition")
                 .order_by("-diagnosed_date")[: _CAP_CONDITIONS + 5])
        names = [c.name for c in conds if (c.name or "").strip()]
        if names:
            facts.append(_fact("health.active_conditions", names[: _CAP_CONDITIONS],
                               module="medical", source="health.MedicalCondition",
                               sensitivity=_SENS_MEDICAL))
    except Exception:
        logger.warning("personal_truth: conditions failed", exc_info=True)
    try:
        from apps.health.services.medicine_queries import MedicineQueries
        meds = MedicineQueries.active_names(user) or []
        if meds:
            facts.append(_fact("health.active_medications", meds[: _CAP_MEDICATIONS],
                               module="medicine", source="health.MedicineQueries.active",
                               sensitivity=_SENS_MEDICAL))
    except Exception:
        logger.warning("personal_truth: medications failed", exc_info=True)
    return {"status": "ready" if facts else "empty", "facts": facts}


def _goals_section(user):
    try:
        from apps.purpose.models import LifeGoal
        goals = (LifeGoal.objects.filter(user=user, status="active")
                 .order_by("-is_primary_mission", "-is_foundational", "-updated_at")
                 [: _CAP_GOALS + 3])
        facts = []
        for g in goals[: _CAP_GOALS]:
            facts.append(_fact(
                "purpose.active_goal",
                {"title": g.title, "primary_mission": bool(g.is_primary_mission),
                 "timeframe": getattr(g, "timeframe", None) or None},
                module="purpose", source="purpose.LifeGoal", updated_at=g.updated_at))
        return {"status": "ready" if facts else "empty", "facts": facts}
    except Exception:
        logger.warning("personal_truth: goals failed", exc_info=True)
        return {"status": "error", "facts": []}


def _priorities_section(user):
    try:
        from apps.core.blueprint.models import UserPriorityProfile
        rows = (UserPriorityProfile.objects.filter(user=user)
                .exclude(declared_priority_level__isnull=True)
                .order_by("-importance_weight", "-updated_at")[: _CAP_PRIORITIES + 3])
        facts = []
        for r in rows[: _CAP_PRIORITIES]:
            facts.append(_fact(
                "priority.declared",
                {"area": r.module_key, "level": r.declared_priority_level,
                 "reason": (r.declared_reason or None)},
                module="core", source="core.UserPriorityProfile", updated_at=r.updated_at))
        return {"status": "ready" if facts else "empty", "facts": facts}
    except Exception:
        logger.warning("personal_truth: priorities failed", exc_info=True)
        return {"status": "error", "facts": []}


def _clean_list(v):
    """A JSON/list field → a bounded clean list of strings, or []."""
    if not v:
        return []
    if isinstance(v, str):
        parts = [p.strip() for p in v.replace(";", ",").split(",")]
        return [p for p in parts if p][:12]
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()][:12]
    return []


# ── the ONE canonical composer (feeds BOTH standing context and the tool) ────
def build_personal_truth(user, *, use_cache=True):
    """Compose the full durable-fact projection for `user`. Cache-first (slow TTL);
    resilient per-source (one failing module never erases the others). Deterministic —
    NO LLM, NO derivation. Returns a JSON-safe dict:

        {status, schema_version, sections:{relationship,nutrition,health,goals,
         priorities}, contradictions:[...], generated_at}
    """
    uid = getattr(user, "id", None)
    if use_cache and uid is not None:
        cached = cache.get(_key(uid))
        if cached is not None:
            return cached

    sections = {
        "relationship": _relationship_section(user),
        "nutrition": _nutrition_section(user),
        "health": _health_section(user),
        "goals": _goals_section(user),
        "priorities": _priorities_section(user),
    }
    contradictions = []
    contradictions.extend(sections["nutrition"].pop("contradictions", []) or [])

    from django.utils import timezone
    any_ready = any(s.get("status") == "ready" for s in sections.values())
    payload = {
        "status": "ready" if any_ready else "empty",
        "schema_version": PERSONAL_TRUTH_SCHEMA_VERSION,
        "provenance": _PROVENANCE_EXPLICIT,   # Slice 1: explicit stored facts only
        "sections": sections,
        "contradictions": contradictions,
        "generated_at": timezone.now().isoformat(),
    }
    if use_cache and uid is not None:
        try:
            cache.set(_key(uid), payload, _TTL)
        except Exception:
            logger.debug("personal_truth: cache set skipped", exc_info=True)
    return payload


def personal_truth_for_context(profile):
    """The bounded STANDING-CONTEXT view — the highest-value facts the CoS should know
    every turn, kept compact so it does not inflate the prompt. Same composer output;
    this only SELECTS + flattens (no new retrieval). Standing-appropriate facts only."""
    if not isinstance(profile, dict):
        return {"status": "empty"}
    out = {"status": profile.get("status", "empty"),
           "provenance": _PROVENANCE_EXPLICIT}
    sections = profile.get("sections") or {}
    compact = {}
    for name, sec in sections.items():
        vals = [{"key": f["key"], "value": f["value"], "source": f["source"]}
                for f in (sec.get("facts") or []) if f.get("standing")]
        if vals:
            compact[name] = vals
    out["facts"] = compact
    if profile.get("contradictions"):
        # Contradictions are surfaced, never hidden — but compactly.
        out["contradictions"] = [
            {"key": c["key"], "canonical": c["canonical"], "conflicting": c["conflicting"]}
            for c in profile["contradictions"]
        ]
    out["note"] = ("Durable, explicitly-stored user facts to reason FROM (targets, "
                   "conditions, medications, relationship, priorities). Deterministic; "
                   "not inferred. For the full profile call get_user_truth.")
    return out


def get_user_truth(user, section=None):
    """Targeted retrieval tool surface. Returns the FULL Personal Truth projection, or a
    single named section. Uses the SAME `build_personal_truth` composer — no duplicate
    retrieval logic. JSON-safe; wrappable by the Model Interface truth envelope."""
    profile = build_personal_truth(user)
    if section:
        sec = (profile.get("sections") or {}).get(section.strip().lower())
        if sec is None:
            return {"status": "unsupported", "section": section,
                    "available_sections": sorted((profile.get("sections") or {}).keys())}
        return {"status": sec.get("status", "empty"), "section": section,
                "schema_version": PERSONAL_TRUTH_SCHEMA_VERSION,
                "provenance": _PROVENANCE_EXPLICIT, "facts": sec.get("facts", [])}
    return profile
