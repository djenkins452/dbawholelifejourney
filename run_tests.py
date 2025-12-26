#!/usr/bin/env python
"""
Test Runner with Separate Output Files

Runs Django tests and outputs:
- test_summary.txt: Summary with pass/fail counts per app
- test_errors.txt: Detailed error messages (if any)

Usage:
    python run_tests.py
    python run_tests.py apps.life
    python run_tests.py apps.life apps.users
"""

import subprocess
import sys
import re
from datetime import datetime


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
    
    # Capture error blocks - look for lines starting with ====
    in_error = False
    current_error = []
    for line in lines:
        # Start of error block
        if line.startswith('======') and ('FAIL:' in line or 'ERROR:' in line):
            in_error = True
            current_error = [line]
        elif in_error:
            current_error.append(line)
            # End of error block (line of dashes)
            if line.startswith('------') and len(current_error) > 2:
                results['error_details'].append('\n'.join(current_error))
                current_error = []
                in_error = False
    
    # Also capture any remaining error block
    if current_error:
        results['error_details'].append('\n'.join(current_error))
    
    return results


def main():
    """Main entry point."""
    
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
    all_errors = []
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
        all_errors.extend(results['error_details'])
        
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
    
    # Write summary file
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    with open('test_summary.txt', 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("TEST SUMMARY REPORT\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Timestamp: {timestamp}\n\n")
        
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
    
    # Write errors file
    with open('test_errors.txt', 'w') as f:
        f.write("=" * 60 + "\n")
        f.write("TEST ERROR DETAILS\n")
        f.write("=" * 60 + "\n\n")
        
        if not all_errors:
            f.write("No errors! All tests passed.\n")
        else:
            f.write(f"Total Failures/Errors: {len(all_errors)}\n")
            for i, error in enumerate(all_errors, 1):
                f.write(f"\n{'=' * 60}\n")
                f.write(f"ERROR #{i}\n")
                f.write(f"{'=' * 60}\n")
                f.write(error)
                f.write("\n")
    
    # Print final summary to console
    print("=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    print(f"Total:  {total_tests}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"Errors: {total_errors}")
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