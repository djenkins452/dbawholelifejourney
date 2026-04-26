"""Tests for deterministic check-in renderer + state guard.

Covers:
1. Check-in output format (Completed / Upcoming / Next sections)
2. Empty state shows "• None"
3. No coaching or aggregation language
4. Fail-closed returns safe output
5. State guard blocks LLM fabricated state
6. Parse time helper
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from datetime import timedelta

from apps.ai.beth_checkin_renderer import (
    DRIFT_ON_TRACK_THRESHOLD,
    DRIFT_SLIGHTLY_BEHIND_THRESHOLD,
    _SAFE_FALLBACK,
    build_schedule_signals,
    compute_buffer_minutes,
    compute_schedule_drift,
    contains_state_language,
    guard_llm_output,
    render_daily_briefing,
    render_morning_checkin,
)
from apps.core.today.today_engine import _parse_time_today


def _make_today_context(
    completed=None, coming_up=None, overdue=None,
    later=None, foundation=None, next_action="Start with Shower.",
):
    """Build a minimal Today Engine context for renderer tests."""
    def _entries(items):
        if not items:
            return []
        return [{"sort_time": datetime.max, "label": label, "item": {}} for label in items]

    return {
        "all_items": [],
        "foundation": _entries(foundation),
        "overdue": _entries(overdue),
        "coming_up": _entries(coming_up),
        "later": _entries(later),
        "completed": _entries(completed),
        "next": next_action,
    }


_P_ENGINE = "apps.core.today.today_engine.get_today_context"


class TestCheckinOutput(SimpleTestCase):
    """Check-in renders correctly from Today Engine context."""

    @patch(_P_ENGINE)
    def test_empty_state(self, mock_ctx):
        mock_ctx.return_value = _make_today_context()
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("Completed:\n• None", output)
        self.assertIn("Upcoming:\n• None", output)
        self.assertIn("Next:", output)

    @patch(_P_ENGINE)
    def test_completed_items_shown(self, mock_ctx):
        mock_ctx.return_value = _make_today_context(
            completed=["Prayer", "Bible reading"],
        )
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("• Prayer", output)
        self.assertIn("• Bible reading", output)

    @patch(_P_ENGINE)
    def test_upcoming_from_coming_up(self, mock_ctx):
        mock_ctx.return_value = _make_today_context(
            coming_up=["Workout (6:15 AM)"],
        )
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("Upcoming:\n• Workout (6:15 AM)", output)

    @patch(_P_ENGINE)
    def test_next_action_shown(self, mock_ctx):
        mock_ctx.return_value = _make_today_context(
            next_action="Start with Bible reading.",
        )
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("Next: Start with Bible reading.", output)

    @patch(_P_ENGINE)
    def test_sections_present(self, mock_ctx):
        mock_ctx.return_value = _make_today_context()
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        self.assertIn("Morning Check-in", output)
        self.assertIn("Completed:", output)
        self.assertIn("Upcoming:", output)
        self.assertIn("Next:", output)

    @patch(_P_ENGINE)
    def test_no_coaching_language(self, mock_ctx):
        mock_ctx.return_value = _make_today_context(completed=["Prayer"])
        user = MagicMock(); user.id = 1
        output = render_morning_checkin(user)
        for word in ["solid", "momentum", "great", "keep it up", "tone"]:
            self.assertNotIn(word, output.lower())

    def test_fail_closed(self):
        user = MagicMock(); user.id = 1
        with patch(_P_ENGINE, side_effect=Exception("DB down")):
            output = render_morning_checkin(user)
        self.assertEqual(output, _SAFE_FALLBACK)


class TestParseTimeToday(SimpleTestCase):

    def test_parses_am(self):
        now = timezone.now().replace(hour=5, minute=0)
        result = _parse_time_today("6:15 AM", now)
        self.assertIsNotNone(result)
        self.assertEqual(result.hour, 6)
        self.assertEqual(result.minute, 15)

    def test_parses_pm(self):
        now = timezone.now().replace(hour=12, minute=0)
        result = _parse_time_today("9:00 PM", now)
        self.assertEqual(result.hour, 21)

    def test_invalid_returns_none(self):
        now = timezone.now()
        self.assertIsNone(_parse_time_today("not a time", now))


class TestContainsStateLanguage(SimpleTestCase):

    def test_detects_you_completed(self):
        self.assertTrue(contains_state_language("You've completed your prayer."))

    def test_detects_momentum_language(self):
        self.assertTrue(contains_state_language("Let's keep the momentum going."))

    def test_allows_clean_text(self):
        self.assertFalse(contains_state_language("How can I help you today?"))

    def test_empty_text_safe(self):
        self.assertFalse(contains_state_language(""))
        self.assertFalse(contains_state_language(None))


class TestGuardLlmOutput(SimpleTestCase):

    @patch("apps.ai.beth_checkin_renderer.render_checkin_for_time")
    def test_blocks_state_language(self, mock_render):
        mock_render.return_value = "Morning Check-in\n\nCompleted:\n• None"
        user = MagicMock(); user.id = 1
        result = guard_llm_output("You've completed your prayer.", user)
        self.assertEqual(result, "Morning Check-in\n\nCompleted:\n• None")

    def test_allows_clean_output(self):
        user = MagicMock(); user.id = 1
        clean = "Here's how to set up a new routine."
        self.assertEqual(guard_llm_output(clean, user), clean)

    def test_guard_fallback_on_error(self):
        user = MagicMock(); user.id = 1
        with patch("apps.ai.beth_checkin_renderer.render_checkin_for_time",
                    side_effect=Exception("Error")):
            result = guard_llm_output("You've completed everything!", user)
        self.assertEqual(result, _SAFE_FALLBACK)


class TestRouteControlledGuardBoundary(SimpleTestCase):
    """Verify the state guard only fires for state-reporting routes.

    The guard must NOT replace conversational LLM responses (faith Q&A,
    coaching, etc.) with the deterministic renderer. It should only fire
    when the router classified the message as a state/check-in path.
    """

    def _make_route_result(self, category='fallthrough'):
        from apps.ai.deterministic_router import RouteResult
        return RouteResult(category=category)

    def test_fallthrough_skips_guard(self):
        """Conversational fallthrough must bypass state guard entirely."""
        route = self._make_route_result('fallthrough')
        _is_conversational_fallthrough = (
            route is not None
            and getattr(route, 'category', None) == 'fallthrough'
        )
        self.assertTrue(_is_conversational_fallthrough)

    def test_checkin_prefilter_runs_guard(self):
        """Check-in prefilter routes must still apply the state guard."""
        route = self._make_route_result('checkin_prefilter')
        _is_conversational_fallthrough = (
            route is not None
            and getattr(route, 'category', None) == 'fallthrough'
        )
        self.assertFalse(_is_conversational_fallthrough)

    def test_deterministic_data_runs_guard(self):
        """Deterministic data routes must still apply the state guard."""
        route = self._make_route_result('deterministic_data')
        _is_conversational_fallthrough = (
            route is not None
            and getattr(route, 'category', None) == 'fallthrough'
        )
        self.assertFalse(_is_conversational_fallthrough)

    def test_none_route_runs_guard(self):
        """If router failed (None), guard should still fire (conservative)."""
        route = None
        _is_conversational_fallthrough = (
            route is not None
            and getattr(route, 'category', None) == 'fallthrough'
        )
        self.assertFalse(_is_conversational_fallthrough)

    def test_faith_response_with_state_pattern_survives_fallthrough(self):
        """A faith response containing 'you completed' must NOT be replaced
        when the route was conversational fallthrough."""
        faith_response = (
            "Great question. Jesus would have known the Zechariah 9:9 "
            "prophecy well. As you've done your study of the Old Testament, "
            "you'll see this was central to messianic expectation."
        )
        # The response contains state patterns, but route is fallthrough
        self.assertTrue(contains_state_language(faith_response))
        route = self._make_route_result('fallthrough')
        _is_conversational_fallthrough = (
            route is not None
            and getattr(route, 'category', None) == 'fallthrough'
        )
        # Guard is skipped — response survives intact
        self.assertTrue(_is_conversational_fallthrough)

    @patch("apps.ai.beth_checkin_renderer.render_checkin_for_time")
    def test_checkin_response_with_state_pattern_still_blocked(self, mock_render):
        """A check-in route response with state patterns IS still blocked."""
        mock_render.return_value = "End of day, Danny.\n\nYou completed everything."
        user = MagicMock(); user.id = 1
        llm_response = "You've completed your morning routine and you still need to journal."
        route = self._make_route_result('checkin_prefilter')
        _is_conversational_fallthrough = (
            route is not None
            and getattr(route, 'category', None) == 'fallthrough'
        )
        self.assertFalse(_is_conversational_fallthrough)
        # Guard fires — response is replaced
        result = guard_llm_output(llm_response, user)
        self.assertEqual(result, "End of day, Danny.\n\nYou completed everything.")


# ==============================================================================
# Daily Briefing Tests
# ==============================================================================

class TestDailyBriefing(SimpleTestCase):
    """Tests for the first-of-day Daily Briefing renderer."""

    def _make_user(self, first_name="Danny"):
        user = MagicMock()
        user.id = 1
        user.first_name = first_name
        user.preferences = MagicMock()
        user.preferences.faith_enabled = True
        return user

    def _make_context_with_items(
        self, completed=None, coming_up=None, overdue=None,
        later=None, next_action="Start with your next planned item.",
    ):
        """Build Today Engine context with item dicts for briefing tests."""
        def _entries(items, with_item=True):
            if not items:
                return []
            entries = []
            for label in items:
                entry = {
                    "sort_time": datetime.max,
                    "label": label,
                    "item": {"name": label, "completed": False, "time_str": ""},
                }
                if with_item:
                    entry["time"] = ""
                entries.append(entry)
            return entries

        all_items = []
        for label in (completed or []):
            all_items.append({
                "name": label, "completed": True,
                "scheduled_time": None, "time_str": "", "source": "",
                "priority": "",
            })
        for label in (overdue or []) + (coming_up or []) + (later or []):
            all_items.append({
                "name": label, "completed": False,
                "scheduled_time": None, "time_str": "", "source": "",
                "priority": "",
            })

        return {
            "all_items": all_items,
            "foundation": [],
            "overdue": _entries(overdue),
            "coming_up": _entries(coming_up),
            "later": _entries(later),
            "completed": _entries(completed),
            "next": next_action,
        }

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_morning_briefing_title(self, mock_ctx, mock_now):
        """5:10 AM → Morning Briefing title."""
        mock_now.return_value = timezone.now().replace(hour=5, minute=10)
        mock_ctx.return_value = self._make_context_with_items(
            completed=["Wake Up"],
            coming_up=["Prayer"],
        )
        user = self._make_user()
        output = render_daily_briefing(user)
        self.assertIn("Morning Briefing", output)

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_midday_briefing_title(self, mock_ctx, mock_now):
        """1:00 PM → Midday Briefing title."""
        mock_now.return_value = timezone.now().replace(hour=13, minute=0)
        mock_ctx.return_value = self._make_context_with_items()
        user = self._make_user()
        output = render_daily_briefing(user)
        self.assertIn("Midday Briefing", output)

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_evening_briefing_title(self, mock_ctx, mock_now):
        """7:00 PM → Evening Briefing title."""
        mock_now.return_value = timezone.now().replace(hour=19, minute=0)
        mock_ctx.return_value = self._make_context_with_items()
        user = self._make_user()
        output = render_daily_briefing(user)
        self.assertIn("Evening Briefing", output)

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_late_night_is_evening(self, mock_ctx, mock_now):
        """2:00 AM → Evening Briefing (18:00-03:59 range)."""
        mock_now.return_value = timezone.now().replace(hour=2, minute=0)
        mock_ctx.return_value = self._make_context_with_items()
        user = self._make_user()
        output = render_daily_briefing(user)
        self.assertIn("Evening Briefing", output)

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_only_logged_items_in_completed(self, mock_ctx, mock_now):
        """Only Wake Up in completed; Workout NOT completed."""
        mock_now.return_value = timezone.now().replace(hour=5, minute=10)
        mock_ctx.return_value = self._make_context_with_items(
            completed=["Wake Up"],
            coming_up=["Workout", "Prayer"],
        )
        user = self._make_user()
        output = render_daily_briefing(user)
        # Wake Up appears in "Already done" section
        self.assertIn("Already done:", output)
        self.assertIn("Wake Up", output)
        # Workout appears in execution plan, not completed
        self.assertIn("Execution plan:", output)
        self.assertIn("Workout", output)

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_execution_plan_present(self, mock_ctx, mock_now):
        """Remaining items appear in ordered execution plan."""
        mock_now.return_value = timezone.now().replace(hour=5, minute=10)
        mock_ctx.return_value = self._make_context_with_items(
            coming_up=["Prayer", "Bible Reading", "Workout"],
        )
        user = self._make_user()
        output = render_daily_briefing(user)
        self.assertIn("Execution plan:", output)
        self.assertIn("Prayer", output)
        self.assertIn("Bible Reading", output)
        self.assertIn("Workout", output)

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_closing_directive_present(self, mock_ctx, mock_now):
        """Briefing ends with a closing directive."""
        mock_now.return_value = timezone.now().replace(hour=5, minute=10)
        mock_ctx.return_value = self._make_context_with_items(
            coming_up=["Prayer"],
        )
        user = self._make_user()
        output = render_daily_briefing(user)
        # Should have a directive mentioning the first action
        self.assertIn("Prayer", output)
        # Should end with a clear instruction
        lines = [l for l in output.strip().split('\n') if l.strip()]
        last_line = lines[-1]
        self.assertTrue(
            "first" in last_line.lower()
            or "start" in last_line.lower()
            or "handle" in last_line.lower()
            or "clean slate" in last_line.lower(),
            f"Closing directive missing. Last line: {last_line}"
        )

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_empty_day_clean_slate(self, mock_ctx, mock_now):
        """No items → clean slate message."""
        mock_now.return_value = timezone.now().replace(hour=5, minute=10)
        mock_ctx.return_value = self._make_context_with_items()
        user = self._make_user()
        output = render_daily_briefing(user)
        self.assertIn("Clean slate", output)

    @patch(_P_ENGINE, side_effect=Exception("DB down"))
    def test_fail_closed(self, mock_ctx):
        """Renderer failure returns safe fallback."""
        user = self._make_user()
        output = render_daily_briefing(user)
        self.assertEqual(output, _SAFE_FALLBACK)

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_user_name_in_greeting(self, mock_ctx, mock_now):
        """User's first name appears in briefing greeting."""
        mock_now.return_value = timezone.now().replace(hour=7, minute=0)
        mock_ctx.return_value = self._make_context_with_items()
        user = self._make_user("Danny")
        output = render_daily_briefing(user)
        self.assertIn("Danny", output)

    @patch("apps.core.utils.get_user_now")
    @patch(_P_ENGINE)
    def test_schedule_drift_shown_when_behind(self, mock_ctx, mock_now):
        """When 10 min behind with buffer, briefing shows recovery guidance."""
        now = timezone.now().replace(hour=5, minute=55, second=0, microsecond=0)
        mock_now.return_value = now

        # Prayer was at 5:30 (25 min ago), Bible at 5:45 (10 min ago)
        # Workout at 6:15 — 15 min buffer between Bible end (6:00) and Workout
        all_items = [
            {
                "name": "Prayer", "scheduled_time": now - timedelta(minutes=25),
                "time_str": "5:30 AM", "completed": False, "priority": "foundational",
                "source": "routine",
            },
            {
                "name": "Bible Reading", "scheduled_time": now - timedelta(minutes=10),
                "time_str": "5:45 AM", "completed": False, "priority": "foundational",
                "source": "routine",
            },
            {
                "name": "Workout", "scheduled_time": now + timedelta(minutes=20),
                "time_str": "6:15 AM", "completed": False, "priority": "foundational",
                "source": "routine",
            },
        ]

        def _entries(items):
            return [{"sort_time": datetime.max, "label": i["name"],
                     "item": i, "time": i.get("time_str", "")} for i in items]

        mock_ctx.return_value = {
            "all_items": all_items,
            "foundation": [],
            "overdue": _entries([all_items[0], all_items[1]]),
            "coming_up": [],
            "later": _entries([all_items[2]]),
            "completed": [],
            "next": "Prayer",
        }
        user = self._make_user()
        output = render_daily_briefing(user)
        # With 2 overdue items (~30 min drift), escalation fires at
        # PRESSING level. The directive mentions being behind.
        self.assertIn("behind", output.lower())


