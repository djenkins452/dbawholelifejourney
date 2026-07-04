# ==============================================================================
# File: apps/ai/chatgpt_cos/foundational_facts.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic foundational-fact fast path (no tools, no agentic loop)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-06-24
# ==============================================================================
"""
Foundation fact fast path.

For the five foundational fact prompts we do NOT use the agentic tool loop.
Instead:

    classify intent  ->  get_foundational_health_facts(keys)  ->  plain _call_api
    to phrase the already-retrieved truth  ->  answer.

This mirrors the proven OpenAI mechanism (plain ``ai_service._call_api`` — no
``tools``, no ``tool_choice``, no agentic loop). If ``_call_api`` fails for any
reason, we return a deterministic factual sentence built directly from the
retrieved payload, so the user NEVER sees an empty/failure response.

No legacy Beth, no Beth renderers, no Beth validators are involved.
"""

import json
import logging
import re

from apps.ai.cos_services.execution_facts import EXECUTION_FACT_KEYS

logger = logging.getLogger(__name__)

# Deterministic intent -> fact key map (narrow, foundational facts only).
# First keyword that matches wins; the five categories do not overlap.
_FACT_KEYWORDS = [
    ("current_weight",       ("weight", "weigh", "how much do i weigh")),
    ("last_glucose_reading", ("glucose", "blood glucose", "blood sugar", "blood-sugar",
                              "bloodsugar", "sugar", " bg", "bg ", "bg?", "my bg")),
    ("current_medications",  ("medication", "medicine", "meds", "what meds",
                              "drugs i", "pills i")),
    ("calories_today",       ("calorie", "calories")),
    ("protein_today",        ("protein",)),
    ("sleep_last_night",     ("sleep", "slept", "rest last night")),
    # "steps" (plural) only — never bare "step" (avoids matching "next step").
    ("steps_recent",         ("steps", "step count", "how many steps")),
    ("last_blood_pressure_reading", ("blood pressure", "blood-pressure", "bp")),
    ("latest_meal_logged",   ("meal", "meals", "did i eat", "last food")),
    # ----- GOALS domain facts (deterministic, canonical build_goal_state) -----
    # Goal-specific keywords only — never the reasoning cues ("biggest goal risk",
    # "goals at risk"), which fall through to the Goals reasoning quartet.
    ("active_goal_count",    ("how many goals", "how many active goals",
                              "how many goal", "number of goals", "count of goals")),
    ("goals_overdue",        ("overdue goals", "goals overdue", "goals past due",
                              "goals are overdue", "any goals overdue")),
    ("next_goal_deadline",   ("next goal deadline", "goal deadline", "next goal due",
                              "when is my next goal", "when's my next goal")),
    ("top_goal",             ("top goal", "main goal", "primary goal",
                              "what is my goal", "what's my goal", "whats my goal")),
]

FOUNDATIONAL_KEYS = [k for k, _ in _FACT_KEYWORDS]

# Keys resolved from the Goals canonical state instead of the health-facts source.
GOAL_FACT_KEYS = {"top_goal", "active_goal_count", "goals_overdue",
                  "next_goal_deadline"}

_UNKNOWN_SENTENCE = {
    "current_weight": "I don't have a current weight recorded for you yet.",
    "last_glucose_reading": "I don't have a recent glucose reading recorded for you.",
    "previous_glucose_reading": "I don't have a previous glucose reading recorded for you.",
    "current_medications": "I don't have any current medications recorded for you.",
    "adherence_7d": "I don't have enough dose history yet to calculate your medication adherence.",
    "adherence_30d": "I don't have enough dose history yet to calculate your 30-day medication adherence.",
    "adherence_90d": "I don't have enough dose history yet to calculate your 90-day medication adherence.",
    "calories_today": "I don't have any calories logged for you today.",
    "protein_today": "I don't have any protein logged for you today.",
    "sleep_last_night": "I don't have last night's sleep recorded yet — it may not have synced.",
    "steps_recent": "I don't have recent step data recorded for you — it may not have synced yet.",
    "next_appointment": "You have nothing else on your calendar today.",
    "last_journal": "I don't have any journal entries recorded for you yet.",
    "steps_today": "I don't have today's steps yet — they may not have synced.",
    "steps_yesterday": "I don't have yesterday's steps recorded.",
    "calories_yesterday": "I don't have any calories logged for you yesterday.",
    "average_sleep_7d": "I don't have enough sleep data to show an average yet.",
    "sleep_trend": "I don't have a sleep trend for you yet.",
    "last_blood_pressure_reading": "I don't have a blood pressure reading recorded for you.",
    "latest_meal_logged": "I don't have any logged meals recorded for you yet.",
    "top_goal": "I don't have an active goal recorded for you yet.",
    "active_goal_count": "I don't have any active goals recorded for you yet.",
    "goals_overdue": "I don't have any goals recorded for you yet.",
    "next_goal_deadline": "I don't have any upcoming goal deadlines recorded for you.",
}


