# ==============================================================================
# File: apps/health/tests/test_sleep_truth_lineage.py
# Description: Layer 1 Canonical Sleep Truth lineage. A known Apple-Health night
#   must propagate to EVERY downstream consumer as the SAME value, or via an
#   explicitly-documented deterministic transformation — no consumer may silently
#   change it. Origin: Apple Health showed a night as 6 hr 9 min while WLJ reported
#   4.8 hr, because the SAE picked a record non-deterministically and read the
#   wrong duration field (time in bed, not time asleep).
# ==============================================================================
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.utils import get_user_today
from apps.health.models import SleepEntry
from apps.health.services import sleep_queries as sq

User = get_user_model()


class SleepTruthLineageTests(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="sleep@test.com", password="pw12345!")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        p = self.user.preferences
        p.has_completed_onboarding = True
        p.timezone = "America/New_York"
        p.save()
        self.today = get_user_today(self.user)
        self.night = self.today - timedelta(days=1)   # "last night"

    def _sleep(self, sleep_date, *, in_bed, asleep=None, source="apple_health",
               quality_score=None, sync_id=""):
        bedtime = timezone.make_aware(
            datetime.combine(sleep_date, time(22, 0)) - timedelta(days=1))
        return SleepEntry.objects.create(
            user=self.user, sleep_date=sleep_date, bedtime=bedtime,
            wake_time=bedtime + timedelta(minutes=in_bed),
            total_duration_minutes=in_bed, asleep_duration_minutes=asleep,
            source=source, quality_score=quality_score, sync_id=sync_id)

    # ── Transformation #1 — canonical metric is TIME ASLEEP (Apple's headline) ──

    def test_canonical_duration_is_time_asleep_not_time_in_bed(self):
        # Apple: 6 hr 9 min asleep (369) within 6 hr 15 min in bed (375).
        self._sleep(self.night, in_bed=375, asleep=369)
        ln = sq.last_night(self.user)
        self.assertEqual(ln["minutes"], 369)                 # asleep, NOT 375
        self.assertEqual(ln["asleep_minutes"], 369)
        self.assertEqual(ln["in_bed_minutes"], 375)
        self.assertAlmostEqual(ln["hours"], 6.2, delta=0.15)  # ~6 hr 9 min
        self.assertEqual(ln["date"], self.night)
        self.assertEqual(ln["freshness"], "current")

    def test_falls_back_to_in_bed_when_asleep_absent(self):
        # Manual / legacy rows without asleep → documented fallback to in-bed.
        self._sleep(self.night, in_bed=360, asleep=None, source="manual")
        self.assertEqual(sq.last_night(self.user)["minutes"], 360)

    # ── Transformation #2 — deterministic authoritative record ─────────────────

    def test_the_production_case_authoritative_record_not_arbitrary(self):
        # The reported divergence: two records for the SAME night — the Apple
        # full-night (6 hr 9 min asleep = 369) AND a partial/manual record (288 =
        # 4.8 hr). A non-deterministic `.first()` could pick the 288 one → 4.8 hr.
        # The canonical accessor deterministically picks the authoritative Apple
        # record → 6.1 hr. Same night → same record for everyone.
        self._sleep(self.night, in_bed=300, asleep=288, source="manual",
                    sync_id="manual-1")
        self._sleep(self.night, in_bed=375, asleep=369, source="apple_health",
                    sync_id="ah-1")
        ln = sq.last_night(self.user)
        self.assertEqual(ln["record_count"], 2)
        self.assertEqual(ln["source"], "apple_health")
        self.assertEqual(ln["minutes"], 369)                 # NOT 288 (4.8 hr)
        self.assertNotAlmostEqual(ln["hours"], 4.8, delta=0.2)

    def test_no_sleep_data_returns_none(self):
        self.assertIsNone(sq.last_night(self.user))
        self.assertIsNone(sq.recent_average_hours(self.user))

    # ── Recent average uses the SAME truth (one record per night) ──────────────

    def test_recent_average_dedupes_by_night_and_uses_asleep(self):
        for i in range(3):
            d = self.today - timedelta(days=i + 1)
            self._sleep(d, in_bed=375, asleep=360, source="apple_health",
                        sync_id=f"ah-{i}")
            # a duplicate lower manual record for the same night must NOT drag the
            # average down (dedup by night, authoritative record wins).
            self._sleep(d, in_bed=200, asleep=180, source="manual",
                        sync_id=f"m-{i}")
        self.assertEqual(sq.recent_average_hours(self.user), 6.0)  # 360/60, not 180

    # ── Lineage: the SAE consumer observes the canonical truth ─────────────────

    def test_sae_health_state_matches_canonical_last_night(self):
        # The exact production shape: an Apple full-night + a partial record.
        self._sleep(self.night, in_bed=300, asleep=288, source="manual", sync_id="m")
        self._sleep(self.night, in_bed=375, asleep=369, source="apple_health", sync_id="a")
        from apps.core.ai_state.state_builder import build_health_state
        state = build_health_state(self.user)
        canonical = sq.last_night(self.user)
        # Beth/dashboard read sleep_last_night_hours from the SAE — it MUST equal
        # the canonical value (no silent divergence), and NOT the 4.8 hr partial.
        self.assertEqual(state["sleep_last_night_hours"], canonical["hours"])
        self.assertNotAlmostEqual(state["sleep_last_night_hours"], 4.8, delta=0.2)
