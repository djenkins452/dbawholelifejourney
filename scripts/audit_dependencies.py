#!/usr/bin/env python3
# ==============================================================================
# File: scripts/audit_dependencies.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Audit the PRODUCTION-resolved dependency set against OSV.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Audit `constraints.txt` — the exact set production resolved — against OSV.

    python3 scripts/audit_dependencies.py            # report
    python3 scripts/audit_dependencies.py --strict   # non-zero exit on any new finding

Why not `pip-audit -r`: it resolves and installs to audit, which cannot work from a
developer machine whose Python is older than production's (WLJ's local Python is 3.9;
production runs 3.12). Querying OSV directly audits the pins as recorded, from anywhere.

`ACCEPTED_FINDINGS` is the reviewed exception list. Each entry states WHY the finding does
not affect the deployed application. Anything not listed is actionable.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

CONSTRAINTS = "constraints.txt"
OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"

#: Reviewed exceptions: package -> why the advisories do not affect the running service.
ACCEPTED_FINDINGS = {
    "pip": (
        "BUILD-TIME ONLY. pip is the installer, not a runtime import of the application; "
        "its advisories require installing a hostile package. WLJ installs from PyPI "
        "against this pinned constraints file, so the attack surface is not reachable "
        "from the deployed service. Revisit if pip ever becomes a runtime dependency."
    ),
}


def read_pins(path=CONSTRAINTS):
    pins = []
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([A-Za-z0-9._-]+)==(.+)$", line)
            if not match:
                raise SystemExit(f"{path}: unpinned or malformed entry: {line!r}")
            pins.append((match.group(1), match.group(2)))
    return pins


def query_osv(pins):
    queries = [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v}
               for n, v in pins]
    request = urllib.request.Request(
        OSV_BATCH_URL, data=json.dumps({"queries": queries}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response).get("results", [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero when an unaccepted finding exists.")
    args = parser.parse_args()

    pins = read_pins()
    results = query_osv(pins)

    actionable, accepted = [], []
    for (name, version), result in zip(pins, results):
        ids = [v["id"] for v in (result.get("vulns") or [])]
        if not ids:
            continue
        (accepted if name.lower() in ACCEPTED_FINDINGS else actionable).append(
            (name, version, ids))

    print(f"Audited {len(pins)} pinned packages from the production-resolved set.")
    for name, version, ids in sorted(accepted):
        print(f"  ACCEPTED  {name}=={version}: {len(ids)} advisories — "
              f"{ACCEPTED_FINDINGS[name.lower()].split('.')[0]}.")
    if not actionable:
        print("  No actionable vulnerabilities.")
        return 0
    for name, version, ids in sorted(actionable):
        print(f"  ACTIONABLE {name}=={version}: {', '.join(ids[:8])}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