def get_foundational_goal_facts(user, keys):
    """Deterministic Goal facts from canonical build_goal_state (no LLM, P24).

    Reads the warm SAE goals module — never recomputes goal truth. Returns the
    same {key: {status, value, ...}} shape the health-facts source uses.
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state
        gs = get_module_state(user, "goals", allow_rebuild=False) or {}
    except Exception:
        logger.warning("COS_FOUNDATION_GOAL_STATE_FAILED user=%s",
                       getattr(user, "id", None), exc_info=True)
        gs = {}
    out = {}
    for key in keys:
        if key == "active_goal_count":
            n = gs.get("active_goal_count")
            out[key] = ({"status": "ok", "value": int(n)} if n is not None
                        else {"status": "unknown"})
        elif key == "top_goal":
            mission = gs.get("mission") if isinstance(gs.get("mission"), dict) else None
            title = None
            if mission:
                title = (mission.get("title") or mission.get("goal_title")
                         or mission.get("name"))
            if not title:
                titles = gs.get("active_titles") or []
                title = titles[0].get("title") if titles else None
            out[key] = ({"status": "ok", "value": title} if title
                        else {"status": "unknown"})
        elif key == "goals_overdue":
            n = gs.get("overdue_goal_count")
            names = [t.get("title") for t in (gs.get("overdue_titles") or [])
                     if t.get("title")]
            out[key] = {"status": "ok", "value": int(n or 0), "titles": names}
        elif key == "next_goal_deadline":
            d = gs.get("days_to_next_deadline")
            upcoming = gs.get("upcoming_titles") or []
            title = upcoming[0].get("title") if upcoming else None
            out[key] = ({"status": "ok", "value": int(d), "title": title}
                        if d is not None else {"status": "unknown"})
    return out

_PHRASE_SYSTEM = (
    "You are the user's Chief of Staff. In ONE short, natural, warm sentence, "
    "state the fact provided. Use ONLY the data given — never add, infer, round, "
    "or invent any number. If the value is unknown, say it isn't recorded yet. "
    "CLINICAL SAFETY: never add your own medical judgment or reassurance "
    "('good', 'fine', 'normal', 'in range', 'healthy') about any health value. If the "
    "fact includes an 'interpretation' object, state ONLY its 'display' wording and, "
    "when its 'concern' is true, surface the 'advice' and suggest verifying — never "
    "downplay or reassure away a flagged value. "
            "EVIDENCE INTEGRITY: if the fact includes an 'integrity' object whose "
            "'ok' is false, the evidence contradicts itself — do NOT confidently "
            "state the value. Instead say you've spotted something that doesn't add "
            "up and will verify it first (use the provided 'investigation' wording). "
            "If the fact includes a 'temporal_warning', say the reading's time is "
            "unconfirmed (a sync/clock issue) and NEVER report a future or impossible "
            "timestamp as if it were the current time."
)


# Personal/external BOUNDARY (P26 DC#3). A definitional/general question that
# happens to contain a domain word ("what is a healthy WEIGHT generally?") must NOT
# trigger personal retrieval. EXTERNAL framing + NO personal grounding => general.
_EXTERNAL_SIGNALS = (
    "generally", "in general", "typically", "typical", "usually", "on average", "average",
    "healthy range", "normal range", "healthy level", "normal level", "ideal range",
    "what is a healthy", "what's a healthy", "what is a normal", "what's a normal",
    "what is normal", "what's normal", "what is the normal", "what is an ideal",
    "what counts as", "considered healthy", "considered normal", "supposed to be",
    "recommended range", "what range", "definition of", "what does it mean",
)

# EDUCATIONAL OVERLAY — phrases that ask for GENERAL education layered ON a personal
# fact ("which of my medications are commonly USED FOR diabetes", "list each med and
# what it is COMMONLY USED FOR"). These are HYBRID: WLJ owns the personal list, but
# the educational part is general knowledge. The deterministic fact-stater can't
# combine them, so it must DECLINE and let the tool loop (WLJ tools + general
# knowledge) handle it. Distinct from _EXTERNAL_SIGNALS, which mark a PURELY general
# question (no personal data needed).
_EDUCATIONAL_OVERLAY = (
    "used for", "use for", "used to treat", "what do they treat", "what does it treat",
    "what are they for", "what is it for", "what's it for", "what they're for",
    "what it's for", "what are these for", "commonly used", "purpose of",
    "what's the purpose", "what is the purpose", "why do i take", "why am i taking",
    "what do they do", "what does it do", "what are they used", "what is it used",
)


def _has_educational_overlay(text):
    """True when a message asks for general education on top of a personal fact."""
    return any(sig in text for sig in _EDUCATIONAL_OVERLAY)


def external_general_signal(message):
    """True when a message is clearly an EXTERNAL/definitional question (not about
    the user's own data): strong external framing AND no personal grounding. Shared
    by the foundational classifier (suppress personal retrieval) and the general
    lane (claim it). Pure, deterministic (P26 DC#3)."""
    if not message:
        return False
    t = str(message).lower()
    tokens = set(re.findall(r"[a-z']+", t))
    personal = bool(tokens & {"my", "i", "me", "mine", "myself", "our", "we"}) or \
        any(p in t for p in ("am i", "do i", "should i", "i'm", "i've"))
    if personal:
        return False
    return any(sig in t for sig in _EXTERNAL_SIGNALS)


def classify_foundational_fact(message):
    """Return the fact key for a foundational-fact prompt, or None.

    Deterministic keyword match — no LLM, no Beth, no broad NLU. EXTERNAL/
    definitional questions ("what is a healthy weight generally?") are suppressed so
    they never retrieve the user's personal data (P26 DC#3)."""
    if not message:
        return None
    if external_general_signal(message):
        return None
    text = str(message).lower()
    # HYBRID (personal fact + general education) — e.g. "which of my medications are
    # commonly used for diabetes". The deterministic fact-stater would answer with
    # the bare list and the educational layer would never run. Decline so it falls
    # through to the tool loop, which combines WLJ truth with general knowledge.
    if _has_educational_overlay(text):
        return None
    # PROGRESSION questions ("what's after Goal Weight 284.9?") are milestone-
    # sequence questions owned by Goals, NOT current-fact lookups — even though the
    # milestone NAME contains a fact keyword like "weight" (P29 DC#1).
    if any(c in text for c in ("what's after", "whats after", "what is after",
                               "what comes after", "next after", "after goal weight",
                               "comes next in", "next milestone", "next phase")):
        return None
    # EXECUTION status facts (journaled/worked out/appointments today, next appt) —
    # deterministic providers that previously fell to the LLM (Batch 2).
    exec_key = _classify_execution_fact(text)
    if exec_key:
        return exec_key
    # MEDICATION DOMAIN — the full retrieval surface (four entities × inventory /
    # execution / adherence / profile, plus combined + remaining). Resolved deterministically.
    med_key = _classify_medicine(text)
    if med_key:
        return med_key
    # PRIOR-READING TRUTH: "what was the PREVIOUS/PRIOR glucose reading?" is a
    # DISTINCT reading from the current one — checked BEFORE the keyword loop so the
    # "glucose" term can never collapse it into last_glucose_reading (current).
    if _is_previous_glucose_query(text):
        return "previous_glucose_reading"
    matched = None
    for key, keywords in _FACT_KEYWORDS:
        if any(kw in text for kw in keywords):
            matched = key
            break
    if matched is None:
        return None
    return _refine_to_day(matched, text)


_GLUCOSE_TERMS = ("glucose", "blood sugar", "blood glucose", "bloodsugar",
                  "blood-sugar", " bg ", " bg?")
_PREVIOUS_QUALIFIERS = ("previous", "prior", "before that", "before it",
                        "before this", "the one before", "one before",
                        "reading before", "earlier reading", "reading prior")


def _is_previous_glucose_query(text):
    """A question about the PREVIOUS glucose reading (a glucose term + an
    earlier-reading qualifier) — never the current/latest reading."""
    t = f" {text} "
    return (any(g in t for g in _GLUCOSE_TERMS) and
            any(q in text for q in _PREVIOUS_QUALIFIERS))


def _format_single_entity(ent):
    """One complete answer for a single named entity (dict from CompleteEntity.to_dict()):
    answers dose / schedule / purpose / taken-today / adherence from ONE object."""
    d = ent.get("definition") or {}
    sched = (ent.get("plan") or {}).get("schedule") or []
    st = (ent.get("standing") or {}).get("today") or {}
    perf = (ent.get("performance") or {}).get("adherence") or {}
    seg = [x for x in (d.get("dose"), d.get("category")) if x]
    if sched:
        seg.append("scheduled at " + ", ".join(sched))
    out = [f"{ent.get('identity')} — {', '.join(seg)}.".replace(" — .", ".")]
    if d.get("purpose"):
        out.append(f"Purpose: {d['purpose']}.")
    if st.get("expected"):
        pend = f", {st.get('pending', 0)} still pending" if st.get("pending") else ""
        out.append(f"Today: {st.get('taken', 0)} of {st['expected']} taken{pend}.")
    if perf.get("7d") is not None:
        out.append(f"7-day adherence: {perf['7d']}%.")
    return " ".join(out)


def _single_entity_medication(user, message):
    """Single-entity retrieval: if the message names a SPECIFIC active intake and asks
    about it (dose / schedule / today / adherence / purpose / "am I taking X"), answer
    from the ONE complete entity — not the whole inventory. Deterministic, data-aware."""
    text = (message or "").lower()
    cues = ("dose", "how's my", "how is my", "how am i doing", "tell me about",
            "when do i take", "when should i take", "did i take my", "what's my",
            "what is my", "am i taking", "do i take", "details on", "info on",
            "purpose of", "what is", "schedule for", "adherence for")
    if not any(c in text for c in cues):
        return None
    # A plural/collection question is NOT single-entity.
    if any(p in text for p in ("medications", "supplements", "everything", "all my",
                               "all of my", "all the")):
        return None
    from apps.health.services.medicine_queries import MedicineQueries
    ent = MedicineQueries.describe_one(user, text)
    if ent is None:
        return None
    d = ent.to_dict()
    answer = _format_single_entity(d)
    return {"answer": answer, "empty_reason": None, "tools_advertised": [],
            "tools_called": ["MedicineQueries"], "fast_path": "foundational_fact",
            "fact_key": "medication_detail", "fact": d, "basis": answer, "supporting": {}}


_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})


