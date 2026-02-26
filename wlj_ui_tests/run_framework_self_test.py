#!/usr/bin/env python3
"""Framework self-test script — Phase 13.

Validates runner, reporting, artifacts, prompt generation, test data registry,
and smoke module without Playwright. Runs as a standalone script.

Usage:
    python3 wlj_ui_tests/run_framework_self_test.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from framework import (
    __version__, SuiteRunner, generate_run_id,
    ReportWriter, ArtifactCapture, PromptBuilder,
    SchemaValidator, ValidationError,
    SafetyController, SafetyError, is_production,
    TestDataRegistry,
    resolve_selector,
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
    print(f"\n=== WLJ Framework Self-Test v{__version__} ===\n")

    # --- 1. Runner subsystem ---
    print("1. Runner subsystem:")
    runner = SuiteRunner(module="journal", base_url="http://localhost:8000")
    runner.load_suite()
    check("Journal suite loads", runner.suite_data is not None)
    check("RUN_ID format", len(runner.run_id) == 8 and all(
        c in "0123456789abcdef" for c in runner.run_id
    ))
    cases = runner.suite_data.get("cases", [])
    check("Journal has 4 cases", len(cases) == 4, f"found {len(cases)}")
    check("JRN-004 has cleanup_scope",
          cases[3].get("cleanup_scope", "").startswith("AUTOTEST|journal|"))

    # Variable substitution
    substituted = runner.get_cases()
    check("Variable substitution works",
          "${RUN_ID}" not in json.dumps(substituted))
    check("RUN_ID substituted in cleanup_scope",
          runner.run_id in substituted[3].get("cleanup_scope", ""))

    # Module listing
    modules = SuiteRunner.list_modules()
    check("10 modules found", len(modules) == 10, f"found {len(modules)}")
    check("smoke in modules", "smoke" in modules)

    # --- 2. Reporting subsystem ---
    print("\n2. Reporting subsystem:")
    with tempfile.TemporaryDirectory() as tmpdir:
        rw = ReportWriter(
            run_id="self0001", suite="Self-Test Suite", module="selftest",
            base_url="http://localhost:8000", environment="development",
            module_reports_dir=f"{tmpdir}/mod_reports",
            aggregated_reports_dir=f"{tmpdir}/agg_reports",
        )

        # Record mixed results
        rw.record_pass("ST-001", 120, 5)
        rw.record_pass("ST-002", 80, 3)
        rw.record_fail(
            case_id="ST-003", duration_ms=200,
            failed_step=2, action="CLICK",
            selector={"strategy": "data-testid", "value": "missing-btn"},
            error="Element not found",
            screenshot=f"{tmpdir}/st003.png",
            html_dump=f"{tmpdir}/st003.html",
        )
        rw.write_all()

        # Verify module reports
        mod_dir = Path(tmpdir) / "mod_reports"
        check("pass.ndjson exists", (mod_dir / "pass.ndjson").exists())
        check("fail.ndjson exists", (mod_dir / "fail.ndjson").exists())
        check("execution_log.ndjson exists",
              (mod_dir / "execution_log.ndjson").exists())
        check("run_summary.json exists",
              (mod_dir / "run_summary.json").exists())

        # Verify aggregated reports
        agg_dir = Path(tmpdir) / "agg_reports"
        check("aggregated pass.ndjson exists",
              (agg_dir / "pass.ndjson").exists())
        check("aggregated run_summary.json exists",
              (agg_dir / "run_summary.json").exists())

        # Verify summary contents
        summary = json.loads((mod_dir / "run_summary.json").read_text())
        check("summary total=3", summary["total_cases"] == 3)
        check("summary passed=2", summary["passed"] == 2)
        check("summary failed=1", summary["failed"] == 1)
        check("summary has framework_version",
              summary["framework_version"] == __version__)

        # Verify pass NDJSON
        pass_lines = (mod_dir / "pass.ndjson").read_text().strip().split("\n")
        check("2 pass entries", len(pass_lines) == 2)

        # Verify fail NDJSON
        fail_text = (mod_dir / "fail.ndjson").read_text().strip()
        fail_entry = json.loads(fail_text)
        check("fail has selector strategy",
              fail_entry["selector"]["strategy"] == "data-testid")
        check("fail has error message",
              "not found" in fail_entry["error"].lower())

    # --- 3. Artifact paths ---
    print("\n3. Artifact capture paths:")
    ac = ArtifactCapture(module="journal")
    check("Artifacts dir for journal",
          "modules/journal/artifacts" in str(ac.artifacts_dir))
    ac_smoke = ArtifactCapture(module="smoke")
    check("Artifacts dir for smoke",
          "modules/smoke/artifacts" in str(ac_smoke.artifacts_dir))

    # --- 4. Prompt builder ---
    print("\n4. Prompt generation:")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fail.ndjson to feed the prompt builder
        fail_path = Path(tmpdir) / "fail.ndjson"
        fail_data = {
            "case_id": "ST-PROMPT-1",
            "suite": "Self-Test",
            "module": "selftest",
            "status": "fail",
            "failed_step": 3,
            "action": "TYPE",
            "selector": {"strategy": "data-testid", "value": "input-field"},
            "error": "Timeout: element not found within 5000ms",
            "screenshot": "/tmp/screenshot.png",
            "html_dump": "/tmp/dump.html",
            "run_id": "self0001",
        }
        fail_path.write_text(json.dumps(fail_data) + "\n")

        pb = PromptBuilder(
            run_id="self0001", module="selftest",
            base_url="http://localhost:8000",
        )
        prompt = pb.generate_from_ndjson(
            fail_path, output_path=f"{tmpdir}/fix_prompt.md"
        )
        prompt_path = Path(tmpdir) / "fix_prompt.md"
        check("Prompt file generated", prompt_path.exists())
        check("Prompt has case_id", "ST-PROMPT-1" in prompt)
        check("Prompt has error", "Timeout" in prompt)
        check("Prompt has selector strategy", "data-testid" in prompt)
        check("Prompt has reproduction cmd", "run_suite.py" in prompt)

    # --- 5. Test data registry ---
    print("\n5. Test data registry:")
    with tempfile.TemporaryDirectory() as tmpdir:
        reg_path = Path(tmpdir) / "registry.ndjson"
        reg = TestDataRegistry(registry_path=reg_path)

        # Register objects
        reg.register(
            run_id="reg00001", module="journal", case_id="JRN-002",
            object_type="journal_entry",
            title="AUTOTEST|journal|reg00001|Test Entry",
        )
        reg.register(
            run_id="reg00001", module="smoke", case_id="SMK-002",
            object_type="journal_entry",
            title="AUTOTEST|smoke|reg00001|Smoke Entry",
        )
        reg.register(
            run_id="reg00002", module="journal", case_id="JRN-002",
            object_type="journal_entry",
            title="AUTOTEST|journal|reg00002|Other Run Entry",
        )

        check("3 entries registered", len(reg._entries) == 3)
        check("3 uncleaned", len(reg.get_uncleaned()) == 3)
        check("2 uncleaned for reg00001",
              len(reg.get_uncleaned("reg00001")) == 2)

        # Mark one cleaned
        found = reg.mark_cleaned_up(
            "reg00001", "AUTOTEST|journal|reg00001|Test Entry"
        )
        check("mark_cleaned_up returns True", found is True)
        check("2 uncleaned after cleanup", len(reg.get_uncleaned()) == 2)
        check("1 uncleaned for reg00001",
              len(reg.get_uncleaned("reg00001")) == 1)

        # Summary
        summary = reg.summary()
        check("summary total=3", summary["total"] == 3)
        check("summary cleaned_up=1", summary["cleaned_up"] == 1)
        check("summary uncleaned=2", summary["uncleaned"] == 2)

        # Flush and read back
        reg.flush()
        check("Registry file created", reg_path.exists())
        all_entries = reg.read_all()
        check("3 entries in file", len(all_entries) == 3)
        uncleaned = reg.read_uncleaned("reg00001")
        check("1 uncleaned in file for reg00001", len(uncleaned) == 1)

    # --- 6. Schema validation (both suites) ---
    print("\n6. Schema validation:")
    sv = SchemaValidator()
    for module in ["journal", "smoke"]:
        suite_path = Path(__file__).parent / "modules" / module / "suite.yaml"
        try:
            sv.validate_file(suite_path)
            check(f"{module}/suite.yaml passes", True)
        except (ValidationError, Exception) as e:
            check(f"{module}/suite.yaml passes", False, str(e))

    # --- 7. Safety + cleanup scope ---
    print("\n7. Safety and cleanup scope:")
    sc = SafetyController(
        base_url="https://wholelifejourney.com",
        module="journal", run_id="abc12345",
    )
    prefix = sc.make_cleanup_prefix("Test Entry")
    check("Prefix includes run_id",
          "abc12345" in prefix)
    check("Prefix format correct",
          prefix == "AUTOTEST|journal|abc12345|Test Entry")

    # Validate RUN_ID scoping: a different run's prefix should not match
    sc2 = SafetyController(
        base_url="https://wholelifejourney.com",
        module="journal", run_id="ffffffff",
    )
    other_prefix = sc2.make_cleanup_prefix("Test Entry")
    check("Different RUN_ID produces different prefix",
          other_prefix != prefix)
    check("Other prefix has its own run_id",
          "ffffffff" in other_prefix)

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"  Results: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}\n")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
