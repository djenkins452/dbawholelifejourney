"""Executable agreement contract: HealthKit ingest handlers ↔ Health Sync registry.

This is the CI guard that keeps the canonical HealthKit surface in agreement so it
can never silently drift again (the audit found ~27 ingested types with NO telemetry
row). It asserts:

  1. Every ingest ``metric_type`` (apps.mobile.views.HEALTH_METRIC_HANDLERS) has a
     Health Sync registry row (HEALTH_SYNC_TYPES) — and vice versa. One canonical set.
  2. Every registry row resolves against the real models: model imports, ``date_field``
     is a real field, every ``presence_filter`` key targets a real field, and the
     ``category`` is a declared category.
  3. ``build_health_sync_status`` executes for a real user across ALL registered types
     without raising (catches a bad presence_filter / date_field / missing ``source``).

If you add a HealthKit metric type, you must add it to BOTH the handler map and the
registry (and the iOS producer) — this test fails otherwise.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.health.healthkit_registry import AUTHORIZED_SWIFT_READS, HEALTHKIT_TYPES
from apps.health.services.health_sync_status import (
    CATEGORY_LABELS,
    HEALTH_SYNC_TYPES,
    HEALTH_SYNC_TYPES_BY_KEY,
    build_health_sync_status,
)
from apps.mobile.views import HEALTH_METRIC_HANDLERS
from apps.users.models import TermsAcceptance, User

_IOS_HEALTHKIT_MANAGER = (
    Path(settings.BASE_DIR) / "ios" / "WLJWrapper" / "WLJWrapper"
    / "Services" / "HealthKitManager.swift"
)


def _field_name(lookup: str) -> str:
    """'hrv_value__isnull' -> 'hrv_value'; 'count__gt' -> 'count'; 'metric_name' -> 'metric_name'."""
    return lookup.split("__", 1)[0]


class HealthSyncRegistryContractTests(TestCase):
    def test_registry_and_handler_map_are_in_agreement(self):
        """The ingest handler map and the Health Sync registry must cover the SAME
        set of metric types — no ingested-but-unmonitored type, no phantom row."""
        handler_keys = set(HEALTH_METRIC_HANDLERS.keys())
        registry_keys = {t.key for t in HEALTH_SYNC_TYPES}

        ingested_but_no_telemetry = handler_keys - registry_keys
        telemetry_but_no_handler = registry_keys - handler_keys

        self.assertEqual(
            ingested_but_no_telemetry, set(),
            f"Ingested metric types with NO Health Sync registry row (add them to "
            f"HEALTH_SYNC_TYPES): {sorted(ingested_but_no_telemetry)}",
        )
        self.assertEqual(
            telemetry_but_no_handler, set(),
            f"Health Sync registry rows with NO ingest handler (add a handler or remove "
            f"the row): {sorted(telemetry_but_no_handler)}",
        )

    def test_registry_identifiers_are_authorized_in_ios(self):
        """Django → Swift agreement: every HealthKit identifier the canonical registry
        references must be read by the iOS app. Prevents the exact drift the audit found
        (a server handler with no iOS producer — e.g. waist before it was wired). If you
        add a registry row, you must add its `.enumCase` to HealthKitManager.readTypes +
        a fetch, or this fails."""
        if not _IOS_HEALTHKIT_MANAGER.exists():
            self.skipTest("iOS HealthKitManager.swift not present in this checkout")
        text = _IOS_HEALTHKIT_MANAGER.read_text()
        ios_reads = set(re.findall(r"forIdentifier:\s*(\.\w+)", text))

        missing = {r for r in AUTHORIZED_SWIFT_READS if r not in ios_reads}
        self.assertEqual(
            missing, set(),
            f"Canonical registry references HealthKit identifiers the iOS app does not "
            f"read (add them to HealthKitManager.readTypes + a fetch): {sorted(missing)}",
        )

    def test_registry_hk_metadata_is_complete(self):
        """Every non-workout registry row declares its HealthKit identity + display
        metadata (the single-authority promise) so no consumer has to hardcode it."""
        for t in HEALTHKIT_TYPES:
            self.assertTrue(t.hk_identifier, f"{t.key}: missing hk_identifier")
            self.assertTrue(t.subtitle, f"{t.key}: missing display subtitle")
            self.assertIn(t.kind, ("quantity", "category", "correlation", "workout", "composite"))
            if t.kind != "workout":
                self.assertTrue(t.hk_swift_reads, f"{t.key}: missing hk_swift_reads")

    def test_registry_keys_are_unique(self):
        keys = [t.key for t in HEALTH_SYNC_TYPES]
        self.assertEqual(len(keys), len(set(keys)), "Duplicate keys in HEALTH_SYNC_TYPES")

    def test_every_registry_row_resolves_against_its_model(self):
        for t in HEALTH_SYNC_TYPES:
            model = t.get_model()  # raises if model_path is wrong
            # date_field must be a real field
            model._meta.get_field(t.date_field)
            # every presence_filter key must target a real field
            for lookup in (t.presence_filter or {}):
                model._meta.get_field(_field_name(lookup))
            # category must be declared
            self.assertIn(
                t.category, CATEGORY_LABELS,
                f"{t.key}: unknown category {t.category!r}",
            )

    def test_build_status_runs_for_all_types_without_error(self):
        """The strongest guard: actually execute the deterministic status across every
        registered type for a real user. A bad presence_filter or missing ``source``
        field surfaces here as a FieldError rather than silently in production."""
        user = User.objects.create_user(email="hk_contract@test.com", password="x")
        TermsAcceptance.objects.create(
            user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        status = build_health_sync_status(user)

        # Every registered type appears exactly once in the flat list...
        self.assertEqual(len(status["data_types"]), len(HEALTH_SYNC_TYPES))
        keys = {d["key"] for d in status["data_types"]}
        self.assertEqual(keys, set(HEALTH_SYNC_TYPES_BY_KEY.keys()))

        # ...with no data yet, so every source truthfully reports no_data.
        self.assertTrue(all(d["status"] == "no_data" for d in status["data_types"]))
        self.assertEqual(status["active_types_count"], 0)

        # ...and every type is placed in exactly one rendered category group.
        grouped = [d["key"] for c in status["categories"] for d in c["types"]]
        self.assertEqual(sorted(grouped), sorted(keys))
        for c in status["categories"]:
            self.assertIn(c["key"], CATEGORY_LABELS)
            self.assertEqual(c["label"], CATEGORY_LABELS[c["key"]])
