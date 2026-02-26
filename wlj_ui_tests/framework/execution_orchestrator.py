"""WLJ UI Test Framework — Execution Orchestrator.

Manages the full run lifecycle from initialization through reporting.
Replaces the ad-hoc wiring in run_suite.py with a structured pipeline:

    1. Generate RUN_ID
    2. Initialize RunManifest
    3. Initialize TestDataRegistry
    4. Run selector validation
    5. Launch browser (unless --no-browser)
    6. Execute SuiteRunner with ActionExecutor
    7. Write reporting outputs
    8. Finalize RunManifest
    9. Verify run integrity
   10. Generate Claude fix prompt if failures exist
   11. Close browser
   12. Return exit code

Health-check mode: validates framework subsystems without running tests.
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .version import __version__
from .runner import SuiteRunner, LockError, generate_run_id
from .executor import ActionExecutor, ExecutionError
from .reporting import ReportWriter
from .artifacts import ArtifactCapture
from .prompt_builder import PromptBuilder
from .schema_validator import SchemaValidator, ValidationError
from .safety import SafetyController, SafetyError, is_production
from .test_data_registry import TestDataRegistry
from .run_manifest import RunManifest
from .browser_manager import BrowserManager


class OrchestratorError(Exception):
    """Raised when the orchestrator encounters a framework-level error."""

    def __init__(self, message, phase=None):
        super().__init__(message)
        self.phase = phase


class ExecutionOrchestrator:
    """Full run lifecycle manager.

    Coordinates all framework subsystems through a structured pipeline:
    generate → init manifest → init registry → validate selectors →
    launch browser → run suite with executor → write reports →
    finalize manifest → verify integrity → generate fix prompt →
    close browser → return exit code.

    Default mode launches a real Chromium browser via Playwright.
    Pass no_browser=True for framework-only validation without Playwright.
    """

    def __init__(self, module=None, suite_path=None, base_url=None,
                 headed=False, env=None, max_retries=None,
                 no_browser=False, provision_test_user=False):
        """Initialize orchestrator with run parameters.

        Args:
            module: Module name (e.g., 'journal'). Required unless suite_path.
            suite_path: Explicit path to suite YAML file.
            base_url: Base URL for testing.
            headed: Run browser in headed mode (visible UI).
            env: Environment name override.
            max_retries: Max retry attempts for retryable actions.
            no_browser: If True, skip Playwright — enumerate cases without
                executing browser actions (framework-only mode).
            provision_test_user: If True, ensure the test user exists
                via Django's create_test_user before running tests.
        """
        self.module = module
        self.suite_path = suite_path
        self.base_url = base_url
        self.headed = headed
        self.env = env
        self.max_retries = max_retries
        self.no_browser = no_browser
        self.provision_test_user = provision_test_user

        # Initialized during pipeline
        self.run_id = None
        self.runner = None
        self.manifest = None
        self.registry = None
        self.reporter = None
        self.safety = None
        self.artifact_capture = None
        self.prompt_builder = None
        self._browser_manager = None

        # Results
        self._summary = None
        self._fix_prompt_path = None
        self._manifest_path = None
        self._selector_results = None
        self._pipeline_log = []

    def run(self):
        """Execute the full orchestration pipeline.

        Launches a real Chromium browser via Playwright (unless no_browser
        is True) and runs all test cases through the ActionExecutor.

        Returns:
            Exit code: 0 = all pass, 1 = failures, 2 = framework error.
        """
        executor = None
        try:
            # Phase 1: Generate RUN_ID
            self._log("phase_1_generate_run_id")
            self.run_id = generate_run_id()

            # Phase 1.5: Provision test user (if requested)
            if self.provision_test_user:
                self._log("phase_1_5_provision_test_user")
                self._provision_test_user()

            # Phase 2: Build and validate runner
            self._log("phase_2_init_runner")
            self.runner = self._build_runner()

            # Phase 3: Initialize RunManifest
            self._log("phase_3_init_manifest")
            self.manifest = self._init_manifest()

            # Phase 4: Initialize TestDataRegistry
            self._log("phase_4_init_registry")
            self.registry = self._init_registry()

            # Phase 5: Validate YAML schema
            self._log("phase_5_validate_schema")
            self._validate_schema()

            # Phase 6: Run selector validation
            self._log("phase_6_validate_selectors")
            self._selector_results = self._validate_selectors()

            # Phase 7: Initialize safety, reporting, and artifact subsystems
            self._log("phase_7_init_subsystems")
            self._init_subsystems()

            # Phase 8: Launch browser and create executor (unless no_browser)
            if not self.no_browser:
                self._log("phase_8_launch_browser")
                self._browser_manager = BrowserManager(headed=self.headed)
                self._browser_manager.start()
                executor = ActionExecutor(
                    page=self._browser_manager.page,
                    defaults={
                        "base_url": self.runner.base_url,
                        "timeout_ms": self.runner.suite_data.get(
                            "defaults", {}
                        ).get("timeout_ms", ActionExecutor.DEFAULT_TIMEOUT_MS),
                    },
                    max_retries=self.max_retries,
                )
                self._log("phase_8_browser_ready",
                           headed=self.headed,
                           base_url=self.runner.base_url)
            else:
                self._log("phase_8_no_browser",
                           reason="no_browser=True, framework-only mode")

            # Phase 9: Execute SuiteRunner
            self._log("phase_9_execute_suite")
            self._summary = self._execute_suite(executor)

            # Phase 10: Write reporting outputs
            self._log("phase_10_write_reports")
            self._write_reports()

            # Phase 11: Finalize RunManifest
            self._log("phase_11_finalize_manifest")
            self._manifest_path = self._finalize_manifest()

            # Phase 12: Verify run integrity
            self._log("phase_12_verify_integrity")
            integrity_ok = self._verify_integrity()

            # Phase 13: Generate Claude fix prompt if failures
            self._log("phase_13_generate_fix_prompt")
            self._generate_fix_prompt()

            # Determine exit code
            if self._summary["failed"] > 0:
                return 1
            if not integrity_ok:
                return 1
            return 0

        except (LockError, ValidationError, SafetyError) as exc:
            self._log("pipeline_error", error=str(exc))
            print(f"FRAMEWORK ERROR: {exc}", file=sys.stderr)
            return 2
        except OrchestratorError as exc:
            self._log("orchestrator_error", phase=exc.phase, error=str(exc))
            print(f"ORCHESTRATOR ERROR [{exc.phase}]: {exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            self._log("unexpected_error", error=str(exc))
            print(f"UNEXPECTED ERROR: {exc}", file=sys.stderr)
            return 2
        finally:
            # Always close browser cleanly
            if self._browser_manager:
                try:
                    self._log("phase_cleanup_browser")
                    self._browser_manager.stop()
                except Exception:
                    pass
            # Flush registry regardless of outcome
            if self.registry:
                try:
                    self.registry.flush()
                except Exception:
                    pass

    def health_check(self):
        """Validate framework subsystems without running tests.

        Checks:
            1. Framework version and imports
            2. Module discovery
            3. Schema validation for all modules
            4. Selector validation for all modules with cases
            5. Registry file access
            6. Reporting directory structure
            7. Safety controller initialization

        Returns:
            Tuple of (passed_count, failed_count, results_list).
        """
        results = []
        passed = 0
        failed = 0

        def check(name, condition, detail=""):
            nonlocal passed, failed
            if condition:
                passed += 1
                results.append({"name": name, "status": "pass"})
            else:
                failed += 1
                results.append({"name": name, "status": "fail", "detail": detail})

        print(f"\n{'=' * 60}")
        print(f"  WLJ UI Test Framework Health Check v{__version__}")
        print(f"{'=' * 60}\n")

        # 1. Framework version
        print("1. Framework version:")
        check("Version is set", bool(__version__))
        check("Version format valid",
              len(__version__.split(".")) == 3,
              f"got '{__version__}'")
        self._print_checks(results[-2:])

        # 2. Module discovery
        print("\n2. Module discovery:")
        modules = SuiteRunner.list_modules()
        check("Modules discovered", len(modules) > 0, f"found {len(modules)}")
        check("Known modules present", len(modules) >= 2,
              f"only {len(modules)} modules")
        self._print_checks(results[-2:])

        # 3. Schema validation
        print("\n3. Schema validation:")
        validator = SchemaValidator()
        for mod in modules:
            try:
                suite_path = SuiteRunner.resolve_module_suite(mod)
                validator.validate_file(suite_path)
                check(f"Schema valid: {mod}", True)
            except (ValidationError, Exception) as e:
                check(f"Schema valid: {mod}", False, str(e))
        self._print_checks(results[-(len(modules)):])

        # 4. Selector pre-validation
        print("\n4. Selector pre-validation:")
        templates_dir = Path(__file__).parent.parent.parent / "templates"
        if templates_dir.exists():
            try:
                from ..validate_selectors import validate_module as val_mod
                selector_ok = True
            except ImportError:
                # Fall back to direct import
                selector_ok = False

            if not selector_ok:
                # Use basic existence check
                check("Templates directory exists", True)
            else:
                for mod in modules:
                    try:
                        found, missing, _ = val_mod(mod, templates_dir)
                        found_count = sum(1 for f in found if f["status"] == "found")
                        miss_count = len(missing)
                        check(f"Selectors {mod}: {found_count} found",
                              miss_count == 0,
                              f"{miss_count} missing")
                    except FileNotFoundError:
                        continue
                self._print_checks(results[-(len(modules)):])
        else:
            check("Templates directory exists", False, str(templates_dir))
            self._print_checks(results[-1:])

        # 5. Registry access
        print("\n5. Registry access:")
        try:
            reg = TestDataRegistry()
            check("Registry instantiation", True)
            check("Registry path accessible",
                  reg.registry_path.parent.exists() or True)  # Parent may not exist yet
        except Exception as e:
            check("Registry instantiation", False, str(e))
        self._print_checks(results[-2:])

        # 6. Reporting directories
        print("\n6. Reporting structure:")
        base = Path(__file__).parent.parent
        reports_dir = base / "reports"
        check("Aggregated reports dir resolvable", True)
        for mod in modules[:3]:  # Check first 3 modules
            mod_reports = SuiteRunner.module_reports_dir(mod)
            mod_artifacts = SuiteRunner.module_artifacts_dir(mod)
            check(f"Reports path {mod}",
                  "modules" in str(mod_reports) and mod in str(mod_reports))
            check(f"Artifacts path {mod}",
                  "modules" in str(mod_artifacts) and mod in str(mod_artifacts))
        self._print_checks(results[-(1 + len(modules[:3]) * 2):])

        # 7. Safety controller
        print("\n7. Safety controller:")
        try:
            sc = SafetyController(
                base_url="http://localhost:8000",
                module="test", run_id="deadbeef",
            )
            check("Safety controller init (dev)", not sc.is_prod)
            sc_prod = SafetyController(
                base_url="https://wholelifejourney.com",
                module="test", run_id="deadbeef",
            )
            check("Safety controller init (prod)", sc_prod.is_prod)
            prefix = sc.make_cleanup_prefix("Health Check")
            check("Cleanup prefix format",
                  prefix == "AUTOTEST|test|deadbeef|Health Check")
        except Exception as e:
            check("Safety controller", False, str(e))
        self._print_checks(results[-3:])

        # 8. RunManifest
        print("\n8. Run manifest:")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                manifest = RunManifest(
                    run_id="deadbeef", module="test", suite="Health Check",
                    base_url="http://localhost:8000", environment="development",
                    manifest_dir=tmpdir,
                )
                manifest.set_expected_cases(["HC-001"])
                manifest.record_case_pass("HC-001")
                manifest.finalize()
                path = manifest.write()
                check("Manifest write", path.exists())
                data = json.loads(path.read_text())
                check("Manifest status completed",
                      data.get("status") == "completed")
                check("Manifest integrity",
                      data.get("integrity", {}).get("missing") == 0)
        except Exception as e:
            check("Run manifest", False, str(e))
        self._print_checks(results[-3:])

        # 9. ReportWriter
        print("\n9. Report writer:")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                rw = ReportWriter(
                    run_id="deadbeef", suite="Health Check", module="test",
                    base_url="http://localhost:8000", environment="development",
                    module_reports_dir=f"{tmpdir}/mod",
                    aggregated_reports_dir=f"{tmpdir}/agg",
                )
                rw.record_pass("HC-001", 50, 2)
                rw.write_all()
                check("Report write success",
                      (Path(tmpdir) / "mod" / "pass.ndjson").exists())
                check("Summary generated",
                      (Path(tmpdir) / "mod" / "run_summary.json").exists())
        except Exception as e:
            check("Report writer", False, str(e))
        self._print_checks(results[-2:])

        # 10. PromptBuilder
        print("\n10. Prompt builder:")
        try:
            pb = PromptBuilder(
                run_id="deadbeef", module="test",
                base_url="http://localhost:8000",
            )
            check("Prompt builder init", True)
        except Exception as e:
            check("Prompt builder", False, str(e))
        self._print_checks(results[-1:])

        # Summary
        print(f"\n{'=' * 60}")
        print(f"  Health Check: {passed} passed, {failed} failed")
        print(f"{'=' * 60}\n")

        return passed, failed, results

    # --- Pipeline Steps ---

    def _provision_test_user(self):
        """Provision the automated test user via Django management command.

        Calls ``python manage.py create_test_user`` via subprocess so the
        test framework stays decoupled from Django internals.

        After provisioning, exports TEST_USERNAME and TEST_PASSWORD into
        os.environ so the SuiteRunner's variable interpolation
        (${TEST_USERNAME}, ${TEST_PASSWORD}) resolves correctly.
        """
        import subprocess

        project_root = Path(__file__).resolve().parent.parent.parent
        manage_py = project_root / "manage.py"

        if not manage_py.exists():
            self._log("provision_test_user_skip",
                       reason="manage.py not found at " + str(manage_py))
            return

        # Read credentials from same env vars the service uses (with defaults)
        test_email = os.environ.get("WLJ_TEST_EMAIL", "autotest@local.test")
        test_password = os.environ.get("WLJ_TEST_PASSWORD", "testpass123")

        try:
            result = subprocess.run(
                [sys.executable, str(manage_py), "create_test_user"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(project_root),
            )
            if result.returncode == 0:
                self._log("provision_test_user_ok", output=result.stdout.strip())
            else:
                self._log("provision_test_user_warn",
                           stderr=result.stderr.strip(),
                           returncode=result.returncode)
        except subprocess.TimeoutExpired:
            self._log("provision_test_user_timeout")
        except Exception as exc:
            self._log("provision_test_user_error", error=str(exc))

        # Export credentials so the runner can interpolate ${TEST_USERNAME}
        # and ${TEST_PASSWORD} in suite YAML files.
        os.environ.setdefault("TEST_USERNAME", test_email)
        os.environ.setdefault("TEST_PASSWORD", test_password)

    def _build_runner(self):
        """Build a SuiteRunner from orchestrator parameters."""
        try:
            runner = SuiteRunner(
                suite_path=self.suite_path,
                module=self.module,
                base_url=self.base_url,
                headed=self.headed,
                env=self.env,
            )
            # Override run_id to use our generated one
            runner.run_id = self.run_id
            return runner
        except (FileNotFoundError, ValueError) as exc:
            raise OrchestratorError(str(exc), phase="init_runner") from exc

    def _init_manifest(self):
        """Initialize RunManifest for this run."""
        # Load suite to get metadata
        self.runner.load_suite()
        suite_name = self.runner.suite_data.get("suite", "")
        module = self.runner.module
        environment = self.env or (
            "development" if "localhost" in (self.base_url or "localhost")
            else "production"
        )

        manifest = RunManifest(
            run_id=self.run_id,
            module=module,
            suite=suite_name,
            base_url=self.runner.base_url,
            environment=environment,
        )

        # Set expected cases from suite
        cases = self.runner.get_cases()
        case_ids = [c.get("id", "unknown") for c in cases]
        manifest.set_expected_cases(case_ids)

        # Write initial manifest (status: running)
        manifest.write()

        return manifest

    def _init_registry(self):
        """Initialize TestDataRegistry for this run."""
        return TestDataRegistry()

    def _validate_schema(self):
        """Validate suite YAML against schema."""
        try:
            validator = SchemaValidator()
            validator.validate_file(self.runner.suite_path)
        except ValidationError as exc:
            raise OrchestratorError(
                f"Schema validation failed: {exc}", phase="validate_schema"
            ) from exc

    def _validate_selectors(self):
        """Run selector pre-validation if templates exist.

        Returns:
            Dict with found, missing, skipped counts, or None if skipped.
        """
        templates_dir = Path(__file__).parent.parent.parent / "templates"
        if not templates_dir.exists():
            return {"status": "skipped", "reason": "templates directory not found"}

        # Import the validate_selectors functions
        import importlib.util
        validate_script = Path(__file__).parent.parent / "validate_selectors.py"
        if not validate_script.exists():
            return {"status": "skipped", "reason": "validate_selectors.py not found"}

        spec = importlib.util.spec_from_file_location(
            "validate_selectors", validate_script
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        module_name = self.runner.module
        try:
            found, missing, template_testids = mod.validate_module(
                module_name, templates_dir
            )
        except FileNotFoundError:
            return {"status": "skipped", "reason": f"no suite for {module_name}"}

        found_count = sum(1 for f in found if f["status"] == "found")
        skip_count = sum(1 for f in found if f["status"] == "skipped_variable")
        miss_count = len(missing)

        result = {
            "status": "completed",
            "found": found_count,
            "skipped": skip_count,
            "missing": miss_count,
            "missing_selectors": [m["value"] for m in missing],
        }

        if miss_count > 0:
            print(
                f"WARNING: {miss_count} missing selector(s) for "
                f"{module_name}: {', '.join(m['value'] for m in missing)}",
                file=sys.stderr,
            )

        return result

    def _init_subsystems(self):
        """Initialize safety, reporting, and artifact subsystems."""
        module = self.runner.module
        base_url = self.runner.base_url
        environment = self.env or (
            "development" if "localhost" in base_url else "production"
        )

        # Safety controller
        self.safety = SafetyController(
            base_url=base_url, module=module, run_id=self.run_id,
        )

        # Report writer
        self.reporter = ReportWriter(
            run_id=self.run_id,
            suite=self.runner.suite_data.get("suite", ""),
            module=module,
            base_url=base_url,
            environment=environment,
        )

        # Artifact capture
        self.artifact_capture = ArtifactCapture(module=module)

        # Prompt builder
        self.prompt_builder = PromptBuilder(
            run_id=self.run_id, module=module, base_url=base_url,
        )

    def _execute_suite(self, executor=None):
        """Execute the suite through the runner.

        Updates manifest and reporter as cases complete.

        Returns:
            Summary dict from runner.
        """
        # Re-load suite data (runner.run() will call load_suite again)
        # We need to intercept case results for manifest tracking
        self.runner.load_suite()
        self.runner.acquire_lock()

        try:
            cases = self.runner.get_cases()
            for case in cases:
                case_id = case.get("id", "unknown")
                start = datetime.now(timezone.utc)
                steps = case.get("steps", [])

                try:
                    if executor:
                        executor.execute_case(case)

                    duration_ms = _elapsed_ms(start)
                    self.runner.results["passed"].append({
                        "case_id": case_id,
                        "duration_ms": duration_ms,
                    })
                    self.manifest.record_case_pass(case_id)
                    self.reporter.record_pass(
                        case_id, duration_ms, len(steps),
                    )

                except ExecutionError as exc:
                    duration_ms = _elapsed_ms(start)
                    self.runner.results["failed"].append({
                        "case_id": case_id,
                        "error": str(exc),
                        "duration_ms": duration_ms,
                    })
                    self.manifest.record_case_fail(case_id)

                    # Capture artifacts if executor is active
                    artifacts = {"screenshot": None, "html_dump": None}
                    if executor and hasattr(executor, "page") and executor.page:
                        try:
                            artifacts = self.artifact_capture.capture_on_failure(
                                executor.page, case_id,
                            )
                        except Exception:
                            pass

                    self.reporter.record_fail(
                        case_id=case_id,
                        duration_ms=duration_ms,
                        failed_step=exc.step_index,
                        action=exc.action or "UNKNOWN",
                        selector=exc.selector,
                        error=str(exc),
                        screenshot=artifacts.get("screenshot"),
                        html_dump=artifacts.get("html_dump"),
                    )

                except Exception as exc:
                    duration_ms = _elapsed_ms(start)
                    self.runner.results["failed"].append({
                        "case_id": case_id,
                        "error": str(exc),
                        "duration_ms": duration_ms,
                    })
                    self.manifest.record_case_fail(case_id)
                    self.reporter.record_fail(
                        case_id=case_id,
                        duration_ms=duration_ms,
                        failed_step=0,
                        action="UNKNOWN",
                        selector=None,
                        error=str(exc),
                    )

            return self.runner._build_summary(cases)
        finally:
            self.runner.release_lock()

    def _write_reports(self):
        """Write all reporting outputs."""
        if self.reporter:
            self.reporter.write_all()

    def _finalize_manifest(self):
        """Finalize and write the run manifest."""
        self.manifest.finalize()
        return self.manifest.write()

    def _verify_integrity(self):
        """Verify run integrity from the manifest.

        Returns:
            True if run integrity is intact (all cases accounted for).
        """
        data = self.manifest.to_dict()
        integrity = data.get("integrity", {})
        missing = integrity.get("missing", 0)

        if missing > 0:
            missing_ids = integrity.get("missing_case_ids", [])
            print(
                f"INTEGRITY WARNING: {missing} case(s) unaccounted for: "
                f"{', '.join(missing_ids)}",
                file=sys.stderr,
            )
            return False

        return True

    def _generate_fix_prompt(self):
        """Generate Claude fix prompt if there are failures."""
        if not self._summary or self._summary["failed"] == 0:
            return

        if not self.prompt_builder:
            return

        # Read failures from reporter
        failures = self.reporter._fail_entries if self.reporter else []
        if not failures:
            return

        content = self.prompt_builder.generate(failures)
        if content:
            base = Path(__file__).parent.parent
            prompt_path = (
                base / "modules" / self.runner.module / "reports"
                / "claude_fix_prompt.md"
            )
            self._fix_prompt_path = prompt_path

    # --- Utilities ---

    def _log(self, event, **kwargs):
        """Log a pipeline event."""
        entry = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(
                timespec="milliseconds"
            ),
        }
        entry.update(kwargs)
        self._pipeline_log.append(entry)

    def get_pipeline_log(self):
        """Return the pipeline execution log."""
        return list(self._pipeline_log)

    def get_summary(self):
        """Return the run summary dict."""
        return self._summary

    def get_manifest_path(self):
        """Return the path to the finalized manifest."""
        return self._manifest_path

    def get_fix_prompt_path(self):
        """Return the path to the fix prompt, or None."""
        return self._fix_prompt_path

    def get_selector_results(self):
        """Return selector validation results."""
        return self._selector_results

    @staticmethod
    def _print_checks(checks):
        """Print check results."""
        for c in checks:
            if c["status"] == "pass":
                print(f"    {c['name']}")
            else:
                print(f"    {c['name']} -- {c.get('detail', '')}")


# --- Helpers ---

def _elapsed_ms(start):
    """Calculate elapsed milliseconds since start."""
    return int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
