"""Health Sync truth-model regression tests.

Incident (2026-07-16): the Health Sync dashboard reported

    "Needs Attention — Flights Climbed has not synced in 6 days."

while synchronization was working perfectly. The user simply hadn't climbed stairs.
The engine measured days-since-last-data-row and called that "sync health", collapsing
three unrelated truths into one number.

These tests pin the corrected model:

    IMPORT HEALTH   (HealthIngestionRun)  — did sync technically work?  → the ONLY
                                            thing that may say "Needs Attention"
    SOURCE ACTIVITY (persisted rows)      — did records arrive?         → never health
    ACTIVITY CLASS  (registry)            — should records be expected? → policy

The governing rule under test: **record age can never mark a source unhealthy.**
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import SleepEntry, StepsEntry, WeightEntry
from apps.health.services.health_sync_status import build_health_sync_status
from apps.mobile.models import HealthIngestionRun
from apps.users.models import TermsAcceptance

User = get_user_model()


class HealthSyncTruthModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="sync-truth@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.now = timezone.now()
        self.today = self.now.date()

    # ── helpers ────────────────────────────────────────────────────────────────
    def _steps_day(self, days_ago, count=8000, flights=None):
        """A synced day. `flights=None` mirrors reality for a day with no stairs:
        the StepsEntry row EXISTS (proving the sync ran) but carries no flights."""
        return StepsEntry.objects.create(
            user=self.user, source="apple_health", count=count,
            flights_climbed=flights,
            logged_date=self.today - timedelta(days=days_ago),
        )

    def _run(self, *, status="completed", type_results=None, errors=None,
             client_debug=None, age_hours=0, error_message=""):
        run = HealthIngestionRun.objects.create(user=self.user, metrics_received=1)
        if status == "completed":
            run.mark_completed(1, 0, 0, type_results=type_results or {})
        elif status == "partial":
            run.mark_partial(0, 0, 1, errors=errors or [], type_results=type_results or {})
        elif status == "failed":
            run.mark_failed(error_message or "network error")
        if client_debug:
            run.client_debug = client_debug
            run.save(update_fields=["client_debug"])
        if age_hours:
            HealthIngestionRun.objects.filter(pk=run.pk).update(
                created_at=self.now - timedelta(hours=age_hours),
            )
            run.refresh_from_db()
        return run

    def _type(self, st, key):
        return next(d for d in st["data_types"] if d["key"] == key)

    # ── 1 & 2: the reported acceptance case ────────────────────────────────────
    def test_1_successful_sync_with_zero_flights_stays_healthy(self):
        """THE acceptance case: recent successful sync, last positive Flights Climbed
        record six days ago, no import failure, no permission problem."""
        self._steps_day(6, flights=12)            # last day with stairs
        for d in range(0, 6):                     # six synced days, no stairs
            self._steps_day(d, flights=None)
        self._run(type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0},
                                "flights_climbed": {"created": 0, "updated": 0,
                                                    "skipped": 6, "failed": 0}})

        st = build_health_sync_status(self.user, now=self.now)
        flights = self._type(st, "flights_climbed")

        # Sync is provably fine, so Flights Climbed is fine — whatever its record age.
        self.assertEqual(flights["import_health"], "ok")
        self.assertEqual(flights["activity_class"], "event_driven")
        # Neutral/informational — never "Needs Attention".
        self.assertIn(flights["status"], ("healthy", "idle"))
        self.assertNotEqual(flights["status"], "attention")
        self.assertNotIn("has not synced", flights["message"].lower())
        # Health Sync reports healthy overall, and Flights Climbed raises no issue.
        self.assertEqual(st["overall_health"]["status"], "healthy")
        self.assertEqual(st["issues"], [])

    def test_2_many_days_without_flights_never_needs_attention(self):
        self._steps_day(30, flights=5)
        for d in range(0, 30):
            self._steps_day(d, flights=None)
        self._run(type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}})

        st = build_health_sync_status(self.user, now=self.now)
        flights = self._type(st, "flights_climbed")
        self.assertNotEqual(flights["status"], "attention")
        self.assertEqual(st["overall_health"]["status"], "healthy")
        self.assertFalse(any(i["key"] == "flights_climbed" for i in st["issues"]))

    # ── 3: rest day ────────────────────────────────────────────────────────────
    def test_3_rest_day_without_exercise_minutes_stays_healthy(self):
        StepsEntry.objects.create(
            user=self.user, source="apple_health", count=6000,
            exercise_minutes=45, logged_date=self.today - timedelta(days=4),
        )
        for d in range(0, 4):
            self._steps_day(d)  # synced, but no exercise minutes
        self._run(type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}})

        st = build_health_sync_status(self.user, now=self.now)
        ex = self._type(st, "exercise_minutes")
        self.assertEqual(ex["activity_class"], "event_driven")
        self.assertNotEqual(ex["status"], "attention")
        self.assertEqual(st["overall_health"]["status"], "healthy")

    # ── 4: watch-dependent metric ──────────────────────────────────────────────
    def test_4_watch_dependent_metric_without_recent_records_is_not_a_failure(self):
        """Decision A: the watch may simply not have been worn. Absence of sleep/HRV
        records is never proof of a sync problem."""
        SleepEntry.objects.create(
            user=self.user, source="apple_health", hrv_value=42,
            sleep_date=self.today - timedelta(days=9), total_duration_minutes=420,
            bedtime=self.now - timedelta(days=9, hours=8),
            wake_time=self.now - timedelta(days=9, hours=1),
        )
        self._steps_day(0)
        self._run(type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}})

        st = build_health_sync_status(self.user, now=self.now)
        for key in ("sleep", "hrv"):
            d = self._type(st, key)
            self.assertNotEqual(d["status"], "attention", f"{key} must not be a failure")
            self.assertEqual(d["import_health"], "ok")
        self.assertEqual(st["overall_health"]["status"], "healthy")
        self.assertEqual(st["issues"], [])

    def test_4b_blood_oxygen_absence_is_not_a_failure(self):
        """Apple disabled the SpO₂ sensor on US watches sold after Jan 2024 — silence
        here is a device reality, not a sync fault."""
        self._steps_day(0)
        self._run(type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}})
        st = build_health_sync_status(self.user, now=self.now)
        spo2 = self._type(st, "blood_oxygen")
        self.assertEqual(spo2["activity_class"], "device_generated")
        self.assertNotEqual(spo2["status"], "attention")

    # ── 5: a real ingestion failure DOES warn ──────────────────────────────────
    def test_5_verified_ingestion_failure_produces_needs_attention(self):
        self._steps_day(0)
        self._run(
            status="partial",
            type_results={"steps": {"created": 0, "updated": 0, "skipped": 1, "failed": 1}},
            errors=[{"index": 0, "type": "steps", "error": "Invalid steps value: -5"}],
        )
        st = build_health_sync_status(self.user, now=self.now)
        steps = self._type(st, "steps")
        self.assertEqual(steps["import_health"], "failed")
        self.assertEqual(steps["status"], "attention")
        self.assertEqual(st["overall_health"]["status"], "attention")
        issue = next(i for i in st["issues"] if i["key"] == "steps")
        self.assertIn("rejected", issue["message"].lower())
        # Ordinary rejection is not a permissions problem — don't send them to settings.
        self.assertIsNone(issue["action"])

    def test_5b_whole_run_failure_is_one_account_level_issue(self):
        self._steps_day(0)
        self._run(status="failed", error_message="Connection reset")
        st = build_health_sync_status(self.user, now=self.now)
        self.assertEqual(st["sync_path"]["status"], "failed")
        self.assertEqual(st["overall_health"]["status"], "attention")
        self.assertTrue(any(i["key"] == "_sync" for i in st["issues"]))

    def test_5c_device_not_checking_in_is_one_issue_not_thirteen(self):
        """The genuine "sync is broken" case: the phone has stopped sending anything.
        ONE honest account-level issue — not a per-metric false alarm storm."""
        self._steps_day(5)
        self._run(age_hours=96,
                  type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}})
        st = build_health_sync_status(self.user, now=self.now)
        self.assertEqual(st["sync_path"]["status"], "not_checking_in")
        self.assertEqual(st["overall_health"]["status"], "attention")
        self.assertEqual([i["key"] for i in st["issues"]], ["_sync"])

    # ── 6: permission denial ───────────────────────────────────────────────────
    def test_6_permission_denial_produces_permission_specific_warning(self):
        """Only provable via the client's own fetch telemetry (HealthKit hides
        authorization). The app told us its read failed → we may say so, and only then
        offer the Apple Health fix."""
        self._steps_day(0)
        self._run(
            type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}},
            client_debug={"heart_rate": {"fetch_failed": 1}},
        )
        st = build_health_sync_status(self.user, now=self.now)
        hr = self._type(st, "heart_rate")
        self.assertEqual(hr["import_health"], "blocked")
        self.assertEqual(hr["status"], "attention")
        issue = next(i for i in st["issues"] if i["key"] == "heart_rate")
        self.assertIn("Apple Health", issue["message"])
        self.assertEqual(issue["action"], "open_health_settings")

    def test_6b_inactivity_never_offers_the_apple_health_fix(self):
        """Do not send users to settings for ordinary inactivity."""
        self._steps_day(6, flights=3)
        for d in range(0, 6):
            self._steps_day(d, flights=None)
        self._run(type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}})
        st = build_health_sync_status(self.user, now=self.now)
        self.assertFalse(any(i.get("action") == "open_health_settings" for i in st["issues"]))

    # ── 7: wording ─────────────────────────────────────────────────────────────
    def test_7_never_says_has_not_synced_from_data_absence(self):
        self._steps_day(12, flights=9)          # beyond the 7-day observation window
        for d in range(0, 12):
            self._steps_day(d, flights=None)
        WeightEntry.objects.create(
            user=self.user, source="apple_health", value=286,
            recorded_at=self.now - timedelta(days=40),
        )
        self._run(type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}})

        st = build_health_sync_status(self.user, now=self.now)
        for d in st["data_types"]:
            self.assertNotIn("has not synced", d["message"].lower(), f"{d['key']}: {d['message']}")
        for i in st["issues"]:
            self.assertNotIn("has not synced", i["message"].lower())
        # And the honest wording is present.
        self.assertIn("No recent Flights Climbed records",
                      self._type(st, "flights_climbed")["message"])

    # ── 9: summary counts are import health, not activity ──────────────────────
    def test_9_summary_health_counts_reflect_import_health_not_activity(self):
        self._steps_day(6, flights=4)
        for d in range(0, 6):
            self._steps_day(d, flights=None)
        WeightEntry.objects.create(
            user=self.user, source="apple_health", value=286,
            recorded_at=self.now - timedelta(days=40),
        )
        self._run(type_results={"steps": {"created": 1, "updated": 0, "skipped": 0, "failed": 0}})

        st = build_health_sync_status(self.user, now=self.now)
        oh = st["overall_health"]
        # Every active source is importing fine → all healthy, despite inactivity.
        self.assertEqual(oh["healthy_count"], oh["active_count"])
        self.assertEqual(oh["attention_count"], 0)
        self.assertEqual(oh["status"], "healthy")
        # Activity is reported separately and is NOT health.
        activity = st["source_activity_summary"]
        self.assertGreaterEqual(activity["no_recent_records"], 1)
        self.assertIn("produced_recently", activity)

    # ── 10: genuine success reporting is intact ────────────────────────────────
    def test_10_successful_import_still_reported(self):
        self._steps_day(0)
        self._run(type_results={"steps": {"created": 3, "updated": 0, "skipped": 0, "failed": 0}})
        st = build_health_sync_status(self.user, now=self.now)
        steps = self._type(st, "steps")
        self.assertEqual(steps["status"], "healthy")
        self.assertEqual(steps["source_activity"], "recent")
        self.assertTrue(any(x["key"] == "steps" for x in st["last_sync_summary"]["imported"]))
        self.assertEqual(st["sync_path"]["status"], "ok")
        self.assertEqual(st["overall_health"]["status"], "healthy")

    def test_10b_never_synced_account_is_setup_not_broken(self):
        st = build_health_sync_status(self.user, now=self.now)
        self.assertEqual(st["overall_health"]["status"], "setup")
        self.assertEqual(st["sync_path"]["status"], "never_synced")
        self.assertEqual(st["issues"], [])
