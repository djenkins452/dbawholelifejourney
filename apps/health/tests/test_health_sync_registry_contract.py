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

        # Overall-health rollup for the native hero card (the iOS OverallHealth model
        # decodes exactly these keys — this pins the contract so the UI can't break).
        oh = status["overall_health"]
        self.assertEqual(
            set(oh.keys()),
            {"status", "healthy_count", "active_count", "total_count", "issue_count"},
        )
        self.assertEqual(oh["status"], "setup")          # no data yet for a fresh user
        self.assertEqual(oh["active_count"], 0)
        self.assertEqual(oh["healthy_count"], 0)
        self.assertEqual(oh["total_count"], len(HEALTH_SYNC_TYPES))
        self.assertEqual(oh["issue_count"], len(status["issues"]))


# The fetch strategies the registry documents (how the iOS producer reads each sample).
_KNOWN_FETCH_STRATEGIES = {
    "cumulative_sum", "discrete_latest", "discrete_avg", "discrete_all",
    "category", "correlation", "composite", "workout",
}


class CanonicalContractHardeningTests(TestCase):
    """Stronger executable guarantees so the HealthKit surface cannot drift as it grows
    domain by domain. Complements the agreement tests above — these pin per-row validity,
    generic-store discipline, and (crucially) that every generic type has a real iOS
    PRODUCER, not just authorization (the class of bug that let `waist` sit half-wired)."""

    def test_every_fetch_strategy_is_known(self):
        for t in HEALTHKIT_TYPES:
            self.assertIn(
                t.fetch_strategy, _KNOWN_FETCH_STRATEGIES,
                f"{t.key}: unknown fetch_strategy {t.fetch_strategy!r}")

    def test_no_duplicate_hk_identifiers(self):
        """Two rows claiming the same HealthKit identifier is a copy-paste bug. (The
        composite nutrient parent legitimately carries a representative identifier while
        reading many, so it is exempt.)"""
        seen = {}
        for t in HEALTHKIT_TYPES:
            if t.kind == "composite":
                continue
            self.assertNotIn(
                t.hk_identifier, seen,
                f"{t.key} and {seen.get(t.hk_identifier)} share hk_identifier "
                f"{t.hk_identifier!r}")
            seen[t.hk_identifier] = t.key

    def test_no_unsupported_type_is_presented_as_active(self):
        """Every telemetry-surfaced type must be part of the iOS read-authorization set —
        we never show a source in Health Sync that the app cannot actually read."""
        for t in HEALTHKIT_TYPES:
            if t.telemetry:
                self.assertTrue(
                    t.authorized, f"{t.key}: surfaced in Health Sync but not authorized")

    def test_generic_fact_store_rows_are_well_formed(self):
        """Every row that lands in the shared HealthKitDailyMetric store must carry a unit,
        a category, a known fetch strategy, and a presence_filter that discriminates on its
        OWN key — ``presence_filter == {"metric_key": key}`` (a mismatch silently reports
        another metric's data as this one's)."""
        generic = [t for t in HEALTHKIT_TYPES if t.model_path.endswith("HealthKitDailyMetric")]
        self.assertTrue(generic, "expected at least one generic-store type")
        for t in generic:
            self.assertTrue(t.unit, f"{t.key}: generic-store row missing unit")
            self.assertIn(t.category, CATEGORY_LABELS, f"{t.key}: bad category")
            self.assertIn(t.fetch_strategy, _KNOWN_FETCH_STRATEGIES, f"{t.key}: bad strategy")
            self.assertEqual(
                t.presence_filter, {"metric_key": t.key},
                f"{t.key}: presence_filter must discriminate on its own metric_key")

    def test_every_queried_identifier_is_authorized_or_allowlisted(self):
        """Code=5 guard (the Steps root cause). An identifier a fetch QUERIES but that is
        NOT in the iOS authorization `readTypes` set throws
        `errorAuthorizationNotDetermined` — and before `safeFetch`, one such throw aborted
        the ENTIRE sync before `submit`, silently killing Steps (already fetched) and
        everything else. The prior authorization test greps `forIdentifier:` anywhere, so
        a fetch-only identifier looked authorized — this closes that blind spot by
        splitting the readTypes closure from the fetch code and asserting queried ⊆
        authorized (plus a documented allowlist of types we intentionally don't authorize
        but handle gracefully)."""
        if not _IOS_HEALTHKIT_MANAGER.exists():
            self.skipTest("iOS HealthKitManager.swift not present in this checkout")
        text = _IOS_HEALTHKIT_MANAGER.read_text()
        marker = text.find("return types")  # end of the readTypes authorization closure
        self.assertNotEqual(marker, -1, "could not locate the readTypes closure")
        authz_region, fetch_region = text[:marker], text[marker:]
        authorized = set(re.findall(r"forIdentifier:\s*(\.\w+)", authz_region))
        queried = set(re.findall(r"forIdentifier:\s*(\.\w+)", fetch_region))

        # Types we KNOWINGLY query without authorizing. `.bloodPressure` is a correlation
        # type that hangs requestAuthorization on some iOS versions, so we authorize its
        # systolic/diastolic members instead and let the correlation query fail gracefully
        # under safeFetch (it returns [] and the sync continues).
        ALLOWLIST = {".bloodPressure"}

        unauthorized = queried - authorized - ALLOWLIST
        self.assertEqual(
            unauthorized, set(),
            f"Fetches query HealthKit identifiers NOT in readTypes (these throw Code=5 and "
            f"silently never sync — add them to readTypes, or to the documented allowlist "
            f"if intentional + handled by safeFetch): {sorted(unauthorized)}",
        )

    def test_every_generic_type_has_an_ios_producer(self):
        """Django→Swift PRODUCER agreement (beyond authorization): every generic-store key
        must be emitted by an iOS fetch as ``metricType: \"<key>\"``. A registry row +
        handler with no producer is a dead ingest path — this fails CI before it ships."""
        if not _IOS_HEALTHKIT_MANAGER.exists():
            self.skipTest("iOS HealthKitManager.swift not present in this checkout")
        text = _IOS_HEALTHKIT_MANAGER.read_text()
        producers = set(re.findall(r'metricType:\s*"(\w+)"', text))
        generic_keys = {
            t.key for t in HEALTHKIT_TYPES if t.model_path.endswith("HealthKitDailyMetric")
        }
        missing = {k for k in generic_keys if k not in producers}
        self.assertEqual(
            missing, set(),
            f"Generic-store types with a registry row + handler but NO iOS producer "
            f"(add a fetch emitting metricType): {sorted(missing)}")
