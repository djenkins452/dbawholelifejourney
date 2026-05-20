"""
One-shot startup diagnostics — investigation-only instrumentation.

Production boot logs repeatedly show Django's
  RuntimeWarning: Accessing the database during app initialization is
  discouraged. To fix this warning, avoid executing queries in
  AppConfig.ready() or when your app modules are imported.
(emitted from django/db/backends/utils.py)

A code audit of every AppConfig.ready() method and a grep for
module-level `.objects.` calls did not surface a direct cause. To
identify the offender without invasive code changes, this module
installs a wrapper around `warnings.showwarning` that captures the
full Python stack the FIRST time the warning fires per process and
logs it. Subsequent occurrences pass through to the original handler
unchanged.

This is investigation-only. No behavior change, no error swallowing,
no perf cost in the steady state. Once the source is identified and
fixed, this module should be removed (or the install_diagnostics()
call removed from settings.py).

Safe by construction:
  * The shim falls through to the original `warnings.showwarning` so
    the warning still appears in logs normally.
  * It only captures the FIRST occurrence per process (no log spam
    across the 4 workers × N requests).
  * Logged at WARNING (not ERROR) so it does NOT trigger
    mail_admins — only console + file handlers per LOGGING config.
  * Wrapped in try/except so the diagnostic itself cannot crash boot.
  * Only acts on the specific Django warning message — every other
    warning is unaffected.

Reference: docs/wlj_claude_changelog.md — 2026-05-20 entry (F7).
"""

import logging
import traceback
import warnings

logger = logging.getLogger("apps.core.startup_diagnostics")

# Process-local one-shot guard. Reset per-process (no cross-process state).
_apps_not_ready_logged = False

# Substring of Django's APPS_NOT_READY_WARNING_MSG. Matching by substring
# (not exact equality) so a minor Django wording change doesn't silently
# disable the diagnostic.
_TARGET_FRAGMENT = "Accessing the database during app initialization"

# Capture the original handler ONCE so re-installs are idempotent.
_original_showwarning = warnings.showwarning


def _diagnostic_showwarning(message, category, filename, lineno, file=None, line=None):
    """Wrap warnings.showwarning to capture the APPS_NOT_READY stack once."""
    global _apps_not_ready_logged

    try:
        if (
            not _apps_not_ready_logged
            and _TARGET_FRAGMENT in str(message)
        ):
            _apps_not_ready_logged = True
            # format_stack() returns the stack up to (but not including)
            # this call — which is exactly the chain that produced the
            # warning. Cheap (one allocation) and only runs once.
            stack = "".join(traceback.format_stack())
            logger.warning(
                "APPS_NOT_READY_WARNING source captured (one-shot diagnostic).\n"
                "Warning emitted at %s:%s\n"
                "Full Python stack at warning time:\n%s",
                filename, lineno, stack,
            )
    except Exception as e:  # noqa: BLE001 — diagnostic must never crash boot.
        # If our logging itself fails, swallow it. The warning will still
        # be delivered by the fallthrough below — we are strictly additive.
        try:
            logger.debug("startup_diagnostics shim failed: %s", e)
        except Exception:
            pass

    # ALWAYS fall through to the original handler so the warning still
    # surfaces normally. We are decorating, not replacing.
    _original_showwarning(message, category, filename, lineno, file, line)


def install_diagnostics():
    """Install the one-shot APPS_NOT_READY stack-capture shim.

    Idempotent: if already installed (the wrapper is already in place),
    re-installing is a no-op. Called from config/settings.py at module
    load time so the shim is in place before Django boots its apps.
    """
    if warnings.showwarning is _diagnostic_showwarning:
        # Already installed — don't double-wrap and re-capture the
        # original handler as the original (which would create an
        # infinite recursion through the same wrapper).
        return
    warnings.showwarning = _diagnostic_showwarning
