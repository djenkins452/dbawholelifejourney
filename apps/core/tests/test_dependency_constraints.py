# ==============================================================================
# File: apps/core/tests/test_dependency_constraints.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: CI guard against silent dependency drift. Offline.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""The deployed dependency set must stay reproducible and auditable.

`requirements.txt` pins RANGES, so the deployed versions were whatever pip resolved at
build time — not reproducible, and not auditable from the repository. `constraints.txt`
records the exact set production resolved.

These checks are OFFLINE (no network, no install) so they can run in any CI environment.
The vulnerability sweep itself lives in `scripts/audit_dependencies.py`, which queries OSV
and exits non-zero under `--strict` on any finding outside the reviewed exception list.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[3]
REQUIREMENTS = REPO_ROOT / "requirements.txt"
CONSTRAINTS = REPO_ROOT / "constraints.txt"
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit_dependencies.py"

_REQ_NAME = re.compile(r"^([A-Za-z0-9._-]+)\s*(?:\[[^\]]+\])?\s*(?:[<>=!~]|$)")
_PIN = re.compile(r"^([A-Za-z0-9._-]+)==(.+)$")


def _normalise(name):
    return name.lower().replace("_", "-")


def _requirement_names():
    names = set()
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = _REQ_NAME.match(line)
        if match:
            names.add(_normalise(match.group(1)))
    return names


def _constraint_pins():
    pins = {}
    for line in CONSTRAINTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = _PIN.match(line)
        if match:
            pins[_normalise(match.group(1))] = match.group(2)
    return pins


class DependencyConstraintsTests(SimpleTestCase):

    def test_constraints_file_exists_and_is_fully_pinned(self):
        self.assertTrue(CONSTRAINTS.exists(), "constraints.txt is missing")
        pins = _constraint_pins()
        self.assertGreater(len(pins), 50, "constraints.txt looks truncated")
        for line in CONSTRAINTS.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            self.assertRegex(stripped, _PIN,
                             f"constraints.txt must pin exactly: {stripped!r}")

    def test_every_declared_requirement_is_pinned(self):
        """A new requirement without a constraint is silent drift."""
        pins = _constraint_pins()
        missing = sorted(name for name in _requirement_names() if name not in pins)
        self.assertEqual(
            missing, [],
            "These requirements have no pinned version in constraints.txt. Refresh it "
            "from the production audit (`/admin-console/api/claude/finance-audit/` -> "
            f"dependencies) after the next deploy: {missing}",
        )

    def test_security_critical_packages_are_pinned(self):
        """The packages a provider attestation actually rests on."""
        pins = _constraint_pins()
        for package in ("django", "cryptography", "pyjwt", "plaid-python", "requests",
                        "urllib3", "gunicorn"):
            self.assertIn(package, pins, f"{package} must be pinned for auditability")

    def test_audit_script_is_present_and_declares_its_exceptions(self):
        self.assertTrue(AUDIT_SCRIPT.exists())
        source = AUDIT_SCRIPT.read_text()
        self.assertIn("ACCEPTED_FINDINGS", source)
        self.assertIn("--strict", source)

    def test_accepted_findings_are_justified_not_merely_listed(self):
        """An exception without a written reason is an exception nobody reviewed."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("wlj_dep_audit", AUDIT_SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(module.ACCEPTED_FINDINGS)
        for package, reason in module.ACCEPTED_FINDINGS.items():
            self.assertGreater(len(reason), 80,
                               f"{package}: exception needs a real justification")

    def test_constraints_records_the_production_runtime(self):
        header = CONSTRAINTS.read_text()[:2000]
        self.assertIn("Python", header)
        self.assertIn("Django", header)
