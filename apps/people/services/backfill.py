"""
Person Consolidation identity backfill — the ONE population path (Phase 0c).

Feature-agnostic by injection: the caller (a data migration) passes the legacy source
model classes; this module reads plain field values from them and drives the canonical
seam (`reconciliation.ingest_source_person`). The Core Person domain never imports a
feature app — the feature-table reads live here, at the migration layer.

Two phases, deliberately separate identity domains:
  * 0c-A  living contacts  — relationships.Person (A) + ai_relationships.Person (C),
          NAME_IDENTITY matching (unify the same human across A and C, never guess).
  * 0c-B  legacy genealogy — legacy.Person (B), SOURCE_LINK_ONLY (create-distinct;
          same-name individuals are normal; GEDCOM identity = xref, never name).

Every function is:
  * idempotent   — re-running relinks nothing (PersonSourceLink is the key).
  * dedup-safe   — one match links, ≥2 route to review, zero creates.
  * preservation-safe — never overwrites a survivor field; never deletes a legacy row.
  * auditable    — returns per-source counts; the seam records PersonEvents.
  * resilient    — a single bad row is counted and skipped, never aborts the batch.

Nothing here redirects a consumer or mutates a legacy table.
"""
import logging

from ..models import PersonMembership, PersonOrigin
from . import reconciliation as recon

logger = logging.getLogger(__name__)


def _split_name(display_name):
    """Best-effort first/last from a single display string. Only used to seed a NEW
    canonical person's name fields so first-name resolution works; never used to match."""
    parts = (display_name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _tally(summary, outcome):
    summary[outcome] = summary.get(outcome, 0) + 1


def backfill_relationships(PersonA, *, user_ids=None):
    """A = relationships.Person (owner-scoped, SoftDelete `status`). Real contacts."""
    summary = {"source": "relationships", "seen": 0, "created": 0, "linked": 0,
               "already_linked": 0, "review": 0, "errors": 0}
    qs = PersonA.objects.filter(status="active")
    if user_ids is not None:
        qs = qs.filter(owner_id__in=user_ids)
    for row in qs.iterator():
        summary["seen"] += 1
        try:
            _person, outcome = recon.ingest_source_person(
                user_id_to_user(PersonA, row.owner_id),
                source_domain="relationships", source_pk=row.pk,
                display_name=row.display_name or "",
                first_name=row.first_name or "", last_name=row.last_name or "",
                email=row.email or "", phone=row.phone or "",
                origin=PersonOrigin.CONTACT_IMPORT,
                membership_via=PersonMembership.Grant.CONTACT_IMPORT,
                match_mode=recon.MATCH_NAME_IDENTITY,
            )
            _tally(summary, outcome)
        except Exception:
            summary["errors"] += 1
            logger.warning("backfill relationships pk=%s failed", row.pk, exc_info=True)
    return summary


def backfill_ai_relationships(PersonC, *, user_ids=None):
    """C = ai_relationships.Person (user-scoped, `is_active` bool, display_name only).
    Extraction shadows — unify with A by NAME_IDENTITY (bare first name → contact)."""
    summary = {"source": "ai_relationships", "seen": 0, "created": 0, "linked": 0,
               "already_linked": 0, "review": 0, "errors": 0}
    qs = PersonC.objects.filter(is_active=True)
    if user_ids is not None:
        qs = qs.filter(user_id__in=user_ids)
    for row in qs.iterator():
        summary["seen"] += 1
        try:
            first, last = _split_name(row.display_name)
            _person, outcome = recon.ingest_source_person(
                user_id_to_user(PersonC, row.user_id),
                source_domain="ai_relationships", source_pk=row.pk,
                display_name=row.display_name or "",
                first_name=first, last_name=last,
                origin=PersonOrigin.EXTRACTION,
                membership_via=PersonMembership.Grant.MENTION,
                match_mode=recon.MATCH_NAME_IDENTITY,
            )
            _tally(summary, outcome)
        except Exception:
            summary["errors"] += 1
            logger.warning("backfill ai_relationships pk=%s failed", row.pk, exc_info=True)
    return summary


def user_id_to_user(SourceModel, user_id):
    """Resolve the FK target (a real User) the canonical services require. Works for
    both real and historical source models by hopping to the concrete user model."""
    from django.contrib.auth import get_user_model
    return get_user_model().objects.get(pk=user_id)


def backfill_living_people(PersonA, PersonC, *, user_ids=None):
    """Phase 0c-A: A then C (order matters — contacts first, so C's bare first names
    unify to them). Returns both per-source summaries."""
    a = backfill_relationships(PersonA, user_ids=user_ids)
    c = backfill_ai_relationships(PersonC, user_ids=user_ids)
    logger.info("[0c-A] relationships=%s ai_relationships=%s", a, c)
    return {"relationships": a, "ai_relationships": c}
