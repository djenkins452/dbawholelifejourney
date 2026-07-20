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
# every multimodal import shares "unrecognised" and "implausible" skip classes.
_SKIP_REASON_TEXT = {
    "unrecognized_metric": "WLJ doesn't have a place to store this one yet, so I left it out.",
    "implausible": "the reading looked out of range, so I left it out rather than save a likely misread.",
}

# renderer key → presentation config. A future domain adds one line here (or calls
# register_import_renderer) — no change to the presenter itself.
_RENDERERS = {}


def register_import_renderer(key, *, lead, noun="items"):
    """Register a multimodal-import renderer. ``lead`` is a one-line template that may reference
    ``{source}``; ``noun`` is the plural noun for the import summary ("measurements", "results")."""
    _RENDERERS[key] = {"lead": lead, "noun": noun}


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
    return "screenshot"


def _humanize(key):
    return str(key).replace("_", " ").replace("-", " ").strip()


def render_import_confirmation(detail):
    """Render a multimodal-import ``confirmation_detail`` to RESULTS-not-intentions text.

    Returns the summary string, or ``None`` when ``detail`` carries no registered renderer — the
    caller then keeps its own fallback message. Pure presentation over deterministic truth: every
    line comes from a field the handler set; no verdicts, no invented facts.
    """
    if not isinstance(detail, dict):
        return None
    cfg = _RENDERERS.get(detail.get("renderer"))
    if cfg is None:
        return None

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