def _parse_history_date(text, today):
    import re
    from datetime import date
    if "last month" in text:
        y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        return date(y, m, 1)
    mo = re.search(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})\b", text)
    if mo:
        d = date(today.year, _MONTHS[mo.group(1)], int(mo.group(2)))
        return d.replace(year=today.year - 1) if d > today else d
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if iso:
        return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    return None


def _hist_result(answer, fact_key, detail):
    return {"answer": answer, "empty_reason": None, "tools_advertised": [],
            "tools_called": ["MedicineQueries"], "fast_path": "foundational_fact",
            "fact_key": fact_key, "fact": detail, "basis": answer, "supporting": {}}


def _medication_history(user, message):
    """Layer 1 medication HISTORY + condition mapping (deterministic, data-aware): point-
    in-time inventory, lifecycle (start/stopped), dose-change history, condition/purpose,
    and program-change. Parameters (name / condition / date / window) are read from the
    message and resolved against canonical truth."""
    text = (message or "").lower()
    from datetime import date  # noqa
    from apps.core.utils import get_user_today
    from apps.health.services.medicine_queries import MedicineQueries
    med_word = any(w in text for w in ("medication", "meds", "prescription", "pill",
                                       "taking", "take", "on for"))

    # 1) Per-med lifecycle — "when did I start X", "when did X's dose change".
    ent = MedicineQueries.describe_one(user, text)
    if ent is not None:
        name = ent.identity
        if "when" in text and ("start" in text or "begin" in text or "put on" in text):
            d = MedicineQueries.started_on(user, name)
            return _hist_result(
                f"You started {name} on {d}." if d else
                f"I don't have a start date on record for {name}.",
                "medication_started", {"name": name, "date": d})
        if "dose" in text and ("change" in text or "changed" in text or "history" in text):
            ch = MedicineQueries.dose_changes(user, name)
            if not ch:
                ans = f"{name}'s dose hasn't changed on record."
            else:
                ans = f"{name} dose changes: " + "; ".join(
                    f"{c['date']}: {c['from']} → {c['to']}" for c in ch) + "."
            return _hist_result(ans, "medication_dose_history", {"name": name, "changes": ch})

    # 2) Condition / purpose — "which medications are for diabetes".
    _conditions = ("diabetes", "blood pressure", "hypertension", "cholesterol", "thyroid",
                   "depression", "anxiety", "pain", "allergy", "acid reflux", "heartburn")
    cond = next((c for c in _conditions if c in text), None)
    if cond and ("which" in text or "what" in text or "for" in text) and med_word:
        names = MedicineQueries.for_condition(user, cond)
        return _hist_result(
            (f"Your prescriptions for {cond}: {', '.join(names)}." if names
             else f"You don't have any prescriptions on file for {cond}."),
            "medications_for_condition", {"condition": cond, "names": names})

    # 3) Discontinued / stopped.
    if med_word and any(k in text for k in ("stopped", "discontinued", "no longer",
                                            "came off", "quit", "have i stopped")):
        d = MedicineQueries.discontinued(user)
        return _hist_result(
            ("You haven't discontinued any medications on record." if not d else
             "You've stopped: " + "; ".join(f"{x['name']} ({x['date']})" for x in d) + "."),
            "discontinued_medications", {"discontinued": d})

    # 4) Program change over a window — "has my medication program changed in 90 days".
    if med_word and ("program" in text or "changed" in text or "changes" in text) and \
            any(k in text for k in ("last", "past", "90", "60", "30", "month", "days")):
        days = 90 if "90" in text else (60 if "60" in text else 30)
        ch = MedicineQueries.program_changes(user, days)
        return _hist_result(
            (f"No changes to your medication program in the last {days} days." if not ch else
             f"In the last {days} days: " + "; ".join(
                 f"{c['name']} — {c['event']} ({c['date']})" for c in ch) + "."),
            "medication_program_changes", {"days": days, "changes": ch})

    # 5) Point-in-time inventory — "what was I taking on June 1 / last month".
    if any(p in text for p in ("was i taking", "were i taking", "what was i on",
                               "what medications was i")):
        d = _parse_history_date(text, get_user_today(user))
        if d:
            names = MedicineQueries.taking_on(user, d)
            return _hist_result(
                (f"On {d.isoformat()} you were taking: {', '.join(names)}." if names
                 else f"I have nothing on record as active on {d.isoformat()}."),
                "taking_on_date", {"date": d.isoformat(), "names": names})
    return None


