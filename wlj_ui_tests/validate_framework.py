#!/usr/bin/env python3
"""Framework validation script — Phase 12.

Validates all framework subsystems work correctly without Playwright.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from framework import (
    __version__, SuiteRunner, generate_run_id,
    ActionExecutor, ExecutionError,
    SelectorResolver, SelectorError, resolve_selector,
    ReportWriter, ArtifactCapture, PromptBuilder,
    SchemaValidator, ValidationError,
    SafetyController, SafetyError, is_production,
)

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name} — {detail}")


def main():
    print(f"\n=== WLJ UI Test Framework Validation v{__version__} ===\n")

    # --- 1. Run journal stub suite ---
    print("1. Journal stub suite execution:")
    with tempfile.TemporaryDirectory() as tmpdir:
        runner = SuiteRunner(module="journal", base_url="http://localhost:8000")
        runner.load_suite()
        check("Suite loaded", runner.suite_data is not None)
        check("Module is 'journal'", runner.module == "journal")
        check("RUN_ID is 8 hex chars", len(runner.run_id) == 8)
        check("Cases is empty list", runner.suite_data.get("cases") == [])

        # Test reporting writes
        rw = ReportWriter(
            run_id=runner.run_id, suite="Journal Module Tests",
            module="journal", base_url="http://localhost:8000",
            environment="development",
            module_reports_dir=f"{tmpdir}/module_reports",
            aggregated_reports_dir=f"{tmpdir}/agg_reports",
        )
        rw.record_pass("test-case-1", 100, 3)
        rw.write_all()

        pass_path = Path(tmpdir) / "module_reports" / "pass.ndjson"
        summary_path = Path(tmpdir) / "module_reports" / "run_summary.json"
        check("pass.ndjson generated", pass_path.exists())
        check("run_summary.json generated", summary_path.exists())

        if summary_path.exists():
            summary = json.loads(summary_path.read_text())
            check("summary has framework_version", summary.get("framework_version") == __version__)
            check("summary has schema_version", summary.get("schema_version") == "1.0")
            check("summary total_cases=1", summary.get("total_cases") == 1)
            check("summary passed=1", summary.get("passed") == 1)

    # --- 2. Failure pipeline ---
    print("\n2. Failure artifact pipeline:")
    with tempfile.TemporaryDirectory() as tmpdir:
        rw = ReportWriter(
            run_id="deadbeef", suite="Test", module="journal",
            base_url="http://localhost:8000", environment="development",
            module_reports_dir=f"{tmpdir}/reports",
            aggregated_reports_dir=f"{tmpdir}/agg",
        )
        rw.record_fail(
            case_id="fail-case-1", duration_ms=50,
            failed_step=2, action="CLICK",
            selector={"strategy": "data-testid", "value": "nonexistent-btn"},
            error="Timeout waiting for selector",
            screenshot=f"{tmpdir}/screenshot.png",
            html_dump=f"{tmpdir}/dump.html",
        )
        rw.write_all()

        fail_path = Path(tmpdir) / "reports" / "fail.ndjson"
        check("fail.ndjson generated", fail_path.exists())
        if fail_path.exists():
            line = fail_path.read_text().strip()
            entry = json.loads(line)
            check("fail entry has case_id", entry.get("case_id") == "fail-case-1")
            check("fail entry has error", "Timeout" in entry.get("error", ""))

        # Prompt builder
        pb = PromptBuilder(
            run_id="deadbeef", module="journal",
            base_url="http://localhost:8000",
        )
        prompt = pb.generate_from_ndjson(
            fail_path, output_path=f"{tmpdir}/claude_fix_prompt.md"
        )
        prompt_path = Path(tmpdir) / "claude_fix_prompt.md"
        check("claude_fix_prompt.md generated", prompt_path.exists())
        check("prompt contains case_id", "fail-case-1" in prompt)
        check("prompt contains reproduction cmd", "run_suite.py" in prompt)
        check("prompt contains selector strategy", "data-testid" in prompt)

    # --- 3. Safety controller ---
    print("\n3. Safety controls:")
    sc = SafetyController(
        base_url="https://wholelifejourney.com",
        module="journal", run_id="a1b2c3d4",
    )
    check("Production detected for wholelifejourney.com", sc.is_prod is True)
    check("Development detected for localhost",
          is_production("http://localhost:8000") is False)

    valid_prefix = sc.make_cleanup_prefix("Test Entry")
    check("Cleanup prefix format correct",
          valid_prefix == "AUTOTEST|journal|a1b2c3d4|Test Entry")
    check("Valid prefix passes validation",
          sc.validate_cleanup_prefix(valid_prefix) is True)

    blocked = False
    try:
        sc.validate_cleanup_prefix("Regular entry without prefix")
    except SafetyError:
        blocked = True
    check("Non-AUTOTEST prefix blocked in prod", blocked is True)

    # Dev mode should not block
    sc_dev = SafetyController(
        base_url="http://localhost:8000",
        module="journal", run_id="a1b2c3d4",
    )
    check("Dev mode does not block non-prefix",
          sc_dev.validate_cleanup_prefix("No prefix here") is False)

    destructive_blocked = False
    try:
        sc.check_action_allowed("DELETE")
    except SafetyError:
        destructive_blocked = True
    check("Destructive DELETE blocked in prod", destructive_blocked is True)

    # --- 4. Schema validator ---
    print("\n4. Schema validation:")
    sv = SchemaValidator()
    suite_path = Path(__file__).parent / "modules" / "journal" / "suite.yaml"
    try:
        sv.validate_file(suite_path)
        check("Journal suite.yaml passes validation", True)
    except (ValidationError, Exception) as e:
        check("Journal suite.yaml passes validation", False, str(e))

    bad_caught = False
    try:
        sv.validate({"no_version": True})
    except ValidationError:
        bad_caught = True
    check("Invalid YAML caught with descriptive errors", bad_caught is True)

    # --- 5. Selector resolver ---
    print("\n5. Selector resolution:")
    check("data-testid resolves",
          resolve_selector({"strategy": "data-testid", "value": "btn"}) == '[data-testid="btn"]')
    check("id resolves",
          resolve_selector({"strategy": "id", "value": "main"}) == '#main')
    check("name resolves",
          resolve_selector({"strategy": "name", "value": "email"}) == '[name="email"]')
    check("string passthrough",
          resolve_selector(".my-class") == '.my-class')

    # --- 6. Module isolation ---
    print("\n6. Module isolation:")
    modules = SuiteRunner.list_modules()
    check("10 modules found", len(modules) == 10, f"found {len(modules)}")
    check("journal in modules", "journal" in modules)
    check("admin in modules", "admin" in modules)

    reports_dir = SuiteRunner.module_reports_dir("journal")
    artifacts_dir = SuiteRunner.module_artifacts_dir("journal")
    check("Reports dir path correct", "modules/journal/reports" in str(reports_dir))
    check("Artifacts dir path correct", "modules/journal/artifacts" in str(artifacts_dir))

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}\n")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
