"""WLJ UI Test Framework — Test Data Registry.

Logs all AUTOTEST objects created during a test run to an NDJSON file.
Enables post-run audit and cleanup verification.

Registry file: wlj_ui_tests/reports/test_data_registry.ndjson

Each line is a JSON object:
  {
    "run_id": "a1b2c3d4",
    "module": "journal",
    "case_id": "JRN-002",
    "object_type": "journal_entry",
    "title": "AUTOTEST|journal|a1b2c3d4|Smoke Test Entry",
    "created_at": "2026-02-25T22:00:00.000Z",
    "cleaned_up": false,
    "cleaned_up_at": null
  }
"""

import json
from datetime import datetime, timezone
from pathlib import Path


# Default registry file location
REGISTRY_PATH = Path(__file__).parent.parent / "reports" / "test_data_registry.ndjson"


class TestDataRegistry:
    """Tracks all AUTOTEST objects created during test runs.

    Append-only NDJSON log for audit trail and cleanup verification.
    Thread-safe through file-level append operations.
    """

    def __init__(self, registry_path=None):
        """Initialize registry.

        Args:
            registry_path: Override path to registry NDJSON file.
                Defaults to wlj_ui_tests/reports/test_data_registry.ndjson.
        """
        self.registry_path = Path(registry_path) if registry_path else REGISTRY_PATH
        self._entries = []

    def register(self, run_id, module, case_id, object_type, title,
                 extra=None):
        """Register a newly created AUTOTEST object.

        Args:
            run_id: 8-char hex run ID.
            module: Module name (e.g., 'journal', 'smoke').
            case_id: Test case ID (e.g., 'JRN-002').
            object_type: Type of object created (e.g., 'journal_entry').
            title: Full title/name of the created object (with AUTOTEST prefix).
            extra: Optional dict of additional metadata.

        Returns:
            The registry entry dict.
        """
        entry = {
            "run_id": run_id,
            "module": module,
            "case_id": case_id,
            "object_type": object_type,
            "title": title,
            "created_at": _now_iso(),
            "cleaned_up": False,
            "cleaned_up_at": None,
        }
        if extra:
            entry.update(extra)

        self._entries.append(entry)
        return entry

    def mark_cleaned_up(self, run_id, title):
        """Mark an object as cleaned up by run_id and title.

        Args:
            run_id: 8-char hex run ID.
            title: Exact title to match.

        Returns:
            True if an entry was found and marked, False otherwise.
        """
        for entry in self._entries:
            if entry["run_id"] == run_id and entry["title"] == title:
                entry["cleaned_up"] = True
                entry["cleaned_up_at"] = _now_iso()
                return True
        return False

    def get_uncleaned(self, run_id=None):
        """Return all entries not yet cleaned up.

        Args:
            run_id: Optional filter by run ID.

        Returns:
            List of entry dicts where cleaned_up is False.
        """
        entries = self._entries
        if run_id:
            entries = [e for e in entries if e["run_id"] == run_id]
        return [e for e in entries if not e["cleaned_up"]]

    def flush(self):
        """Write all pending entries to the registry NDJSON file.

        Appends to existing file (does not overwrite).
        """
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_path, "a") as f:
            for entry in self._entries:
                f.write(json.dumps(entry, default=str) + "\n")
        self._entries.clear()

    def read_all(self):
        """Read all entries from the registry file.

        Returns:
            List of entry dicts from the NDJSON file.
        """
        if not self.registry_path.exists():
            return []
        entries = []
        with open(self.registry_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def read_uncleaned(self, run_id=None):
        """Read uncleaned entries from the registry file.

        Args:
            run_id: Optional filter by run ID.

        Returns:
            List of entry dicts where cleaned_up is False.
        """
        entries = self.read_all()
        if run_id:
            entries = [e for e in entries if e.get("run_id") == run_id]
        return [e for e in entries if not e.get("cleaned_up")]

    def summary(self):
        """Return summary stats of in-memory entries.

        Returns:
            Dict with total, cleaned_up, and uncleaned counts.
        """
        total = len(self._entries)
        cleaned = sum(1 for e in self._entries if e["cleaned_up"])
        return {
            "total": total,
            "cleaned_up": cleaned,
            "uncleaned": total - cleaned,
        }


def _now_iso():
    """Return current UTC time as ISO 8601 with millisecond precision."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
