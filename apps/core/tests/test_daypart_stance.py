# ==============================================================================
# File: apps/core/tests/test_daypart_stance.py
# Description: EXECUTIVE STANCE — the canonical situational grounding of the day
#   (apps/core/truth/daypart.py). One deterministic source maps the user's local
#   hour to a phase and the executive POSTURE it implies (plan/execute/wind_down/
#   close_out). The night 'close_out' stance is the fix for a bedtime "how am I
#   doing?" producing a morning planning narrative. Pure, clock-injectable.
# ==============================================================================
from datetime import datetime, timezone as _tz

from django.test import SimpleTestCase

from apps.core.truth import daypart as dp


class _Now:
    def __init__(self, hour):
        self.hour = hour


class _U:
    """A stand-in user; `now` is always injected so no timezone lookup happens."""


class PhaseMappingTests(SimpleTestCase):
    def test_hour_buckets_map_to_phases(self):
        cases = {
            5: dp.MORNING, 8: dp.MORNING, 10: dp.MORNING,
            11: dp.MIDDAY, 13: dp.MIDDAY, 16: dp.MIDDAY,
            17: dp.EVENING, 19: dp.EVENING, 20: dp.EVENING,
            21: dp.NIGHT, 23: dp.NIGHT, 0: dp.NIGHT, 2: dp.NIGHT, 3: dp.NIGHT,
        }
        for hour, expected in cases.items():
            self.assertEqual(dp.phase_of_day(_U(), now=_Now(hour)), expected, hour)

    def test_each_phase_has_one_stance(self):
        self.assertEqual(dp.executive_stance(_U(), now=_Now(8)), dp.PLAN)
        self.assertEqual(dp.executive_stance(_U(), now=_Now(13)), dp.EXECUTE)
        self.assertEqual(dp.executive_stance(_U(), now=_Now(19)), dp.WIND_DOWN)
        self.assertEqual(dp.executive_stance(_U(), now=_Now(23)), dp.CLOSE_OUT)

    def test_night_wraps_midnight(self):
        # The small hours are the END of the prior day, never a new morning.
        for hour in (22, 23, 0, 1, 2, 3):
            self.assertEqual(dp.executive_stance(_U(), now=_Now(hour)), dp.CLOSE_OUT, hour)


class ResolveTests(SimpleTestCase):
    def test_resolve_returns_full_situational_read(self):
        r = dp.resolve(_U(), now=_Now(22))
        self.assertEqual(r["phase"], dp.NIGHT)
        self.assertEqual(r["stance"], dp.CLOSE_OUT)
        self.assertEqual(r["hour"], 22)
        self.assertTrue(r["is_close_out"])
        self.assertIn("rest", r["posture"].lower())

    def test_close_out_posture_forbids_planning_the_day(self):
        posture = dp.resolve(_U(), now=_Now(23))["posture"].lower()
        self.assertIn("never plan the day", posture)
        self.assertIn("over", posture)                 # the day is over

    def test_morning_posture_forbids_winding_down(self):
        posture = dp.resolve(_U(), now=_Now(7))["posture"].lower()
        self.assertIn("do not", posture)
        self.assertIn("winding down", posture)

    def test_resolve_never_raises_and_defaults_to_execute(self):
        # A broken clock source degrades to a coherent EXECUTE stance, never an error.
        class Boom:
            @property
            def hour(self):
                raise RuntimeError("clock down")

        r = dp.resolve(_U(), now=Boom())
        self.assertEqual(r["stance"], dp.EXECUTE)
        self.assertFalse(r["is_close_out"])
        self.assertTrue(r["posture"])


class RealClockTests(SimpleTestCase):
    def test_uses_user_local_clock_when_now_omitted(self):
        # With now omitted it must consult get_user_now — patched here to a night hour.
        from unittest import mock
        night = datetime(2026, 7, 3, 23, 30, tzinfo=_tz.utc)
        with mock.patch("apps.core.utils.get_user_now", return_value=night):
            self.assertEqual(dp.executive_stance(_U()), dp.CLOSE_OUT)
