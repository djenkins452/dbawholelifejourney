"""
E3 — Evidence & Explainability Engine.

Attaches evidence and explainability metadata to intelligence outputs.
Answers: "Why are you saying this?" and "What data is that based on?"

Public API:
    ensure_explain_record(user, source_engine, obj) — create/return explain record
    get_explain_record(user, source_engine, obj_type, obj_id) — read-only lookup
"""

from apps.core.ai_explain.explain_engine import ensure_explain_record, get_explain_record

__all__ = ["ensure_explain_record", "get_explain_record"]