def _med_window(text):
    if "90" in text or "ninety" in text:
        return "90d"
    if "30" in text or "thirty" in text or "monthly" in text:
        return "30d"
    return "7d"


def _classify_medicine(text):
    """Deterministic routing across the Medication domain's full retrieval surface.
    OTC / Supplement / Wellness are first-class and never route to prescription; each
    entity type supports inventory / execution / adherence / profile symmetrically."""
    has_otc = "otc" in text or "over the counter" in text or "over-the-counter" in text
    has_supp = "supplement" in text
    has_well = "wellness" in text
    _exec_cue = ("did i take", "have i taken", "taken today", "take today", "still to take")
    _detail_cue = ("for each", "review", "rundown", "breakdown", "for today")

    # COMBINED — everything I take (only when not scoped to one category).
    if not (has_otc or has_supp or has_well) and any(
            p in text for p in ("what am i taking", "what do i take", "everything i take",
                                "everything i'm taking", "everything i am taking",
                                "everything i'm on", "everything i am on",
                                "all my medications and supplements", "all that i take",
                                "list everything")):
        return "current_intake_all"
    # REMAINING / pending today.
    if any(p in text for p in ("still need to take", "still have to take", "left to take",
                               "what's left to take", "whats left to take", "remaining dose",
                               "haven't taken", "have not taken", "what's left today",
                               "what do i have left", "what's pending", "doses pending")):
        return "medications_remaining_today"

    # ENTITY-SCOPED routing. Supplement is fully symmetric (inventory/execution/adherence/
    # profile); OTC/Wellness expose inventory (their execution/adherence use the same
    # mechanism when needed).
    if has_supp:
        # Profile (a "review"/"for each" detail request) precedes adherence — a detailed
        # request that merely mentions "adherence" is still a profile.
        if any(c in text for c in _detail_cue):
            return "supplement_profile"
        if "adherence" in text:
            return "supplement_adherence_" + _med_window(text)
        if any(c in text for c in _exec_cue):
            return "supplement_execution_today"
        return "current_supplements"
    if has_otc:
        return "current_otc"
    if has_well:
        return "current_wellness"

    # PRESCRIPTION (default "medicine" sense).
    _med_words = ("medication", "meds", "prescription", "prescriptions", "pill")
    if any(w in text for w in _med_words):
        if any(c in text for c in _detail_cue) or (
                ("list" in text or "show" in text or "give me" in text)
                and any(c in text for c in ("dose", "schedule", "category", "status",
                                            "today", "details", "everything"))):
            return "medication_profile"
        if "adherence" in text:
            return "adherence_" + _med_window(text)
        if any(c in text for c in _exec_cue):
            return "meds_today"
    return None


