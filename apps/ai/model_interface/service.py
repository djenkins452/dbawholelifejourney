# ==============================================================================
# File: apps/ai/model_interface/service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: ModelInterfaceService — drives the model over the WLJ four pillars
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-07-09
# ==============================================================================
"""
ModelInterfaceService — the runtime that hands WLJ's four pillars to the model.

docs/WLJ_MODEL_INTERFACE_DESIGN.md.

Per turn it:
  1. builds the standing context = CONSTITUTION (fixed) + AI Relationship projection
     (Pillar 3) + Current Context baseline (Pillar 4) + capability index — structured
     DATA, not a prompt of instructions;
  2. exposes the minimal Day-1 tools (3 truth reads + 2 action calls);
  3. drives the model via the existing tool loop; every truth read is wrapped in the
     canonical truth envelope and AUDITED; action calls audit themselves;
  4. records the final response in the audit ledger.

It performs NO reasoning of its own (no classifier, no planner) and issues no direct
writes — all writes go through the action interface → execute_intent → UAIO.
"""

import json
import logging
import uuid

from apps.ai.cos_services import audit as _audit
from apps.ai.cos_services import (
    action_interface,
    get_ai_relationship,
    get_current_context_baseline,
    get_domain_adherence,
    get_domain_analysis,
    get_domain_comparison,
    get_domain_entity,
    get_domain_event_frequency,
    get_domain_history,
    get_domain_readings,
    get_domain_state,
    get_foundational_health_facts,
    get_user_truth,
    search_history,
)
from apps.ai.model_interface.constitution import (
    ALLOWED_WRITE_INTENTS as _ALLOWED_WRITE_INTENTS,
    CONSTITUTION,
    RESPONSE_COMPLETION_REMINDER,
    all_tools,
)
from apps.core.truth import envelope as _env

logger = logging.getLogger(__name__)

# How many prior turns of history to give the model (reuses AssistantMessage — no new
# memory engine). Kept modest to bound tokens.
_HISTORY_LIMIT = 12


def load_conversation_history(conversation, *, limit=_HISTORY_LIMIT):
    """Load prior turns for `conversation` as [{role, content}] for the model, reusing
    the existing AssistantMessage store (Blocker 2 — conversation continuity). Returns
    the most recent `limit` user/assistant messages, chronologically. Never raises.

    The model's loaded history MUST equal the conversation the user actually saw in the
    chat thread. Every user/assistant AssistantMessage is displayed to the user — including
    the CoS's own PROACTIVE turns (end-of-day/mid-day check-ins are `message_type='nudge'`,
    briefings are `'state_assessment'`, etc.). Filtering to `message_type='text'` silently
    dropped exactly those proactive turns, so a conversation the CoS itself initiated came
    back with no memory of it (Blocker 3 — continuity loss). We therefore load ALL
    user/assistant turns regardless of `message_type`; only `role` (system excluded) and
    non-empty content bound the set. `role='system'` messages are excluded by the filter.

    Call this BEFORE persisting the current user message so the current turn is not
    duplicated into the history.
    """
    if conversation is None or not getattr(conversation, "id", None):
        return []
    try:
        from apps.ai.models import AssistantMessage
        rows = list(
            AssistantMessage.objects.filter(
                conversation=conversation, role__in=("user", "assistant"),
            ).order_by("-created_at").values("role", "content")[:limit]
        )
    except Exception:  # pragma: no cover - defensive
        logger.warning("mi: history load failed", exc_info=True)
        return []
    rows.reverse()  # chronological
    return [{"role": r["role"], "content": r["content"] or ""}
            for r in rows if (r["content"] or "").strip()]


def _wrap_truth(result, source):
    """Wrap an existing cos_services result in the canonical truth envelope, mapping
    the service's own status into an envelope status. Never raises."""
    try:
        status = result.get("status") if isinstance(result, dict) else None
    except Exception:
        status = None

    if status in ("empty",):
        return _env.empty(source=source)
    if status in ("pending",):
        return _env.pending(source=source)
    if status in ("unsupported", "unsupported_domain", "no_state_source"):
        # Blocker #5: NEVER re-emit the raw status token as the model-facing reason — the model
        # narrates it ("the life domain isn't supported"). Preserve the customer-safe guidance +
        # assessable areas the truth surface already composed, so the model pivots gracefully and
        # the internal routing outcome never reaches the user.
        reason = detail = None
        if isinstance(result, dict):
            reason = result.get("reason")
            detail = {k: result[k]
                      for k in ("analysis_capable_domains", "analyzable_subjects")
                      if result.get(k)} or None
        return _env.insufficient_evidence(
            source=source,
            reason=reason or "No assessable data for this request; assess a concrete area.",
            detail=detail)
    if status in ("error",):
        return _env.error(str(result), source=source)
    # ok / plain payload → present it with provenance.
    return _env.make_envelope(result, source=source, status=_env.STATUS_OK)


