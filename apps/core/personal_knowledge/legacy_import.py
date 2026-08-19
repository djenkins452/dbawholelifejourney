# ==============================================================================
# File: apps/core/personal_knowledge/legacy_import.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: M3 — bring legacy knowledge forward for review (never trusted)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-19
# ==============================================================================
"""Adopt legacy knowledge into the canonical Personal Knowledge authority.

Sources (Contract 14): `UserPreferences._ai_personal_context` (the encrypted
newline-delimited blob), `UserPreferences.ai_profile` (free-text biography), and
`core.PersonalFact` rows.

FOUR RULES, all enforced here:

1. **Nothing is trusted.** Everything lands as `provenance=legacy_extraction` +
   `review_state=unreviewed`, so it is retrievable and reviewable but can NEVER enter
   standing context until the user accepts it. These statements were extracted by an LLM
   from transcripts, never reviewed, possibly stale and possibly wrong.
2. **Idempotent.** Each import records `attributes.legacy_source` + `legacy_ref`, and a
   re-run skips anything already adopted. Running it twice adds nothing.
3. **Non-destructive.** Legacy source rows/fields are never modified or deleted. M7 owns
   retirement.
4. **Deterministic.** Plain parsing — no model call, no extraction, no inference. M3 is a
   management surface, not learning.
"""

import logging

from apps.core.personal_knowledge import service as pk
from apps.core.personal_knowledge.models import (
    PersonalKnowledgeFact,
    Provenance,
    ReviewState,
    Topic,
)

logger = logging.getLogger(__name__)

SOURCE_AI_CONTEXT = "ai_personal_context"
SOURCE_AI_PROFILE = "ai_profile"
SOURCE_PERSONAL_FACT = "personal_fact"

# A legacy line shorter than this is noise, not a fact ("-", "ok", stray punctuation).
_MIN_STATEMENT = 12
# Defensive ceiling so one pathological blob cannot create thousands of rows.
_MAX_PER_SOURCE = 500

# `PersonalFact.fact_type` -> canonical topic. Anything unmapped lands in OTHER rather
# than being dropped; the user can re-file it.
_FACT_TYPE_TOPIC = {
    "family_relationship": Topic.FAMILY,
    "death": Topic.HISTORY,
    "health_condition": Topic.HEALTH_CONTEXT,
    "life_milestone": Topic.HISTORY,
    "personal_value": Topic.VALUES,
    "life_circumstance": Topic.WORK,
    "preference": Topic.COMMUNICATION,
}


def _already_imported(user, source, ref):
    """True when this exact legacy item was adopted before (idempotency)."""
    return PersonalKnowledgeFact.all_objects.filter(
        user=user,
        attributes__legacy_source=source,
        attributes__legacy_ref=str(ref),
    ).exists()


def _adopt(user, statement, *, source, ref, topic=Topic.OTHER, subject_label="",
           extra_attributes=None):
    """Create ONE unreviewed legacy fact, or skip if already adopted."""
    text = (statement or "").strip()
    if len(text) < _MIN_STATEMENT:
        return None
    if _already_imported(user, source, ref):
        return None
    attributes = {"legacy_source": source, "legacy_ref": str(ref)}
    if extra_attributes:
        attributes.update(extra_attributes)
    try:
        return pk.add_fact(
            user, text, topic=topic, subject_label=subject_label,
            attributes=attributes,
            provenance=Provenance.LEGACY_EXTRACTION,
            review_state=ReviewState.UNREVIEWED,
            confidence=0.5,          # unverified extraction, by definition
        )
    except Exception:
        # One malformed legacy line must never abort the whole adoption.
        logger.warning("PK legacy import: skipped %s ref=%s", source, ref, exc_info=True)
        return None


def _split_profile(text):
    """Split a free-text AI Profile into candidate statements, deterministically.

    Paragraph and bullet aware, then sentence-split long paragraphs. No model call: the
    user reviews the result, so a slightly coarse split is safe and honest, whereas an
    LLM pass here would be M4 learning wearing a migration hat.
    """
    import re
    out = []
    for block in re.split(r"\n\s*\n|\r\n\s*\r\n", text or ""):
        block = block.strip()
        if not block:
            continue
        for line in block.splitlines():
            line = line.strip().lstrip("-•*").strip()
            if not line:
                continue
            if len(line) <= 200:
                out.append(line)
                continue
            # Long prose: split on sentence boundaries, keeping the terminator.
            parts = re.split(r"(?<=[.!?])\s+", line)
            buf = ""
            for part in parts:
                if len(buf) + len(part) < 200:
                    buf = f"{buf} {part}".strip()
                else:
                    if buf:
                        out.append(buf)
                    buf = part
            if buf:
                out.append(buf)
    return out


