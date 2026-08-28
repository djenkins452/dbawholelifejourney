"""Rich Confirmation — the presentation-independent action contract.

docs/WLJ_RICH_CONFIRMATION_ARCHITECTURE.md. Turns a pending deterministic action (its name,
params, and optional structured ``confirmation_detail`` preview) into ONE reusable, client-
agnostic confirmation VIEW: title, summary, preview lines, and Available Actions (primary +
secondary[]), each with a label, a style, and the natural-language aliases the typed path
matches. The SAME view drives every client (desktop pills, mobile stacked, voice) and the
SAME aliases resolve a typed "yes"/"cancel" deterministically — buttons and text can never
drift because both come from this one contract over one bound record.

Binary by default (derived generically); N-way capable (a handler may supply an explicit
``actions`` list in ``confirmation_detail`` — e.g. Medication Merge: Merge / Keep Both / Cancel).
"""
import re

# Natural-language equivalents. Buttons submit these `key`s; the typed pre-parser matches a
# message against these aliases → the same `key`. ONE vocabulary for both input styles.
CONFIRM_ALIASES = ["yes", "y", "yeah", "yep", "sure", "ok", "okay", "confirm", "confirmed",
                   "proceed", "go ahead", "go", "do it", "looks good", "sounds good",
                   "import", "save", "save it", "log it", "add it", "create it"]
CANCEL_ALIASES = ["no", "n", "nope", "cancel", "stop", "never mind", "nevermind",
                  "don't", "dont", "don't do it", "do not", "forget it", "abort",
                  "discard", "delete it no"]

# action → (primary label, style). Default primary is "Confirm". A destructive action's
# primary renders in the danger style.
_PRIMARY_LABELS = {
    "import_journal_entries": ("Import", "primary"),
    "log_body_measurements": ("Save", "primary"),
    "log_weight": ("Save", "primary"),
    "create_task": ("Create", "primary"),
    "create_goal": ("Create", "primary"),
    "create_event": ("Add", "primary"),
    "create_journal_entry": ("Save", "primary"),
    "add_gratitude": ("Save", "primary"),
    "mutate_task": ("Update", "primary"),
    "complete_task": ("Complete", "primary"),
}


def _is_destructive(action):
    a = (action or "").lower()
    return a.startswith("delete") or "delete" in a or a.startswith("remove") or "discard" in a


def _primary_for(action):
    """(label, style) for the primary action, derived from the action name."""
    if action in _PRIMARY_LABELS:
        return _PRIMARY_LABELS[action]
    if _is_destructive(action):
        return ("Delete", "danger")
    return ("Confirm", "primary")


def _fmt_date(iso):
    from datetime import date
    try:
        d = date.fromisoformat(str(iso))
    except (ValueError, TypeError):
        return str(iso)
    return d.strftime("%b ") + str(d.day) + d.strftime(", %Y")


def _preview_from_detail(detail):
    """Structured preview LINES (facts only) derived from a confirmation_detail, or []."""
    if not isinstance(detail, dict):
        return "", []
    kind = detail.get("kind")
    if kind == "record":  # Structured Import (journal, …)
        records = list(detail.get("records") or [])
        skipped = list(detail.get("skipped") or [])
        noun = detail.get("noun") or "records"
        recognized = len(records) + len(skipped)
        isos = sorted([r.get("date_iso") for r in records if r.get("date_iso")]
                      + [s.get("date_iso") for s in skipped if s.get("date_iso")])
        lines = [f"{len(records)} will be imported"]
        if skipped:
            lines.append(f"{len(skipped)} will be skipped")
        if isos:
            lines.append(f"Date range: {_fmt_date(isos[0])} – {_fmt_date(isos[-1])}"
                         if isos[0] != isos[-1] else f"Date: {_fmt_date(isos[0])}")
        return f"I found {recognized} {noun}.", lines
    if kind == "exceptional_measurement":
        d = detail.get("detail") or {}
        lines = []
        if d.get("proposed_value") is not None:
            lines.append(f"Proposed: {d['proposed_value']} {d.get('proposed_unit', '')}".strip())
        if d.get("compared_with") is not None:
            lines.append(f"Most recent recorded: {d['compared_with']} "
                         f"{d.get('canonical_unit', '')}".strip())
        if d.get("absolute_delta") is not None:
            lines.append(f"Difference: {d['absolute_delta']} "
                         f"{d.get('canonical_unit', '')}".strip())
        return detail.get("exception") or "", lines
    # measurement kind (body measurements) or any list-of-rows import
    rows = list(detail.get("measurements") or [])
    skipped = list(detail.get("skipped") or [])
    if rows or skipped:
        noun = detail.get("noun") or "measurements"
        lines = [f"{len(rows)} will be saved"]
        if skipped:
            lines.append(f"{len(skipped)} can't be saved")
        absent = int(detail.get("absent_count") or 0)
        if absent:
            lines.append(f"{absent} field{'s' if absent != 1 else ''} were blank")
        return f"I found {len(rows)} {noun}.", lines
    return "", []


