#!/usr/bin/env python3
"""WLJ UI Test Framework — CLI Runner.

Entry point for running test suites from the command line.
Uses the ExecutionOrchestrator for full run lifecycle management.

Usage:
    python wlj_ui_tests/run_suite.py --module journal
    python wlj_ui_tests/run_suite.py --suite modules/journal/suite.yaml
    python wlj_ui_tests/run_suite.py --module journal --headed --base-url http://localhost:8000
    python wlj_ui_tests/run_suite.py --health-check
    python wlj_ui_tests/run_suite.py --list-modules

Exit codes:
    0 — All tests passed (or health check passed)
    1 — One or more tests failed
    2 — Framework error (invalid args, file not found, etc.)
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure the framework package is importable
sys.path.insert(0, str(Path(__file__).parent))

from framework import __version__, SuiteRunner
from framework.execution_orchestrator import ExecutionOrchestrator


def main():
    """Parse arguments, run the suite via orchestrator, and exit."""
    args = parse_args()

    # Health check mode
    if args.health_check:
        orchestrator = ExecutionOrchestrator()
        passed, failed, results = orchestrator.health_check()
        return 0 if failed == 0 else 1

    # Standard run via orchestrator
    try:
        orchestrator = ExecutionOrchestrator(
            module=args.module,
            suite_path=args.suite,
            base_url=args.base_url,
            headed=args.headed,
            env=args.env,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    exit_code = orchestrator.run()

    # Print summary
    summary = orchestrator.get_summary()
    if summary:
        print_summary(summary)

        # Report fix prompt location if generated
        fix_prompt = orchestrator.get_fix_prompt_path()
        if fix_prompt and fix_prompt.exists():
            print(f"  Fix prompt: {fix_prompt}\n")

        # Report manifest location
        manifest_path = orchestrator.get_manifest_path()
        if manifest_path and manifest_path.exists():
            print(f"  Manifest: {manifest_path}")

        # Report selector validation
        sel_results = orchestrator.get_selector_results()
        if sel_results and sel_results.get("status") == "completed":
            missing = sel_results.get("missing", 0)
            if missing > 0:
                print(f"  ⚠ Selector warnings: {missing} missing")

        # Emit machine-readable JSON summary to stderr for CI integration
        print(json.dumps(summary, indent=2, default=str), file=sys.stderr)

    return exit_code


def parse_args():
    """Build and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="run_suite",
        description="WLJ UI Test Framework — Run test suites",
        epilog="Exit codes: 0=pass, 1=failures, 2=error",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {__version__}",
    )

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--suite", type=str,
        help="Path to a YAML suite file",
    )
    group.add_argument(
        "--module", type=str,
        help="Module name (resolves to modules/<name>/suite.yaml)",
    )

    parser.add_argument(
        "--base-url", type=str, default=None,
        help="Base URL for testing (default: $BASE_URL or http://localhost:8000)",
    )
    parser.add_argument(
        "--headed", action="store_true", default=False,
        help="Run browser in headed mode for debugging",
    )
    parser.add_argument(
        "--env", type=str, default=None,
        help="Environment name override (development/production)",
    )
    parser.add_argument(
        "--list-modules", action="store_true", default=False,
        help="List available modules and exit",
    )
    parser.add_argument(
        "--health-check", action="store_true", default=False,
        help="Run framework health check without executing tests",
    )

    args = parser.parse_args()

    if args.list_modules:
        modules = SuiteRunner.list_modules()
        print(f"Available modules ({len(modules)}):")
        for m in modules:
            print(f"  - {m}")
        sys.exit(0)

    # Require --module or --suite unless --health-check or --list-modules
    if not args.health_check and not args.suite and not args.module:
        parser.error("one of --module, --suite, or --health-check is required")

    return args


def print_summary(summary):
    """Print run summary to stdout."""
    total = summary["total_cases"]
    passed = summary["passed"]
    failed = summary["failed"]
    rate = summary["pass_rate"]

    print()
    print("=" * 60)
    print(f"  WLJ UI Test Run: {summary['run_id']}")
    print(f"  Module: {summary['module']}")
    print(f"  Suite:  {summary['suite']}")
    print(f"  URL:    {summary['base_url']}")
    print(f"  Env:    {summary['environment']}")
    print("=" * 60)
    print(f"  Total:  {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Rate:   {rate:.0%}")
    print("=" * 60)

    if failed > 0:
        print("\n  FAILED CASES:")
        for f in summary["results"]["failed"]:
            print(f"    {f['case_id']}: {f['error']}")
        print()


if __name__ == "__main__":
    sys.exit(main())
