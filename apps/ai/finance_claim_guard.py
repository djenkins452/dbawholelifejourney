# ==============================================================================
# File: apps/ai/finance_claim_guard.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A currency amount stated as this user's fact must have been retrieved.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""A money figure the assistant states as fact must exist in THIS turn's evidence.

THE INCIDENT (2026-08-31, 22:56). Danny asked: *"Didn't july have a $2300 is house
payment? why did you ignore that one?"* — a deliberate test. The assistant called no
tool at all (`tools_called: []`), replied *"It seems I overlooked the $2,300.00 house
payment from July"*, and placed **House Payment in July — $2,300.00** at number 3 of a
ranked list of largest expenses. Danny: *"You are making things up... I wanted to see if
you would lie and you did."*

It had happened twice already in the same conversation. At 22:54 he mentioned a $5,000
payment; the assistant answered *"I made an error by not including the $5,000.00
transaction"* — no tool call. At 22:55 it asserted both that figure and a $2,388.95 he
had supplied, as a ranked answer. Every one of those numbers came out of his own
messages and went back to him wearing the clothes of retrieved truth.

WHY A PROMPT RULE WAS NOT ENOUGH. The constitution already forbids this. It also says a
value may be reused when *"already present as WLJ-grounded evidence in THIS
conversation"* — and conversation history reaches the model as ordinary `assistant` and
`user` turns with nothing marking which numbers were retrieved. The rule asks the model
to make a distinction its context cannot express. Worse, the history builder truncates
each message at 800 characters, so a hedge can be severed from the number it qualified.

So this is not another instruction. It is a boundary: after the answer is written and
before it is shown, every currency amount in it is checked against what the turn
actually retrieved. Unsupported amounts do not reach the user as fact.

WHAT IS DELIBERATELY ALLOWED.
  * **Denial.** "I don't see a $2,300 payment in July" is the CORRECT answer to the
    question that caused this, and it necessarily contains the number.
  * **General knowledge.** "A gym membership is typically about $50 a month" is not a
    claim about this user's records, and the constitution gives it to the model.
  * **The user's own words, quoted back to question them.** Same mechanism as denial.

What is NOT allowed is an amount asserted as a fact about this person's money that no
Finance service produced this turn — whether it came from their question, from the
assistant's own earlier prose, or from nowhere.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

#: `$1,234.56`, `$2,300`, `1,234.56 dollars`. Deliberately NOT a bare number: a count,
#: a year and a step total are not money, and flagging them would make the guard noise.
MONEY = re.compile(
    r"\$\s?(\d[\d,]*(?:\.\d{1,2})?)"
    r"|\b(\d[\d,]*(?:\.\d{1,2})?)\s?(?:dollars|USD)\b",
    re.I,
)

#: How far either side of an amount to read when deciding whether it is being asserted.
WINDOW = 120

#: The assistant saying it does NOT have this. The answer the incident should have given.
_DENIAL = re.compile(
    r"\b(?:no|not|n't|never|nothing)\b[^.]{0,60}?\b(?:see|find|show|record|"
    r"matching|any|such|there)\b"
    r"|\b(?:don't|doesn't|didn't|cannot|can't|couldn't|unable)\b"
    r"|\bno (?:record|transaction|payment|match|such|sign|trace)\b"
    r"|\bnot (?:in|among|on) (?:your|the)\b"
    r"|\bI (?:have|hold) no\b",
    re.I,
)

#: Not a claim about THIS person's records — general knowledge, an example, a hypothetical.
_GENERAL = re.compile(
    r"\b(?:typically|usually|generally|on average|roughly|approximately|about|around|"
    r"say|example|e\.g\.|for instance|might|would|could|if you|suppose|hypothetical|"
    r"ballpark|order of|rule of thumb|per month typically)\b",
    re.I,
)

#: The user asked a question containing a figure and the assistant is repeating it in
#: order to address it — legitimate only alongside a denial or a retrieval, both of
#: which are handled above. Kept separate so the reason is legible in the log.
_QUOTING = re.compile(
    r"\byou (?:mentioned|said|asked|referred|pointed)\b|\byour question\b",
    re.I,
)


def amounts_in_text(text):
    """Every currency amount a piece of prose states, as Decimals."""
    found = set()
    for match in MONEY.finditer(text or ""):
        raw = match.group(1) or match.group(2) or ""
        try:
            found.add(Decimal(raw.replace(",", "")))
        except InvalidOperation:
            continue
    return found


