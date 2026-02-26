"""WLJ UI Test Framework — Reporting Engine.

Writes pass/fail NDJSON logs, execution logs, and run summaries
per Sections 8.1–8.5 of the master requirements.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from .version import __version__


class ReportWriter:
    """Writes NDJSON pass/fail logs, execution logs, and run summaries.

    Supports both module-scoped and aggregated report paths.
    """

    def __init__(self, run_id, suite, module, base_url, environment,
                 module_reports_dir=None, aggregated_reports_dir=None):
        self.run_id = run_id
        self.suite = suite
        self.module = module
        self.base_url = base_url
        self.environment = environment

        base = Path(__file__).parent.parent
        self.module_dir = Path(module_reports_dir) if module_reports_dir else (
            base / "modules" / module / "reports"
        )
        self.aggregated_dir = Path(aggregated_reports_dir) if aggregated_reports_dir else (
            base / "reports"
        )

        self._pass_entries = []
        self._fail_entries = []
        self._exec_log = []
        self._start_time = datetime.now(timezone.utc)

    # --- Case-level recording ---

    def record_pass(self, case_id, duration_ms, steps_executed):
        """Record a passing case."""
        entry = {
            "case_id": case_id,
            "suite": self.suite,
            "module": self.module,
            "status": "pass",
            "duration_ms": duration_ms,
            "timestamp": _now_iso(),
            "steps_executed": steps_executed,
            "run_id": self.run_id,
        }
        self._pass_entries.append(entry)

    def record_fail(self, case_id, duration_ms, failed_step, action,
                    selector, error, screenshot=None, html_dump=None):
        """Record a failing case."""
        entry = {
            "case_id": case_id,
            "suite": self.suite,
            "module": self.module,
            "status": "fail",
            "duration_ms": duration_ms,
            "timestamp": _now_iso(),
            "failed_step": failed_step,
            "action": action,
            "selector": selector,
            "error": str(error),
            "screenshot": screenshot,
            "html_dump": html_dump,
            "run_id": self.run_id,
        }
        self._fail_entries.append(entry)

    # --- Step-level execution log (Section 8.5) ---

    def log_event(self, event, **kwargs):
        """Log a framework-level event (suite_start, case_start, etc.)."""
        entry = {
            "run_id": self.run_id,
            "module": self.module,
            "event": event,
            "timestamp": _now_iso(),
        }
        entry.update(kwargs)
        self._exec_log.append(entry)

    def log_step(self, case_id, step_index, action, target, status,
                 duration_ms, error=None, input_value=None):
        """Log a single step execution."""
        entry = {
            "run_id": self.run_id,
            "module": self.module,
            "case_id": case_id,
            "step_index": step_index,
            "action": action,
            "target": target,
            "status": status,
            "duration_ms": duration_ms,
            "timestamp": _now_iso(),
        }
        if input_value is not None:
            entry["input"] = input_value
        if error is not None:
            entry["error"] = str(error)
        self._exec_log.append(entry)

    # --- File output ---

    def write_all(self):
        """Write all report files to both module and aggregated dirs."""
        self._ensure_dirs()
        for directory in (self.module_dir, self.aggregated_dir):
            self._write_ndjson(directory / "pass.ndjson", self._pass_entries)
            self._write_ndjson(directory / "fail.ndjson", self._fail_entries)
            self._write_ndjson(directory / "execution_log.ndjson", self._exec_log)
            self._write_summary(directory / "run_summary.json")

    def _write_ndjson(self, path, entries):
        """Write entries as newline-delimited JSON."""
        with open(path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry, default=str) + "\n")

    def _write_summary(self, path):
        """Write the run_summary.json per Section 8.3."""
        total_duration = int(
            (datetime.now(timezone.utc) - self._start_time).total_seconds() * 1000
        )
        total = len(self._pass_entries) + len(self._fail_entries)
        passed = len(self._pass_entries)
        summary = {
            "run_id": self.run_id,
            "framework_version": __version__,
            "schema_version": "1.0",
            "suite": self.suite,
            "module": self.module,
            "timestamp": self._start_time.isoformat(),
            "duration_ms": total_duration,
            "environment": self.environment,
            "base_url": self.base_url,
            "total_cases": total,
            "passed": passed,
            "failed": len(self._fail_entries),
            "pass_rate": passed / total if total else 0.0,
            "failures": [
                {"case_id": e["case_id"], "error": e["error"]}
                for e in self._fail_entries
            ],
        }
        with open(path, "w") as f:
            json.dump(summary, f, indent=2, default=str)

    def _ensure_dirs(self):
        """Create report directories if they don't exist."""
        self.module_dir.mkdir(parents=True, exist_ok=True)
        self.aggregated_dir.mkdir(parents=True, exist_ok=True)


# --- Helpers ---

def _now_iso():
    """Return current UTC time as ISO 8601 with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
