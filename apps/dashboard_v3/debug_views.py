"""TEMPORARY debug endpoint — raw truth for the "Purpose recommendation" card.

Purpose (2026-07-06 investigation): production still shows the OLD milestone
commentary on the dashboard's Purpose accountability card. This endpoint returns
the RAW deterministic record the card actually renders — no composition, no
summarization, no regeneration — so we can see exactly which DB row, which
builder, when it was generated, whether it is persisted/cached, and the code
path.

It does NOT change any production logic. It replicates the card's real selection
query verbatim (``apps/dashboard_v3/services/composer.py :: _build_accountability_cards``)
and reports what that query returns.

Remove after the investigation concludes.
"""
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse

User = get_user_model()

# The EXACT render surface (confirmed by tracing the live path):
#   DashboardV3View → build_dashboard_v3_context → _build_accountability_cards
#   → GuidanceItem.objects.filter(user=user, is_active=True)
#         .order_by("priority", "-created_at")
#   → [g for g in fresh_guidance if g.module == "purpose"][0]
#   → recommendation = {id, title, message: _strip_leading_greeting(message), priority}
#   → templates/dashboard_v3/sections/accountability_cards.html
_RENDER_PATH = [
    "DashboardV3View.get_context_data  (apps/dashboard_v3/views.py)",
    "build_dashboard_v3_context  (apps/dashboard_v3/services/composer.py)",
    "_build_accountability_cards  (composer.py: GuidanceItem.filter(is_active=True)"
    ".order_by('priority','-created_at') → module=='purpose' → [0])",
    "recommendation dict {id,title,message:_strip_leading_greeting(message),priority}",
    "templates/dashboard_v3/sections/accountability_cards.html  (card.recommendation)",
    "HTML",
]


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def _generator_for(item):
    """Which builder/generator produced this row — derived from its identity,
    not guessed."""
    key = item.dedupe_key or ""
    meta = item.metadata or {}
    cat = meta.get("category")
    if key.startswith("cos_event:win:milestone:"):
        return ("apps/ai/significant_events.py :: _persist_major_win "
                "(Significant Event Pipeline — MAJOR_WIN)")
    if key.startswith("cos_event:win:"):
        return "apps/ai/cos_event_engine.py :: run_cos_event_engine (MAJOR_WIN)"
    if key.startswith("cos_event:"):
        return f"apps/ai/cos_event_engine.py :: run_cos_event_engine ({cat or 'event'})"
    src = item.source or "?"
    return f"source={src} guidance_type={item.guidance_type or '?'}"


def _milestone_id_from(item):
    m = re.match(r"cos_event:win:milestone:(\d+)$", item.dedupe_key or "")
    return int(m.group(1)) if m else (item.metadata or {}).get("milestone_id")


def _goal_id_for(milestone_id):
    if not milestone_id:
        return None
    try:
        from apps.purpose.models import GoalMilestone
        ms = GoalMilestone.objects.filter(pk=milestone_id).only("goal_id").first()
        return ms.goal_id if ms is not None else None
    except Exception:
        return None