def _classify_execution_fact(text):
    """Deterministic 'did I X today/yesterday / what's on my calendar' detection.
    Gated on a status phrasing ('did i'/'have i'/'do i have') so coaching questions
    ('what workout should I do today') never match."""
    status_q = any(p in text for p in ("did i", "have i", "do i have", "am i"))
    is_yesterday = "yesterday" in text
    today_q = any(p in text for p in ("today", "yet", "so far"))
    is_workout = any(w in text for w in ("work out", "workout", "worked out",
                                         "exercise", "exercised", "gym"))
    # WORKOUT status — a completed-day truth answerable for today OR yesterday.
    # WorkoutQueries.is_completed_on supports any date, so the deterministic provider
    # must too (this was the certification blocker: yesterday fell to the LLM).
    if is_workout and status_q:
        if is_yesterday:
            return "workout_yesterday"
        if today_q:
            return "workout_today"
        return None
    # "did I take my meds today" — adherence status (today-scoped). NOTE: avoid bare
    # "med" — it is a substring of "consumed" ("calories consumed today").
    if (any(w in text for w in ("meds", "medication", "medicine", "pill", "dose"))
            and status_q and today_q and not is_yesterday):
        return "meds_today"
    # "when did I last journal" — date of last entry (distinct from journal_today bool).
    if ("journal" in text or "journaled" in text) and not today_q \
            and ("when" in text or "last" in text):
        return "last_journal"
    # "what did I eat today/yesterday" — retrieve the actual MEALS (past-framing).
    # A CALORIE question ("how many calories did I eat") is a different intent — it
    # wants the calorie TOTAL, not the meal list — so it must NOT match here.
    _is_calorie_q = "calorie" in text
    _ate = any(p in text for p in ("did i eat", "have i eaten", "what did i eat",
                                   "what have i eaten", "what i ate", "what i've eaten",
                                   "food did i", "meals did i", "meals have i"))
    if _ate and not _is_calorie_q and is_yesterday:
        return "meals_yesterday"
    if _ate and not _is_calorie_q and today_q:
        return "meals_today"
    # journal / appointments status: today-scope only (the question space asks today).
    if is_yesterday:
        return None
    if ("journal" in text or "journaled" in text) and status_q and today_q:
        return "journal_today"
    if ("appointment" in text or "on my calendar" in text
            or "on my schedule" in text):
        if "next" in text or "upcoming" in text:
            return "next_appointment"
        return "appointments_today"
    return None


def _refine_to_day(key, text):
    """Batch 1 — when a metric is asked for a SPECIFIC day, route to the per-day
    deterministic fact (DailyHealthQueries) instead of the 7-day average. 'Retrieve,
    never derive': "steps yesterday" -> steps_yesterday, "sleep last night" -> the
    actual last night. Bare "steps" defaults to today."""
    is_yesterday = "yesterday" in text
    if key == "steps_recent":
        return "steps_yesterday" if is_yesterday else "steps_today"
    if key == "calories_today" and is_yesterday:
        return "calories_yesterday"
    if key == "sleep_last_night" and any(
            w in text for w in ("average", "this week", "past week", "7 day", "7-day",
                                "weekly", "lately", "typically")):
        # "average/this-week sleep" stays on the 7-day-average SAE fact; only a
        # specific-night question ("last night") gets the per-day deterministic fact.
        return "average_sleep_7d"
    return key


def _humanize_minutes(mins):
    """A short, human gap: 'a few minutes', '25 minutes', 'about 1 hour',
    'about 2 hours 10 minutes'. Deterministic."""
    try:
        m = int(mins)
    except (TypeError, ValueError):
        return "a short time"
    if m < 2:
        return "about a minute"
    if m < 60:
        return f"{m} minutes"
    h, r = divmod(m, 60)
    hh = f"{h} hour" + ("s" if h != 1 else "")
    if r == 0:
        return f"about {hh}"
    return f"about {hh} {r} minutes"


