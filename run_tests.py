#!/usr/bin/env python
"""
Test Runner with Database History and Separate Output Files

Runs Django tests and:
- Saves results to database (TestRun/TestRunDetail models)
- Outputs test_summary.txt with current run summary
- Outputs test_errors.txt with detailed error messages
- Maintains historical record of all test runs

Usage:
    python run_tests.py
    python run_tests.py apps.life
    python run_tests.py apps.life apps.users
"""

import os
import sys
import subprocess
import re
import json
import time
from datetime import datetime
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from apps.core.models import TestRun, TestRunDetail


def get_git_info():
    """Get current git branch and commit hash."""
    branch = ''
    commit = ''

    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass  # Git not available or timed out

    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass  # Git not available or timed out

    return branch, commit


def run_single_app(app):
    """Run tests for a single app and return results."""
    cmd = [sys.executable, 'manage.py', 'test', '--settings=config.settings_test', '--verbosity=2', app]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    return result.stdout + result.stderr, result.returncode


def parse_app_output(output, app_name):
    """Parse output for a single app run."""

    results = {
        'app': app_name,
        'passed': 0,
        'failed': 0,
        'errors': 0,
        'total': 0,
        'failed_tests': [],
        'error_tests': [],
        'error_details': []
    }

    lines = output.split('\n')

    # Count ok/FAIL/ERROR from test lines
    for line in lines:
        if ' ... ok' in line:
            results['passed'] += 1
            results['total'] += 1
        elif ' ... FAIL' in line:
            results['failed'] += 1
            results['total'] += 1
            # Extract test name
            match = re.match(r'^(\w+) \(([^)]+)\)', line)
            if match:
                results['failed_tests'].append(f"{match.group(1)} ({match.group(2)})")
        elif ' ... ERROR' in line:
            results['errors'] += 1
            results['total'] += 1
            match = re.match(r'^(\w+) \(([^)]+)\)', line)
            if match:
                results['error_tests'].append(f"{match.group(1)} ({match.group(2)})")

    # Capture error/failure blocks more robustly
    # Look for the separator lines that Django uses
    in_error_section = False
    current_error = []

    for i, line in enumerate(lines):
        # Detect start of error/failure block
        if line.startswith('=' * 50) or line.startswith('=' * 70):
            # Check if next line contains FAIL: or ERROR:
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if 'FAIL:' in next_line or 'ERROR:' in next_line:
                    in_error_section = True
                    current_error = [line]
                    continue

        if in_error_section:
            current_error.append(line)
            # End of error block (line of dashes followed by another error or end)
            if line.startswith('-' * 50) or line.startswith('-' * 70):
                # Save this error block
                error_text = '\n'.join(current_error)
                if error_text.strip():
                    results['error_details'].append(error_text)
                current_error = []
                in_error_section = False

    # Capture any remaining error block
    if current_error:
        error_text = '\n'.join(current_error)
        if error_text.strip():
            results['error_details'].append(error_text)

    # Also capture the FAILED message at the end which contains traceback summary
    full_output = output

    # Find traceback sections
    traceback_pattern = r'Traceback \(most recent call last\):.*?(?=\n\n|\Z)'
    tracebacks = re.findall(traceback_pattern, full_output, re.DOTALL)
    for tb in tracebacks:
        if tb.strip() and tb not in [e for e in results['error_details']]:
            # Check if this traceback is already captured
            already_captured = any(tb in e for e in results['error_details'])
            if not already_captured:
                results['error_details'].append(tb)

    return results


