"""WLJ UI Test Framework — Run Manifest.

Generates run_manifest.json at start and completion of each test run.
Tracks expected_cases and completed_cases for run integrity verification.

Manifest file: <module_reports_dir>/run_manifest.json

Structure:
  {
    "run_id": "a1b2c3d4",
    "module": "journal",
    "suite": "Journal Module Tests",
    "status": "running" | "completed" | "failed" | "interrupted",
    "started_at": "2026-02-25T22:00:00.000Z",
    "completed_at": null | "2026-02-25T22:01:00.000Z",
    "expected_cases": ["JRN-001", "JRN-002", ...],
    "completed_cases": ["JRN-001"],
    "failed_cases": ["JRN-002"],
    "skipped_cases": [],
    "integrity": { "expected": 4, "completed": 1, "failed": 1, "missing": 2 }
  }
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .version import __version__


class RunManifest:
    """Tracks run lifecycle from start to completion.

    Written at run start with expected_cases, updated as cases complete,
    and finalized with status and integrity summary at run end.
    """

    def __init__(self, run_id, module, suite, base_url, environment,
                 manifest_dir=None):
        """Initialize run manifest.

        Args:
            run_id: 8-char hex run ID.
            module: Module name.
            suite: Suite display name.
            base_url: Target base URL.
            environment: Environment name (development/production).
            manifest_dir: Override directory for manifest file.
                Defaults to module reports dir.
        """
        self.run_id = run_id
        self.module = module
        self.suite = suite
        self.base_url = base_url
        self.environment = environment

        base = Path(__file__).parent.parent
        self.manifest_dir = Path(manifest_dir) if manifest_dir else (
            base / "modules" / module / "reports"
        )

        self._started_at = _now_iso()
        self._completed_at = None
        self._status = "initializing"
        self._expected_cases = []
        self._completed_cases = []
        self._failed_cases = []
        self._skipped_cases = []

    def set_expected_cases(self, case_ids):
        """Set the list of expected case IDs from the loaded suite.

        Args:
            case_ids: List of case ID strings.
        """
        self._expected_cases = list(case_ids)
        self._status = "running"

    def record_case_pass(self, case_id):
        """Record a case that completed successfully."""
        if case_id not in self._completed_cases:
            self._completed_cases.append(case_id)

    def record_case_fail(self, case_id):
        """Record a case that failed."""
        if case_id not in self._failed_cases:
            self._failed_cases.append(case_id)

    def record_case_skip(self, case_id):
        """Record a case that was skipped."""
        if case_id not in self._skipped_cases:
            self._skipped_cases.append(case_id)

    def finalize(self, status=None):
        """Finalize the manifest at run completion.

        Args:
            status: Override status. Auto-detected if not provided:
                'completed' if all expected cases accounted for,
                'failed' if any failures, 'interrupted' if missing cases.
        """
        self._completed_at = _now_iso()

        if status:
            self._status = status
        elif self._failed_cases:
            self._status = "failed"
        elif len(self._completed_cases) == len(self._expected_cases):
            self._status = "completed"
        else:
            self._status = "interrupted"

    def to_dict(self):
        """Return manifest as a dict."""
        accounted = set(self._completed_cases) | set(self._failed_cases) | set(self._skipped_cases)
        missing = [c for c in self._expected_cases if c not in accounted]

        return {
            "framework_version": __version__,
            "run_id": self.run_id,
            "module": self.module,
            "suite": self.suite,
            "base_url": self.base_url,
            "environment": self.environment,
            "status": self._status,
            "started_at": self._started_at,
            "completed_at": self._completed_at,
            "expected_cases": self._expected_cases,
            "completed_cases": self._completed_cases,
            "failed_cases": self._failed_cases,
            "skipped_cases": self._skipped_cases,
            "integrity": {
                "expected": len(self._expected_cases),
                "completed": len(self._completed_cases),
                "failed": len(self._failed_cases),
                "skipped": len(self._skipped_cases),
                "missing": len(missing),
                "missing_case_ids": missing,
            },
        }

    def write(self):
        """Write the manifest to run_manifest.json."""
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        path = self.manifest_dir / "run_manifest.json"
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return path

    def is_complete(self):
        """Check if all expected cases have been accounted for."""
        accounted = set(self._completed_cases) | set(self._failed_cases) | set(self._skipped_cases)
        return accounted == set(self._expected_cases)


def _now_iso():
    """Return current UTC time as ISO 8601 with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