def _clean_action(a, *, default_key, default_label, default_style, default_aliases):
    """Normalize one action spec (from a handler-supplied actions list) into the contract."""
    a = a if isinstance(a, dict) else {}
    return {
        "key": a.get("key") or default_key,
        "label": a.get("label") or default_label,
        "style": a.get("style") or default_style,
        "aliases": list(a.get("aliases") or default_aliases),
    }


def build_view(action, params=None, confirmation_detail=None, *, summary=None):
    """Build the presentation-independent confirmation VIEW for a pending action.

    Returns {title, summary, preview[], actions{primary, secondary[]}}. Binary by default;
    if ``confirmation_detail['actions']`` is present it is used verbatim (N-way)."""
    params = params or {}
    detail = confirmation_detail if isinstance(confirmation_detail, dict) else {}

    detail_summary, preview = _preview_from_detail(detail)
    label, style = _primary_for(action)

    # N-way: a handler may declare explicit actions. Otherwise derive binary confirm/cancel.
    explicit = detail.get("actions")
    if isinstance(explicit, dict) and explicit.get("primary"):
        primary = _clean_action(explicit.get("primary"), default_key="confirm",
                                 default_label=label, default_style=style,
                                 default_aliases=CONFIRM_ALIASES)
        secondary = [
            _clean_action(s, default_key=f"opt{i}", default_label="Option",
                          default_style="secondary", default_aliases=[])
            for i, s in enumerate(explicit.get("secondary") or [])
        ]
        # Guarantee a cancel escape hatch exists.
        if not any(s["key"] == "cancel" for s in secondary):
            secondary.append({"key": "cancel", "label": "Cancel", "style": "secondary",
                              "aliases": CANCEL_ALIASES})
    else:
        primary = {"key": "confirm", "label": label, "style": style,
                   "aliases": CONFIRM_ALIASES}
        secondary = [{"key": "cancel", "label": "Cancel", "style": "secondary",
                      "aliases": CANCEL_ALIASES}]

    title = detail.get("title") or _title_for(action)
    # The authorization line is ALWAYS derived from the bound action+params — a handler's
    # `detail` may enrich the preview but may never restate what is being authorized.
    authorization = authorization_line(action, params)
    if not authorization:
        return None            # fail closed: nothing deterministic to present
    # M2: an EXCEPTIONAL measurement carries its deterministic discrepancy INTO the
    # authorization line, so what the user is asked to authorize states plainly how far
    # the value sits from canonical truth. It rides M1's bound payload — there is no
    # separate "are you sure" path.
    exception = detail.get("exception")
    if exception:
        authorization = f"{authorization} — {exception}"
    return {
        "title": title,
        "authorization": authorization,
        # Never empty: a handler may enrich the summary, but the bound authorization
        # line is the floor, so the card always states what is being authorized.
        "summary": summary or detail.get("summary") or detail_summary or authorization,
        "preview": preview,
        "actions": {"primary": primary, "secondary": secondary},
    }


