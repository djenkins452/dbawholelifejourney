#!/usr/bin/env python
"""
Whole Life Journey - Dependency Checker

Project: Whole Life Journey
Path: check_dependencies.py
Purpose: Verify development environment has all required packages installed

Description:
    A utility script that compares installed packages against requirements.txt
    to identify missing dependencies. Can optionally auto-install missing
    packages to quickly set up a development environment.

Key Responsibilities:
    - Parse requirements.txt to extract package names
    - Query pip to get list of installed packages
    - Compare required vs installed and report missing packages
    - Optionally install missing packages automatically

Usage:
    python check_dependencies.py           # Check dependencies
    python check_dependencies.py --install # Auto-install missing packages

Common Missing Packages:
    - cloudinary, django-cloudinary-storage: Media file storage
    - markdown: Help system rendering
    - psycopg2-binary: PostgreSQL database driver

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

import subprocess
import sys
import re
from pathlib import Path


def parse_requirements(requirements_path):
    """Parse requirements.txt and return list of package names."""
    packages = []

    with open(requirements_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Extract package name (before any version specifier)
            # Handle formats like: package>=1.0, package==1.0, package[extra]>=1.0
            match = re.match(r'^([a-zA-Z0-9_-]+)', line)
            if match:
                packages.append(match.group(1).lower())

    return packages


def get_installed_packages():
    """Get list of installed packages."""
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'list', '--format=freeze'],
        capture_output=True,
        text=True
    )

    installed = set()
    for line in result.stdout.split('\n'):
        if '==' in line:
            pkg_name = line.split('==')[0].lower()
            installed.add(pkg_name)

    return installed


def check_dependencies(requirements_path, auto_install=False):
    """Check if all required packages are installed."""

    print("=" * 60)
    print("DEPENDENCY CHECK")
    print("=" * 60)
    print(f"Requirements file: {requirements_path}")
    print(f"Python executable: {sys.executable}")
    print()

    required = parse_requirements(requirements_path)
    installed = get_installed_packages()

    # Map common package name differences
    name_mappings = {
        'pillow': 'pillow',
        'psycopg2-binary': 'psycopg2-binary',
        'django-environ': 'django-environ',
        'django-allauth': 'django-allauth',
        'django-crispy-forms': 'django-crispy-forms',
        'crispy-tailwind': 'crispy-tailwind',
        'django-cloudinary-storage': 'django-cloudinary-storage',
        'django-htmx': 'django-htmx',
        'python-dateutil': 'python-dateutil',
        'google-auth': 'google-auth',
        'google-auth-oauthlib': 'google-auth-oauthlib',
        'google-api-python-client': 'google-api-python-client',
        'django-debug-toolbar': 'django-debug-toolbar',
        'django-extensions': 'django-extensions',
    }

    missing = []
    found = []

    for pkg in required:
        # Check if package is installed (handle name variations)
        pkg_lower = pkg.lower()
        pkg_normalized = pkg_lower.replace('-', '_')

        if pkg_lower in installed or pkg_normalized in installed:
            found.append(pkg)
        else:
            missing.append(pkg)

    # Report results
    print(f"Required packages: {len(required)}")
    print(f"Found:   {len(found)}")
    print(f"Missing: {len(missing)}")
    print()

    if missing:
        print("-" * 40)
        print("MISSING PACKAGES:")
        print("-" * 40)
        for pkg in missing:
            print(f"  - {pkg}")
        print()

        if auto_install:
            print("Installing missing packages...")
            for pkg in missing:
                print(f"  Installing {pkg}...")
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', pkg],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    print(f"    ERROR: Failed to install {pkg}")
                    print(f"    {result.stderr}")
                else:
                    print(f"    OK")
            print()
            print("Re-running dependency check...")
            return check_dependencies(requirements_path, auto_install=False)
        else:
            print("To install missing packages, run:")
            print(f"  pip install {' '.join(missing)}")
            print()
            print("Or run this script with --install flag:")
            print("  python check_dependencies.py --install")
            print()
            return 1
    else:
        print("-" * 40)
        print("ALL DEPENDENCIES INSTALLED!")
        print("-" * 40)
        return 0


def main():
    # Find requirements.txt
    script_dir = Path(__file__).parent
    requirements_path = script_dir / 'requirements.txt'

    if not requirements_path.exists():
        print(f"ERROR: requirements.txt not found at {requirements_path}")
        return 1

    auto_install = '--install' in sys.argv

    return check_dependencies(requirements_path, auto_install)


if __name__ == '__main__':
    sys.exit(main())
