# ==============================================================================
# File: apps/ai/cos_services/follow_up.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Durable Conversational Follow-Through (Proactive Product Phase 2, M2).
#   Two halves of the ownership boundary:
#     - schedule_follow_up(): the CoS ACTION that persists a promised follow-up as a
#       deterministic ConversationFollowUp commitment (WLJ owns the time/subject/status).
#       Created ONLY by an explicit tool call — prose never creates scheduled state.
#     - deliver_due_follow_ups_for_user(): the PGS-cycle scanner that, when a follow-up
#       comes due, authors it FRESH from CURRENT truth via the certified CoS (never replays
#       stored prose) and delivers it through the existing proactive machinery. Duplicate-safe
#       via an atomic status claim; respects the proactive preference; never raises.
#   Reuses: the existing PGS scheduler, ModelInterfaceService.generate (certified reasoning),
#   _create_proactive_message (delivery), and the cost-accounting seam (traffic=proactive).
# ==============================================================================
import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

# How far out a follow-up may be scheduled (sanity bound; keeps "later today / tonight /
# tomorrow / this week" natural without becoming a long-term reminder system).
MAX_HORIZON_DAYS = 14
# Cap deliveries per user per PGS pass so due follow-ups never stack into a burst.
MAX_DELIVER_PER_CYCLE = 1


def _follow_up_directive(topic):
    return (
        f"Earlier, Danny asked you to follow up with him about: {topic}. It is now that time. "
        "Before you say anything, check his CURRENT truth relevant to this. If the truth shows "
        "he has ALREADY done or handled it, acknowledge it warmly and close the loop — do NOT "
        "nag or re-ask. If it is still open, follow up briefly and naturally, the way a trusted "
        "chief of staff gently returns to something he asked you to check on. Keep it to THIS one "
        "thing — do not open a broad review or a day briefing. Speak to Danny directly, briefly."
    )


def _parse_local_iso(when_local):
    """Tolerantly parse the model-computed local datetime string. Python 3.9's
    datetime.fromisoformat is strict (no 'Z', limited offsets), and the model may emit a
    'Z' suffix, an offset, a space separator, or a date-only value — accept them all. Returns
    an aware/naive datetime, or None if unparseable. Never raises."""
    s = str(when_local).strip()
    if not s:
        return None
    candidates = [s]
    if s.endswith("Z"):
        candidates.append(s[:-1] + "+00:00")
    candidates.append(s.replace(" ", "T"))
    for c in candidates:
        try:
            return datetime.fromisoformat(c)
        except (ValueError, TypeError):
            continue
    # Last resort: strptime a few common shapes.
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.replace("Z", ""), fmt)
        except (ValueError, TypeError):
            continue
    return None


def schedule_follow_up(user, conversation, *, topic, when_local, when_label=None,
                       subject_ref=None, origin=None):
    """Persist a promised follow-up. `when_local` is an ISO-8601 datetime the MODEL computed
    in Danny's local time (it has the current time in context) — WLJ only validates + stores;
    it does not do fuzzy NLP time parsing (reasoning belongs to the model). Returns an honest
    status dict. Never raises."""
    from apps.ai.models import ConversationFollowUp
    from apps.core.utils import get_user_now, _get_user_tz

    topic = (topic or "").strip()
    if not topic:
        return {"status": "needs_info", "message": "What should I follow up about?"}
    if not when_local:
        return {"status": "needs_info", "message": "When should I follow up?"}

    dt = _parse_local_iso(when_local)
    if dt is None:
        return {"status": "needs_info",
                "message": "I need a concrete time to follow up (e.g. later today or tomorrow)."}

    try:
        tz = _get_user_tz(user)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        now = get_user_now(user)
    except Exception:
        logger.warning("FOLLOW_UP tz resolve failed user=%s", user.pk, exc_info=True)
        return {"status": "error", "message": "I couldn't work out the timing just now."}

    if dt <= now + timedelta(seconds=30):
        return {"status": "needs_info",
                "message": "That time has already passed — when would you like me to check back?"}
    if dt > now + timedelta(days=MAX_HORIZON_DAYS):
        return {"status": "needs_info",
                "message": (f"I can follow up within about {MAX_HORIZON_DAYS} days — "
                            "for anything longer, set a reminder or task instead.")}

    try:
        # datetime.timezone.utc (NOT django.utils.timezone.utc — removed in Django 5.x).
        due_at_utc = dt.astimezone(dt_timezone.utc)
        # Supersede any prior PENDING follow-up on the SAME durable subject (keep one live
        # promise per subject); otherwise let distinct topics coexist.
        if subject_ref:
            (ConversationFollowUp.objects
             .filter(user=user, status=ConversationFollowUp.STATUS_PENDING,
                     subject_ref=subject_ref)
             .update(status=ConversationFollowUp.STATUS_RESOLVED, resolved_at=timezone.now()))
        fu = ConversationFollowUp.objects.create(
            user=user,
            conversation=conversation if getattr(conversation, "pk", None) else None,
            due_at=due_at_utc,
            topic=topic[:280],
            subject_ref=(subject_ref or "")[:120],
            origin=origin or ConversationFollowUp.ORIGIN_USER,
            metadata={"when_label": when_label or ""},
        )
    except Exception:
        logger.warning("FOLLOW_UP schedule write failed user=%s", user.pk, exc_info=True)
        return {"status": "error",
                "message": "I couldn't set that follow-up up just now."}
    logger.info("FOLLOW_UP_SCHEDULED user=%s id=%s due=%s topic=%s",
                user.pk, fu.pk, due_at_utc.isoformat(), topic[:60])
    return {"status": "scheduled", "follow_up_id": fu.pk,
            "due_at": due_at_utc.isoformat(),
            "when": when_label or dt.strftime("%A %I:%M %p").lstrip("0"),
            "topic": topic}