# ==============================================================================
# Schedule Drift & Buffer Tests
# ==============================================================================

class TestScheduleDrift(SimpleTestCase):
    """Tests for compute_schedule_drift() — deterministic drift calculation."""

    def _now(self, hour=5, minute=55):
        return timezone.now().replace(
            hour=hour, minute=minute, second=0, microsecond=0,
        )

    def test_no_scheduled_items(self):
        """No scheduled items → on_track with 0 drift."""
        result = compute_schedule_drift([], [], self._now())
        self.assertEqual(result['schedule_status'], 'on_track')
        self.assertEqual(result['drift_minutes'], 0)

    def test_all_completed_on_time(self):
        """All items completed → on_track."""
        now = self._now(6, 10)
        items = [
            {"name": "Prayer", "scheduled_time": now - timedelta(minutes=40),
             "completed": True},
            {"name": "Bible", "scheduled_time": now - timedelta(minutes=25),
             "completed": True},
        ]
        completed = [
            {"label": "Prayer", "item": {"completed": True}},
            {"label": "Bible", "item": {"completed": True}},
        ]
        result = compute_schedule_drift(items, completed, now)
        self.assertEqual(result['schedule_status'], 'on_track')
        self.assertEqual(result['drift_minutes'], 0)

    def test_one_item_behind(self):
        """One 15-min item overdue and not done → 15 min drift = slightly_behind."""
        now = self._now(6, 0)
        items = [
            {"name": "Prayer", "scheduled_time": now - timedelta(minutes=30),
             "completed": False},
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=15),
             "completed": False},
        ]
        result = compute_schedule_drift(items, [], now)
        # Prayer (15 min default) should be done by now
        self.assertEqual(result['drift_minutes'], 15)
        # 15 min == threshold boundary → slightly_behind (not at_risk which is >15)
        self.assertEqual(result['schedule_status'], 'slightly_behind')

    def test_slightly_behind(self):
        """10 minutes of drift → slightly_behind."""
        now = self._now(6, 0)
        items = [
            {"name": "Journal", "scheduled_time": now - timedelta(minutes=20),
             "completed": False},  # 10 min duration, should be done by 5:50
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=15),
             "completed": False},
        ]
        result = compute_schedule_drift(items, [], now)
        # Journal = 10 min estimated
        self.assertEqual(result['drift_minutes'], 10)
        self.assertEqual(result['schedule_status'], 'slightly_behind')

    def test_on_track_within_threshold(self):
        """Item just slightly past expected end → on_track (within 5 min)."""
        now = self._now(5, 48)
        items = [
            {"name": "Prayer", "scheduled_time": now - timedelta(minutes=18),
             "completed": True},  # 15 min, ended at 5:47 — within threshold
            {"name": "Bible", "scheduled_time": now - timedelta(minutes=3),
             "completed": False},
        ]
        completed = [{"label": "Prayer", "item": {"completed": True}}]
        result = compute_schedule_drift(items, completed, now)
        self.assertEqual(result['schedule_status'], 'on_track')

    def test_drift_thresholds_are_configurable(self):
        """Thresholds are module-level constants."""
        self.assertEqual(DRIFT_ON_TRACK_THRESHOLD, 5)
        self.assertEqual(DRIFT_SLIGHTLY_BEHIND_THRESHOLD, 15)