def format_fact_sentence(key, fact):
    """Build a deterministic factual sentence straight from the payload.

    This is the guaranteed answer used when phrasing via _call_api is
    unavailable — it is never empty and never invents data."""
    if not isinstance(fact, dict) or fact.get("status") in (
        "unknown", "unsupported_fact",
    ):
        return _UNKNOWN_SENTENCE.get(key, "That isn't recorded for you yet.")

    # PRIOR-READING TRUTH: "previous reading" when there is no earlier reading is said
    # PLAINLY — never substituted with the current reading (the production defect).
    if fact.get("status") == "no_previous":
        if fact.get("has_current"):
            return ("You only have one glucose reading on record, so there isn't an "
                    "earlier reading before it yet.")
        return "I don't have any glucose readings recorded for you yet."

    # EVIDENCE INTEGRITY gate: the evidence contradicts itself (impossible timestamp,
    # duplicated/out-of-order predecessor, stale-as-current). A CoS does NOT
    # confidently present a value she can't stand behind — she transitions to
    # investigation. Preserve any upstream temporal_warning wording verbatim.
    from apps.core.truth import integrity as _integrity
    if _integrity.failed(fact):
        msg = _integrity.investigation_for(fact)
        tw = fact.get("temporal_warning")
        if tw and msg and tw not in msg:
            msg = f"{msg} ({tw})"
        if msg:
            return msg

    value = fact.get("value")
    unit = (fact.get("unit") or "").strip()

    if key == "current_weight":
        s = f"Your current weight is {value} {unit}".strip()
        if fact.get("trend"):
            s += f", and the trend is {fact['trend']}"
        return s + "."
    if key == "last_glucose_reading":
        from apps.core.truth.present import humanize_number
        base = f"Your last glucose reading was {humanize_number(value)} {unit}".strip()
        interp = fact.get("interpretation") or {}
        if interp.get("display"):
            base += f" ({interp['display']})"
        s = base + "."
        # Clinical safety: a flagged value is surfaced with its advice, never reassured.
        if interp.get("concern") and interp.get("advice"):
            s += " " + interp["advice"]
        # Temporal sanity: never present an impossible time; surface the warning.
        if fact.get("temporal_warning"):
            s += " " + fact["temporal_warning"]
        return s
    if key == "previous_glucose_reading":
        from apps.core.truth.present import humanize_number
        s = f"Your previous glucose reading was {humanize_number(value)} {unit}".strip()
        interp = fact.get("interpretation") or {}
        if interp.get("display"):
            s += f" ({interp['display']})"
        rel = fact.get("relation") or {}
        mins = rel.get("minutes_before_current")
        if mins is not None:
            s += f", recorded {_humanize_minutes(mins)} before your current reading"
        cv = rel.get("current_value")
        direction = rel.get("direction")
        if cv is not None and direction in ("rose", "fell"):
            verb = "risen" if direction == "rose" else "fallen"
            s += f" — glucose has since {verb} to {humanize_number(cv)}"
        elif cv is not None and direction == "held":
            s += f" — your current reading is the same, {humanize_number(cv)}"
        s += "."
        if interp.get("concern") and interp.get("advice"):
            s += " " + interp["advice"]
        return s
    if key == "current_medications":
        meds = value if isinstance(value, list) else [value]
        count = fact.get("count", len(meds))
        if count == 0:
            return "You don't have any prescription medications on file right now."
        return (f"You're currently taking {count} prescription medication(s): "
                f"{', '.join(str(m) for m in meds)}.")
    if key in ("current_supplements", "current_otc", "current_wellness"):
        items = value if isinstance(value, list) else [value]
        count = fact.get("count", len(items))
        noun = fact.get("noun") or {"current_supplements": "supplement",
                                    "current_otc": "over-the-counter medication",
                                    "current_wellness": "wellness product"}[key]
        verb = "tracking" if key == "current_wellness" else "taking"
        if count == 0:
            return f"You're not currently {verb} any {noun}s."
        return (f"You're currently {verb} {count} {noun}(s): "
                f"{', '.join(str(m) for m in items)}.")
    if key.endswith(("adherence_7d", "adherence_30d", "adherence_90d")):
        days = 7 if key.endswith("7d") else (30 if key.endswith("30d") else 90)
        scope = "supplement" if key.startswith("supplement") else "medication"
        return f"Your {days}-day {scope} adherence is {value}%."
    if key in ("medication_execution_today", "supplement_execution_today"):
        noun = "supplement" if key.startswith("supplement") else "medication"
        expected = fact.get("expected", 0)
        if not expected:
            return f"You don't have any {noun}s scheduled for today."
        pending = fact.get("pending", 0)
        tail = f", with {pending} still to take" if pending else ""
        return f"You've taken {fact.get('taken', 0)} of {expected} {noun} dose(s) today{tail}."
    if key == "current_intake_all":
        groups = [("prescription medications", fact.get("prescription") or []),
                  ("supplements", fact.get("supplement") or []),
                  ("OTC medications", fact.get("otc") or []),
                  ("wellness products", fact.get("wellness") or [])]
        present = [(label, items) for label, items in groups if items]
        if not present:
            return "You're not currently tracking anything you take."
        lines = ["Here's everything you're currently taking:", ""]
        for label, items in present:
            lines.append(f"{label.capitalize()} ({len(items)}): {', '.join(items)}")
        return "\n".join(lines)
    if key == "medications_remaining_today":
        doses = fact.get("doses") or []
        if not doses:
            return "You've taken everything scheduled for today — nothing left."
        items = ", ".join(f"{d.get('medication')} ({d.get('time')})" for d in doses)
        return f"You still have {len(doses)} dose(s) to take today: {items}."
    if key == "medication_detail":
        return _format_single_entity(fact)
    if key in ("medication_profile", "supplement_profile"):
        noun = fact.get("noun") or ("supplement" if key.startswith("supplement")
                                    else "prescription medication")
        meds = fact.get("medications") or []          # list of CompleteEntity dicts
        if not meds:
            return f"You don't have any active {noun}s on file right now."

        def _pct(v):
            return f"{v}%" if v is not None else "not enough history yet"
        lines = [f"You have {len(meds)} active {noun}(s):", ""]
        for m in meds:
            d = m.get("definition") or {}
            sched = ", ".join((m.get("plan") or {}).get("schedule") or []) or "no set schedule"
            td = (m.get("standing") or {}).get("today") or {}
            took = (f"{td.get('taken', 0)} of {td.get('expected', 0)} taken today"
                    if td.get("expected") else "none scheduled today")
            detail = ", ".join(x for x in (d.get("dose"), d.get("category"),
                                           m.get("status")) if x)
            lines.append(f"• {m.get('identity')} — {detail}; schedule: {sched}; {took}")
            # Dose-level truth (never collapsed): show each scheduled dose's status.
            doses = td.get("doses") or []
            if len(doses) > 1:
                for dose in doses:
                    lines.append(f"    – {dose.get('time')}: {dose.get('status')}")
        adh = fact.get("adherence") or {}
        today = fact.get("today") or {}
        lines.append("")
        lines.append(f"Today: {today.get('taken', 0)} of {today.get('expected', 0)} "
                     f"{noun} doses taken.")
        scope_label = "Supplement" if key.startswith("supplement") else "Medication"
        lines.append(f"{scope_label} adherence — 7-day: {_pct(adh.get('7d'))}, "
                     f"30-day: {_pct(adh.get('30d'))}, 90-day: {_pct(adh.get('90d'))}.")
        return "\n".join(lines)
    if key == "calories_today":
        from apps.core.truth.present import humanize_number, present_remaining
        if fact.get("target"):       # answer the next question: how much is left
            return present_remaining("Calories", value, fact["target"]) + "."
        return f"You've logged {humanize_number(value)} calories today."
    if key == "protein_today":
        from apps.core.truth.present import humanize_number, present_remaining
        if fact.get("target"):
            return present_remaining("Protein", value, fact["target"], "g") + "."
        return f"You've logged {humanize_number(value)} g of protein today."
    if key == "sleep_last_night":
        # Batch 1/3 — the ACTUAL most-recent night, with read freshness (Law 1).
        if fact.get("freshness") == "stale":
            fd = fact.get("for_date")
            return (f"I don't have last night's sleep yet — your most recent is "
                    f"{value} {unit or 'hours'}, from {fd}.")
        return f"You slept {value} {unit or 'hours'} last night."
    if key == "average_sleep_7d":
        s = f"You've been averaging {value} {unit or 'hours'} of sleep"
        if fact.get("trend"):
            s += f", and your sleep trend is {fact['trend']}"
        return s + "."
    if key == "average_glucose_yesterday":
        return f"Your recent average glucose is {value} {unit or 'mg/dL'}.".replace("  ", " ")
    if key == "glucose_yesterday":
        from apps.core.truth.present import humanize_number
        return f"Yesterday your glucose was {humanize_number(value)} {unit or 'mg/dL'}.".replace("  ", " ")
    if key == "journal_today":
        return ("Yes — you've journaled today." if value
                else "Not yet — you haven't journaled today.")
    if key == "workout_today":
        return ("Yes — you've logged a workout today." if value
                else "Not yet — you haven't logged a workout today.")
    if key == "workout_yesterday":
        return ("Yes — you logged a workout yesterday." if value
                else "No — you didn't log a workout yesterday.")
    if key == "appointments_today":
        if not value:
            return "You have nothing on your calendar today."
        items = fact.get("items") or []
        listed = ("; ".join(items)) if items else ""
        n = value
        head = f"You have {n} appointment{'s' if n != 1 else ''} today"
        return f"{head}: {listed}." if listed else f"{head}."
    if key == "next_appointment":
        return f"Your next appointment is {value}."
    if key in ("meals_today", "meals_yesterday"):
        from apps.core.truth.present import present_groups
        when = "yesterday" if key == "meals_yesterday" else "today"
        meals = fact.get("meals") or {}
        if not value or not meals:
            return ("You didn't log any food yesterday." if when == "yesterday"
                    else "You haven't logged any food today yet.")
        # Grouped, bulleted, duplicate-collapsed list — scannable, not a dense sentence.
        lead = "Yesterday you logged:" if when == "yesterday" else "Today you've logged:"
        return present_groups(meals.items(), lead=lead)
    if key == "meds_today":
        expected = fact.get("expected", 0)
        if not expected:
            return "You don't have any medications scheduled for today."
        taken, pending = value or 0, fact.get("pending", 0)
        s = f"You've taken {taken} of {expected} doses today"
        if pending:
            s += f", with {pending} still to take"
        return s + "."
    if key == "last_journal":
        days = fact.get("days_since")
        if days == 0:
            return "You journaled today."
        s = f"You last journaled on {value}"
        if days:
            s += f" ({days} day{'s' if days != 1 else ''} ago)"
        return s + "."
    if key in ("steps_today", "steps_yesterday"):
        if key == "steps_today" and fact.get("freshness") == "partial":
            return f"You've logged {value} steps so far today."
        when = "yesterday" if key == "steps_yesterday" else "today"
        return f"You logged {value} steps {when}."
    if key == "calories_yesterday":
        n = int(value) if isinstance(value, (int, float)) and float(value).is_integer() else value
        return f"Yesterday you logged {n} calories."
    if key == "steps_recent":
        # Legacy 7-day-average fallback (the classifier now routes to the per-day
        # fact above); kept honest as an average, never a specific day.
        return f"You've been averaging about {value} steps a day over the past week."
    if key == "sleep_trend":
        return f"Your sleep trend is {value}."
    if key == "last_blood_pressure_reading":
        dia = fact.get("diastolic")
        bp = f"{value}/{dia}" if dia is not None else f"{value}"
        return f"Your last blood pressure reading was {bp} mmHg."
    if key == "latest_meal_logged":
        # No storage jargon ("meal entry" / "logged ... entry"); plain language.
        return f"The last time you tracked any food was {value}."
    if key == "active_goal_count":
        return f"You have {value} active goal(s) right now."
    if key == "top_goal":
        return f"Your top goal right now is \"{value}\"."
    if key == "goals_overdue":
        if not value:
            return "You don't have any overdue goals right now."
        names = fact.get("titles") or []
        if names:
            return f"You have {value} overdue goal(s): {', '.join(names)}."
        return f"You have {value} overdue goal(s)."
    if key == "next_goal_deadline":
        title = fact.get("title")
        if title:
            return f"Your next goal deadline is in {value} day(s) — \"{title}\"."
        return f"Your next goal deadline is in {value} day(s)."
    # TF3 PRESENTATION CONSISTENCY: the default must NEVER leak a raw snake_case key to
    # the user. Humanize the label so the worst case is still plain language.
    label = key.replace("_", " ").strip().capitalize()
    return f"{label}: {value} {unit}".strip()


