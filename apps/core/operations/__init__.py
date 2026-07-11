"""
WLJ Operations — the ACTION subsystem (Phase II: Deterministic Recovery).

This package is the frozen observation/action seam (WLJ_OPERATIONS_VISION.md §10/§11):

  * ``apps/core/ai_observability/``  = OBSERVATION / Operations Truth (read-only).
  * ``apps/core/operations/``        = ACTION (recovery / verification / audit / escalation).

Permanent import boundaries (vision §11, CI-enforced by
``apps/core/operations/tests/test_import_boundaries.py``):

  * ``operations/`` MAY consume Operations Truth from ``ai_observability/``.
  * ``ai_observability/`` MUST NEVER import ``operations/`` (truth never imports action).
  * ``operations/`` MUST NEVER import Chief-of-Staff reasoning / conversation /
    Current-Context reasoning / LLM orchestration / prompt composition / model interface.
  * No request-path module may import ``operations/`` (worker-only by construction).

Nothing here runs on the HTTP request path. Recovery executes only in the background
worker, strictly downstream of the SAME telemetry cycle, and only when
``settings.OPS_RECOVERY_ENABLED`` is True.
"""
