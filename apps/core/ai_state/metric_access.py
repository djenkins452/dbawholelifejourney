"""
Metric Access Layer — the approved entry point for AI-facing code
to read canonical user metrics.

Behavior
--------
* Looks the key up in the registry. Unregistered keys log a warning
  and return None. No silent fallback to raw model queries.
* Reads the value from SAE state via ``get_state_value``. If SAE has
  not populated the key yet, logs an info event (an "orphan" — a
  real canonical gap to be fixed by extending SAE) and returns None.
* Returns a ``MetricResult`` envelope with source and metadata.

Non-goals
---------
This module does not aggregate, compute, cache, or fall back. It is
a thin facade on top of ``get_state_value``. Any new AI-facing metric
read must flow through ``get_metric``; raw ``.aggregate()`` calls in
``assistant/``, ``apps/ai/``, and ``apps/core/ai_orchestrator/`` are
blocked by the purity test in
``apps/core/ai_state/tests/test_metric_registry.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

from apps.core.ai_state.metric_registry import METRIC_REGISTRY
from apps.core.ai_state.state_engine import get_state_value

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MetricResult:
    key: str
    value: Any
    source: str  # e.g. "SAE:health.glucose_avg_7d"
    domain: str
    window: str
    unit: Optional[str]


def get_metric(user, key: str) -> Optional[MetricResult]:
    """
    Return the canonical value for ``key``, or None.

    None is returned either when the key is not registered (caller is
    trying to read a metric that was never declared canonical) or when
    SAE state does not yet hold a value (a real gap — extend SAE, do
    not reroute to raw data).
    """
    definition = METRIC_REGISTRY.get(key)
    if definition is None:
        logger.warning(
            "metric_access.unregistered_key",
            extra={
                "metric_access": True,
                "event": "unregistered_key",
                "key": key,
                "user_id": getattr(user, "id", None),
            },
        )
        return None

    value = get_state_value(user, definition.state_path, default=None)
    if value is None:
        logger.info(
            "metric_access.orphan",
            extra={
                "metric_access": True,
                "event": "orphan",
                "key": key,
                "user_id": getattr(user, "id", None),
                "state_path": definition.state_path,
            },
        )
        return None

    return MetricResult(
        key=definition.key,
        value=value,
        source=f"SAE:{definition.state_path}",
        domain=definition.domain,
        window=definition.window,
        unit=definition.unit,
    )


def get_metric_value(user, key: str, default: Any = None) -> Any:
    """
    Convenience wrapper that returns the raw value, or ``default``.

    Use this when the caller only needs the scalar and does not care
    about source/window metadata (e.g. a simple presence check).
    """
    result = get_metric(user, key)
    if result is None:
        return default
    return result.value


def has_metric(user, key: str) -> bool:
    """True if the canonical metric has a value in SAE state."""
    return get_metric(user, key) is not None


def record_divergence(key: str, values: Iterable[Any], user=None) -> None:
    """
    Observability hook: log when the same metric key surfaces
    conflicting values in a single CoS turn.

    No-op when all values agree (or fewer than two distinct
    non-None values are supplied) so the log stream stays quiet on
    the happy path.
    """
    unique = {v for v in values if v is not None}
    if len(unique) <= 1:
        return
    logger.warning(
        "metric_access.divergence",
        extra={
            "metric_access": True,
            "event": "divergence",
            "key": key,
            "user_id": getattr(user, "id", None),
            "values": sorted(unique, key=str),
        },
    )


def log_state_gap(
    missing_key: str,
    source: str,
    user=None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Observability hook: CoS (or another AI-facing module) is reaching
    past SAE because a canonical state key does not yet exist.

    Unlike ``log_direct_orm_read``, which records *tolerated* reads,
    this event explicitly flags a gap in the signals/state layer
    that should be closed. Emits a warning so it surfaces in logs.
    """
    payload = {
        "metric_access": True,
        "event": "state_gap",
        "missing_key": missing_key,
        "source": source,
        "user_id": getattr(user, "id", None),
    }
    if extra:
        payload.update(extra)
    logger.warning("metric_access.state_gap", extra=payload)


def log_direct_orm_read(source: str, user=None, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Observability hook: AI-facing modules that still read raw models
    directly must call this before the query. It emits a structured
    ``cos_context.direct_orm_read`` event so the Phase 2 cleanup has
    telemetry for every remaining raw read.

    Call-site conventions
    ---------------------
    * ``source`` is a stable label identifying the read site, e.g.
      ``"cos_context:data_state_snapshot"``. Keep it short and stable
      so log aggregation groups cleanly.
    * This is a warning so it shows in production logs but does not
      page — the read is tolerated during migration, not forbidden.
    """
    payload = {
        "metric_access": True,
        "event": "direct_orm_read",
        "source": source,
        "user_id": getattr(user, "id", None),
    }
    if extra:
        payload.update(extra)
    logger.warning("metric_access.direct_orm_read", extra=payload)
