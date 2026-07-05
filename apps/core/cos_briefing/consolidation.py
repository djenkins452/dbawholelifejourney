"""Executive consolidation — one synthesized truth, not an event log.

The Executive Briefing "Needs Attention" column and the Domain Accountability
cards both surface warning/critical ``Insight`` rows. When a single metric drifts
for several days the store holds one row per day with the value baked into the
title ("Protein intake 53% of target", "… 55%", "… 72%", "… 80%"), so the
dashboard repeats four near-identical bullets instead of summarizing the
underlying truth.

``consolidate_findings`` is a FINAL, presentational pass: it groups findings by
their SUBJECT (the title with the varying number masked) and collapses any group
of 2+ into ONE executive item carrying the range, average, and span
("Protein intake below target — 53–80% (avg 65%) over 4 days"). Single findings
pass through untouched. It NEVER mutates DB rows — it returns Insight-like
stand-ins that the briefing/card consumers render exactly like real rows.

Generic by construction: it keys off the title shape, so it consolidates
protein, calories, glucose, blood pressure, or any future repeated metric with
no per-metric special-casing.
"""
from __future__ import annotations

import logging
import re
from collections import OrderedDict

logger = logging.getLogger(__name__)

# Any number, with an optional trailing % (the varying part of a repeated title).
_NUM = re.compile(r"\d+(?:\.\d+)?\s*%?")
_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_TRAILING_CONNECTOR = re.compile(r"\b(?:by|of|at|to|is|was|-|–|—)\s*$", re.IGNORECASE)
_SEVERITY_RANK = {"critical": 3, "warning": 2, "positive": 1, "info": 0}
_DIRECTION_WORDS = ("target", "goal", "under", "over", "above", "below")


class _SynthesizedFinding:
    """Lightweight Insight stand-in — duck-typed for the briefing consumers
    (they read .title / .message / .severity / .module / .insight_type)."""

    def __init__(self, *, title, message, severity, module, insight_type, created_at):
        self.title = title
        self.message = message
        self.severity = severity
        self.module = module
        self.insight_type = insight_type
        self.created_at = created_at
        self.synthesized = True  # marker for consumers/tests


def _topic_key(finding) -> str:
    """Normalize a title to its SUBJECT by masking the varying number, so
    'Protein intake 53% of target' and '… 80% of target' share one key."""
    t = (getattr(finding, "title", "") or "").strip().lower()
    return re.sub(r"\s+", " ", _NUM.sub("#", t)).strip()


def _pct(finding):
    m = _PCT.search(getattr(finding, "title", "") or "")
    return float(m.group(1)) if m else None


def _subject(title: str) -> str:
    """The subject core = the title up to its first number, trailing connector
    removed ('Calories under target by 27%' → 'Calories under target')."""
    title = title or ""
    m = _NUM.search(title)
    core = (title[:m.start()] if m else title).strip(" -–—:,")
    core = _TRAILING_CONNECTOR.sub("", core).strip(" -–—:,")
    return core or title.strip()


def _max_severity(members) -> str:
    best = max(
        members,
        key=lambda m: _SEVERITY_RANK.get((getattr(m, "severity", "") or "").lower(), 0),
    )
    return getattr(best, "severity", "warning") or "warning"


def _span_days(members) -> int:
    dates = {
        getattr(m, "created_at").date()
        for m in members
        if getattr(m, "created_at", None) is not None
    }
    return len(dates) or len(members)


def _synthesize_group(members: list) -> _SynthesizedFinding:
    """Compose ONE executive item from a group of same-subject findings.
    Deterministic — every clause names real, aggregated truth."""
    rep = members[0]  # input is -created_at ordered → first is most recent
    subject = _subject(getattr(rep, "title", "") or "")
    pcts = [p for p in (_pct(m) for m in members) if p is not None]
    days = _span_days(members)
    span = "1 day" if days == 1 else f"{days} days"

    subj_lc = subject.lower()
    has_direction = any(w in subj_lc for w in _DIRECTION_WORDS)
    core = subject
    below = None
    if pcts:
        below = max(pcts) < 100  # "% of target" semantics: <100 is below
        if not has_direction:
            core = f"{subject} {'below' if below else 'above'} target"

    if pcts:
        lo, hi = min(pcts), max(pcts)
        avg = round(sum(pcts) / len(pcts))
        stat = f"~{lo:g}%" if lo == hi else f"{lo:g}–{hi:g}% (avg {avg:g}%)"
        title = f"{core} — {stat} over {span}"
        if has_direction:
            # Subject already states the direction ("Calories under target") —
            # don't repeat it.
            message = (
                f"{subject} — {span}, range {lo:g}–{hi:g}%, average {avg:g}%. "
                f"Consolidated from {len(members)} readings into one concern."
            )
        else:
            where = "below" if below else "above"
            message = (
                f"{subject} has been {where} target for {span} — "
                f"range {lo:g}–{hi:g}%, average {avg:g}%. Consolidated from "
                f"{len(members)} readings into one concern."
            )
    else:
        # No parseable percentage — still collapse repeated same-subject rows.
        title = f"{core} — flagged {len(members)}× over {span}"
        message = getattr(rep, "message", "") or ""

    return _SynthesizedFinding(
        title=title,
        message=message,
        severity=_max_severity(members),
        module=getattr(rep, "module", "") or "",
        insight_type=getattr(rep, "insight_type", "") or "",
        created_at=getattr(rep, "created_at", None),
    )


def consolidate_findings(findings: list, *, min_group: int = 2) -> list:
    """Collapse near-identical same-subject findings into one synthesized item.

    Args:
        findings: Insight-like objects, already ordered by importance/recency.
        min_group: minimum group size to trigger consolidation (default 2).

    Returns:
        A new list where each consolidatable group is replaced by ONE
        synthesized stand-in at the group's most-recent position; singletons
        pass through unchanged. Order and severity precedence are preserved.
        Never raises — on any failure returns the input untouched.
    """
    try:
        if not findings or len(findings) < min_group:
            return findings

        groups: "OrderedDict[str, list]" = OrderedDict()
        for f in findings:
            groups.setdefault(_topic_key(f), []).append(f)

        if all(len(members) < min_group for members in groups.values()):
            return findings  # nothing repeats

        rebuilt: list = []
        emitted: set = set()
        for f in findings:
            key = _topic_key(f)
            if key in emitted:
                continue
            members = groups[key]
            if len(members) < min_group:
                rebuilt.append(f)
            else:
                emitted.add(key)
                rebuilt.append(_synthesize_group(members))
        return rebuilt
    except Exception:
        logger.warning("consolidate_findings failed — returning raw findings",
                       exc_info=True)
        return findings
