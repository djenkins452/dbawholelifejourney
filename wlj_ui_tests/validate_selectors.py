#!/usr/bin/env python3
"""Selector validator — Phase 14.

Verifies that data-testid selectors referenced in suite YAML files
exist in the corresponding Django templates. Runs before test execution
to catch missing selectors early (without Playwright).

Usage:
    python3 wlj_ui_tests/validate_selectors.py [--module MODULE] [--templates-dir DIR]

Exit codes:
    0 = all selectors found
    1 = missing selectors detected
    2 = error
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from framework import SuiteRunner

# Default templates directory (Django project root)
DEFAULT_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def extract_selectors_from_suite(suite_path):
    """Extract all data-testid selector values from a suite YAML file.

    Scans steps, asserts, and cleanup blocks for selectors using the
    'data-testid' strategy.

    Args:
        suite_path: Path to the suite.yaml file.

    Returns:
        List of dicts with 'value', 'case_id', 'context' (step/assert/cleanup).
    """
    with open(suite_path) as f:
        data = yaml.safe_load(f)

    selectors = []
    for case in data.get("cases", []):
        case_id = case.get("id", "unknown")

        # Steps
        for step in case.get("steps", []):
            sel = step.get("selector")
            if sel and _is_testid(sel):
                selectors.append({
                    "value": sel["value"],
                    "case_id": case_id,
                    "context": f"step/{step.get('action', '?')}",
                })

        # Asserts
        for assertion in case.get("asserts", []):
            sel = assertion.get("selector")
            if sel and _is_testid(sel):
                selectors.append({
                    "value": sel["value"],
                    "case_id": case_id,
                    "context": f"assert/{assertion.get('type', '?')}",
                })

        # Cleanup
        for step in case.get("cleanup", []):
            sel = step.get("selector")
            if sel and _is_testid(sel):
                selectors.append({
                    "value": sel["value"],
                    "case_id": case_id,
                    "context": f"cleanup/{step.get('action', '?')}",
                })

    return selectors


def scan_templates_for_testids(templates_dir):
    """Scan all HTML templates for data-testid attributes.

    Args:
        templates_dir: Root directory containing Django templates.

    Returns:
        Set of data-testid values found in templates.
    """
    found = set()
    pattern = re.compile(r'data-testid="([^"]+)"')

    for html_file in templates_dir.rglob("*.html"):
        try:
            content = html_file.read_text(encoding="utf-8")
            for match in pattern.finditer(content):
                found.add(match.group(1))
        except (OSError, UnicodeDecodeError):
            continue

    return found


def validate_module(module, templates_dir):
    """Validate all data-testid selectors for a module's suite.

    Args:
        module: Module name (e.g., 'journal').
        templates_dir: Path to templates root.

    Returns:
        Tuple of (found_selectors, missing_selectors, template_testids).
    """
    suite_path = SuiteRunner.resolve_module_suite(module)
    suite_selectors = extract_selectors_from_suite(suite_path)
    template_testids = scan_templates_for_testids(templates_dir)

    found = []
    missing = []

    # Deduplicate by value for checking, but keep all for reporting
    checked = set()
    for sel in suite_selectors:
        value = sel["value"]
        if value in checked:
            continue
        checked.add(value)

        # Skip selectors with variable placeholders (runtime values)
        if "${" in value:
            found.append({**sel, "status": "skipped_variable"})
            continue

        if value in template_testids:
            found.append({**sel, "status": "found"})
        else:
            missing.append({**sel, "status": "missing"})

    return found, missing, template_testids


def main():
    parser = argparse.ArgumentParser(
        description="Validate data-testid selectors exist in Django templates."
    )
    parser.add_argument(
        "--module",
        help="Validate a specific module. Defaults to all modules with cases.",
    )
    parser.add_argument(
        "--templates-dir",
        type=Path,
        default=DEFAULT_TEMPLATES_DIR,
        help=f"Templates directory (default: {DEFAULT_TEMPLATES_DIR}).",
    )
    args = parser.parse_args()

    templates_dir = args.templates_dir
    if not templates_dir.exists():
        print(f"✗ Templates directory not found: {templates_dir}", file=sys.stderr)
        return 2

    # Determine which modules to validate
    if args.module:
        modules = [args.module]
    else:
        modules = SuiteRunner.list_modules()

    total_found = 0
    total_missing = 0
    total_skipped = 0
    all_missing = []

    print(f"\n=== Selector Validation ===\n")
    print(f"Templates dir: {templates_dir}\n")

    for module in modules:
        try:
            suite_path = SuiteRunner.resolve_module_suite(module)
        except FileNotFoundError:
            continue

        # Skip modules with empty cases
        with open(suite_path) as f:
            data = yaml.safe_load(f)
        if not data.get("cases"):
            continue

        found, missing, template_testids = validate_module(module, templates_dir)

        found_count = sum(1 for f in found if f["status"] == "found")
        skip_count = sum(1 for f in found if f["status"] == "skipped_variable")
        miss_count = len(missing)

        status = "✓" if miss_count == 0 else "✗"
        print(f"  {status} {module}: {found_count} found, {skip_count} skipped (variables), {miss_count} missing")

        for m in missing:
            print(f"      MISSING: data-testid=\"{m['value']}\" "
                  f"(case {m['case_id']}, {m['context']})")
            all_missing.append({**m, "module": module})

        total_found += found_count
        total_missing += miss_count
        total_skipped += skip_count

    # Also show available template testids for debugging
    all_testids = scan_templates_for_testids(templates_dir)

    print(f"\n{'=' * 50}")
    print(f"  Selectors: {total_found} found, {total_skipped} skipped, "
          f"{total_missing} missing")
    print(f"  Templates: {len(all_testids)} data-testid attributes available")
    print(f"{'=' * 50}\n")

    if all_missing:
        print("Missing selectors need to be added to templates before tests run.")
        print("Add data-testid=\"<value>\" to the appropriate HTML elements.\n")

    return 1 if total_missing > 0 else 0


def _is_testid(selector):
    """Check if a selector dict uses the data-testid strategy."""
    if isinstance(selector, dict):
        return selector.get("strategy") == "data-testid"
    return False


if __name__ == "__main__":
    sys.exit(main())
