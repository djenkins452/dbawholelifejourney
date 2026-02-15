"""
SUE -- Semantic Understanding Engine.

Interprets human meaning and intent from raw text without executing actions.
SUE is a signal processor: it parses, classifies, and returns structured
semantic data for the UAIO orchestrator to act on.

Public API:
    interpret(user, raw_text, context=None) -> SemanticResult
"""

from apps.core.ai_semantics.semantic_engine import interpret  # noqa: F401
