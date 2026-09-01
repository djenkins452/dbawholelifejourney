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
    get_domain_change_point,
    get_domain_comparison,
    get_domain_consistency,
    get_domain_entity,
    get_domain_event_frequency,
    get_domain_history,
    get_domain_ranked_entity,
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


def load_conversation_history(conversation, *, limit=_HISTORY_LIMIT, exclude_ids=None):
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
    duplicated into the history. When the current turn is ALREADY persisted (durable
    turn lifecycle — the streaming submit path persists the user message + pending turn
    synchronously, then the worker loads history), pass `exclude_ids` with the current
    turn's message ids so they are not fed back as history.
    """
    if conversation is None or not getattr(conversation, "id", None):
        return []
    try:
        from apps.ai.models import AssistantMessage
        qs = AssistantMessage.objects.filter(
            conversation=conversation, role__in=("user", "assistant"),
        )
        if exclude_ids:
            qs = qs.exclude(id__in=[i for i in exclude_ids if i])
        rows = list(
            qs.order_by("-created_at").values("role", "content")[:limit]
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

        # Getting to Know You (M4) — deterministic interview state, ONLY when a session
        # is live. An inventory of what is known and what the user ruled out; never an
        # agenda. Absent entirely outside the interview, which is what keeps deliberate
        # teaching gated to this surface (M6 natural learning remains separate).
        try:
            from apps.ai.cos_services import interview as _interview
            block = _interview.read(self.user, conversation)
            if block:
                ctx["interview"] = block
        except Exception:  # pragma: no cover - envelope must never hard-fail
            logger.warning("mi: interview state skipped", exc_info=True)

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
            # An "overall" roll-up is a whole-domain / multi-domain assessment, NOT a single
            # narrow subject — after a broad synthesis it is arbitrary (last-retrieval-wins), so
            # asserting it as THE active subject mislabels the referent ("the analysis 'overall'").
            # Drop it: the conversational reference rule (a backward-referring follow-up continues
            # your prior answer) and the prior answer itself carry the real referent.
            # (Conversation Continuity Correction, 2026-08-12.)
            if (subj.get("metric") or subj.get("label") or "").strip().lower() == "overall":
                subj = {}
            guided = cs.get("guided_review") or {}
        except Exception:
            return ""
        if not pend and not subj.get("ref") and not guided.get("current"):
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
                    f"earlier turn as the answer for a different date. "
                    f"A follow-up that instead asks WHY, whether it is good/bad/normal, "
                    f"what is causing it, or uses \"it/that/this\" (\"why does it keep "
                    f"getting worse?\", \"is that bad?\", \"what's causing it?\") is ALSO "
                    f"about THIS metric — reason about '{m}' from its recent values and "
                    f"trend (retrieve more of its history if you need it); do NOT ask which "
                    f"area or metric they mean. "
                    f"Do NOT let an unrelated page's Current Context replace this active "
                    f"subject.")
            else:
                # Kind-aware re-retrieval guidance. The old branch told the model to re-check ANY
                # non-metric subject with get_entity(domain='artifacts') — correct only for an
                # uploaded file, but incoherent for a get_analysis subject (an analysis is
                # re-fetched with get_analysis). (Conversation Continuity Correction, 2026-08-12.)
                if subj.get("artifact") or kind == "artifact":
                    how = "To see it again, retrieve it with get_entity (domain='artifacts')."
                elif kind == "analysis" and subj.get("domain"):
                    how = (f"To go deeper, retrieve it again with get_analysis("
                           f"domain='{subj['domain']}', subject='{subj.get('metric') or label}').")
                elif subj.get("domain"):
                    how = f"To re-check it, retrieve it with get_entity(domain='{subj['domain']}')."
                else:
                    how = "Reason about it from your prior answer; retrieve more only if you need it."
                parts.append(
                    f"ACTIVE SUBJECT: the {kind} \"{label}\"{when}. A short follow-up (\"why?\", "
                    "\"tell me more\", \"what about this part\", \"is that getting worse?\", "
                    "\"it/that/this\") refers to THIS unless the user clearly changes topic or "
                    "explicitly asks about the page/screen. " + how + " Do NOT let an "
                    "unrelated page's Current Context replace this active subject.")
        if guided.get("current"):
            cur = guided.get("current") or {}
            gday = guided.get("relative") or guided.get("day") or "that day"
            gkind = cur.get("kind") or "item"
            gtitle = cur.get("title") or "the item"
            gstate = cur.get("completion_state") or ""
            detail = f" (currently {gstate})" if gstate and gstate != "incomplete" else ""
            parts.append(
                f"AWAITING THE USER'S ANSWER — GUIDED EXECUTION REVIEW of {gday}: you asked "
                f"whether they completed \"{gtitle}\" ({gkind}){detail}. Their reply ANSWERS "
                f"THIS QUESTION — it is NOT an orphaned confirmation and there is nothing to "
                f"'clarify'. Interpret it and act:\n"
                f"  • yes / \"I did\" / \"finished it\" → call complete_execution_item(kind="
                f"\"{gkind}\", title=\"{gtitle}\", day=\"{gday}\"), THEN call next_review_item("
                f"day=\"{gday}\") to move to the next item.\n"
                f"  • no / \"didn't\" / \"I don't remember\" → do NOT record; call "
                f"next_review_item(day=\"{gday}\") to move on.\n"
                f"  • partially / only a specific part → record what genuinely applies (or ask "
                f"ONE brief clarifier), then next_review_item(day=\"{gday}\").\n"
                f"  • stop / \"that's enough\" → call next_review_item(day=\"{gday}\", stop=true).\n"
                f"When next_review_item returns status 'reconciled', tell them {gday} is fully "
                f"reconciled. You OWN this review until every item is handled or they stop — "
                f"never make the user ask for the next item.")
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
            "1. GROUND IT (in EVERY framing): state a value about this user — a weight, rep, "
            "dose, amount, total, or CALCULATED result — only when it is grounded in a tool "
            "result for the scope you are answering, or in already-grounded evidence in THIS "
            "conversation. This holds no matter how the question is worded: 'what was it', 'how "
            "did you calculate it', 'walk me through the math', 'show me for exercise X', 'why "
            "is it that value' all rest on the SAME grounded numbers. If you do NOT already hold "
            "the grounded value, RETRIEVE it — NEVER supply it from a plausible example, a "
            "reverse-engineered figure (a component chosen to fit a total), an inference, or "
            "your OWN earlier prose (your prior wording is not evidence). WLJ owns the "
            "calculation — use its value and exposed components, don't re-derive from numbers "
            "you're unsure of. A number retrieved for one date/record is evidence for THAT "
            "scope only — when the scope changes, retrieve again. If you don't have it, say 'I "
            "don't have that recorded' — never invent a number to keep an explanation flowing.\n"
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
        now" (`current_action`, from decision_authority) — so an EXECUTION / CHECK-IN request is
        answered by LEADING with it, not by asking the user what they want to check in on.

        The facts already reach the model as `current_action` in the structured context; buried
        in a ~60k-char JSON the model overlooked them and, right after sending a proactive
        end-of-day check-in, replied "what would you like to check in on?" (Blocker #3, prod).
        Same inline-salience pattern as the other leads: ONE source (`current_action` — the SAME
        truth the proactive check-in is authored from), named + up front, with what to DO.

        RESPONSIBILITY CORRECTION (Executive Lead Responsibility Correction, 2026-08-12,
        `docs/WLJ_COS_EXECUTIVE_LEAD_CORRECTION.md`): the over-steer fix left this lead as a
        WLJ-side INTENT CLASSIFIER — four phrase-list buckets (EXECUTION / COMPLETENESS /
        DAY-BRIEFING / ASSESSMENT), each dictating a conclusion, most forcefully "you ALREADY
        KNOW the answer — LEAD with the item above". Runtime proved the residual: the classifier
        mis-buckets action-worded questions ("what should I focus on right now?") into EXECUTION
        and the imperative collapses them onto `current_action`, even overriding an established
        conversational subject. WLJ was performing model-owned intent interpretation + reaching
        the conclusion (I.2/I.4). This is corrected by EXPOSING the fact and DELEGATING the
        judgment: `current_action` is surfaced as a deterministic FACT (its truth, I.3) and the
        model decides whether it answers the user's question (its reasoning, I.4). No phrase-list
        classifier, no "you already know the answer" imperative; the prompt is smaller. The one
        preserved deterministic protection is anti-"hand the job back" (never ask the user to
        pick an area or name their own tasks — they are visible). Execution Decision Authority
        (III.2) is untouched — the fact still has exactly one producer; only the answer behavior
        is returned to the model. Empty when there is no current action (WLJ never invents one).
        Never raises."""
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
        # EXECUTABLE IDENTITY — WRONG-TARGET INCIDENT (2026-08-18, ToolCallLog
        # bb930a1d). An earlier version of this lead pre-filled a ready-to-fire
        # completion call carrying THIS action's identity and told the model "use that
        # identity - do NOT look it up by name". The user asked to complete SHOWER while
        # the current action was LOG NUTRITION; the model fired the handed call and
        # mutated the wrong object. A current-action suggestion must NEVER become the
        # target of a write the user did not ask for.
        #
        # The identity still travels in `current_action` for the model to USE - but only
        # after it has decided the user actually means THIS item. No pre-built call, and
        # an explicit rule that a named subject outranks this suggestion.
        _stype = (primary.get("source_type") or primary.get("source") or "").strip()
        _sid = primary.get("source_id", primary.get("pk"))
        if _stype and _sid is not None and primary.get("can_complete", True):
            body += (
                " It is executable, and `current_action.primary_action` carries its "
                "canonical `source_type` and `source_id`. TARGET RULE: if the user NAMES "
                "an object ('mark my workout complete'), that named object is the target - "
                "this current action is NOT a substitute for it, and you must never "
                "complete this item because the one they named was harder to find. Use "
                "this identity ONLY when the user is clearly referring to THIS item "
                "('mark it done', 'finished that', 'complete my current task'). If you "
                "cannot bind what they named to a specific object, complete NOTHING and "
                "say so."
            )
        return (
            "\n\n=== WHAT MATTERS RIGHT NOW (WLJ's deterministic executive read) ===\n"
            f"{body}\n"
            "This is a deterministic FACT — WLJ's current top execution priority — NOT a verdict "
            "on the user's whole life, and NOT automatically the answer to their question. YOU "
            "decide what they are actually asking and whether this fact answers it. If they are "
            "asking what to do or what is next, it is the answer — lead with it, and never hand "
            "the job back by asking them to pick an area or name their own tasks (you can see "
            "their tasks). If they are asking something broader or different — how they are doing, "
            "what to focus on, what concerns you, a specific domain, their whole day, or what is "
            "left — this single task is at most ONE input: retrieve the other truth that matters "
            "and reason across it, and do not collapse the broader question onto this one item. "
            "When they ask for their day, a list, or everything left, cover the rest too (e.g. "
            "get_domain_state for tasks and calendar), not just this item. And when the "
            "conversation has already established what they are focused on, stay with that subject "
            "— this current action does not override it. This is the SAME executive truth carried "
            "in `current_action` below; WLJ surfaces the fact, and YOU decide what it means."
        )

    @staticmethod
    def _persona_lead(standing_context: dict) -> str:
        """M1 — the PERSONA voice, at high salience.

        The persona is the user's CHOSEN relationship with their Chief of Staff and it
        must actually change how the answer sounds. Before M1 the runtime received only
        the persona SLUG (proven 2026-08-18: `"texas_rancher"` with no voice at all), so
        fourteen personas were decorative. The composed voice now rides in
        `ai_relationship.persona_instructions`; this lead makes the model USE it.

        VOICE ONLY — it never changes truth, safety, authorization, confirmation
        requirements, or action behaviour, and it never overrides an explicit
        Operational Preference.
        """
        try:
            rel = standing_context.get("ai_relationship") or {}
            instructions = (rel.get("persona_instructions") or "").strip()
            if not instructions:
                return ""
            persona = ((rel.get("assistant") or {}).get("persona")) or {}
            name = persona.get("name") or "your configured persona"
            display = (rel.get("assistant") or {}).get("display_name") or "Chief of Staff"
            boundaries = ((rel.get("boundaries") or {}).get("sensitivity_topics")) or []
            out = (
                f"\n\n=== YOUR VOICE ({name}) ===\n"
                f"You are {display}. The user CHOSE this persona - speak in it, naturally and "
                "consistently, from the first sentence. It is who you are to them, not a costume "
                "you put on for greetings and drop when the content gets substantive.\n"
                f"{instructions}\n"
                "This governs VOICE ONLY. It NEVER changes the truth you report, a number, a "
                "safety or medical rule, an authorization or confirmation requirement, or which "
                "action you take - and it NEVER overrides the user's explicit settings below "
                "(their choices beat your persona's habits every time). Stay in voice while being "
                "exactly as accurate, careful and honest as you would otherwise be. If the user is "
                "in real distress, keep the voice but drop the shtick - warmth outranks flavour."
            )
            if boundaries:
                out += (
                    "\n\nBOUNDARIES: the user has asked you to be especially careful with "
                    + ", ".join(boundaries)
                    + ". Do not raise these unprompted; when the user raises one, be gentle and "
                    "brief, and let them lead how far it goes."
                )
            return out
        except Exception:  # pragma: no cover - defensive; the prompt must never hard-fail
            logger.warning("mi: persona lead skipped", exc_info=True)
            return ""

    @staticmethod
    def _interview_lead(standing_context: dict) -> str:
        """M4 — conducting Getting to Know You, in the user's chosen persona voice.

        WLJ supplies the inventory and the boundaries; everything about HOW to ask is
        yours. This lead exists to stop the one failure mode the design names: the
        interview decaying into a questionnaire wearing a chat costume.
        """
        try:
            iv = standing_context.get("interview")
            if not isinstance(iv, dict) or iv.get("status") != "active":
                return ""
            declined = iv.get("declined_areas") or []
            out = (
                "\n\n=== YOU ARE GETTING TO KNOW THIS PERSON ===\n"
                "HARD RULE FIRST, because it is the one that breaks trust when missed: the "
                "moment they rule a subject OUT ('I'd rather not talk about X', 'let's not "
                "go there', 'that's off limits') or close one off ('that's enough about X'), "
                "your FIRST act that turn is to call record_interview_knowledge with "
                "`area_outcome` — no `facts` needed. Only then reply. If you answer 'no "
                "problem, we'll skip that' without that call, nothing is saved and you will "
                "raise it again next time, having promised you would not. Agreeing in prose "
                "is not honouring a boundary; recording it is.\n"
                "They opened this to teach you about their life, so this is a CONVERSATION, "
                "not an intake form. Ask about what they actually said — follow the "
                "interesting thread, not the next empty category. One thing at a time, in "
                "your own voice, and let them lead the depth.\n"
                "`interview.areas` below is an UNORDERED inventory of what you already know "
                "and what they have ruled out. It is NOT an agenda: never work through it in "
                "order, never treat an empty area as a gap to fill, never tell them anything "
                "is incomplete or missing, and never imply they owe you information. If "
                "there is nothing natural to ask, say so and let the conversation rest.\n"
                "THEIR CONTROLS, in plain language — honour them the moment you hear them: "
                "'skip' or 'move on' (drop it, keep the area open), 'that's enough about X' "
                "(satisfied), 'come back to this later' (parked), 'I don't want to discuss "
                "that' (declined — never raise it again), 'tell me more' or 'go deeper' "
                "(follow it further), 'just the basics' (stay shallow), 'stop' or 'stop for "
                "now' (end warmly and say it will be here when they return).\n"
                "LEAD THE CONVERSATION. They came here to be asked about their life, so "
                "ASK - do not wait to be given a topic, and never answer with a menu of "
                "areas they could pick from - a numbered list of subjects is an intake form, "
                "which is the one thing this must never become. Even when they ask what "
                "you want to know, answer as a person would: name one or two things you are genuinely curious about and ask about the first. End your turn with one genuine question that "
                "follows from what they just said. Do NOT open with an acknowledgement - "
                "'That's great!', 'Thanks for sharing!', 'Got it!' before every reply is a "
                "verbal tic, not warmth. React to the SUBSTANCE, briefly, then go on.\n"
                "RECORDING WHAT THEY TEACH YOU: recording and replying are NOT alternatives. If "
                "they just told you something durable, you record it AND reply in the same "
                "turn - every time, including when what they said made you curious and you "
                "would rather ask a follow-up. Asking instead of recording is how a fact is "
                "lost: it will still be in this conversation, so you will sound like you "
                "know it, but nothing was saved and it is gone by their next visit. Call "
                "record_interview_knowledge in the SAME turn as your reply — one call "
                "carrying both the facts and any area outcome. Store what they SAID, in "
                "their framing, split into simple statements. Record what they SAID - do not "
                "convert it: if they say 'Tom is 14', store that, NOT a birth year you "
                "worked out, because you do not know his birthday and would be guessing. "
                "WLJ stamps every fact with the date you were told, so a point-in-time "
                "detail stays honest as it ages. NEVER store an inference "
                "about them: 'Heather is my wife' and 'married since 1997' are facts; "
                "'he has a secure attachment style' is you editorialising, and is forbidden. "
                "If they say not to remember something, do not record it. Acknowledge "
                "naturally in one clause - never recite a list back for confirmation.\n"
                "RECORDING WHAT THEY RULE OUT (equally important, and easy to forget): a "
                "boundary only exists once it is RECORDED. If they decline, park or close "
                "off a subject, you MUST call record_interview_knowledge with "
                "`area_outcome` THAT TURN — with no `facts` at all if there is nothing to "
                "store. Saying 'understood, we won't discuss that' without recording it is "
                "a promise you cannot keep: nothing is saved, and the subject will come "
                "back the next time you speak. Record it, then reply.\n"
            )
            if declined:
                out += ("OFF LIMITS - they have declined these and you must not raise them: "
                        + ", ".join(declined) + ".\n")
            return out
        except Exception:  # pragma: no cover - defensive
            logger.warning("mi: interview lead skipped", exc_info=True)
            return ""

    def _system_prompt(self, standing_context: dict) -> str:
        # The completion reminder is placed LAST — the highest-salience position, the final
        # instruction the model reads before the user's turn — so it is not out-weighted by
        # the standing supportive/question-frequency relationship signals in the context above.
        return (
            CONSTITUTION
            + self._persona_lead(standing_context)
            + self._interview_lead(standing_context)
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
                              "get_event_frequency", "get_consistency", "get_change_point",
                              "get_comparison", "get_adherence", "get_analysis",
                              "get_foundational_health_facts")

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
        if name == "get_consistency":
            return cls._subject_from_metric(args.get("domain"), args.get("metric"), result)
        if name == "get_change_point":
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
                       turn_capture=None, conversation_id="", conversation=None):
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
            if name == "get_execution_review":
                # Blocker #14: the ONE composed surface for a day's INTENDED execution
                # (a projection over existing truth; owns nothing). So "yesterday's items"
                # means the whole intended execution, never only tasks.
                from apps.ai.cos_services.execution_review import get_execution_review
                raw = get_execution_review(user, day=args.get("day"))
                out = _wrap_truth(raw, source="execution_review")
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "navigate_to_workspace":
                # Reveal Target: model chose the target (in words); WLJ resolves it to a real
                # URL via the existing destination authority and owns the already-there
                # relation. On `ok`, stash the navigation directive for the client (the app
                # owns the verb via the existing renderNavigation). Audited (reveal action).
                from apps.ai.cos_services.reveal import resolve_reveal
                _cur = (turn_capture or {}).get("current_url")
                _created = (turn_capture or {}).get("created_reveal")
                out = resolve_reveal(user, args.get("target"), current_url=_cur,
                                     created_reveal=_created)
                if out.get("status") == "ok" and turn_capture is not None:
                    turn_capture["navigation"] = {
                        "url": out.get("url"), "label": out.get("label") or "Open",
                        "action_type": "open_workflow"}
                _audit.record_tool_call(
                    user, kind="action", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest={"status": out.get("status"),
                                   "url": (out.get("url") or "")[:200]},
                )
                return out
            if name == "get_data_health":
                # M3: source-sync missingness — reuse the single health-sync authority so the
                # model can distinguish "not synced" from "not done". Facts only; on-demand.
                from apps.ai.cos_services.data_health import get_data_health
                raw = get_data_health(user)
                out = _wrap_truth(raw, source="data_health")
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
            if name == "get_consistency":
                raw = get_domain_consistency(
                    user, args.get("domain", ""), args.get("metric", ""),
                    period=args.get("period", "last_month"),
                )
                out = _wrap_truth(
                    raw,
                    source=f"consistency:{args.get('domain', '')}."
                           f"{args.get('metric', '')}",
                )
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_change_point":
                raw = get_domain_change_point(
                    user, args.get("domain", ""), args.get("metric", ""),
                    period=args.get("period", "last 90 days"),
                )
                out = _wrap_truth(
                    raw,
                    source=f"change_point:{args.get('domain', '')}."
                           f"{args.get('metric', '')}",
                )
                _audit.record_tool_call(
                    user, kind="truth", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest=_audit.truth_digest(name, args, out),
                )
                return out
            if name == "get_ranked_entity":
                raw = get_domain_ranked_entity(
                    user, args.get("subject", ""),
                    period=args.get("period", "this_month"),
                    order=args.get("order", "desc"),
                    limit=args.get("limit", 10),
                )
                out = _wrap_truth(raw, source=f"ranked_entity:{args.get('subject', '')}")
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
                out = action_interface.request_action(
                    user, name, args, turn_id=turn_id, surface=surface,
                    conversation_id=conversation_id,
                )
                # Object-Level Reveal: remember a just-created object that has its own detail
                # URL, so a reveal LATER THIS TURN opens THE object (not just its workspace).
                co = out.get("created_object") if isinstance(out, dict) else None
                if turn_capture is not None and isinstance(co, dict) and co.get("url"):
                    turn_capture["created_reveal"] = {
                        "url": co["url"],
                        "label": co.get("title") or co.get("name") or "Open",
                        "model": co.get("model")}
                return out
            if name == "resolve_pending_action":
                return action_interface.resolve_pending_action(
                    user, args.get("confirmation_id"),
                    confirm=bool(args.get("confirm", False)),
                    turn_id=turn_id, surface=surface,
                    conversation_id=conversation_id,
                )
            if name == "record_interview_knowledge":
                # M4 deliberate teaching. GATED ON AN ACTIVE SESSION — outside Getting to
                # Know You this is a no-op, which is what keeps ordinary conversation from
                # learning (M6 remains separate and unbuilt). No per-fact confirmation: the
                # user opened this surface to teach, and About Me is the review surface.
                # Every write still goes through the canonical PK service.
                from apps.ai.cos_services import interview as _iv
                session = _iv.active_session(user, conversation)
                if session is None:
                    out = {"status": "not_in_interview",
                           "message": ("Nothing was recorded — this only applies during "
                                       "Getting to Know You.")}
                else:
                    recorded, rejected = _iv.record_facts(session, args.get("facts"))
                    outcome = args.get("area_outcome") or {}
                    area_set = False
                    if outcome.get("area") and outcome.get("state"):
                        area_set = _iv.set_topic_state(
                            session, outcome.get("area"), outcome.get("state"))
                    _iv.note_turn(session)
                    out = {
                        "status": "recorded" if recorded else "nothing_recorded",
                        # HONEST result — never claim more was kept than actually was.
                        "remembered": [f.statement for f in recorded],
                        "not_remembered": rejected,
                        "area_outcome_applied": area_set,
                        "message": (
                            f"Kept {len(recorded)} thing(s)."
                            + (f" {len(rejected)} could not be kept; do not say they were."
                               if rejected else "")),
                    }
                _audit.record_tool_call(
                    user, kind="action", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest={"status": out.get("status"),
                                   "recorded": len(out.get("remembered") or []),
                                   "rejected": len(out.get("not_remembered") or []),
                                   "area_outcome_applied": out.get("area_outcome_applied")},
                )
                return out
            if name == "next_review_item":
                # Blocker #15: advance the GUIDED one-at-a-time execution review and return
                # the next item awaiting the user's answer — persisting that pending question
                # in conversation_state so the next short reply binds to it (never lost).
                from apps.ai.cos_services.guided_review import next_review_item as _nri
                out = _nri(user, conversation, day=args.get("day"),
                           stop=bool(args.get("stop")))
                _audit.record_tool_call(
                    user, kind="action", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest={"status": out.get("status"),
                                   "item": (out.get("item") or {}).get("title", "")},
                )
                return out
            if name == "delete_record":
                # M4: remove ONE record by EXACT identity. Always behind a bound
                # confirmation showing the record's CURRENT deterministic state — the
                # user authorizes a record they can see, described from the stored row.
                from apps.ai.cos_services import record_correction as _rc
                target = _rc.describe_target(user, args.get("record_type"),
                                             args.get("record_id"))
                if target["status"] in (_rc.UNSUPPORTED, _rc.AMBIGUOUS, _rc.NOT_FOUND):
                    # FAIL CLOSED — no identity, no confirmation, nothing removed.
                    _audit.record_tool_call(
                        user, kind="action", tool_name=name, turn_id=turn_id,
                        surface=surface, args=args, result_status=target["status"],
                        conversation_id=conversation_id,
                        result_digest={"status": target["status"], "mutated": False})
                    return {"status": "error", "code": target["status"],
                            "result": target["message"]}
                if not args.get("confirmed"):
                    gate = action_interface.request_confirmation_for(
                        user, "delete_record",
                        {**args, "target": target.get("description", "")},
                        turn_id=turn_id, surface=surface,
                        conversation_id=conversation_id,
                    )
                    if gate is not None:
                        return gate
                out = _rc.remove_record(user, args.get("record_type"),
                                        args.get("record_id"))
                _audit.record_tool_call(
                    user, kind="action", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest={"status": out.get("status"),
                                   "removed": out.get("removed"),
                                   "record_type": out.get("record_type"),
                                   "record_id": out.get("record_id"),
                                   "description": out.get("description")})
                return out
            if name == "complete_execution_item":
                # Blocker #14 Layer 2: record an execution item complete on the ACTUAL day,
                # reusing existing per-domain writes. AUTO (the user's 'yes' is the confirm;
                # reversible). Honest result — never a false claim.
                # CONFIRMATION GATE (2026-08-18). This tool previously called the
                # completion service DIRECTLY, bypassing `request_action` and therefore the
                # confirmation authority entirely — so "Confirm before acting = ON" never
                # gated it (ToolCallLog 62d315f8: straight to `recorded`). Its original
                # AUTO exemption was valid only in the guided-review flow, where the user
                # had ALREADY said yes; it is not valid now that this is the general
                # completion verb. Mint a BOUND confirmation instead of mutating, unless
                # the user is resolving one (`confirmed`) or this is an undo of something
                # they just rejected.
                from apps.ai.cos_services.execution_completion import (
                    complete_execution_item as _cei,
                )
                from apps.ai.cos_services.action_execution import confirmation_required_for
                if (not args.get("confirmed") and not args.get("undo")
                        and confirmation_required_for(user, "complete_execution_item")):
                    gate = action_interface.request_confirmation_for(
                        user, "complete_execution_item", args,
                        turn_id=turn_id, surface=surface,
                        conversation_id=conversation_id,
                    )
                    if gate is not None:
                        return gate
                out = _cei(user, kind=args.get("kind"), title=args.get("title"),
                           day=args.get("day"), content=args.get("content"),
                           source_type=args.get("source_type"),
                           source_id=args.get("source_id"),
                           undo=bool(args.get("undo")))
                _audit.record_tool_call(
                    user, kind="action", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest={"status": out.get("status"),
                                   "message": (out.get("message") or "")[:200]},
                )
                return out
            if name == "schedule_follow_up":
                # M2: persist a durable promised follow-up. WLJ owns the commitment; the model
                # computed the concrete local time. The follow-up is authored FRESH from current
                # truth when it fires (deliver_due_follow_ups_for_user), never replayed prose.
                from apps.ai.cos_services.follow_up import schedule_follow_up as _sfu
                out = _sfu(user, conversation, topic=args.get("topic"),
                           when_local=args.get("when_local"),
                           when_label=args.get("when_label"),
                           subject_ref=args.get("subject_ref"))
                _audit.record_tool_call(
                    user, kind="action", tool_name=name, turn_id=turn_id,
                    surface=surface, args=args, result_status=out.get("status", ""),
                    conversation_id=conversation_id,
                    result_digest={"status": out.get("status"),
                                   "due_at": out.get("due_at", ""),
                                   "topic": (out.get("topic") or "")[:120],
                                   "message": (out.get("message") or "")[:200]},
                )
                return out

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
                # EXECUTIVE SYNTHESIS (Phase 2) — retain the deterministic evidence the model
                # chose to gather (truth reads that returned real data), so an eligible broad
                # turn can be synthesized over the SAME evidence without re-retrieving.
                try:
                    from apps.ai.model_interface import synthesis as _synth
                    if _synth.is_substantive_truth(name, result):
                        turn_capture.setdefault("evidence", []).append(
                            {"tool": name, "args": args, "result": result})
                except Exception:  # pragma: no cover - defensive
                    pass
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
        """Public entry point. Establishes LLM accounting provenance for the whole turn,
        then runs it.

        The scope MUST be established before the first provider call, because a turn can
        bill several requests (Phase 1 + tool continuations + Phase 2 synthesis) and all of
        them belong to the same source. Getting to Know You is attributed to its own source
        so interview cost is separable from ordinary chat in `/owner/finance/` — without it
        an interview turn is indistinguishable from `interactive_chat` and the milestone's
        cost question cannot be answered.
        """
        from apps.ai.llm_accounting import (
            SOURCE_GETTING_TO_KNOW_YOU, SOURCE_INTERACTIVE_CHAT, TRAFFIC_PRODUCTION,
            current_traffic_class, llm_traffic_context,
        )

        source = SOURCE_INTERACTIVE_CHAT
        try:
            from apps.ai.cos_services import interview as _iv
            if _iv.active_session(self.user, conversation) is not None:
                source = SOURCE_GETTING_TO_KNOW_YOU
        except Exception:  # pragma: no cover - accounting must never break a turn
            logger.warning("interview accounting probe failed", exc_info=True)

        # Assert PRODUCTION explicitly — the accounting default is now `unattributed`, so
        # real interactive traffic must name itself. Only when nothing has already claimed
        # the turn: an outer certification/dev context must keep its classification.
        traffic = None if current_traffic_class() else TRAFFIC_PRODUCTION
        with llm_traffic_context(source=source, traffic_class=traffic):
            return self._generate_turn(
                conversation, message, page_context=page_context, surface=surface,
                request_id=request_id, observer=observer,
                conversation_history=conversation_history,
                writes_enabled=writes_enabled, images=images, attachments=attachments,
            )

    def _generate_turn(self, conversation, message, *, page_context=None, surface="chat",
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
        # Reveal Target: expose the CURRENT workspace URL to the dispatch so
        # navigate_to_workspace can detect "already here" and skip pointless navigation.
        try:
            turn_capture["current_url"] = (
                ((standing_context.get("current_context") or {})
                 .get("current_screen") or {}).get("location", {}) or {}).get("url")
        except Exception:
            pass
        dispatch = self._make_dispatch(
            turn_id=turn_id, surface=surface, tools_called=tools_called,
            observer=observer, turn_capture=turn_capture,
            conversation_id=conversation_id, conversation=conversation,
        )

        answer = self.ai._call_api_with_tools(
            system_prompt, message or "", tools=all_tools(writes_enabled=writes_enabled),
            dispatch=dispatch, user=self.user, endpoint="model_interface",
            conversation_history=conversation_history, images=images,
        )
        answer = answer or ""

        # ============================================================
        # PHASE 2 — BOUNDED EXECUTIVE SYNTHESIS. Phase 1 (above) INVESTIGATED and gathered
        # evidence. For a turn that genuinely required cross-evidence executive judgment
        # (≥2 independent substantive truth surfaces — a runtime signal, never a phrase
        # classifier), the SAME model steps back from the gathered evidence and produces the
        # final judgment. Phase 2 never sees Phase 1's prose (not judge-the-judge); it reasons
        # over the EVIDENCE. On failure/empty, keep the grounded Phase-1 answer as the
        # justified safe fallback (the durable turn is never lost). Never breaks the turn.
        synthesis_used = False
        try:
            from apps.ai.model_interface import synthesis as _synth
            _evidence = turn_capture.get("evidence") or []
            if answer and _synth.synthesis_eligible(_evidence):
                _synth_answer = _synth.run_executive_synthesis(
                    self.ai, message=message or "", evidence=_evidence,
                    standing_context=standing_context,
                    conversation_history=conversation_history, user=self.user,
                )
                if _synth_answer:
                    answer, synthesis_used = _synth_answer, True
                    logger.info("MI_SYNTHESIS used turn=%s surfaces=%s phase1_discarded",
                                turn_id, len(_evidence))
                else:
                    logger.warning("MI_SYNTHESIS empty; kept grounded phase-1 answer turn=%s",
                                   turn_id)
        except Exception:  # pragma: no cover - defensive
            logger.warning("MI_SYNTHESIS phase skipped (error); kept phase-1 answer turn=%s",
                           turn_id, exc_info=True)

        # ============================================================
        # MONEY-EVIDENCE BOUNDARY. A currency amount stated as this user's fact must
        # exist in what THIS turn actually retrieved.
        #
        # The guard (`apps.ai.finance_claim_guard`) is the LOAD-BEARING mechanism and
        # already existed — but only on the legacy `chatgpt_cos` runtime, while the
        # incident it was written for happened HERE, on the certified `model_interface`
        # path (every ToolCallLog row for it: surface `chat_stream`). A safety boundary
        # installed on a runtime the user is not on protects nobody. Wiring the SAME
        # module in keeps ONE authority on what "grounded" means; the constitution's
        # anchor rule is defence in depth, never the enforcement.
        #
        # It runs AFTER synthesis on purpose: Phase 2 rewrites the answer, and that is
        # exactly where an unsupported figure could re-enter.
        try:
            from apps.ai import finance_claim_guard as _guard
            _ev = [e.get("result") for e in (turn_capture.get("evidence") or [])]
            _violations = _guard.validate_currency_claims(answer, _ev)
            if _violations:
                _guard.log_violations(self.user, _violations,
                                      tools_called=tools_called, stage="model_interface")
                # No silent pass-through: an amount WLJ cannot substantiate is replaced
                # by an honest statement rather than shown as retrieved truth.
                answer = _guard.honest_fallback(_violations)
                logger.warning("MI_MONEY_GUARD blocked turn=%s violations=%s",
                               turn_id, len(_violations))
        except Exception:  # never break a turn on the guard itself
            logger.warning("MI_MONEY_GUARD skipped (non-fatal)", exc_info=True)

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
                           "tools_called": list(tools_called),
                           "synthesis_used": synthesis_used},
        )
        return {"answer": answer, "tools_called": tools_called,
                "standing_context": standing_context, "turn_id": turn_id,
                "synthesis_used": synthesis_used,
                # Reveal Target: the navigation directive (if the model revealed a workspace
                # this turn). Shaped {url,label,action_type} for the existing client renderer.
                "navigation": turn_capture.get("navigation")}