def import_legacy_knowledge(user, *, dry_run=False):
    """Adopt everything reviewable from this user's legacy stores. Idempotent.

    Returns a per-source summary of what was adopted and what was already present.
    Never deletes or edits a legacy source.
    """
    summary = {s: {"adopted": 0, "already": 0, "available": 0}
               for s in (SOURCE_AI_CONTEXT, SOURCE_AI_PROFILE, SOURCE_PERSONAL_FACT)}

    prefs = getattr(user, "preferences", None)

    # ── 1. the newline-delimited learned-context blob ─────────────────────────
    try:
        blob = (getattr(prefs, "ai_personal_context", "") or "") if prefs else ""
        lines = [ln.strip() for ln in blob.split("\n") if ln.strip()]
        summary[SOURCE_AI_CONTEXT]["available"] = len(lines)
        for index, line in enumerate(lines[:_MAX_PER_SOURCE]):
            if _already_imported(user, SOURCE_AI_CONTEXT, index):
                summary[SOURCE_AI_CONTEXT]["already"] += 1
                continue
            if dry_run:
                summary[SOURCE_AI_CONTEXT]["adopted"] += 1
                continue
            if _adopt(user, line, source=SOURCE_AI_CONTEXT, ref=index):
                summary[SOURCE_AI_CONTEXT]["adopted"] += 1
    except Exception:
        logger.warning("PK legacy import: ai_personal_context failed user=%s",
                       getattr(user, "id", None), exc_info=True)

    # ── 2. the hand-maintained AI Profile ─────────────────────────────────────
    try:
        profile = (getattr(prefs, "ai_profile", "") or "") if prefs else ""
        statements = _split_profile(profile)
        summary[SOURCE_AI_PROFILE]["available"] = len(statements)
        for index, statement in enumerate(statements[:_MAX_PER_SOURCE]):
            if _already_imported(user, SOURCE_AI_PROFILE, index):
                summary[SOURCE_AI_PROFILE]["already"] += 1
                continue
            if dry_run:
                summary[SOURCE_AI_PROFILE]["adopted"] += 1
                continue
            if _adopt(user, statement, source=SOURCE_AI_PROFILE, ref=index):
                summary[SOURCE_AI_PROFILE]["adopted"] += 1
    except Exception:
        logger.warning("PK legacy import: ai_profile failed user=%s",
                       getattr(user, "id", None), exc_info=True)

    # ── 3. structured PersonalFact rows ───────────────────────────────────────
    try:
        from apps.core.ai_memory.models import PersonalFact
        rows = list(PersonalFact.objects.filter(user=user, is_active=True)[:_MAX_PER_SOURCE])
        summary[SOURCE_PERSONAL_FACT]["available"] = len(rows)
        for row in rows:
            if _already_imported(user, SOURCE_PERSONAL_FACT, row.pk):
                summary[SOURCE_PERSONAL_FACT]["already"] += 1
                continue
            if dry_run:
                summary[SOURCE_PERSONAL_FACT]["adopted"] += 1
                continue
            adopted = _adopt(
                user, row.fact_text, source=SOURCE_PERSONAL_FACT, ref=row.pk,
                topic=_FACT_TYPE_TOPIC.get(row.fact_type, Topic.OTHER),
                subject_label=(row.subject_name or "").strip(),
                extra_attributes=({"relation": row.relationship.strip()}
                                  if (row.relationship or "").strip() else None),
            )
            if adopted:
                summary[SOURCE_PERSONAL_FACT]["adopted"] += 1
    except Exception:
        logger.warning("PK legacy import: PersonalFact failed user=%s",
                       getattr(user, "id", None), exc_info=True)

    total = sum(v["adopted"] for v in summary.values())
    if total and not dry_run:
        logger.info("PK legacy import: adopted %d fact(s) user=%s", total,
                    getattr(user, "id", None))
    return summary


def pending_review_count(user):
    """How many adopted legacy facts still await the user's review."""
    return pk.active_facts(user).filter(
        provenance=Provenance.LEGACY_EXTRACTION,
        review_state=ReviewState.UNREVIEWED,
    ).count()


def has_legacy_material(user):
    """True when the user has legacy knowledge worth offering to review.

    Read-only: it never adopts. Used to decide whether About Me should offer the review
    at all, so a user with no history never sees a prompt about it.
    """
    summary = import_legacy_knowledge(user, dry_run=True)
    return any(v["available"] for v in summary.values())