def save_to_database(all_results, duration, apps):
    """Save test results to database."""

    total_passed = sum(r['passed'] for r in all_results)
    total_failed = sum(r['failed'] for r in all_results)
    total_errors = sum(r['errors'] for r in all_results)
    total_tests = sum(r['total'] for r in all_results)

    # Determine status
    if total_errors > 0:
        status = 'error'
    elif total_failed > 0:
        status = 'failed'
    else:
        status = 'passed'

    # Calculate pass rate
    pass_rate = Decimal('0.00')
    if total_tests > 0:
        pass_rate = Decimal(str(round((total_passed / total_tests) * 100, 2)))

    # Get git info
    branch, commit = get_git_info()

    # Create TestRun
    test_run = TestRun.objects.create(
        duration_seconds=duration,
        status=status,
        total_tests=total_tests,
        passed=total_passed,
        failed=total_failed,
        errors=total_errors,
        apps_tested=', '.join(apps),
        pass_rate=pass_rate,
        git_branch=branch,
        git_commit=commit
    )

    # Create TestRunDetail for each app
    for r in all_results:
        TestRunDetail.objects.create(
            test_run=test_run,
            app_name=r['app'],
            passed=r['passed'],
            failed=r['failed'],
            errors=r['errors'],
            total=r['total'],
            failed_tests=json.dumps(r['failed_tests']),
            error_tests=json.dumps(r['error_tests']),
            error_details='\n\n'.join(r['error_details'])
        )

    return test_run


