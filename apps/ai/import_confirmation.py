"""Multimodal-import confirmation PRESENTATION framework (domain-agnostic).

WLJ owns truth; a domain handler returns ONLY deterministic structured truth in
``ActionResult.confirmation_detail``. This framework is the single, generic presenter that turns
that truth into the RESULTS-not-intentions confirmation the user sees before anything is written:
what was recognised, what will and won't import, and WHY. **Presentation lives here, never in a
domain handler.** Body measurements is simply the first registered renderer; Labs, Blood Pressure,
Nutrition, Medications, Sleep, Body Composition — any future multimodal import — register a
renderer (a lead line + a noun) and reuse this same presenter unchanged.

When a real structured confirmation CARD is later built (deferred Milestone 3), it consumes the
SAME ``confirmation_detail`` and this text presenter becomes the graceful-degradation fallback —
the truth contract does not change, only the surface that renders it.

confirmation_detail contract (the domain handler fills these — all FACTS, never a verdict):
    renderer      str   registry key selecting the lead + noun (e.g. 'body_measurement_session')
    source        str   where the candidates came from ('Renpho Screenshot', 'photo', …)
    measurements  list  rows WLJ WILL import — {label, value, unit, uncertain?}
    skipped       list  perceived rows WLJ will NOT import — {label|metric, value, unit, reason}
    derived       dict  display-only derived facts, machine-readable — {key: value}
    absent_count  int   perceived-but-blank fields (reported to the user, never hidden)

The presenter renders FACTS only ("I recognised… / I will import… / I cannot import…"); it never
emits a verdict or an "I think…". Every line traces to a field the handler deterministically set.
"""

# reason code (set by the handler) → the plain-language WHY the user reads. Domain-agnostic:
# every multimodal import shares "unrecognised" and "implausible" skip classes; record imports
# (Structured Import Orchestration) add marked-skipped / no-content / invalid / duplicate.
_SKIP_REASON_TEXT = {
    "unrecognized_metric": "WLJ doesn't have a place to store this one yet, so I left it out.",
    "implausible": "the reading looked out of range, so I left it out rather than save a likely misread.",
    "marked_skipped": "the source marked this day as skipped, so I didn't create an entry.",
    "no_content": "there was no entry text for this one, so I left it out.",
    "invalid_date": "I couldn't read a valid date for this one, so I left it out.",
    "uncertain_boundaries": ("I couldn't confidently recognize the journal's date headers, so I "
                             "didn't import anything rather than risk assigning wrong dates."),
    "uncertain_date": "I couldn't confidently read this entry's date, so I left it out.",
    "duplicate": "you already have this one, so I won't create it again.",
}

# renderer key → presentation config. A future domain adds one line here (or calls
# register_import_renderer) — no change to the presenter itself.
_RENDERERS = {}


def register_import_renderer(key, *, lead, noun="items", kind="measurement"):
    """Register an import renderer. ``lead`` is a one-line template that may reference
    ``{source}``; ``noun`` is the plural summary noun ("measurements", "entries"). ``kind``
    selects the render shape: 'measurement' (value+unit rows — the multimodal default) or
    'record' (Structured Import Orchestration — one uploaded document → many dated records)."""
    _RENDERERS[key] = {"lead": lead, "noun": noun, "kind": kind}


register_import_renderer(
    "body_measurement_session",
    lead="I analyzed your body measurement {source}.",
    noun="measurements",
)