def amounts_in_evidence(payloads, _depth=0):
    """Every number anywhere in this turn's tool results.

    Deliberately indiscriminate about WHICH key a number sat under. The question is
    only "did WLJ produce this figure at all this turn" — pinning it to the right field
    is the model's job and the envelope's, not this boundary's. Being generous here
    keeps the guard from firing on a real retrieval it failed to parse, which would be
    a far worse failure than letting a genuine number through.
    """
    found = set()
    if _depth > 12:
        return found
    if isinstance(payloads, dict):
        for value in payloads.values():
            found |= amounts_in_evidence(value, _depth + 1)
    elif isinstance(payloads, (list, tuple, set)):
        for value in payloads:
            found |= amounts_in_evidence(value, _depth + 1)
    elif isinstance(payloads, bool):
        return found
    elif isinstance(payloads, (int, float, Decimal)):
        try:
            found.add(Decimal(str(payloads)))
        except InvalidOperation:
            pass
    elif isinstance(payloads, str):
        # Numbers arrive as strings all over Finance — CalcResult serialises Decimals
        # that way on purpose, so they must count as evidence.
        for token in re.findall(r"-?\d[\d,]*(?:\.\d+)?", payloads):
            try:
                found.add(Decimal(token.replace(",", "")))
            except InvalidOperation:
                continue
    return found


def _supported(amount, evidence):
    """Is this amount in evidence, allowing for how money gets written?

    `2300` and `2300.00` are the same claim. So is `-849.84`: the sign convention is the
    surface's business, and a magnitude quoted from a negative row is still retrieved.
    """
    for candidate in (amount, -amount):
        if candidate in evidence:
            return True
    quantised = amount.quantize(Decimal("0.01"))
    for value in evidence:
        try:
            if abs(value).quantize(Decimal("0.01")) == quantised:
                return True
        except InvalidOperation:
            continue
    return False


def _exempt(window):
    """Is this amount being denied, generalised, or otherwise not asserted as fact?"""
    if _DENIAL.search(window):
        return "denial"
    if _GENERAL.search(window):
        return "general_knowledge"
    return None


def validate_currency_claims(response, evidence_payloads):
    """Currency amounts stated as fact that this turn did not retrieve.

    Returns `[{amount, window, ...}]` — empty when the answer is clean. Takes NO account
    of the user's message: a number the user supplied is exactly what went wrong, and
    treating their wording as a source is the defect, not the exception to it. Quoting
    it back to deny it stays legal through the denial window.
    """
    text = response or ""
    if not text.strip():
        return []
    evidence = amounts_in_evidence(evidence_payloads)

    violations = []
    for match in MONEY.finditer(text):
        raw = match.group(1) or match.group(2) or ""
        try:
            amount = Decimal(raw.replace(",", ""))
        except InvalidOperation:
            continue
        if _supported(amount, evidence):
            continue
        window = text[max(0, match.start() - WINDOW):
                      min(len(text), match.end() + WINDOW)]
        reason = _exempt(window)
        if reason:
            continue
        violations.append({
            "amount": str(amount),
            "stated_as": match.group(0),
            "window": window,
        })
    return violations


# ─────────────────────────────────────────────────────────────────────────────────
# MATERIAL CLAIM COHERENCE (Gate 1B)
#
# Grounding the AMOUNT alone is not enough. Every field in
#     "Your $688.95 Target purchase on July 22 was your largest Dining expense"
# except the amount can be false while the amount is perfectly real — merchant, date,
# category and rank freely recombined across different rows. A guard that only asks
# "did WLJ produce this number" certifies that sentence.
#
# So the boundary also asks: the fields stated ALONGSIDE a grounded amount — do they
# belong to the SAME canonical row that amount came from?
#
# It uses ONLY the structured evidence this turn returned. It never queries the
# database from prose, never re-derives Finance truth, and never becomes a second
# store. And it fails OPEN by construction: a violation is raised only when a stated
# value provably belongs to a DIFFERENT evidence row, never merely because the guard
# could not find it. Silence is not proof of fabrication; contradiction is.
# ─────────────────────────────────────────────────────────────────────────────────

#: Where a row's fields live across the shapes Finance evidence actually arrives in —
#: a ranked result (`results[]` with `meta`), an entity (`definition`), a bare row.
_FIELD_KEYS = {
    "merchant": ("payee", "merchant", "name", "identity", "description", "food_name"),
    "category": ("category",),
    "account": ("account",),
    "date": ("date", "occurred_on", "logged_date", "recorded_at"),
}

