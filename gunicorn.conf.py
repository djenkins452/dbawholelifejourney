"""
Gunicorn configuration — auto-discovered.

Gunicorn loads `gunicorn.conf.py` from the current working directory
automatically when no `--config` flag is passed. The Railway production
start command does NOT pass `--config`, so this file is picked up by
default without any Railway dashboard change required.

Purpose: defensive `post_fork` hook that drops any DB / cache connection
that the master process may have inherited via `--preload`. With
`--preload`, gunicorn loads Django (and runs all AppConfig.ready()
methods) in the master process BEFORE forking workers. If any code
during that initialization opens a database connection (we have a
RuntimeWarning indicating this happens — APPS_NOT_READY_WARNING fires
during boot, source to be identified by F7), that connection's file
descriptor is shared across all forked workers. Two workers trying to
use the same psycopg2 socket simultaneously produces the exact
"SSL SYSCALL error: EOF detected" pattern we've been chasing.

This hook closes all connections in each worker immediately after fork
so each worker opens its own. Closing zero connections is a no-op
(the common case if nothing opened a connection during preload), so
this is strictly additive — it cannot break a working path, it can
only prevent a latent fault.

Worker count and timeout remain controlled by the Railway Custom Start
Command's CLI flags, not by this file, so this config doesn't change
operational characteristics.

Post-incident review reference:
  docs/wlj_claude_changelog.md — 2026-05-20 entry
"""

import logging

logger = logging.getLogger("gunicorn.error")


def post_fork(server, worker):
    """Drop any DB/cache connections inherited from the preload master.

    Runs in each worker exactly once, immediately after fork, before
    the worker begins serving requests. Idempotent: closing an
    unopened connection is a no-op.
    """
    try:
        from django.db import connections

        for alias in list(connections):
            try:
                connections[alias].close()
            except Exception as e:  # noqa: BLE001 — diagnostic only, never propagate
                # We never want a defensive close to crash a worker boot.
                # Log and move on — the worker will open a fresh connection
                # on first request anyway.
                logger.warning(
                    "post_fork: failed to close DB connection alias=%s: %s",
                    alias, e,
                )
    except Exception as e:  # noqa: BLE001
        # Django not importable or connections handler missing — should
        # never happen in this app but we refuse to crash worker boot.
        logger.warning("post_fork: skipping connection cleanup: %s", e)
