# ==============================================================================
# File: apps/core/truth/validation/comparison.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic comparison engine for the Truth Validation Center.
#   Flatten a WLJ truth object into its structured scalar values, then compare each
#   against the structured values present in the Chief-of-Staff response. Scoring is
#   100% deterministic (numeric tolerance + unit normalization, date rendering,
#   normalized text containment). WLJ is always the authority; no model grades a model.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The comparison engine — expected structured truth  VERSUS  values in the response.

This does NOT compare paragraphs. It flattens the deterministic WLJ object into typed
scalar values and, for each, asks a typed deterministic question of the response text:

    PRESENT   the expected value is in the answer (numeric within tolerance / a date
              rendering / normalized text containment)
    MISSING   the expected value is not in the answer, and no competing same-unit value
              contradicts it
    MISMATCH  a value carrying the SAME unit is present but differs from the expected
              value (a confident contradiction — the highest-severity class)
    N/A       the underlying record is absent, so there is nothing to surface

Forbidden values (a prompt's `must_not_surface`) are checked as contamination guards:
their presence in the answer is a violation.
"""
import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Keys that are envelope/metadata plumbing, never user truth to be surfaced.
_SKIP_KEYS = {
    "kind", "identity_key", "freshness", "confidence", "schema_version",
    "generated_at", "id", "pk", "uuid", "slug", "context_ref", "provenance",
    "source_id", "record_id", "entity_id",
}
# Unit tokens we recognize in both the expected object and the response text.
_UNITS = [
    "mg/dl", "mmol/l", "mmhg", "bpm", "kcal", "cal", "calories", "lbs", "lb",
    "kg", "kgs", "%", "mm", "cm", "km", "mi", "miles", "in", "ft", "hrs", "hr",
    "hours", "hour", "mins", "min", "minutes", "minute", "steps", "g", "mg",
    "ml", "oz", "flights", "beats",
]
# Longest-first so "mg/dl" matches before "mg", "lbs" before "lb".
_UNITS_SORTED = sorted(set(_UNITS), key=len, reverse=True)
_UNIT_ALIASES = {
    "lbs": "lb", "kgs": "kg", "hrs": "hr", "hours": "hr", "hour": "hr",
    "mins": "min", "minutes": "min", "minute": "min", "calories": "kcal",
    "cal": "kcal", "miles": "mi", "beats": "bpm",
}

_NUM_RE = re.compile(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")
_UNIT_ALT = "|".join(re.escape(u) for u in _UNITS_SORTED)
# a number immediately followed by a unit token, e.g. "185 lb", "8,432 steps", "42%"
_NUM_UNIT_RE = re.compile(
    r"(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)\s*(" + _UNIT_ALT + r")\b",
    re.IGNORECASE)

_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]


# ---------------------------------------------------------------------------
@dataclass
class ExpectedValue:
    path: str
    label: str
    value: Any
    kind: str            # numeric | date | text
    unit: str = ""       # canonical unit token, or ""


@dataclass
class Check:
    label: str
    path: str
    kind: str
    unit: str
    expected_display: str
    extracted_display: str
    status: str          # present | missing | mismatch | na
    is_forbidden: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label, "path": self.path, "kind": self.kind,
            "unit": self.unit, "expected": self.expected_display,
            "extracted": self.extracted_display, "status": self.status,
            "is_forbidden": self.is_forbidden,
        }


@dataclass
class ObjectGrade:
    present: int = 0
    missing: int = 0
    mismatch: int = 0
    na: int = 0
    forbidden_hits: int = 0
    checks: List[Check] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Denominator excludes N/A (nothing to surface can't be scored)."""
        return self.present + self.missing + self.mismatch

    @property
    def passed(self) -> bool:
        return (self.total > 0 and self.missing == 0
                and self.mismatch == 0 and self.forbidden_hits == 0)

    @property
    def is_na(self) -> bool:
        """The record was absent — object neither passed nor failed."""
        return self.total == 0 and self.forbidden_hits == 0


# ---------------------------------------------------------------------------
def _humanize(path: str) -> str:
    leaf = path.split(".")[-1]
    return leaf.replace("_", " ").strip()


def _canon_unit(unit: str) -> str:
    u = (unit or "").strip().lower()
    return _UNIT_ALIASES.get(u, u)


def _split_num_unit(s: str):
    """'185.2 lb' -> (185.2, 'lb'); '185.2' -> (185.2, ''); None if no number."""
    m = _NUM_UNIT_RE.search(s)
    if m:
        return _to_float(m.group(1)), _canon_unit(m.group(2))
    m = _NUM_RE.search(s)
    if m:
        return _to_float(m.group(0)), ""
    return None, ""


def _to_float(tok: str) -> Optional[float]:
    try:
        return float(str(tok).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _looks_like_date(v: Any):
    """Return a date object if v is date-like, else None."""
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.date() if isinstance(v, _dt.datetime) else v
    if isinstance(v, str):
        s = v.strip()
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            try:
                return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                return None
    return None


def flatten_entity(entity: Dict[str, Any]) -> List[ExpectedValue]:
    """Flatten a CompleteEntity/state dict into typed scalar ExpectedValues.

    Recurses nested dicts. Booleans and collections are skipped (generic presence
    matching on them is unreliable — the operator reviews those). A numeric leaf inherits
    a unit from a sibling `unit`/`units` key, or from a unit embedded in a string value.
    """
    out: List[ExpectedValue] = []
    _walk(entity, "", out)
    # de-duplicate identical (value, unit, kind) — the same fact often appears in more
    # than one dimension (e.g. weight in identity AND standing); one check is enough.
    seen = set()
    deduped = []
    for ev in out:
        key = (ev.kind, ev.unit, _norm_value_key(ev.value))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    return deduped


def _norm_value_key(v):
    f = _to_float(v) if not isinstance(v, bool) else None
    if f is not None:
        return round(f, 4)
    return str(v).strip().lower()


def _walk(node: Any, path: str, out: List[ExpectedValue], sibling_unit: str = ""):
    if isinstance(node, dict):
        unit = _canon_unit(str(node.get("unit") or node.get("units") or "")) or sibling_unit
        for k, v in node.items():
            if str(k).lower() in _SKIP_KEYS or k in ("unit", "units"):
                continue
            _walk(v, f"{path}.{k}" if path else str(k), out, unit)
        return
    if isinstance(node, (list, tuple)) or isinstance(node, bool) or node is None:
        return  # collections + booleans: not auto-scored in v1
    label = _humanize(path)
    # date?
    d = _looks_like_date(node)
    if d is not None:
        out.append(ExpectedValue(path, label, d, "date"))
        return
    # numeric? (int/float, or a string that is a bare/units number)
    if isinstance(node, (int, float)):
        out.append(ExpectedValue(path, label, float(node), "numeric", sibling_unit))
        return
    if isinstance(node, str):
        s = node.strip()
        if not s:
            return
        num, embedded_unit = _split_num_unit(s)
        # treat as numeric only when the string is essentially just a number(+unit)
        if num is not None and re.fullmatch(
                r"\s*-?\d[\d,]*\.?\d*\s*[a-zA-Z/%]*\s*", s):
            out.append(ExpectedValue(path, label, num, "numeric",
                                     embedded_unit or sibling_unit))
            return
        # text/enum — skip ultra-short/uninformative tokens
        if len(s) >= 3:
            out.append(ExpectedValue(path, label, s, "text"))
        return


# ---------------------------------------------------------------------------
def _norm_text(t: str) -> str:
    return " ".join((t or "").lower().split())


def _numbers_in(text: str) -> List[float]:
    return [f for f in (_to_float(m.group(0)) for m in _NUM_RE.finditer(text))
            if f is not None]


def _num_unit_pairs(text: str):
    return [(_to_float(m.group(1)), _canon_unit(m.group(2)))
            for m in _NUM_UNIT_RE.finditer(text)]


def _numeric_tolerance(value: float) -> float:
    # 1% relative, floored at 0.5 absolute — absorbs rounding ("185.2" answered "185").
    return max(0.5, abs(value) * 0.01)


def _match_numeric(ev: ExpectedValue, text: str, pairs, all_nums) -> (str, str):
    val = float(ev.value)
    tol = _numeric_tolerance(val)
    # unit-aware first: a competing same-unit value is a MISMATCH, not a miss.
    if ev.unit:
        same_unit = [n for (n, u) in pairs if u == ev.unit and n is not None]
        for n in same_unit:
            if abs(n - val) <= tol:
                return "present", _fmt_num(n, ev.unit)
        if same_unit:
            return "mismatch", ", ".join(_fmt_num(n, ev.unit) for n in same_unit[:3])
    # unit-agnostic presence
    for n in all_nums:
        if abs(n - val) <= tol:
            return "present", _fmt_num(n, ev.unit)
    return "missing", ""


def _fmt_num(n: float, unit: str = "") -> str:
    s = str(int(n)) if float(n).is_integer() else ("%g" % n)
    return f"{s} {unit}".strip()


def _date_renderings(d: _dt.date, today: Optional[_dt.date]) -> List[str]:
    mon = _MONTHS[d.month - 1]
    forms = [
        d.isoformat(),
        f"{mon} {d.day}",
        f"{mon[:3]} {d.day}",
        f"{d.day} {mon}",
        f"{d.month}/{d.day}",
        f"{d.month}/{d.day}/{d.year}",
        f"{mon} {d.day}, {d.year}",
        d.strftime("%A").lower(),           # weekday name
    ]
    if today:
        delta = (today - d).days
        if delta == 0:
            forms += ["today", "this morning", "tonight"]
        elif delta == 1:
            forms += ["yesterday", "last night"]
        elif 2 <= delta <= 6:
            forms.append(d.strftime("%A").lower())
    return [f.lower() for f in forms]


def _match_date(ev: ExpectedValue, norm: str, today) -> (str, str):
    for form in _date_renderings(ev.value, today):
        if form in norm:
            return "present", form
    return "missing", ""


def _match_text(ev: ExpectedValue, norm: str) -> (str, str):
    val = _norm_text(str(ev.value))
    if not val:
        return "missing", ""
    if val in norm:
        return "present", val
    # multi-word: all significant tokens present (order-independent)
    tokens = [t for t in val.split() if len(t) >= 3]
    if len(tokens) >= 2 and all(t in norm for t in tokens):
        return "present", val
    return "missing", ""


def compare_object(expected_values: List[ExpectedValue], response: str,
                   *, today: Optional[_dt.date] = None,
                   forbidden: Optional[List[str]] = None) -> List[Check]:
    """Compare each expected structured value against the response. Returns Checks."""
    norm = _norm_text(response)
    pairs = _num_unit_pairs(response)
    all_nums = _numbers_in(response)
    checks: List[Check] = []
    for ev in expected_values:
        if ev.kind == "numeric" and ev.value is not None:
            status, extracted = _match_numeric(ev, norm, pairs, all_nums)
            expected_disp = _fmt_num(float(ev.value), ev.unit)
        elif ev.kind == "date":
            status, extracted = _match_date(ev, norm, today)
            expected_disp = ev.value.isoformat()
        else:
            status, extracted = _match_text(ev, norm)
            expected_disp = str(ev.value)
        checks.append(Check(
            label=ev.label, path=ev.path, kind=ev.kind, unit=ev.unit,
            expected_display=expected_disp, extracted_display=extracted,
            status=status))
    # contamination guards: a forbidden phrase's presence is a violation.
    for phrase in (forbidden or []):
        hit = _forbidden_hit(phrase, norm)
        checks.append(Check(
            label=phrase, path="must_not_surface", kind="forbidden", unit="",
            expected_display="(must NOT appear)",
            extracted_display=(hit or ""),
            status="mismatch" if hit else "present", is_forbidden=True))
    return checks


def _forbidden_hit(phrase: str, norm: str) -> str:
    """A forbidden phrase is 'hit' (contamination) when a SUBSTANTIAL share of its
    significant tokens appear in the answer. A single-token phrase must appear exactly;
    a multi-token phrase needs >=60% of its tokens (min 2) — enough to catch a concept
    leaking in ("blood pressure reading" -> "blood pressure ...") without firing on one
    incidental common word. The operator can always override."""
    import math
    tokens = [t for t in _norm_text(phrase).split() if len(t) >= 4]
    if not tokens:
        return ""
    present = [t for t in tokens if t in norm]
    if len(tokens) == 1:
        return tokens[0] if present else ""
    need = max(2, math.ceil(0.6 * len(tokens)))
    if len(present) >= need:
        return " ".join(present)
    return ""


def grade_checks(checks: List[Check]) -> ObjectGrade:
    g = ObjectGrade(checks=list(checks))
    for c in checks:
        if c.is_forbidden:
            if c.status == "mismatch":
                g.forbidden_hits += 1
            continue
        if c.status == "present":
            g.present += 1
        elif c.status == "missing":
            g.missing += 1
        elif c.status == "mismatch":
            g.mismatch += 1
        elif c.status == "na":
            g.na += 1
    return g