_DATE_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b"
    r"|\b(\d{4})-(\d{2})-(\d{2})\b",
    re.I,
)
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _norm(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def evidence_rows(payloads, _depth=0):
    """Canonical rows this turn returned, normalised across evidence shapes.

    A "row" is any dict carrying a number AND at least one identifying field. Ranked
    results, entity records and plain rows all reduce to the same shape, so coherence
    is checked once rather than per-surface.
    """
    rows = []
    if _depth > 12:
        return rows
    if isinstance(payloads, dict):
        amounts = set()
        for key in ("value", "amount", "spend_amount", "total_calories"):
            v = payloads.get(key)
            if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
                try:
                    amounts.add(Decimal(str(v)))
                except InvalidOperation:
                    pass
        fields = {}
        merged = dict(payloads)
        for nested in ("meta", "definition", "plan"):
            if isinstance(payloads.get(nested), dict):
                merged.update(payloads[nested])
        for field, keys in _FIELD_KEYS.items():
            for k in keys:
                if merged.get(k) not in (None, "", [], {}):
                    fields[field] = str(merged[k])
                    break
        if amounts and fields:
            for amount in amounts:
                rows.append({"amount": amount, **fields})
        for value in payloads.values():
            rows.extend(evidence_rows(value, _depth + 1))
    elif isinstance(payloads, (list, tuple)):
        for value in payloads:
            rows.extend(evidence_rows(value, _depth + 1))
    return rows


def _dates_in(text):
    """Specific DAYS stated in a window. A bare month ('in July') is a period, not a
    transaction date, and is deliberately not treated as a claim about one."""
    out = set()
    for m in _DATE_RE.finditer(text or ""):
        if m.group(1):
            out.add((_MONTHS[m.group(1)[:3].lower()], int(m.group(2))))
        elif m.group(3):
            out.add((int(m.group(4)), int(m.group(5))))
    return out


def _row_date(row):
    d = _dates_in(str(row.get("date") or ""))
    if d:
        return d
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(row.get("date") or ""))
    return {(int(m.group(2)), int(m.group(3)))} if m else set()


def validate_claim_coherence(response, evidence_payloads):
    """Fields stated next to a grounded amount that belong to a DIFFERENT canonical row.

    Returns `[{amount, field, stated, window, ...}]`; empty when coherent. Only
    contradictions are reported — a value the guard cannot locate at all is left alone.
    """
    text = response or ""
    rows = evidence_rows(evidence_payloads)
    if not text.strip() or not rows:
        return []

    # Every distinct value Finance returned for each field this turn. A stated value is
    # only judged when WLJ itself produced it somewhere — otherwise the guard would be
    # inventing a vocabulary and policing prose.
    vocab = {}
    for field in ("merchant", "category", "account"):
        seen = {}
        for row in rows:
            value = row.get(field)
            if value:
                seen[_norm(value)] = value
        vocab[field] = seen

    violations = []
    for match in MONEY.finditer(text):
        raw = match.group(1) or match.group(2) or ""
        try:
            amount = Decimal(raw.replace(",", "")).quantize(Decimal("0.01"))
        except InvalidOperation:
            continue
        window = text[max(0, match.start() - WINDOW):
                      min(len(text), match.end() + WINDOW)]
        if _exempt(window):
            continue
        owners = []
        for row in rows:
            try:
                if abs(row["amount"]).quantize(Decimal("0.01")) == amount:
                    owners.append(row)
            except InvalidOperation:
                continue
        if not owners:
            continue        # an ungrounded amount is the other check's business
        win = _norm(window)

        for field in ("merchant", "category", "account"):
            allowed = set()
            for row in owners:
                if row.get(field):
                    allowed.add(_norm(row[field]))
            for norm_value, original in vocab[field].items():
                if not norm_value or norm_value in allowed:
                    continue
                if norm_value in win:
                    violations.append({
                        "amount": str(amount), "field": field,
                        "stated": original, "window": window,
                        "belongs_to": sorted(allowed) or ["(none)"],
                    })

        stated_days = _dates_in(window)
        if stated_days:
            allowed_days = set()
            for row in owners:
                allowed_days |= _row_date(row)
            if allowed_days and not (stated_days & allowed_days):
                violations.append({
                    "amount": str(amount), "field": "date",
                    "stated": [f"{m:02d}-{d:02d}" for m, d in sorted(stated_days)],
                    "window": window,
                    "belongs_to": [f"{m:02d}-{d:02d}" for m, d in sorted(allowed_days)],
                })
    return violations


