"""
Request-path async dispatch — the canonical, non-blocking enqueue primitive.

PRODUCTION GUARANTEE
    Interactive HTTP requests must NEVER block waiting on asynchronous
    infrastructure (Celery, the broker, or the Redis result backend). A request
    may *attempt* to enqueue background work, but it must return immediately
    whether or not the broker is reachable.

WHY THIS EXISTS
    On 2026-07-05 a degraded Redis made every request-path ``.delay()`` block
    ~20 seconds: the redis result backend retried its reconnect 20×1.0s before
    raising, and a synchronous rebuild then ran on the request thread as a
    "fallback". Dashboard load and task completion both regressed from ~2s to
    15–20s because they share the write → post_save → ``.delay()`` pipeline.

    ``config/settings.py`` now makes enqueues fire-and-forget (no result
    backend) and fail-fast (0.5s socket timeouts, bounded publish retry). This
    helper is the belt to that suspenders: a single choke point every
    request-path caller can use so the "attempt, swallow, log, move on"
    contract is guaranteed in one place instead of re-implemented (often
    incorrectly, with a synchronous fallback) at 40+ call sites.

USAGE
    from apps.core.celery_utils import safe_enqueue
    safe_enqueue(deferred_sae_refresh, user.id, ["tasks"], source="signal")

    Returns True if the task was handed to the broker, False if the broker was
    unreachable / enqueue failed. NEVER raises. NEVER blocks beyond the
    configured connection timeout. NEVER falls back to synchronous execution —
    eventual consistency is the caller's background mechanism (the SAME cycle,
    the next successful write), not a request-thread rebuild.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def safe_enqueue(task, *args, **kwargs) -> bool:
    """Enqueue a Celery task without ever blocking or raising on the caller.

    Args:
        task: A Celery task object (the thing you'd call ``.delay()`` on).
        *args: Positional args forwarded to the task.
        **kwargs: Keyword args forwarded to the task. The reserved key
            ``_apply_async_options`` (a dict) is popped and passed to
            ``apply_async`` (e.g. ``queue``, ``countdown``, ``eta``) rather
            than to the task body; when present the dispatch uses
            ``apply_async`` instead of ``delay``.

    Returns:
        True  — the task was published to the broker.
        False — the broker was unreachable or the enqueue failed; the caller
                should rely on its background reconciliation path (never a
                synchronous rebuild on the request thread).
    """
    options = kwargs.pop("_apply_async_options", None)
    try:
        if options:
            task.apply_async(args=args, kwargs=kwargs, **options)
        else:
            # `.delay` is the universal enqueue idiom (it simply forwards to
            # apply_async); using it keeps this primitive a drop-in for every
            # existing `task.delay(...)` call site.
            task.delay(*args, **kwargs)
        return True
    except Exception as exc:
        # Broker down, result backend down, connection timeout, serialization
        # error — none of it may reach the user. Log once at warning so a
        # persistent outage is visible in prod without spamming, then return.
        name = getattr(task, "name", getattr(task, "__name__", repr(task)))
        logger.warning(
            "safe_enqueue: async dispatch failed for %s (%s: %s) — "
            "skipped on request path; background reconciliation will recover",
            name, type(exc).__name__, exc,
        )
        return False
