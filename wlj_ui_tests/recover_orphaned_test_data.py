#!/usr/bin/env python3
"""Recover orphaned AUTOTEST data — Phase 14.

Reads test_data_registry.ndjson to find uncleaned AUTOTEST records
and provides a remediation plan. Does NOT execute cleanup autonomously
— lists orphans and generates actionable output.

Usage:
    python3 wlj_ui_tests/recover_orphaned_test_data.py [--run-id RUN_ID] [--json]

Options:
    --run-id   Filter to a specific run ID.
    --json     Output results as JSON instead of human-readable text.
    --purge    Rewrite registry removing entries marked as cleaned_up.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from framework import TestDataRegistry


def find_orphans(registry, run_id=None):
    """Find uncleaned entries in the registry file.

    Args:
        registry: TestDataRegistry instance.
        run_id: Optional run ID filter.

    Returns:
        List of orphan entry dicts.
    """
    return registry.read_uncleaned(run_id=run_id)


def group_by_run(orphans):
    """Group orphan entries by run_id.

    Returns:
        Dict mapping run_id to list of entries.
    """
    groups = {}
    for entry in orphans:
        rid = entry.get("run_id", "unknown")
        groups.setdefault(rid, []).append(entry)
    return groups


def generate_remediation(orphans):
    """Generate remediation instructions for orphaned entries.

    Returns:
        List of remediation action dicts.
    """
    actions = []
    for entry in orphans:
        obj_type = entry.get("object_type", "unknown")
        title = entry.get("title", "")
        module = entry.get("module", "unknown")
        run_id = entry.get("run_id", "unknown")

        if obj_type == "journal_entry":
            actions.append({
                "object_type": obj_type,
                "title": title,
                "module": module,
                "run_id": run_id,
                "instruction": (
                    f"Search journal entries for '{title}' and soft-delete. "
                    f"URL: /journal/entries/?search={_url_encode_title(title)}"
                ),
            })
        else:
            actions.append({
                "object_type": obj_type,
                "title": title,
                "module": module,
                "run_id": run_id,
                "instruction": (
                    f"Manually locate and remove {obj_type} with title '{title}' "
                    f"in module '{module}'."
                ),
            })
    return actions


def purge_cleaned(registry):
    """Rewrite the registry file keeping only uncleaned entries.

    Returns:
        Tuple of (removed_count, remaining_count).
    """
    all_entries = registry.read_all()
    uncleaned = [e for e in all_entries if not e.get("cleaned_up")]
    removed = len(all_entries) - len(uncleaned)

    # Rewrite file with only uncleaned entries
    with open(registry.registry_path, "w") as f:
        for entry in uncleaned:
            f.write(json.dumps(entry, default=str) + "\n")

    return removed, len(uncleaned)


def print_human(orphans, remediation):
    """Print human-readable orphan report."""
    if not orphans:
        print("\n✓ No orphaned AUTOTEST records found. Registry is clean.\n")
        return

    groups = group_by_run(orphans)
    total = len(orphans)
    runs = len(groups)

    print(f"\n⚠ Found {total} orphaned AUTOTEST record(s) across {runs} run(s):\n")

    for run_id, entries in sorted(groups.items()):
        print(f"  Run {run_id} ({len(entries)} orphan(s)):")
        for entry in entries:
            created = entry.get("created_at", "unknown")
            print(f"    • [{entry.get('module')}] {entry.get('title')}")
            print(f"      Type: {entry.get('object_type')} | Created: {created}")
        print()

    print("Remediation steps:")
    for i, action in enumerate(remediation, 1):
        print(f"  {i}. {action['instruction']}")

    print(f"\nTotal: {total} orphans require cleanup.\n")


def print_json(orphans, remediation):
    """Print JSON orphan report."""
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "total_orphans": len(orphans),
        "runs_affected": len(group_by_run(orphans)),
        "orphans": orphans,
        "remediation": remediation,
    }
    print(json.dumps(output, indent=2, default=str))


def _url_encode_title(title):
    """Simple URL encoding for search parameter."""
    return title.replace("|", "%7C").replace(" ", "+")


def main():
    parser = argparse.ArgumentParser(
        description="Find and report orphaned AUTOTEST records."
    )
    parser.add_argument(
        "--run-id",
        help="Filter to a specific run ID.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Remove cleaned_up entries from registry file.",
    )
    args = parser.parse_args()

    registry = TestDataRegistry()

    # Check registry file exists
    if not registry.registry_path.exists():
        if args.json:
            print(json.dumps({"total_orphans": 0, "message": "Registry file not found."}))
        else:
            print("\n✓ Registry file not found — no AUTOTEST data tracked yet.\n")
        return 0

    if args.purge:
        removed, remaining = purge_cleaned(registry)
        if args.json:
            print(json.dumps({"purged": removed, "remaining": remaining}))
        else:
            print(f"\n✓ Purged {removed} cleaned-up entries. {remaining} entries remaining.\n")
        return 0

    orphans = find_orphans(registry, run_id=args.run_id)
    remediation = generate_remediation(orphans)

    if args.json:
        print_json(orphans, remediation)
    else:
        print_human(orphans, remediation)

    return 1 if orphans else 0


if __name__ == "__main__":
    sys.exit(main())