# Facts answered DETERMINISTICALLY (LLM rephrase bypassed): numeric-value-gated facts
# (the number must always appear) and PRESENTATION-formatted facts (the structured/
# multi-line list must survive — the LLM would flatten it back into a dense sentence).
_NUMERIC_VALUE_KEYS = {"calories_today", "calories_yesterday", "protein_today",
                       "meals_today", "meals_yesterday",
                       # Medication adherence — the % must always appear (canonical truth).
                       "adherence_7d", "adherence_30d", "adherence_90d",
                       # current_medications: the answer must be EXACTLY the canonical
                       # prescription list — the LLM rephrase could embellish or pull
                       # supplements from broader context. Bypass it (trust contract).
                       "current_medications",
                       # Supplement / OTC / Wellness inventories — exact canonical lists.
                       "current_supplements", "current_otc", "current_wellness",
                       # Full medication-domain retrieval surface — exact canonical answers.
                       "current_intake_all", "medications_remaining_today",
                       "medication_execution_today", "supplement_execution_today",
                       "supplement_adherence_7d", "supplement_adherence_30d",
                       "supplement_adherence_90d", "medication_detail",
                       # profiles: the complete structured business object must survive
                       # verbatim (the LLM would flatten/embellish it).
                       "medication_profile", "supplement_profile",
                       # Prior-reading truth: the previous reading must be stated
                       # deterministically (distinct value + relation to current), and
                       # the "only one reading" case must never be embellished.
                       "previous_glucose_reading"}


