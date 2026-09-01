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