def write_summary_file(all_results, timestamp, test_run_id=None):
    """Write the summary file."""

    total_passed = sum(r['passed'] for r in all_results)
    total_failed = sum(r['failed'] for r in all_results)
    total_errors = sum(r['errors'] for r in all_results)
    total_tests = sum(r['total'] for r in all_results)

    with open('test_summary.txt', 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("TEST SUMMARY REPORT\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Timestamp: {timestamp}\n")
        if test_run_id:
            f.write(f"Test Run ID: {test_run_id}\n")
        f.write("\n")

        f.write("-" * 40 + "\n")
        f.write("OVERALL RESULTS\n")
        f.write("-" * 40 + "\n")
        f.write(f"Total Tests:  {total_tests}\n")
        f.write(f"Passed:       {total_passed}\n")
        f.write(f"Failed:       {total_failed}\n")
        f.write(f"Errors:       {total_errors}\n")
        if total_tests > 0:
            pass_rate = (total_passed / total_tests) * 100
            f.write(f"Pass Rate:    {pass_rate:.1f}%\n")

        f.write("\n")
        f.write("-" * 40 + "\n")
        f.write("RESULTS BY APP\n")
        f.write("-" * 40 + "\n")

        for r in all_results:
            status = "PASS" if r['failed'] == 0 and r['errors'] == 0 else "FAIL"
            f.write(f"[{status}] {r['app']}\n")
            f.write(f"       Passed: {r['passed']}, Failed: {r['failed']}, Errors: {r['errors']}\n")

        # List failed tests
        all_failed = []
        all_error_tests = []
        for r in all_results:
            all_failed.extend(r['failed_tests'])
            all_error_tests.extend(r['error_tests'])

        if all_failed:
            f.write("\n")
            f.write("-" * 40 + "\n")
            f.write("FAILED TESTS\n")
            f.write("-" * 40 + "\n")
            for test in all_failed:
                f.write(f"  - {test}\n")

        if all_error_tests:
            f.write("\n")
            f.write("-" * 40 + "\n")
            f.write("ERROR TESTS\n")
            f.write("-" * 40 + "\n")
            for test in all_error_tests:
                f.write(f"  - {test}\n")

        f.write("\n")
        f.write("=" * 60 + "\n")
        if total_failed == 0 and total_errors == 0:
            f.write("ALL TESTS PASSED!\n")
        else:
            f.write("SOME TESTS FAILED - See test_errors.txt for details\n")
        f.write("=" * 60 + "\n")


def write_errors_file(all_results, timestamp):
    """Write the detailed errors file."""

    # Collect all errors
    all_errors = []
    for r in all_results:
        for error in r['error_details']:
            all_errors.append({
                'app': r['app'],
                'error': error
            })

    # Also collect failed/error test names with their app
    failed_tests = []
    error_tests = []
    for r in all_results:
        for t in r['failed_tests']:
            failed_tests.append({'app': r['app'], 'test': t})
        for t in r['error_tests']:
            error_tests.append({'app': r['app'], 'test': t})

    with open('test_errors.txt', 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("TEST ERROR DETAILS\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Timestamp: {timestamp}\n\n")

        if not all_errors and not failed_tests and not error_tests:
            f.write("No errors! All tests passed.\n")
        else:
            # Summary of failures
            if failed_tests:
                f.write("-" * 40 + "\n")
                f.write(f"FAILED TESTS ({len(failed_tests)})\n")
                f.write("-" * 40 + "\n")
                for item in failed_tests:
                    f.write(f"  [{item['app']}] {item['test']}\n")
                f.write("\n")

            if error_tests:
                f.write("-" * 40 + "\n")
                f.write(f"ERROR TESTS ({len(error_tests)})\n")
                f.write("-" * 40 + "\n")
                for item in error_tests:
                    f.write(f"  [{item['app']}] {item['test']}\n")
                f.write("\n")

            # Full error details
            if all_errors:
                f.write("=" * 60 + "\n")
                f.write("FULL ERROR DETAILS\n")
                f.write("=" * 60 + "\n\n")

                for i, item in enumerate(all_errors, 1):
                    f.write(f"{'#' * 60}\n")
                    f.write(f"ERROR #{i} - {item['app']}\n")
                    f.write(f"{'#' * 60}\n\n")
                    f.write(item['error'])
                    f.write("\n\n")


def main():
    """Main entry point."""

    start_time = time.time()

    # Get apps from command line args
    apps = sys.argv[1:] if len(sys.argv) > 1 else None

    # If no apps specified, test these by default
    if not apps:
        apps = [
            'apps.core.tests',
            'apps.users',
            'apps.dashboard',
            'apps.journal',
            'apps.faith',
            'apps.health',
            'apps.help.tests',
            'apps.life',
            'apps.purpose.tests',  # Need full path due to import issue
            'apps.admin_console.tests',
            'apps.ai.tests',
        ]

    print("=" * 60)
    print("RUNNING TESTS")
    print("=" * 60)
    print(f"Apps: {', '.join(apps)}")
    print("=" * 60)
    print()

    # Collect results from all apps
    all_results = []
    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_tests = 0
    final_return_code = 0

    for app in apps:
        print(f"Testing {app}...", end=" ", flush=True)

        output, return_code = run_single_app(app)
        results = parse_app_output(output, app)

        all_results.append(results)

        total_passed += results['passed']
        total_failed += results['failed']
        total_errors += results['errors']
        total_tests += results['total']

        if return_code != 0:
            final_return_code = return_code

        # Print app result
        if results['failed'] == 0 and results['errors'] == 0:
            print(f"OK ({results['passed']} tests)")
        else:
            print(f"FAILED ({results['passed']} passed, {results['failed']} failed, {results['errors']} errors)")

    print()

    # Calculate duration
    duration = time.time() - start_time

    # Get timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Save to database
    try:
        test_run = save_to_database(all_results, duration, apps)
        test_run_id = test_run.id
        print(f"Results saved to database (Test Run ID: {test_run_id})")
    except Exception as e:
        print(f"Warning: Could not save to database: {e}")
        test_run_id = None

    # Write summary file
    write_summary_file(all_results, timestamp, test_run_id)

    # Write errors file
    write_errors_file(all_results, timestamp)

    # Print final summary to console
    print()
    print("=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Total:    {total_tests}")
    print(f"Passed:   {total_passed}")
    print(f"Failed:   {total_failed}")
    print(f"Errors:   {total_errors}")
    print(f"Duration: {duration:.2f}s")
    print("-" * 60)

    if total_failed == 0 and total_errors == 0:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED")
        print("See test_errors.txt for details")

    print("=" * 60)
    print()
    print("Files written: test_summary.txt, test_errors.txt")

    return final_return_code


if __name__ == '__main__':
    sys.exit(main())
