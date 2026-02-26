# ==============================================================================
# File: apps/admin_console/services/test_module_registry.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Discovers UI test modules from wlj_ui_tests/modules/
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-25
# ==============================================================================
"""
UI Test Module Registry — discovers available test modules by scanning
wlj_ui_tests/modules/ for directories containing suite.yaml files.

Usage:
    from apps.admin_console.services.test_module_registry import discover_modules
    modules = discover_modules()
    # [{"name": "journal", "suite_title": "Journal Module Tests",
    #   "cases": [{"id": "JRN-001", "name": "Login to application"}, ...],
    #   "case_count": 4, "path": "wlj_ui_tests/modules/journal/suite.yaml"}, ...]
"""

import logging
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger(__name__)

# Base directory for the UI test framework (project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_MODULES_DIR = _PROJECT_ROOT / "wlj_ui_tests" / "modules"


def discover_modules(base_dir=None):
    """Scan wlj_ui_tests/modules/ for directories containing suite.yaml.

    Args:
        base_dir: Override for the modules directory path.
            Defaults to <project_root>/wlj_ui_tests/modules/.

    Returns:
        Sorted list of dicts, each describing a discovered module:
          - name (str): Module directory name (e.g. "journal")
          - suite_title (str): Human-readable suite name from YAML
          - cases (list[dict]): Each with "id" and "name" keys
          - case_count (int): Number of test cases
          - path (str): Relative path to suite.yaml from project root
    """
    if yaml is None:
        logger.warning("PyYAML not installed — cannot discover UI test modules")
        return []

    modules_dir = Path(base_dir) if base_dir else _MODULES_DIR

    if not modules_dir.is_dir():
        logger.warning("UI test modules directory not found: %s", modules_dir)
        return []

    modules = []
    for suite_path in sorted(modules_dir.glob("*/suite.yaml")):
        module_info = _parse_suite(suite_path, modules_dir)
        if module_info:
            modules.append(module_info)

    return modules


def _parse_suite(suite_path, modules_dir):
    """Parse a single suite.yaml and extract module metadata.

    Args:
        suite_path: Absolute path to the suite.yaml file.
        modules_dir: Base modules directory for computing relative paths.

    Returns:
        Dict with module info, or None if parsing fails.
    """
    try:
        with open(suite_path, "r") as f:
            data = yaml.safe_load(f)

        if not data or not isinstance(data, dict):
            logger.warning("Empty or invalid suite.yaml: %s", suite_path)
            return None

        module_name = suite_path.parent.name
        suite_title = data.get("suite", module_name.title())

        # Extract case IDs and names
        cases = []
        raw_cases = data.get("cases", [])
        if isinstance(raw_cases, list):
            for case in raw_cases:
                if isinstance(case, dict):
                    cases.append({
                        "id": case.get("id", "UNKNOWN"),
                        "name": case.get("name", "Unnamed test"),
                    })

        # Compute relative path from project root
        try:
            rel_path = str(suite_path.relative_to(_PROJECT_ROOT))
        except ValueError:
            rel_path = str(suite_path)

        return {
            "name": module_name,
            "suite_title": suite_title,
            "cases": cases,
            "case_count": len(cases),
            "path": rel_path,
        }

    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", suite_path, exc)
        return None
    except Exception as exc:
        logger.error("Error reading %s: %s", suite_path, exc)
        return None