class ModelInterfaceService:
    def __init__(self, user, ai_service=None):
        self.user = user
        if ai_service is None:
            from apps.ai.services import AIService
            ai_service = AIService()
        self.ai = ai_service

    def _writes_enabled(self) -> bool:
        """Read-only vs write-enabled rollout stage (Blocker 4). Fail-safe to READ-ONLY:
        any error resolves to False, so writes are never accidentally exposed."""
        try:
            return bool(getattr(self.user.preferences, "use_model_interface_writes", False))
        except Exception:
            return False

    # -- standing context: assemble the owned interfaces (assembler owns NOTHING) -----
    def build_standing_context(self, *, page_context=None, conversation=None,
                               writes_enabled=False, attachments=None) -> dict:
        # Four owned interfaces, each at its OWN freshness (Architecture Law — refresh
        # cadence is an ownership boundary). The envelope only ASSEMBLES; it owns none.
        #   AI Relationship          — slow  (projection)
        #   Deterministic Understanding — medium (cache-first; own warm; pending on cold)
        #   Current Context          — fast  (clock, current screen, capabilities)
        from apps.ai.model_interface import understanding
        understanding_read = understanding.read(self.user)
        if isinstance(understanding_read, dict) and understanding_read.get("status") == "pending":
            self._enqueue_understanding_warm()

        ctx = {
            "ai_relationship": get_ai_relationship(self.user),
            "deterministic_understanding": understanding_read,
            "current_context": get_current_context_baseline(
                self.user, page_context=page_context, conversation=conversation,
                attachments=attachments,
            ),
        }

        # CONVERSATION STATE — "what are we talking about / doing / waiting on" (a DIFFERENT
        # deterministic truth from Current Context's "what PAGE is the user on"). It is an
        # OWNED INTERFACE carried INSIDE this Executive Context Envelope — a peer FIELD to
        # `current_context`, assembled here by the SAME one path — NOT an independent retrieval
        # surface (there is no get_conversation_state tool; the model never fetches it). One
        # authority (conversation_state.py), one read, one precedence list. The active
        # subject/artifacts carried across turns; pending confirmations are surfaced from the
        # confirmation authority in the salient lead. Facts only; the model reasons over them.
        try:
            from apps.ai.model_interface import conversation_state as _cs
            cs = _cs.read(conversation)
            if cs:
                ctx["conversation_state"] = cs
        except Exception:  # pragma: no cover - defensive; envelope must never hard-fail
            logger.warning("mi: conversation_state read skipped", exc_info=True)

        # Personal Truth — durable, explicitly-stored cross-module user facts (targets,
        # conditions, medications, relationship, priorities) the model reasons FROM every
        # turn. Cache-first + resilient (never raises); the bounded standing view and the
        # get_user_truth tool share ONE composer. Facts, not reasoning.
        try:
            from apps.ai.cos_services.personal_truth import (
                build_personal_truth, personal_truth_for_context,
            )
            ctx["personal_truth"] = personal_truth_for_context(
                build_personal_truth(self.user))
        except Exception:  # pragma: no cover - defensive; envelope must never hard-fail
            logger.warning("mi: personal_truth assembly skipped", exc_info=True)

        # Mission Link — deterministic relationship truth. The full mission FACTS live
        # ONCE in `missions`; the current execution action carries lightweight
        # signal_type + mission_link REFERENCES into them (no duplicated mission prose).
        # WLJ exposes the relationship + numbers; the model decides what they mean.
        try:
            from apps.core.execution.decision_authority import (
                current_action, execution_facts,
            )
            from apps.core.execution.execution_state import build_execution_state
            from apps.purpose.mission_link import enrich_action, get_mission_map
            # Build execution truth ONCE; derive the decision + the day's facts from it.
            state = build_execution_state(self.user)
            mission_map = get_mission_map(self.user)
            ctx["missions"] = mission_map.get("missions", {})
            ctx["execution_state"] = execution_facts(self.user, state=state)
            decision = current_action(self.user, state=state)
            primary = decision.get("primary_action")
            ctx["current_action"] = {
                "reason": decision.get("reason"),
                "message": decision.get("message"),
                "primary_action": (enrich_action(self.user, primary, mission_map)
                                   if primary else None),
            }
        except Exception:  # pragma: no cover - defensive; envelope must never hard-fail
            logger.warning("mi: execution/mission assembly skipped", exc_info=True)
        # Surface OPEN confirmations so the model can resolve a SPECIFIC one on the
        # user's next "yes" (the id lives in a prior tool result, not the transcript).
        if writes_enabled:
            from apps.ai.model_interface import confirmation
            ctx["pending_confirmations"] = confirmation.list_open(self.user)
        return ctx

    def _enqueue_understanding_warm(self):
        """Non-blocking, never-raises warm of the Understanding cache on a cold miss."""
        try:
            from apps.core.celery_utils import safe_enqueue
            from apps.ai.model_interface.tasks import warm_understanding
            safe_enqueue(warm_understanding, self.user.id)
        except Exception:
            logger.debug("mi: understanding warm enqueue skipped", exc_info=True)

    @staticmethod
    def _focus_lead(standing_context: dict) -> str:
        """A prominent leading pointer to the object the user is viewing RIGHT NOW, so
        Current Context is the model's FIRST-checked source instead of a low-salience field
        buried deep in the structured JSON. The content itself stays in the structured
        context (single source of truth); this only raises its salience + names it up top.
        Empty when nothing is in focus. Never raises."""
        try:
            screen = (standing_context.get("current_context") or {}).get("current_screen") or {}
            focus = screen.get("focus") or {}
        except Exception:
            return ""
        if not isinstance(focus, dict) or not (focus.get("title") or focus.get("content")):
            return ""
        title = (focus.get("title") or "").strip()
        kind = (focus.get("kind") or "").strip()
        label = (f'"{title}"' + (f" ({kind})" if kind else "")) or "the object on screen"
        # INLINE the on-screen content directly in the lead (same fix pattern as
        # _profile_lead below): the content already reaches the model as
        # `current_context.current_screen.focus.content`, but as JSON deep in a ~60k-char
        # prompt the model overlooked it and answered "the content isn't provided" to
        # "summarize this page" / "what's most important here" (Faith cert, prod). Pointing
        # was not enough — the content must be up front and human-readable. Single source:
        # this is the SAME resolved focus, not a duplicate retrieval.
        content = (focus.get("content") or "").strip()
        body = f"\nHere is exactly what is on screen:\n{content[:2500]}" if content else ""
        if focus.get("authority") == "current_request":
            return (
                "\n\n=== ON SCREEN RIGHT NOW (your FIRST source of truth) ===\n"
                f"The user is currently viewing {label}. If their question is about what "
                "they are looking at (\"what am I looking at\", \"summarize this page\", "
                "\"what's most important here\"), answer from THIS and do NOT retrieve — the "
                f"answer is already here:{body}"
            )
        # conversation_fallback — last-seen, not confirmed current; name it but stay cautious.
        return (
            "\n\n=== LAST SEEN (unconfirmed — client reported no focus this turn) ===\n"
            f"The last object seen in this conversation was {label}. Check its freshness "
            f"before treating it as what they mean now.{body}"
        )

    @staticmethod
    def _profile_lead(standing_context: dict) -> str:
        """Raise the salience of the user's DURABLE constraints (nutrition targets, medical
        conditions, allergies) so they are read as binding requirements, not as inert rows
        buried in the structured-context JSON. EVIDENCE-UTILIZATION fix (2026-07-17): the
        facts already reach the model — as `personal_truth.facts.nutrition[i].value` under
        opaque keys ~90% through the prompt — but the model would quote them and still
        violate them (a meal plan with 185g carbs against a stored 90g target). This lead
        reframes the SAME facts (single source — no duplication, no new retrieval) as HARD
        CONSTRAINTS, up front and human-readable. Empty when there is no profile. Never
        raises."""
        try:
            facts = ((standing_context.get("personal_truth") or {}).get("facts")) or {}
        except Exception:
            return ""
        if not facts:
            return ""

        def _idx(section):
            return {f.get("key"): f.get("value")
                    for f in (facts.get(section) or []) if isinstance(f, dict)}

        nut, health, rel = _idx("nutrition"), _idx("health"), _idx("relationship")
        lines = []

        def _int(v):
            try:
                return int(round(float(v)))
            except (TypeError, ValueError):
                return v

        targets = []
        for label, key in (("", "nutrition.calorie_target"),
                           ("protein ", "nutrition.protein_target"),
                           ("carbs ", "nutrition.carb_target"),
                           ("fat ", "nutrition.fat_target")):
            if key in nut and nut[key] is not None:
                unit = "kcal" if key.endswith("calorie_target") else "g"
                targets.append(f"{label}{_int(nut[key])} {unit}".strip())
        if targets:
            lines.append(
                f"Daily nutrition targets: {' · '.join(targets)}. Any meal plan or nutrition "
                "recommendation MUST conform to these — the daily total should MEET the "
                "calorie and protein targets and NOT exceed the carb or fat targets. These "
                "are HARD CONSTRAINTS from the user's stored WLJ profile, not suggestions or "
                "background. Total your plan's macros and check them against these before "
                "answering; if you cannot fit them, say so explicitly rather than silently "
                "exceeding a target.")
        conditions = health.get("health.active_conditions")
        if conditions:
            lines.append(
                f"Medical conditions: {', '.join(map(str, conditions))} — must MATERIALLY "
                "shape any food, nutrition, or health recommendation (not a disclaimer).")
        allergies = nut.get("nutrition.allergies")
        if allergies:
            lines.append(f"Allergies / avoid: {', '.join(map(str, allergies))} — never "
                         "recommend these.")
        restrictions = nut.get("nutrition.dietary_restrictions")
        if restrictions:
            lines.append(f"Dietary restrictions: {', '.join(map(str, restrictions))} — honor "
                         "these.")
        if not lines:
            return ""
        coaching = rel.get("relationship.coaching_style")
        tail = f" Coaching style: {coaching}." if coaching else ""
        body = "\n".join(f"• {ln}" for ln in lines)
        return (
            "\n\n=== THE USER'S STANDING PROFILE (deterministic WLJ truth — these are "
            "CONSTRAINTS on your recommendations, not background) ===\n"
            f"{body}{tail}\n"
            "Reason FROM these facts. A recommendation that contradicts a stored target or "
            "condition is WRONG even if it is generically reasonable — never retrieve these "
            "facts and then produce a generic answer that ignores them. The full structured "
            "profile is in `personal_truth` below; deeper detail via get_user_truth."
        )

    @staticmethod
    def _conversation_state_lead(standing_context: dict) -> str:
        """Raise the salience of the ACTIVE CONVERSATION STATE — what we're discussing and
        what we're waiting on — so it is not overlooked as JSON ~97% through a 60k-char prompt
        (the exact salience failure that lost a pending 'yes' and let page context displace an
        active artifact). Same inline-salience pattern as _focus_lead/_profile_lead. Facts only;
        the model decides whether a follow-up refers to it (WLJ never interprets language).
        Empty when there is nothing active. Never raises."""
        try:
            pend = standing_context.get("pending_confirmations") or []
            cs = standing_context.get("conversation_state") or {}
            subj = cs.get("active_subject") or {}
        except Exception:
            return ""
        if not pend and not subj.get("ref"):
            return ""
        parts = ["\n\n=== ACTIVE CONVERSATION STATE (what we're doing / waiting on — check "
                 "BEFORE page context for follow-ups and short replies) ==="]
        if pend:
            if len(pend) == 1:
                p = pend[0]
                parts.append(
                    f"AWAITING YOUR CONFIRMATION: you asked the user to confirm \""
                    f"{p.get('summary','')}\". If their message is a yes/no/cancel/confirm/"
                    f"\"do it\"/\"import it\" reply, resolve THAT by calling "
                    f"resolve_pending_action(confirmation_id=\"{p.get('confirmation_id')}\", "
                    f"confirm=true|false) — do NOT treat it as a new topic or a page question.")
            else:
                listed = "; ".join(f"[{p.get('confirmation_id')}] {p.get('summary','')}"
                                   for p in pend[:5])
                parts.append(
                    f"MULTIPLE CONFIRMATIONS ARE PENDING: {listed}. A bare \"yes\" is AMBIGUOUS "
                    "— ask which one the user means (or have them restate it) rather than "
                    "resolving an arbitrary action. Fail closed: never execute on ambiguity.")
        if subj.get("ref"):
            kind = subj.get("kind") or "item"
            label = subj.get("label") or "the item you were discussing"
            ago = subj.get("turns_ago")
            when = (" (introduced this turn)" if ago in (0, None)
                    else f" (introduced {ago} turn(s) ago)")
            # A METRIC subject must be re-retrieved from its own authority for the new
            # date — a follow-up that only shifts the date ("Yesterday's?", "and last
            # week?") is the SAME subject, and must never be answered from the number
            # already on screen (that is how one turn's value became another date's
            # answer, 2026-07-22).
            if kind == "metric" and subj.get("domain") and subj.get("metric"):
                d, m = subj["domain"], subj["metric"]
                parts.append(
                    f"ACTIVE SUBJECT: the metric \"{m}\" (domain '{d}'){when}. A short "
                    f"follow-up that only changes the DATE or PERIOD (\"Yesterday's?\", "
                    f"\"and last week?\", \"what about Monday?\") is still about THIS "
                    f"metric — do NOT switch domain and do NOT ask which metric they "
                    f"mean. RETRIEVE it again for the new date with "
                    f"get_history(domain='{d}', metric='{m}', period=<the date "
                    f"expression the user said>). NEVER reuse the number from an "
                    f"earlier turn as the answer for a different date. Do NOT let an "
                    f"unrelated page's Current Context replace this active subject.")
            else:
                parts.append(
                    f"ACTIVE SUBJECT: the {kind} \"{label}\"{when}. A short follow-up (\"for a "
                    "leak?\", \"is that dangerous?\", \"tell me more\", \"what about this part\", "
                    "\"it/that/this\") refers to THIS unless the user clearly changes topic or "
                    "explicitly asks about the page/screen. To see or re-check it, retrieve it "
                    "with get_entity (domain='artifacts' for an uploaded file). Do NOT let an "
                    "unrelated page's Current Context replace this active subject.")
        return "\n".join(parts)

    @staticmethod
    def _grounding_lead() -> str:
        """Raise the salience of the two ANSWER rules that govern every factual turn.

        They are already in the standing CONSTITUTION, but the constitution sits at the
        HEAD of a ~60k-char prompt and these rules were measurably not surviving that
        distance (2026-07-22: asked "why two different numbers?" over a visible
        transcript, the model asked WHICH numbers, twice out of two). Same inline-salience
        pattern as _focus_lead/_profile_lead/_conversation_state_lead: one source, restated
        near the user's turn. GENERAL and unconditional — no contradiction detector, no
        per-question rule, nothing about any particular metric.
        """
        return (
            "\n\n=== ANSWERING WITH NUMBERS (applies to every turn) ===\n"
            "1. GROUND IT: state a value about this user only when a tool returned it for "
            "the SCOPE you are answering. A number retrieved for one date is evidence for "
            "THAT date only — when the date or period changes, retrieve again. Never reuse "
            "an earlier turn's number for a new scope, and never infer one.\n"
            "2. READ THE ENVELOPE: `semantics: exact_date` = recorded on the date asked "
            "about. `latest_on_or_before`/`latest_observation` = most recent reading — if "
            "`exact` is false, say when it was actually recorded. `status: not_recorded` "
            "means it was not recorded that day; say so plainly. That is a complete answer.\n"
            "3. OWN A CONTRADICTION: the transcript above is visible to you. If the user "
            "says your answers disagree — or you are about to contradict yourself — do NOT "
            "ask them which numbers they mean. Re-read the transcript yourself, quote both "
            "values and the scope each belonged to, retrieve the authoritative value, and "
            "say which is correct and why the earlier one was wrong."
        )

    @staticmethod
    def _attachment_lead(standing_context: dict) -> str:
        """Raise the salience of file(s) the user attached THIS turn so the model can never
        overlook them. They already reach the model as `current_context.attachments` — but as
        one small entry deep in a ~60k-char JSON the model asked the user to 'upload the journal
        document' that was ALREADY attached (prod defect 2026-07-20). Same inline-salience fix
        as _focus_lead/_profile_lead: single source (the SAME attachments), named + up front,
        with what to DO. Empty when nothing is attached. Never raises."""
        try:
            atts = (standing_context.get("current_context") or {}).get("attachments") or []
        except Exception:
            return ""
        lines = []
        for a in atts:
            if not isinstance(a, dict):
                continue
            name = a.get("filename") or a.get("kind") or "a file"
            kind = a.get("kind") or "file"
            if a.get("text"):
                state = "readable — its extracted text is in current_context.attachments"
            elif a.get("perception") == "processing":
                state = ("still being read (perception in progress) — tell the user it's being "
                         "read and to ask again in a moment")
            elif a.get("perception") == "unreadable":
                state = "could not be read"
            else:
                state = "attached"
            aid = a.get("artifact_id")
            lines.append(f'• "{name}" ({kind}) — {state}'
                         + (f' [artifact_id={aid}]' if aid else ''))
        if not lines:
            return ""
        return (
            "\n\n=== FILE(S) THE USER ATTACHED THIS TURN (already available — do NOT ask them "
            "to upload again) ===\n"
            "The user attached the following to THIS message. Never tell the user to upload a "
            "document that is listed here.\n"
            + "\n".join(lines) +
            "\nWhen they say import/add/read/summarize \"these\"/\"this\"/\"the document\", they "
            "mean THESE attachment(s). To import a journal, call import_journal_entries with "
            "source_artifact_id = the attachment's artifact_id (or its filename) — WLJ reads the "
            "document itself and determines the dates."
        )

    @staticmethod
    def _executive_lead(standing_context: dict) -> str:
        """Raise the salience of WLJ's deterministic EXECUTIVE READ — the single "what to do
        now" (`current_action`, from decision_authority) — so a check-in / status request is
        answered by LEADING with it, not by asking the user what they want to check in on.

        The facts already reach the model as `current_action` in the structured context; buried
        in a ~60k-char JSON the model overlooked them and, right after sending a proactive
        end-of-day check-in, replied "what would you like to check in on?" (Blocker #3, prod).
        Same inline-salience pattern as the other leads: ONE source (`current_action` — the SAME
        truth the proactive check-in is authored from), named + up front, with what to DO. The
        model still decides what it MEANS; WLJ only surfaces the fact. Empty when there is no
        current action (WLJ never invents one). Never raises."""
        try:
            ca = standing_context.get("current_action") or {}
        except Exception:
            return ""
        if not isinstance(ca, dict):
            return ""
        primary = ca.get("primary_action") if isinstance(ca.get("primary_action"), dict) else {}
        label = (primary.get("title") or primary.get("label")
                 or primary.get("name") or "").strip()
        message = (ca.get("message") or "").strip()
        reason = (ca.get("reason") or "").strip()
        headline = label or message
        if not headline:
            return ""
        body = f"The single most important thing for this user right now: {headline}."
        if reason:
            body += f" (Why it leads: {reason}.)"
        return (
            "\n\n=== WHAT MATTERS RIGHT NOW (WLJ's deterministic executive read — LEAD with "
            "this on any check-in / status request) ===\n"
            f"{body}\n"
            "When the user asks for a check-in, where they stand, or a WHOLE-LIFE assessment — "
            "\"check in\", \"status\", \"overall status\", \"where do things stand\", \"what "
            "should I do\", \"brief me\", \"how am I doing\", \"how am I doing across "
            "everything\", \"give me an overall assessment of my life\", or a short reply "
            "continuing a check-in you just sent — you ALREADY KNOW the answer: lead with the "
            "item above and give ONE clear next action. NEVER ask them what to check in on, to "
            "narrow the request, or to pick an area, and NEVER ask them to name their own tasks "
            "— that hands your job back to them; a Chief of Staff answers directly from what it "
            "can already see. "
            "But if they ask what REMAINS or for their full list or schedule — \"what's left\", "
            "\"what's on my list\", \"is that everything\", \"anything else\", \"how many do I "
            "have left\" — that is a COMPLETENESS question: lead with what matters most AND then "
            "RETRIEVE and ENUMERATE the rest (e.g. get_domain_state for the relevant domain). "
            "Never answer a list/completeness question with only the top item, and never ask the "
            "user to tell you their own tasks — you can see them. This is the SAME executive "
            "truth carried in `current_action` below."
        )

    def _system_prompt(self, standing_context: dict) -> str:
        # The completion reminder is placed LAST — the highest-salience position, the final
        # instruction the model reads before the user's turn — so it is not out-weighted by
        # the standing supportive/question-frequency relationship signals in the context above.
        return (
            CONSTITUTION
            + self._attachment_lead(standing_context)
            + self._conversation_state_lead(standing_context)
            + self._executive_lead(standing_context)
            + self._focus_lead(standing_context)
            + self._profile_lead(standing_context)
            + "\n\n=== STRUCTURED CONTEXT (deterministic; do not invent beyond it) ===\n"
            + json.dumps(standing_context, ensure_ascii=False)
            # AFTER the structured context, so the answer rules are the last thing read
            # before the user's turn (the same placement RESPONSE_COMPLETION_REMINDER uses).
            + self._grounding_lead()
            + "\n\n" + RESPONSE_COMPLETION_REMINDER
        )

    # Truth tools whose successful result deterministically establishes what the
    # conversation is now ABOUT. Anchoring only get_entity left every factual answer
    # delivered by another surface unanchored — proven 2026-07-22: after a weight answer
    # from get_foundational_health_facts, the elliptical follow-up "Yesterday's?" carried
    # no subject and drifted to the Journal domain (0/4 probes stayed on weight).
    _SUBJECT_BEARING_TOOLS = ("get_entity", "get_history", "get_readings",
                              "get_event_frequency", "get_comparison", "get_adherence",
                              "get_analysis", "get_foundational_health_facts")

    @classmethod
    def _subject_from_truth_result(cls, name, args, result):
        """Deterministically derive the ACTIVE SUBJECT from ANY successful truth retrieval
        (a concrete signal, never language). Returns a compact reference
        {kind, ref, label, domain?, metric?} or None — references only, never prose,
        never a summary, never inferred intent."""
        if name not in cls._SUBJECT_BEARING_TOOLS or not isinstance(result, dict):
            return None
        if name == "get_history":
            return cls._subject_from_metric(args.get("domain"), args.get("metric"), result)
        if name == "get_readings":
            return cls._subject_from_metric(args.get("domain"), args.get("metric"), result)
        if name == "get_event_frequency":
            return cls._subject_from_metric(args.get("domain"), args.get("metric"), result)
        if name in ("get_comparison", "get_adherence"):
            return cls._subject_from_metric(args.get("domain"), args.get("metric"), result)
        if name == "get_analysis":
            return cls._subject_from_metric(args.get("domain"), args.get("subject"), result,
                                            kind="analysis")
        if name == "get_foundational_health_facts":
            return cls._subject_from_health_facts(result)
        return cls._subject_from_entity_result(name, args, result)

    @staticmethod
    def _subject_from_metric(domain, metric, result, *, kind="metric"):
        """A metric/subject retrieval anchors the conversation to THAT metric, so a
        follow-up that only shifts the DATE ("Yesterday's?", "and last week?") stays on it."""
        try:
            if (result or {}).get("status") in ("insufficient_evidence", "error", None):
                return None
            domain = (domain or "").strip().lower()
            metric = (metric or "").strip().lower()
            if not domain or not metric:
                return None
            return {"kind": kind, "ref": f"{domain}.{metric}", "label": metric,
                    "domain": domain, "metric": metric}
        except Exception:
            return None

    @staticmethod
    def _subject_from_health_facts(result):
        """Anchor from a curated health-fact answer. The facts now carry their own
        `domain`/`metric` (they delegate to the one date-scoped authority), so the subject
        is read from the RETURNED TRUTH rather than guessed from the requested key."""
        try:
            # The canonical truth envelope carries its payload under `value`
            # (`truth.envelope.make_envelope`); accept a bare payload too.
            facts = (result or {}).get("value")
            if not isinstance(facts, dict):
                facts = (result or {}).get("data")
            if not isinstance(facts, dict):
                facts = result if isinstance(result, dict) else {}
            for key, fact in facts.items():
                if not isinstance(fact, dict):
                    continue
                domain, metric = fact.get("domain"), fact.get("metric")
                if domain and metric:
                    return {"kind": "metric", "ref": f"{domain}.{metric}",
                            "label": metric, "domain": domain, "metric": metric}
            return None
        except Exception:
            return None

    @staticmethod
    def _subject_from_entity_result(name, args, result):
        """Deterministically derive the ACTIVE SUBJECT from a get_entity retrieval (a concrete
        signal, not language): the record the user just pulled up becomes what a follow-up
        ("tell me more about it") refers to. Returns {kind, ref, label} or None."""
        try:
            if name != "get_entity" or not isinstance(result, dict):
                return None
            if result.get("status") not in ("ready", None) and result.get("status"):
                if result.get("status") != "ready":
                    return None
            domain = (args.get("domain") or "").strip().lower()
            ent = result.get("entity")
            if ent is None:
                ents = result.get("entities") or []
                ent = ents[0] if ents else None
            if not isinstance(ent, dict):
                return None
            label = (ent.get("identity") or ent.get("label")
                     or args.get("name") or args.get("entity_type") or "the item you asked about")
            if domain == "artifacts":
                ref = None
                try:
                    from apps.ai.multimodal import artifact_ids_from_entity_envelope
                    ids = artifact_ids_from_entity_envelope(result)
                    ref = ids[0] if ids else None
                except Exception:
                    ref = None
                return {"kind": "artifact", "ref": ref or label, "label": label}
            return {"kind": "entity", "ref": args.get("name") or label, "label": label,
                    "domain": domain}
        except Exception:
            return None

    # -- tool dispatch --------------------------------------------------------
    def _make_dispatch(self, *, turn_id, surface, tools_called, observer=None,
                       turn_capture=None, conversation_id=""):
        user = self.user

        def _do(name, args):
            # --- Truth reads: wrap in the envelope + audit (kind='truth') ----
            if name == "get_domain_state":
                raw = get_domain_state(user, args.get("domain", ""))
                out = _wrap_truth(raw, source=f"domain:{args.get('domain', '')}")
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "search_history":
                raw = search_history(user, args.get("query", ""),
                                     domain=args.get("domain"),
                                     timeframe=args.get("timeframe"))
                out = _wrap_truth(raw, source="history")
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_user_truth":
                raw = get_user_truth(user, section=args.get("section"))
                out = _wrap_truth(raw, source="personal_truth")
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_foundational_health_facts":
                raw = get_foundational_health_facts(user, keys=args.get("keys"))
                out = _wrap_truth(raw, source="health_facts")
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_history":
                raw = get_domain_history(
                    user, args.get("domain", ""), args.get("metric", ""),
                    period=args.get("period", "last_7_days"),
                    start=args.get("start"), end=args.get("end"),
                )
                out = _wrap_truth(
                    raw,
                    source=f"history:{args.get('domain', '')}."
                           f"{args.get('metric', '')}",
                )
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_readings":
                raw = get_domain_readings(
                    user, args.get("domain", ""), args.get("metric", ""),
                    window=args.get("window", ""),
                    start=args.get("start"), end=args.get("end"),
                )
                out = _wrap_truth(
                    raw,
                    source=f"readings:{args.get('domain', '')}."
                           f"{args.get('metric', '')}",
                )
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_event_frequency":
                raw = get_domain_event_frequency(
                    user, args.get("domain", ""), args.get("metric", ""),
                    event=args.get("event", "low"),
                    window=args.get("window", "night"),
                    period=args.get("period", "last_month"),
                )
                out = _wrap_truth(
                    raw,
                    source=f"event_frequency:{args.get('domain', '')}."
                           f"{args.get('metric', '')}.{args.get('event', 'low')}",
                )
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_comparison":
                raw = get_domain_comparison(
                    user, args.get("domain", ""), args.get("metric", ""),
                    period_a=args.get("period_a", ""),
                    period_b=args.get("period_b", ""),
                )
                out = _wrap_truth(
                    raw,
                    source=f"comparison:{args.get('domain', '')}."
                           f"{args.get('metric', '')}",
                )
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_adherence":
                raw = get_domain_adherence(
                    user, args.get("domain", ""), args.get("metric", ""),
                    period=args.get("period", "last_7_days"),
                )
                out = _wrap_truth(
                    raw,
                    source=f"adherence:{args.get('domain', '')}."
                           f"{args.get('metric', '')}",
                )
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_analysis":
                raw = get_domain_analysis(
                    user, args.get("domain", ""), args.get("subject", ""),
                    period=args.get("period"),
                )
                out = _wrap_truth(
                    raw,
                    source=f"analysis:{args.get('domain', '')}."
                           f"{args.get('subject', '')}",
                )
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_entity":
                raw = get_domain_entity(
                    user, args.get("domain", ""),
                    entity_type=args.get("entity_type"), name=args.get("name"),
                    filters=args.get("filters"),
                )
                out = _wrap_truth(
                    raw,
                    source=f"entity:{args.get('domain', '')}."
                           f"{args.get('entity_type') or args.get('name') or ''}",
                )
                # RE-DELIVERY of perceivable visual content: when the user retrieves
                # an IMAGE or VIDEO artifact, give the model the actual pixels/frames
                # (out-of-band, via `_perceive_images`) so it can SEE it again — not
                # just read metadata. The tool loop injects these as image_url and
                # strips them from the text result.
                if (args.get("domain", "").strip().lower() == "artifacts"
                        and out.get("status") not in ("empty", "insufficient_evidence")):
                    try:
                        from apps.ai.multimodal import (
                            artifact_ids_from_entity_envelope,
                            perceive_images_for_artifacts,
                        )
                        ids = artifact_ids_from_entity_envelope(raw)
                        imgs = perceive_images_for_artifacts(user, ids)
                        if imgs:
                            out["_perceive_images"] = imgs
                    except Exception:  # pragma: no cover - defensive
                        pass
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out

            # --- Actions: named deterministic intent tools route through the SAME
            #     execute_action → execute_intent → UAIO → bound-confirmation → audit
            #     pipeline. The tool NAME is the intent; args are its real handler params
            #     (Option B — expose the deterministic interface; centralize the pipeline).
            if name in _ALLOWED_WRITE_INTENTS:
                return action_interface.request_action(
                    user, name, args, turn_id=turn_id, surface=surface,
                )
            if name == "resolve_pending_action":
                return action_interface.resolve_pending_action(
                    user, args.get("confirmation_id"),
                    confirm=bool(args.get("confirm", False)),
                    turn_id=turn_id, surface=surface,
                )

            return {"status": "error", "error": f"unknown tool '{name}'"}

        def dispatch(name, args):
            args = args if isinstance(args, dict) else {}
            tools_called.append(name)
            result = _do(name, args)
            # Capture the retrieved entity as a candidate ACTIVE SUBJECT (last retrieval wins).
            if turn_capture is not None:
                subj = self._subject_from_truth_result(name, args, result)
                if subj is not None:
                    turn_capture["subject"] = subj
            if observer is not None:  # observability only (validation harness); no-op in prod
                try:
                    observer(name, args, result)
                except Exception:
                    pass
            return result

        return dispatch

    @staticmethod
    def _new_turn_id(conversation, *, request_id=""):
        """A UNIQUE id for this turn. An explicit `request_id` (validation harness,
        streaming task) wins; otherwise a fresh one is minted. It is deliberately NOT
        derived from the conversation — that is what collapsed every turn of a
        conversation into one audit id (2026-07-22)."""
        return request_id or f"turn-{uuid.uuid4().hex[:24]}"

    # -- entry point ----------------------------------------------------------
    def generate(self, conversation, message, *, page_context=None, surface="chat",
                 request_id="", observer=None, conversation_history=None,
                 writes_enabled=None, images=None, attachments=None) -> dict:
        # AUDIT IDENTITY: the turn id must be UNIQUE PER TURN. It previously defaulted to
        # f"conv-{id}", and the production gateway calls generate() without a request_id —
        # so every turn in a conversation shared one id and no incident could be replayed
        # turn by turn (proven 2026-07-22). The conversation is carried separately.
        conversation_id = str(getattr(conversation, "id", "") or "")
        turn_id = self._new_turn_id(conversation, request_id=request_id)
        tools_called = []
        if writes_enabled is None:
            writes_enabled = self._writes_enabled()

        standing_context = self.build_standing_context(
            page_context=page_context, conversation=conversation,
            writes_enabled=writes_enabled, attachments=attachments,
        )
        system_prompt = self._system_prompt(standing_context)
        turn_capture = {}
        dispatch = self._make_dispatch(
            turn_id=turn_id, surface=surface, tools_called=tools_called,
            observer=observer, turn_capture=turn_capture,
            conversation_id=conversation_id,
        )

        answer = self.ai._call_api_with_tools(
            system_prompt, message or "", tools=all_tools(writes_enabled=writes_enabled),
            dispatch=dispatch, user=self.user, endpoint="model_interface",
            conversation_history=conversation_history, images=images,
        )
        answer = answer or ""

        # CONVERSATION STATE — deterministically advance the working-state AFTER the turn:
        # this turn's uploads (attachments) or the entity the model just retrieved become the
        # ACTIVE SUBJECT carried to the next turn (the leak-video continuity). Durable in
        # AssistantConversation.metadata; never breaks a turn. Skipped on an empty answer.
        if answer:
            try:
                from apps.ai.model_interface import conversation_state as _cs
                _cs.record_turn(conversation, attachments=attachments,
                                retrieved_subject=turn_capture.get("subject"))
            except Exception:  # pragma: no cover - defensive
                logger.warning("mi: conversation_state.record_turn skipped", exc_info=True)

        _audit.record_tool_call(
            self.user, kind="response", turn_id=turn_id, surface=surface,
            conversation_id=conversation_id,
            result_status="ok" if answer else "empty",
            result_digest={"answer_len": len(answer),
                           "tools_called": list(tools_called)},
        )
        return {"answer": answer, "tools_called": tools_called,
                "standing_context": standing_context, "turn_id": turn_id}