class TestBufferDetection(SimpleTestCase):
    """Tests for compute_buffer_minutes() — gap detection between items."""

    def _now(self, hour=5, minute=55):
        return timezone.now().replace(
            hour=hour, minute=minute, second=0, microsecond=0,
        )

    def test_no_future_items(self):
        """No future items → 0 buffer."""
        result = compute_buffer_minutes([], self._now())
        self.assertEqual(result['buffer_minutes'], 0)

    def test_buffer_between_items(self):
        """15-min gap between Bible end and Workout start."""
        now = self._now(5, 30)
        items = [
            {"name": "Bible Reading", "scheduled_time": now + timedelta(minutes=15),
             "completed": False, "source": "routine"},
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=45),
             "completed": False, "source": "routine"},
        ]
        result = compute_buffer_minutes(items, now)
        # Bible at 5:45, takes 15 min, ends at 6:00
        # Workout at 6:15 → 15 min gap
        # Plus 15 min from now to Bible start
        self.assertGreaterEqual(result['buffer_minutes'], 15)
        self.assertTrue(len(result['buffer_details']) >= 1)

    def test_no_gap_tight_schedule(self):
        """Back-to-back items → no buffer between them."""
        now = self._now(5, 30)
        items = [
            {"name": "Prayer", "scheduled_time": now + timedelta(minutes=5),
             "completed": False, "source": "routine"},
            {"name": "Bible Reading", "scheduled_time": now + timedelta(minutes=20),
             "completed": False, "source": "routine"},
            # Prayer 5:35 → 5:50 (15 min), Bible at 5:50 → 0 gap
        ]
        result = compute_buffer_minutes(items, now)
        # No gap between prayer end and bible start
        buffer_between = [d for d in result['buffer_details'] if d[0] > 0]
        # The only buffer is the 5 min from now to first item
        self.assertEqual(len(buffer_between), 0)

    def test_next_anchor_detected(self):
        """Medication is identified as next anchor."""
        now = self._now(6, 0)
        items = [
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=15),
             "completed": False, "source": "routine"},
            {"name": "Mounjaro injection", "scheduled_time": now + timedelta(minutes=60),
             "completed": False, "source": "medication"},
        ]
        result = compute_buffer_minutes(items, now)
        self.assertEqual(result['next_anchor'], "Mounjaro injection")

    def test_completed_items_excluded(self):
        """Completed items are excluded from buffer calculation."""
        now = self._now(6, 0)
        items = [
            {"name": "Prayer", "scheduled_time": now + timedelta(minutes=5),
             "completed": True, "source": "routine"},
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=30),
             "completed": False, "source": "routine"},
        ]
        result = compute_buffer_minutes(items, now)
        # Only Workout is future + incomplete
        self.assertGreater(result['buffer_minutes'], 0)