def validate_ranking_order(response, evidence_payloads):
    """A stated ranked list must follow the canonical ranked order.

    Only engages when this turn actually produced a ranking and the answer states two
    or more of its amounts — otherwise order is not being claimed.
    """
    text = response or ""
    ranked = _ranked_values(evidence_payloads)
    if len(ranked) < 2 or not text.strip():
        return []
    positions = {}
    for match in MONEY.finditer(text):
        raw = match.group(1) or match.group(2) or ""
        try:
            amount = Decimal(raw.replace(",", "")).quantize(Decimal("0.01"))
        except InvalidOperation:
            continue
        if amount in ranked and amount not in positions:
            if not _exempt(text[max(0, match.start() - WINDOW):
                                min(len(text), match.end() + WINDOW)]):
                positions[amount] = match.start()
    if len(positions) < 2:
        return []
    stated = [a for a, _ in sorted(positions.items(), key=lambda kv: kv[1])]
    canonical = [a for a in ranked if a in positions]
    if stated != canonical:
        return [{"field": "ranking", "stated": [str(a) for a in stated],
                 "belongs_to": [str(a) for a in canonical],
                 "amount": str(stated[0]), "window": "(ranked list)"}]
    return []


def _ranked_values(payloads, _depth=0):
    """The canonical ORDER of a ranking this turn produced, as quantised amounts."""
    if _depth > 12:
        return []
    if isinstance(payloads, dict):
        results = payloads.get("results")
        if isinstance(results, list) and len(results) >= 2:
            out = []
            for r in results:
                if not isinstance(r, dict):
                    continue
                v = r.get("value")
                if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
                    try:
                        out.append(abs(Decimal(str(v))).quantize(Decimal("0.01")))
                    except InvalidOperation:
                        pass
            if len(out) >= 2:
                return out
        for value in payloads.values():
            found = _ranked_values(value, _depth + 1)
            if found:
                return found
    elif isinstance(payloads, (list, tuple)):
        for value in payloads:
            found = _ranked_values(value, _depth + 1)
            if found:
                return found
    return []


def validate_finance_claims(response, evidence_payloads):
    """THE boundary. One authority, one call: amounts must be retrieved, and the fields
    stated beside them must belong to the same canonical row, in the canonical order."""
    return (validate_currency_claims(response, evidence_payloads)
            + validate_claim_coherence(response, evidence_payloads)
            + validate_ranking_order(response, evidence_payloads))


def strict_regeneration_note(violations):
    """What to tell the model when its draft stated a figure nothing produced."""
    amounts = ", ".join(sorted({v["stated_as"] for v in violations}))
    return (
        "STOP. Your draft answer stated these money amounts as fact: "
        f"{amounts}. No WLJ Finance service returned them on this turn, so you do not "
        "know them. A figure that appeared in the user's question, or in something you "
        "said earlier in this conversation, is NOT evidence — repeating it does not "
        "make it true, and presenting it in a ranked list makes it look retrieved when "
        "it is not.\n"
        "Rewrite the answer. Either RETRIEVE the figure from a Finance tool and state "
        "what it actually returned, or say plainly that you cannot find it — naming "
        "the measure and period you checked. 'I don't see a payment of that amount in "
        "July' is a correct and complete answer. Do not estimate, do not round to the "
        "user's number, and do not apologise your way into agreeing with a figure you "
        "have not verified."
    )


def honest_fallback(violations):
    """Used only if the model states an unverified amount twice. Never a number."""
    return (
        "I need to correct myself before I go further: I was about to give you a "
        "figure I haven't actually verified against your records, and I'd rather say "
        "so than hand you a number that looks right.\n\n"
        "Let me pull the real transactions and come back to you with what's actually "
        "there — including the period and account each one came from."
    )


def log_violations(user, violations, *, tools_called, stage):
    logger.error(
        "FINANCE_CLAIM_UNSUPPORTED user=%s stage=%s tools_called=%s amounts=%s",
        getattr(user, "id", "?"), stage, ",".join(tools_called or []) or "none",
        ",".join(v["stated_as"] for v in violations),
    )