# Params that identify WHAT is being written, in the order a human reads them. Generic:
# these are the argument names WLJ's write handlers already use across domains — no
# domain, product or question is special-cased here.
_IDENTIFYING_PARAMS = ("target", "record_type", "record_id",
                       "title", "name", "food_name", "value", "amount", "quantity",
                       "hours", "content", "text", "query", "task_query", "metric",
                       "meal_type", "unit", "date", "due_date", "on_date",
                       "scheduled_time")
_AUTHORIZATION_MAX_VALUES = 4
# After the identifying params, every remaining NUMERIC argument is appended: those are
# the values the write will actually store. Without this a nutrition write read as
# "Log food — food name Stuffed Peppers, meal type dinner" and the user would have
# authorized eight numbers they were never shown (caught by the end-to-end acceptance
# run, 2026-08-28). Generic — it keys on the argument being a number, never on a domain.
_AUTHORIZATION_MAX_NUMERIC = 12
_NEVER_SHOW = frozenset({"confirmed", "record_id", "source_artifact_id", "confidence"})


def authorization_line(action, params=None):
    """THE ONE DETERMINISTIC SENTENCE naming exactly what this confirmation authorizes.

    Rendered from the BOUND (action, params) — never from model prose, and never from a
    handler's free-text message. This exists because a production confirmation was
    narrated to the user as *"I've prepared to log Stuffed Peppers for dinner"* while the
    bound action was `create_task`: the user authorized something they were never shown.
    The action's own name leads the sentence, so a task always reads as a task and a
    weight write always reads as a weight write.

    Returns "" when the action is unknown/empty — the caller then FAILS CLOSED rather
    than presenting an ambiguous authorization.
    """
    act = (action or "").strip()
    if not act:
        return ""
    params = params if isinstance(params, dict) else {}
    bits = []
    for key in _IDENTIFYING_PARAMS:
        if key not in params:
            continue
        val = params[key]
        if val is None or val == "" or isinstance(val, (dict, list)):
            continue
        text = str(val)
        if len(text) > 60:
            text = text[:60] + "…"
        bits.append(f"{key.replace('_', ' ')} {text}")
        if len(bits) >= _AUTHORIZATION_MAX_VALUES:
            break
    shown = set(_IDENTIFYING_PARAMS[:len(bits)]) | {k for k in _IDENTIFYING_PARAMS
                                                    if f"{k.replace('_', ' ')} " in
                                                    " ".join(bits) + " "}
    numeric = []
    for key, val in params.items():
        if key in _NEVER_SHOW or key in shown:
            continue
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        numeric.append(f"{key.replace('_', ' ')} {val}")
        if len(numeric) >= _AUTHORIZATION_MAX_NUMERIC:
            break
    detail = ", ".join(bits + sorted(numeric))
    return f"{_title_for(act)}" + (f" — {detail}" if detail else "")


def _title_for(action):
    """A short human title from the action name ('import_journal_entries' → 'Import journal entries')."""
    words = (action or "action").replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else "Confirm action"


def _norm(text):
    return re.sub(r"[^a-z0-9' ]+", " ", (text or "").strip().lower()).strip()


def match_typed(message, view):
    """Deterministically map a typed message to an action `key` in this confirmation's view,
    or None when it doesn't clearly match (then the model handles it). Matches when the whole
    message equals an alias, or is a very short message that starts with an alias (so
    "yes please" / "cancel that" resolve, but a long unrelated sentence does not)."""
    if not isinstance(view, dict):
        return None
    msg = _norm(message)
    if not msg or len(msg) > 40:
        return None
    actions = view.get("actions") or {}
    ordered = [actions.get("primary")] + list(actions.get("secondary") or [])
    # Exact-match first (most confident), across all actions.
    for a in ordered:
        if not a:
            continue
        for alias in a.get("aliases") or []:
            if msg == _norm(alias):
                return a["key"]
    # Short leading-token match ("yes please", "no thanks", "cancel that").
    words = msg.split()
    if len(words) <= 3:
        for a in ordered:
            if not a:
                continue
            for alias in a.get("aliases") or []:
                na = _norm(alias)
                if na and (msg.startswith(na + " ") or (" " in na and na in msg)):
                    return a["key"]
    return None
