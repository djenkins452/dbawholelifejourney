# ==============================================================================
# File: apps/ai/chatgpt_cos/executive_reasoning.py
# Capability: EXECUTIVE REASONING STRUCTURE.
#
# An exceptional Chief of Staff does not jump from a question straight to a
# recommendation. She first states her ASSESSMENT (the verdict), then the REASONING
# (why she believes it), then the recommended ACTION. Production failures showed Beth
# doing the reverse — answering an executive question with a bare fact or a
# recommendation and no assessment.
#
# `frame()` is the one place that order is enforced for the deterministic executive
# lanes (risk, priority, …). It is a pure formatter — it invents nothing; each lane
# supplies the three parts from deterministic truth. Any part may be omitted, but the
# assessment always leads.
# ==============================================================================


def _clean(text):
    text = (text or "").strip()
    if text.endswith("."):
        text = text[:-1]
    # Each part is its own sentence — capitalize its first letter so reasoning/action
    # don't read as lowercase fragments after the assessment.
    return (text[0].upper() + text[1:]) if text else text


def frame(assessment, reasoning=None, action=None):
    """Render an executive answer in Chief-of-Staff order: ASSESSMENT → REASONING →
    ACTION. `assessment` is required (the verdict); `reasoning` and `action` are
    optional. Returns natural prose, never the reverse order."""
    parts = [_clean(assessment)]
    if reasoning:
        parts.append(_clean(reasoning))
    if action:
        parts.append(_clean(action))
    body = ". ".join(p for p in parts if p)
    return (body + ".") if body else ""