def format_value(value, unit):
    """Human-readable value+unit for one candidate (16.29\" / 24.5% / 150 lb / 120 mmHg).
    Domain-agnostic: reads the unit the handler already validated; unknown values pass through."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    u = (unit or "").lower()
    if u == "in":
        return f'{s}"'
    if u == "pct":
        return f"{s}%"
    if u:
        return f"{s} {u}"
    return s


def _source_phrase(source):
    """A natural noun for where the candidates came from, for the lead line."""
    s = (source or "").lower()
    if "photo" in s:
        return "photo"
    if "document" in s or "export" in s or "file" in s:
        return "document"
    return "screenshot"


def _humanize(key):
    return str(key).replace("_", " ").replace("-", " ").strip()


def _fmt_date(iso):
    """'2022-09-10' → 'September 10, 2022' (de-zeroed). Falls back to the raw string."""
    from datetime import date
    try:
        d = date.fromisoformat(str(iso))
    except (ValueError, TypeError):
        return str(iso)
    return d.strftime("%B ") + str(d.day) + d.strftime(", %Y")


def _render_record(detail, cfg):
    """Render a Structured Import Orchestration ``confirmation_detail`` (one document → many
    dated records). Facts only: count, date range, how many have/haven't a time, what will and
    won't be created and why. Every line derives from structured fields the adapter set."""
    records = list(detail.get("records") or [])
    skipped = list(detail.get("skipped") or [])
    noun = cfg["noun"]
    n = len(records)
    recognized = n + len(skipped)  # every dated item the model surfaced (created + skipped)

    isos = [r.get("date_iso") for r in records if r.get("date_iso")]
    isos += [s.get("date_iso") for s in skipped if s.get("date_iso")]
    isos = sorted(i for i in isos if i)
    with_time = sum(1 for r in records if r.get("has_time"))
    without_time = n - with_time

    lines = [cfg["lead"].format(source=_source_phrase(detail.get("source")))]
    if isos and isos[0] != isos[-1]:
        lines.append(f"Found {recognized} {noun} — "
                     f"{_fmt_date(isos[0])} through {_fmt_date(isos[-1])}.")
    else:
        lines.append(f"Found {recognized} {noun}"
                     f"{f' — {_fmt_date(isos[0])}' if isos else ''}.")

    lines += ["", "Will be imported:"]
    for r in records:
        lines.append(f"✓ {r.get('label')}")
    if skipped:
        lines += ["", "Won't be imported:"]
        for s in skipped:
            lines.append(f"⚠ {s.get('label')} — "
                         f"{_SKIP_REASON_TEXT.get(s.get('reason'), 'I left it out.')}")

    lines += ["", "Import summary:",
              f"• {n} will be imported"]
    if with_time:
        lines.append(f"• {with_time} {'has' if with_time == 1 else 'have'} a recorded time")
    if without_time:
        lines.append(f"• {without_time} {'has' if without_time == 1 else 'have'} no recorded time")
    if skipped:
        lines.append(f"• {len(skipped)} won't be imported")

    lines += ["", (f"Import this {noun[:-1] if noun.endswith('s') else noun}?"
                   if n == 1 else f"Import these {n} {noun}?")]
    return "\n".join(lines)


def render_import_confirmation(detail):
    """Render an import ``confirmation_detail`` to RESULTS-not-intentions text.

    Returns the summary string, or ``None`` when ``detail`` carries no registered renderer — the
    caller then keeps its own fallback message. Pure presentation over deterministic truth: every
    line comes from a field the handler/adapter set; no verdicts, no invented facts. Dispatches by
    the renderer's ``kind``: 'record' (Structured Import) vs 'measurement' (multimodal default).
    """
    if not isinstance(detail, dict):
        return None
    cfg = _RENDERERS.get(detail.get("renderer"))
    if cfg is None:
        return None
    if cfg.get("kind") == "record":
        return _render_record(detail, cfg)

    validated = list(detail.get("measurements") or [])
    skipped = list(detail.get("skipped") or [])
    derived = detail.get("derived") or {}
    absent_count = int(detail.get("absent_count") or 0)
    noun = cfg["noun"]
    recognized = len(validated) + len(skipped)

    lines = [cfg["lead"].format(source=_source_phrase(detail.get("source"))),
             "", "Recognized:"]
    for v in validated:
        note = "  — please double-check (low confidence)" if v.get("uncertain") else ""
        lines.append(f"✓ {v.get('label')} — {format_value(v.get('value'), v.get('unit'))}{note}")
    for s in skipped:
        label = s.get("label") or s.get("metric") or "Unrecognized reading"
        lines.append(f"⚠ {label} — {format_value(s.get('value'), s.get('unit'))} (can't import)")

    lines += ["", "Import summary:",
              f"• {recognized} recognized",
              f"• {len(validated)} will be imported",
              f"• {len(skipped)} cannot be imported"]
    if absent_count:
        lines.append(f"• {absent_count} field{'s' if absent_count != 1 else ''} "
                     "were blank (not measured)")

    if skipped:
        lines += ["", "Skipped:"]
        for s in skipped:
            label = s.get("label") or s.get("metric") or "Unrecognized reading"
            lines.append(f"• {label} — {_SKIP_REASON_TEXT.get(s.get('reason'), 'I left it out.')}")

    for key, val in (derived.items() if isinstance(derived, dict) else []):
        if val is not None:
            lines += ["", f"I'll also show your {_humanize(key)} ({val}), computed from the "
                          "values above (never stored separately)."]

    lines.append("")
    if len(validated) == 1:
        lines.append(f"Import this {noun[:-1] if noun.endswith('s') else noun}?")
    elif skipped:
        lines.append(f"Import the remaining {len(validated)} {noun}?")
    else:
        lines.append(f"Import these {len(validated)} {noun}?")
    return "\n".join(lines)