def _temporal_or_clinical(fact):
    """A fact whose answer MUST be deterministic (LLM rephrase bypassed) because a
    follow-up will read the same struct: anything with a timestamp or a clinical
    interpretation. Keeps the value answer and its follow-ups from ever diverging."""
    if not isinstance(fact, dict):
        return False
    # A FAILED integrity verdict must be answered deterministically — the investigation
    # must never be rephrased by the LLM back into a confident value.
    from apps.core.truth import integrity as _integrity
    if _integrity.failed(fact):
        return True
    return bool(fact.get("recorded_at") or fact.get("as_of") or fact.get("for_date")
                or fact.get("temporal_warning") or fact.get("interpretation"))


def answer_foundational_fact(user, message):
    """Deterministic foundational-fact fast path.

    Returns the same result shape as ChatGPTCoSService.generate, or None if the
    message is not a foundational fact prompt (caller proceeds normally).
    """
    # Medication HISTORY + condition mapping (data-aware) — checked BEFORE present-time
    # single-entity, so "when did my Mounjaro dose CHANGE?" isn't captured by the "dose"
    # attribute cue: "when did I start Metformin?", "which prescriptions are for diabetes?",
    # "what was I taking on June 1?".
    hist = _medication_history(user, message)
    if hist is not None:
        return hist
    # Single-entity retrieval (data-aware): "what's my Metformin dose?", "am I taking fish
    # oil?", "how's my Lantus adherence?" — answered from the ONE complete entity.
    single = _single_entity_medication(user, message)
    if single is not None:
        return single
    key = classify_foundational_fact(message)
    if key is None:
        return None
    return answer_fact_by_key(user, key)


def answer_fact_by_key(user, key):
    """Answer a KNOWN foundational-fact key deterministically (same result shape as
    answer_foundational_fact). Used by the referential resolver to re-point the active
    topic to a new timeframe ("what about yesterday?") without re-classifying a message."""
    from apps.ai.services import ai_service

    # Deterministic Provider Registry routes the key to the owning domain provider
    # (goal / execution / health-default). New domains register, not branch here.
    fact, fact_source = _resolve_fact(user, key)

    # The guaranteed, deterministic answer built from the payload.
    deterministic = format_fact_sentence(key, fact)

    # TRUTH CONSISTENCY: a fact that carries a TIMESTAMP or a CLINICAL interpretation is
    # answered DETERMINISTICALLY — the LLM rephrase is bypassed. Otherwise the LLM can
    # assert temporal/clinical claims NOT in the struct (it once said "time is
    # unconfirmed" over a valid timestamp), while the follow-up (compose_when) reads the
    # struct — producing contradictory answers from the same fact. Bypassing guarantees
    # the value answer and every follow-up originate from the SAME deterministic object.
    # Calorie/value-total questions are gated on a numeric VALUE — answer them
    # deterministically so the number always appears (the LLM rephrase could drop it).
    deterministic_only = _temporal_or_clinical(fact) or key in _NUMERIC_VALUE_KEYS
    if deterministic_only:
        answer = deterministic
    else:
        # Phrase the retrieved truth with the PLAIN _call_api (no tools, no loop).
        phrased = None
        try:
            phrased = ai_service._call_api(
                _PHRASE_SYSTEM,
                f"Fact to state ({key}): {json.dumps(fact, default=str)}",
                max_tokens=120,
                temperature=0.3,
                endpoint="cos_chat",
                user=user,
            )
        except Exception:
            logger.warning("COS_FOUNDATION_PHRASING_FAILED user=%s key=%s",
                           getattr(user, "id", None), key, exc_info=True)
            phrased = None
        answer = (phrased or "").strip() or deterministic
    logger.info(
        "COS_FOUNDATION_FASTPATH user=%s key=%s deterministic_only=%s answer_len=%d",
        getattr(user, "id", None), key, deterministic_only, len(answer),
    )
    return {
        "answer": answer,
        "empty_reason": None,
        "tools_advertised": [],
        "tools_called": [fact_source],
        "fast_path": "foundational_fact",
        "fact_key": key,
        # Supporting evidence for DETERMINISTIC conversation memory: a follow-up
        # ("why do you say that?") is explained from this fact, not an LLM reconstruction.
        "fact": fact,
        "basis": deterministic,
        # Supporting facts a natural follow-up will need (e.g. the MEALS behind a
        # calorie total) — gathered once now, read from memory on the follow-up.
        "supporting": _gather_supporting(user, key),
    }


def _gather_supporting(user, key):
    try:
        from apps.ai.chatgpt_cos.supporting_facts import gather_supporting
        return gather_supporting(user, key)
    except Exception:
        return {}


# ============================================================================
# Deterministic Provider Registry wiring (Layer 1 — last platform capability).
# New domains register a provider instead of adding an if/elif branch above.
# ============================================================================
from apps.ai.chatgpt_cos.fact_registry import (  # noqa: E402
    register_fact_provider, resolve as _registry_resolve,
)


def _exec_fact_provider(user, keys):
    from apps.ai.cos_services.execution_facts import get_foundational_execution_facts
    return get_foundational_execution_facts(user, keys)


def _health_fact_provider(user, keys):
    from apps.ai.cos_services.health_facts import get_foundational_health_facts
    return get_foundational_health_facts(user, keys)


def _register_builtin_fact_providers():
    register_fact_provider(lambda k: k in GOAL_FACT_KEYS,
                           get_foundational_goal_facts,
                           "get_foundational_goal_facts")
    register_fact_provider(lambda k: k in EXECUTION_FACT_KEYS,
                           _exec_fact_provider,
                           "get_foundational_execution_facts")
    # Default: health/nutrition/medicine facts (all remaining keys).
    register_fact_provider(lambda k: False, _health_fact_provider,
                           "get_foundational_health_facts", default=True)


_register_builtin_fact_providers()


def _resolve_fact(user, key):
    """Registry-driven dispatch for answer_foundational_fact (returns (fact, source))."""
    return _registry_resolve(user, key)
