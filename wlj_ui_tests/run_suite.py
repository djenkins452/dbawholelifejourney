#!/usr/bin/env python3
"""WLJ UI Test Framework — CLI Runner.

Entry point for running test suites from the command line.
Supports running by suite file path or module name.

Usage:
    python wlj_ui_tests/run_suite.py --module journal
    python wlj_ui_tests/run_suite.py --suite modules/journal/suite.yaml
    python wlj_ui_tests/run_suite.py --module journal --headed --base-url http://localhost:8000

Exit codes:
    0 — All tests passed
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
from framework.schema_validator import SchemaValidator, ValidationError


def main():
    """Parse arguments, run the suite, and exit with appropriate code."""
    args = parse_args()

    try:
        runner = build_runner(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Validate YAML schema before running
    try:
        validator = SchemaValidator()
        validator.validate_file(runner.suite_path)
    except ValidationError as exc:
        print(f"SCHEMA ERROR: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Run the suite (without Playwright executor — framework-only mode)
    try:
        summary = runner.run()
    except Exception as exc:
        print(f"RUNTIME ERROR: {exc}", file=sys.stderr)
        return 2

    print_summary(summary)

    if summary["failed"] > 0:
        return 1
    return 0


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

    group = parser.add_mutually_exclusive_group(required=True)
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

    args = parser.parse_args()

    if args.list_modules:
        modules = SuiteRunner.list_modules()
        print(f"Available modules ({len(modules)}):")
        for m in modules:
            print(f"  - {m}")
        sys.exit(0)

    return args


def build_runner(args):
    """Construct a SuiteRunner from parsed CLI arguments."""
    return SuiteRunner(
        suite_path=args.suite,
        module=args.module,
        base_url=args.base_url,
        headed=args.headed,
        env=args.env,
    )


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
            print(f"    ✗ {f['case_id']}: {f['error']}")
        print()

    # Emit machine-readable JSON summary to stderr for CI integration
    print(json.dumps(summary, indent=2, default=str), file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
