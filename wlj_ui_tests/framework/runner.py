"""WLJ UI Test Framework — Core Runner Engine.

Loads YAML suite files, iterates test cases, and orchestrates execution
through the executor, reporting, and artifact subsystems.
"""

import json
import os
import signal
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml


class LockError(Exception):
    """Raised when the framework state lock cannot be acquired."""


class SuiteRunner:
    """YAML suite loader and case orchestrator.

    Loads a YAML suite file, generates a unique RUN_ID, manages the
    framework state lock, iterates test cases, and delegates to
    executor/reporting/artifact subsystems via hooks.
    """

    BASE_DIR = Path(__file__).parent.parent
    MODULES_DIR = BASE_DIR / "modules"
    LOCK_FILE = BASE_DIR / ".wlj_test.lock"
    LOCK_STALE_MINUTES = 30

    # The 10 modules per Section 4 directory structure + smoke
    KNOWN_MODULES = (
        "journal", "faith", "health", "organize", "goals",
        "capture", "cos", "preferences", "admin", "smoke",
    )

    def __init__(self, suite_path=None, base_url=None, headed=False,
                 env=None, module=None):
        """Initialize runner with suite path or module name.

        Args:
            suite_path: Explicit path to a suite YAML file.
            base_url: Base URL for testing. Defaults to $BASE_URL.
            headed: Run browser in headed mode.
            env: Environment name override.
            module: Module name — resolves to modules/<module>/suite.yaml.
                Ignored if suite_path is provided.
        """
        if suite_path:
            self.suite_path = Path(suite_path)
        elif module:
            self.suite_path = self.resolve_module_suite(module)
        else:
            raise ValueError("Either suite_path or module must be provided")

        self.base_url = base_url or os.environ.get("BASE_URL", "http://localhost:8000")
        self.headed = headed
        self.env = env or os.environ.get("WLJ_TEST_ENV")
        self.run_id = generate_run_id()
        self.suite_data = None
        self.module = module
        self.results = {"passed": [], "failed": []}
        self._lock_acquired = False
        self._orig_sigint = None
        self._orig_sigterm = None

    @classmethod
    def resolve_module_suite(cls, module):
        """Resolve module name to its suite.yaml path.

        Args:
            module: Module name (e.g., 'journal').

        Returns:
            Path to the module's suite.yaml file.

        Raises:
            FileNotFoundError: If the suite file doesn't exist.
        """
        suite_path = cls.MODULES_DIR / module / "suite.yaml"
        if not suite_path.exists():
            raise FileNotFoundError(
                f"Suite file not found for module '{module}': {suite_path}"
            )
        return suite_path

    @classmethod
    def module_reports_dir(cls, module):
        """Return the reports directory for a module."""
        return cls.MODULES_DIR / module / "reports"

    @classmethod
    def module_artifacts_dir(cls, module):
        """Return the artifacts directory for a module."""
        return cls.MODULES_DIR / module / "artifacts"

    @classmethod
    def list_modules(cls):
        """List all modules that have a suite.yaml file."""
        return [
            m for m in cls.KNOWN_MODULES
            if (cls.MODULES_DIR / m / "suite.yaml").exists()
        ]

    def load_suite(self):
        """Load and parse the YAML suite file."""
        with open(self.suite_path, "r") as f:
            self.suite_data = yaml.safe_load(f)
        self.module = self.suite_data.get("module", "unknown")
        return self.suite_data

    def get_cases(self):
        """Return test cases with variables substituted."""
        if not self.suite_data:
            raise RuntimeError("Suite not loaded. Call load_suite() first.")
        return [self._substitute_deep(c) for c in self.suite_data.get("cases", [])]

    def run(self, executor=None, reporter=None, artifact_capture=None):
        """Run all cases in the loaded suite.

        Args:
            executor: Action executor (Phase 3+). None = enumerate only.
            reporter: Report writer (Phase 5+).
            artifact_capture: Artifact capture (Phase 6+).

        Returns:
            Summary dict with run_id, counts, and per-case results.
        """
        self.load_suite()
        self.acquire_lock()

        try:
            cases = self.get_cases()
            for case in cases:
                case_id = case.get("id", "unknown")
                start = datetime.now(timezone.utc)
                try:
                    if executor:
                        executor.execute_case(case)
                    self.results["passed"].append({
                        "case_id": case_id,
                        "duration_ms": _elapsed_ms(start),
                    })
                except Exception as exc:
                    self.results["failed"].append({
                        "case_id": case_id,
                        "error": str(exc),
                        "duration_ms": _elapsed_ms(start),
                    })
            return self._build_summary(cases)
        finally:
            self.release_lock()

    # --- Variable Substitution (Section 7.4) ---

    def _substitute_variables(self, value):
        """Replace ${VAR} placeholders in a string value."""
        if not isinstance(value, str):
            return value
        replacements = {
            "${BASE_URL}": self.base_url,
            "${TEST_USERNAME}": os.environ.get("TEST_USERNAME", ""),
            "${TEST_PASSWORD}": os.environ.get("TEST_PASSWORD", ""),
            "${RUN_ID}": self.run_id,
            "${MODULE}": self.module or "",
            "${TIMESTAMP}": datetime.now(timezone.utc).isoformat(),
        }
        for var, val in replacements.items():
            value = value.replace(var, val)
        return value

    def _substitute_deep(self, obj):
        """Recursively substitute variables in nested data structures."""
        if isinstance(obj, str):
            return self._substitute_variables(obj)
        if isinstance(obj, dict):
            return {k: self._substitute_deep(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._substitute_deep(item) for item in obj]
        return obj

    # --- Framework State Lock (Section 6.5) ---

    def acquire_lock(self):
        """Acquire the framework state lock.

        Raises LockError if the same module is already locked.
        Allows cross-module parallelism per Section 6.5.
        """
        if self.LOCK_FILE.exists():
            try:
                with open(self.LOCK_FILE, "r") as f:
                    lock_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                lock_data = {}

            if not self._is_lock_stale(lock_data):
                if lock_data.get("module") == self.module:
                    raise LockError(
                        f"Module '{self.module}' is locked by "
                        f"run_id={lock_data.get('run_id')} "
                        f"pid={lock_data.get('pid')}"
                    )
                # Different module holds lock — cross-module parallelism OK
                return

        lock_data = {
            "run_id": self.run_id,
            "module": self.module,
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.LOCK_FILE, "w") as f:
            json.dump(lock_data, f)
        self._lock_acquired = True
        self._register_signal_handlers()

    def release_lock(self):
        """Release the framework state lock if we hold it."""
        if self._lock_acquired and self.LOCK_FILE.exists():
            try:
                self.LOCK_FILE.unlink()
            except OSError:
                pass
            self._lock_acquired = False
        self._restore_signal_handlers()

    def _is_lock_stale(self, lock_data):
        """Check if an existing lock is stale (dead PID or expired)."""
        pid = lock_data.get("pid")
        if pid:
            try:
                os.kill(pid, 0)
            except OSError:
                return True

        started_at = lock_data.get("started_at")
        if started_at:
            try:
                lock_time = datetime.fromisoformat(started_at)
                elapsed = (datetime.now(timezone.utc) - lock_time).total_seconds()
                if elapsed > self.LOCK_STALE_MINUTES * 60:
                    return True
            except (ValueError, TypeError):
                return True

        return False

    def _register_signal_handlers(self):
        """Register handlers for graceful lock release on interrupt."""
        self._orig_sigint = signal.getsignal(signal.SIGINT)
        self._orig_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _restore_signal_handlers(self):
        """Restore original signal handlers."""
        if self._orig_sigint is not None:
            signal.signal(signal.SIGINT, self._orig_sigint)
            self._orig_sigint = None
        if self._orig_sigterm is not None:
            signal.signal(signal.SIGTERM, self._orig_sigterm)
            self._orig_sigterm = None

    def _signal_handler(self, signum, frame):
        """Release lock then re-raise via original handler."""
        self.release_lock()
        if signum == signal.SIGINT and callable(self._orig_sigint):
            self._orig_sigint(signum, frame)
        elif signum == signal.SIGTERM and callable(self._orig_sigterm):
            self._orig_sigterm(signum, frame)

    # --- Summary ---

    def _build_summary(self, cases):
        """Build the run summary dict."""
        total = len(cases)
        passed = len(self.results["passed"])
        return {
            "run_id": self.run_id,
            "module": self.module,
            "suite": self.suite_data.get("suite", ""),
            "base_url": self.base_url,
            "environment": self.env or (
                "development" if "localhost" in self.base_url else "production"
            ),
            "total_cases": total,
            "passed": passed,
            "failed": len(self.results["failed"]),
            "pass_rate": passed / total if total else 0.0,
            "results": self.results,
        }


def generate_run_id():
    """Generate a unique 8-char hex RUN_ID for this test run."""
    return uuid.uuid4().hex[:8]


def _elapsed_ms(start):
    """Calculate elapsed milliseconds since start."""
    return int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