def deliver_due_follow_ups_for_user(user, now=None, max_per_cycle=MAX_DELIVER_PER_CYCLE):
    """PGS-cycle scanner: deliver any due follow-ups for this user, authored FRESH by the
    certified CoS from current truth. Duplicate-safe (atomic pending→delivering claim so only
    one worker/cycle delivers). Respects the proactive preference. Never raises."""
    from apps.ai.models import AssistantConversation, ConversationFollowUp
    from apps.ai.llm_accounting import (llm_traffic_context, TRAFFIC_PROACTIVE,
                                        SOURCE_CONVERSATION_FOLLOW_UP)
    from apps.ai.llm_admission import proactive_ai_enabled

    # Provider-backed proactive work is paused pre-production. Return BEFORE claiming any
    # follow-up, so nothing is flipped to `delivering` and left stranded — the follow-up
    # stays pending and delivers normally once proactive AI is re-enabled.
    if not proactive_ai_enabled():
        return 0

    prefs = getattr(user, "preferences", None)
    if not (prefs and getattr(prefs, "personal_assistant_enabled", False)
            and getattr(prefs, "assistant_proactive_checkins", False)):
        return 0

    now = now or timezone.now()
    delivered = 0
    try:
        due = list(ConversationFollowUp.objects.filter(
            user=user, status=ConversationFollowUp.STATUS_PENDING, due_at__lte=now
        ).order_by("due_at")[:max_per_cycle])
    except Exception:
        logger.warning("FOLLOW_UP scan failed user=%s", user.pk, exc_info=True)
        return 0

    for fu in due:
        # Atomic claim — only the worker that flips pending→delivering proceeds.
        claimed = (ConversationFollowUp.objects
                   .filter(pk=fu.pk, status=ConversationFollowUp.STATUS_PENDING)
                   .update(status=ConversationFollowUp.STATUS_DELIVERING,
                           attempts=F("attempts") + 1))
        if claimed != 1:
            continue
        fu.refresh_from_db()
        try:
            conversation = (fu.conversation
                            or AssistantConversation.get_or_create_active(user))
            from apps.ai.model_interface.service import ModelInterfaceService
            with llm_traffic_context(traffic_class=TRAFFIC_PROACTIVE,
                                     source=SOURCE_CONVERSATION_FOLLOW_UP):
                out = ModelInterfaceService(user).generate(
                    conversation, _follow_up_directive(fu.topic), surface="chat")
            answer = (out or {}).get("answer") if isinstance(out, dict) else None
            answer = (answer or "").strip()
            if not answer:
                # No fabricated follow-up. Retry a bounded number of times, then give up
                # honestly (never deliver an empty/fake message).
                if fu.attempts >= ConversationFollowUp.MAX_ATTEMPTS:
                    fu.status = ConversationFollowUp.STATUS_FAILED
                    fu.save(update_fields=["status"])
                    logger.warning("FOLLOW_UP gave up user=%s id=%s (empty after %d attempts)",
                                   user.pk, fu.pk, fu.attempts)
                else:
                    fu.status = ConversationFollowUp.STATUS_PENDING
                    fu.save(update_fields=["status"])
                continue

            from apps.ai.proactive_checkins import ProactiveCheckInService
            msg = ProactiveCheckInService(user)._create_proactive_message(
                content=answer, quick_replies=[], message_type="follow_up",
                metadata={"check_in_type": "follow_up", "follow_up_id": fu.pk,
                          "topic": fu.topic, "authored_by": "model_interface"})
            fu.status = ConversationFollowUp.STATUS_DELIVERED
            fu.delivered_at = timezone.now()
            fu.save(update_fields=["status", "delivered_at"])
            delivered += 1
            logger.info("FOLLOW_UP_DELIVERED user=%s id=%s msg=%s",
                        user.pk, fu.pk, getattr(msg, "id", None))
        except Exception:
            logger.warning("FOLLOW_UP delivery failed user=%s id=%s", user.pk, fu.pk,
                           exc_info=True)
            # Release the claim so a later cycle can retry (bounded by MAX_ATTEMPTS).
            try:
                if fu.attempts >= ConversationFollowUp.MAX_ATTEMPTS:
                    ConversationFollowUp.objects.filter(pk=fu.pk).update(
                        status=ConversationFollowUp.STATUS_FAILED)
                else:
                    ConversationFollowUp.objects.filter(pk=fu.pk).update(
                        status=ConversationFollowUp.STATUS_PENDING)
            except Exception:
                pass
    return delivered