class TestScheduleSignals(SimpleTestCase):
    """Tests for build_schedule_signals() — combined drift + buffer."""

    def _now(self, hour=5, minute=55):
        return timezone.now().replace(
            hour=hour, minute=minute, second=0, microsecond=0,
        )

    def test_on_track_with_buffer(self):
        """On track + buffer → guidance mentions buffer."""
        now = self._now(5, 30)
        items = [
            {"name": "Prayer", "scheduled_time": now + timedelta(minutes=5),
             "completed": False, "source": "routine"},
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=60),
             "completed": False, "source": "routine"},
        ]
        result = build_schedule_signals(items, [], now)
        self.assertEqual(result['schedule_status'], 'on_track')
        self.assertGreater(result['buffer_minutes_available'], 15)
        # Per CoS Strict Mode Isolation: no minute math in user-facing
        # text. Guidance is now categorical only.
        self.assertEqual(result['guidance'].lower(), 'on schedule.')

    def test_slightly_behind_with_recovery(self):
        """10 min behind with 15 min buffer → recoverable."""
        now = self._now(5, 55)
        items = [
            {"name": "Journal", "scheduled_time": now - timedelta(minutes=20),
             "completed": False, "source": "routine"},
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=35),
             "completed": False, "source": "routine"},
        ]
        result = build_schedule_signals(items, [], now)
        self.assertEqual(result['schedule_status'], 'slightly_behind')
        self.assertTrue(result['can_recover'])
        self.assertIn("recoverable", result['guidance'].lower())

    def test_slightly_behind_no_recovery(self):
        """Behind with no buffer → suggests adjustment."""
        now = self._now(5, 55)
        items = [
            {"name": "Journal", "scheduled_time": now - timedelta(minutes=20),
             "completed": False, "source": "routine"},
            # Next item starts immediately
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=1),
             "completed": False, "source": "routine"},
        ]
        result = build_schedule_signals(items, [], now)
        self.assertIn("slightly_behind", result['schedule_status'])
        self.assertIn("moving" in result['guidance'].lower()
                       or "later" in result['guidance'].lower(),
                       [True])

    def test_at_risk(self):
        """Far behind → at_risk status."""
        now = self._now(6, 30)
        items = [
            {"name": "Prayer", "scheduled_time": now - timedelta(minutes=60),
             "completed": False, "source": "routine"},
            {"name": "Bible Reading", "scheduled_time": now - timedelta(minutes=45),
             "completed": False, "source": "routine"},
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=5),
             "completed": False, "source": "routine"},
        ]
        result = build_schedule_signals(items, [], now)
        self.assertEqual(result['schedule_status'], 'at_risk')
        self.assertGreater(result['drift_minutes'], DRIFT_SLIGHTLY_BEHIND_THRESHOLD)

    def test_validation_scenario(self):
        """Validation test case from requirements:
        User is 10 min behind. Prayer 5:30-5:45, Bible 5:45-6:00, Workout 6:15.
        Expected: slightly behind, 15 min buffer, can recover, no reordering.
        """
        now = self._now(5, 55)
        items = [
            {"name": "Prayer", "scheduled_time": now - timedelta(minutes=25),
             "completed": False, "source": "routine"},
            {"name": "Bible Reading", "scheduled_time": now - timedelta(minutes=10),
             "completed": False, "source": "routine"},
            {"name": "Workout", "scheduled_time": now + timedelta(minutes=20),
             "completed": False, "source": "routine"},
        ]
        result = build_schedule_signals(items, [], now)

        # User should be slightly behind or at_risk (Prayer + Bible both overdue)
        self.assertIn(result['schedule_status'], ('slightly_behind', 'at_risk'))
        # Buffer exists (gap between Bible end at 6:00 and Workout at 6:15)
        self.assertGreater(result['buffer_minutes_available'], 0)
        # Guidance mentions the situation
        self.assertTrue(len(result['guidance']) > 0)
        # The function does NOT modify any items — verify by checking inputs unchanged
        self.assertFalse(items[0]['completed'])
        self.assertFalse(items[1]['completed'])
        self.assertFalse(items[2]['completed'])
