# ==============================================================================
# File: wlj_ui_tests/framework/result_sync.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Sync client for posting UI test results to production
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-26
#
# Callable from:
#   - wlj_ui_tests/run_suite.py (CLI after orchestrator.run())
#   - apps/admin_console/views.py (after UITestRun creation)
#
# Uses pure stdlib (urllib.request) to avoid Django dependency.
# ==============================================================================

import json
import logging
import os
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_SYNC_URL = (
    "https://wholelifejourney.com/admin-console/api/test-results/ingest/"
)
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1  # 1s, 2s, 4s
OUTPUT_TRUNCATE_BYTES = 10240  # 10KB max for output field


def sync_result(summary, ui_run_output="", sync_url=None, api_key=None):
    """
    POST test results to the production ingest API.

    Args:
        summary: Dict from orchestrator.get_summary() or UITestRun fields.
        ui_run_output: Optional raw output text (truncated to 10KB).
        sync_url: Override URL (default from env or hardcoded).
        api_key: Override API key (default from env).

    Returns:
        True if sync succeeded, False otherwise.
        Never raises — always returns a boolean.
    """
    url = sync_url or os.environ.get("TEST_RESULTS_SYNC_URL", DEFAULT_SYNC_URL)
    key = api_key or os.environ.get("TEST_RESULTS_API_KEY", "")

    if not key:
        logger.debug("TEST_RESULTS_API_KEY not set, skipping sync")
        return False

    payload = _build_payload(summary, ui_run_output)

    for attempt in range(MAX_RETRIES):
        try:
            return _post_payload(url, key, payload)
        except (URLError, HTTPError, OSError) as exc:
            wait = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
            logger.warning(
                "Sync attempt %d/%d failed: %s (retrying in %ds)",
                attempt + 1, MAX_RETRIES, exc, wait,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(wait)

    logger.error("All %d sync attempts failed, giving up", MAX_RETRIES)
    return False


def _build_payload(summary, output=""):
    """Build the ingest payload from a summary dict."""
    # Handle both orchestrator summary (module as str) and view payload (modules as list)
    modules = summary.get("modules")
    if modules is None:
        module = summary.get("module", "unknown")
        modules = [module] if isinstance(module, str) else ["unknown"]

    return {
        "run_id": summary.get("run_id", ""),
        "modules": modules,
        "status": _derive_status(summary),
        "total_cases": summary.get("total_cases", 0),
        "passed": summary.get("passed", 0),
        "failed": summary.get("failed", 0),
        "pass_rate": float(summary.get("pass_rate", 0)),
        "duration_seconds": float(summary.get("duration_seconds", 0)
                                  if "duration_seconds" in summary
                                  else summary.get("duration_ms", 0) / 1000),
        "results": summary.get("results", {}),
        "environment": summary.get("environment", "local"),
        "source_host": summary.get("source_host", socket.gethostname()),
        "source_user": summary.get(
            "source_user",
            os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
        ),
        "output": (output or "")[:OUTPUT_TRUNCATE_BYTES],
        # Include children for full-suite runs
        **({"children": summary["children"]} if "children" in summary else {}),
    }


def _derive_status(summary):
    """Derive status string from summary data."""
    if summary.get("status") and summary["status"] in (
        "running", "passed", "failed", "error"
    ):
        return summary["status"]
    if summary.get("failed", 0) > 0:
        return "failed"
    if summary.get("passed", 0) > 0:
        return "passed"
    return "error"


def _post_payload(url, api_key, payload):
    """POST JSON payload to the ingest URL. Returns True on success."""
    data = json.dumps(payload, default=str).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Test-Results-API-Key", api_key)

    resp = urlopen(req, timeout=15)
    if resp.status in (200, 201):
        logger.info(
            "Synced test result (run_id=%s) → %s [%d]",
            payload.get("run_id"), url, resp.status,
        )
        return True
    logger.warning("Unexpected status %d from sync endpoint", resp.status)
    return False