def _raw_record(item, *, rendered):
    """The RAW row — every field the card path can see, plus the exact displayed
    message after the render-time greeting strip. No composition."""
    meta = dict(item.metadata or {})
    milestone_id = _milestone_id_from(item)
    goal_id = _goal_id_for(milestone_id)

    # The exact transform the card applies to message before display.
    displayed = item.message
    try:
        from apps.dashboard_v3.services.composer import _strip_leading_greeting
        displayed = _strip_leading_greeting(item.message)
    except Exception:
        pass

    return {
        "is_the_rendered_record": rendered,
        "source": "core_guidance_item (apps.core.ai_guidance.models.GuidanceItem)",
        "builder": "apps/dashboard_v3/services/composer.py :: _build_accountability_cards",
        "generator": _generator_for(item),
        "record_id": item.id,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
        "event_type": meta.get("category") or item.guidance_type,
        "module": item.module,
        "priority": item.priority,
        "is_active": item.is_active,
        "is_read": item.is_read,
        "dismissed_at": _iso(item.dismissed_at),
        "expires_at": _iso(item.expires_at),
        "dedupe_key": item.dedupe_key,
        "source_field": item.source,
        "guidance_type": item.guidance_type,
        "title": item.title,
        # RAW stored message (what+why+wd joined at persist time).
        "message": item.message,
        # What the card ACTUALLY displays after _strip_leading_greeting().
        "displayed_message": displayed,
        # The three parts as stored in metadata by persist_event().
        "what_happened": meta.get("what_happened"),
        "why_it_matters": meta.get("why_it_matters"),
        "what_to_do": meta.get("what_to_do"),
        "mission_id": goal_id,
        "goal_id": goal_id,
        "milestone_id": milestone_id,
        "metadata_first_seen": meta.get("first_seen"),
        "metadata_last_seen": meta.get("last_seen"),
        "occurrence_count": meta.get("occurrence_count"),
        "significant_event": meta.get("significant_event"),
        "mission_progress": meta.get("mission_progress"),
        "next_milestone": meta.get("next_milestone"),
        "is_persisted": True,
        "is_cached": False,
    }


@login_required
def debug_purpose_recommendation(request):
    """Return the raw deterministic data behind the Purpose recommendation card.

    Authenticated. Uses the requesting user by default; a superuser may inspect
    another account via ?user_id= or ?email=.
    """
    from apps.core.ai_guidance.models import GuidanceItem

    user = request.user
    if request.user.is_superuser:
        uid = request.GET.get("user_id")
        email = request.GET.get("email")
        if uid:
            user = User.objects.filter(pk=uid).first() or user
        elif email:
            user = User.objects.filter(email=email).first() or user

    # ── EXACT replication of the card's selection (composer.py:2088-2123) ──
    fresh_guidance = list(
        GuidanceItem.objects.filter(user=user, is_active=True)
        .order_by("priority", "-created_at")
    )
    purpose_candidates = [g for g in fresh_guidance if g.module == "purpose"]
    rendered = purpose_candidates[0] if purpose_candidates else None

    # ── Cache probes — prove whether ANYTHING cached feeds this card. The live
    #    trace shows NO cache between query and render; we probe the known keys
    #    anyway and report presence, so "is it cached" is answered with evidence.
    cache_probes = {}
    for key in (
        f"dashboard_v1:{user.id}:purpose",   # DashboardCacheService (legacy dash)
        f"wlj:user_state:{user.id}",         # SAE snapshot
        f"wlj:cos_context:{user.id}",        # CoS context readiness cache
    ):
        val = cache.get(key)
        cache_probes[key] = {
            "present": val is not None,
            "type": type(val).__name__ if val is not None else None,
        }

    # ── The milestone MAJOR_WIN row(s) specifically — the smoking gun, whether
    #    or not it is the one currently outranking others for the card. ──
    win_rows = list(
        GuidanceItem.objects.filter(
            user=user, dedupe_key__startswith="cos_event:win:milestone:")
        .order_by("-updated_at")
    )

    payload = {
        "user_id": user.id,
        "user_email": getattr(user, "email", None),
        "render_path": _RENDER_PATH,
        "cache_between_query_and_render": False,
        "cache_probes": cache_probes,

        # THE record the card renders (module=="purpose", first by
        # priority asc, then newest). None if no purpose guidance is active.
        "rendered_record": _raw_record(rendered, rendered=True) if rendered else None,

        # Every active purpose-module row, in the EXACT render order — so a
        # stale row outranking a fresh one is visible.
        "purpose_candidates_in_render_order": [
            _raw_record(g, rendered=(g is rendered)) for g in purpose_candidates
        ],

        # Milestone MAJOR_WIN rows regardless of ranking (created/updated
        # timestamps reveal if the message predates the fix deploy).
        "milestone_win_rows": [
            _raw_record(g, rendered=(g is rendered)) for g in win_rows
        ],

        "counts": {
            "active_guidance_total": len(fresh_guidance),
            "active_purpose_guidance": len(purpose_candidates),
            "milestone_win_rows": len(win_rows),
        },
    }
    return JsonResponse(payload, json_dumps_params={"indent": 2})
