"""Tests for Beth Status Renderer — deterministic response contract.

Validates:
1. Status query detection (match + exclusion)
2. Response structure (3 sections: STATE, COMPLETED, NEXT)
3. No coaching/explanation language
4. Remaining items from execution truth
5. Completed items section
6. Next action from decision engine
7. Edge cases (nothing left, only time-based items)
8. Micro labels (time, importance)
9. Time formatting
10. Domain deduplication
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai.beth_status_renderer import (
    _format_micro_label,
    _format_time,
    _is_covered,
    build_status_response,
    is_status_query,
)


# ---------------------------------------------------------------------------
# 1. Status query detection
# ---------------------------------------------------------------------------


class TestStatusQueryDetection(SimpleTestCase):

    def test_whats_left_today(self):
        self.assertTrue(is_status_query("what's left today"))

    def test_what_is_left_today(self):
        self.assertTrue(is_status_query("what is left today"))

    def test_what_do_i_have_left(self):
        self.assertTrue(is_status_query("what do i have left"))

    def test_whats_remaining(self):
        self.assertTrue(is_status_query("what's remaining"))

    def test_anything_left_today(self):
        self.assertTrue(is_status_query("anything left today"))

    def test_where_do_i_stand(self):
        self.assertTrue(is_status_query("where do i stand today"))

    def test_todays_status(self):
        self.assertTrue(is_status_query("today's status"))

    def test_give_me_my_status(self):
        self.assertTrue(is_status_query("give me my status"))

    def test_what_still_needs_to_be_done(self):
        self.assertTrue(is_status_query("what still needs to be done today"))

    def test_status_for_today(self):
        self.assertTrue(is_status_query("status for today"))

    # Exclusions — should NOT match
    def test_coaching_excluded(self):
        self.assertFalse(is_status_query("should i work out today"))

    def test_planning_excluded(self):
        self.assertFalse(is_status_query("help me plan my day"))

    def test_reflection_excluded(self):
        self.assertFalse(is_status_query("why did i miss my workout"))

    def test_advice_excluded(self):
        self.assertFalse(is_status_query("can you suggest what to do"))

    def test_random_message_excluded(self):
        self.assertFalse(is_status_query("good morning"))

    def test_logging_excluded(self):
        self.assertFalse(is_status_query("log my weight at 300"))


# ---------------------------------------------------------------------------
# 2. Response structure
# ---------------------------------------------------------------------------


class TestResponseStructure(SimpleTestCase):

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_has_three_sections(self, mock_exec, mock_facts):
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": True, "bible_expected": True,
                "workout_done": False, "workout_expected": True,
                "journal_done": False, "journal_expected": True,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Prayer. Then move to Workout.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Section 1: STATE
        self.assertIn("Here's what's left today:", response)
        # Section 2: COMPLETED
        self.assertIn("Completed:", response)
        # Section 3: NEXT
        self.assertIn("Next:", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_completed_section_omitted_when_empty(self, mock_exec, mock_facts):
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": True,
                "workout_done": False, "workout_expected": True,
                "journal_done": False, "journal_expected": True,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Prayer.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertNotIn("Completed:", response)


# ---------------------------------------------------------------------------
# 3. No coaching/explanation language
# ---------------------------------------------------------------------------


class TestNoCoachingLanguage(SimpleTestCase):

    PROHIBITED = [
        "focus on",
        "you should",
        "great job",
        "keep it up",
        "well done",
        "nice work",
        "i recommend",
        "consider",
        "remember to",
        "don't forget",
        "tip:",
        "good luck",
        "you've got this",
        "proud of you",
    ]

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_no_prohibited_language(self, mock_exec, mock_facts):
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": True, "prayer_expected": True,
                "bible_done": False, "bible_expected": True,
                "workout_done": False, "workout_expected": True,
                "journal_done": True, "journal_expected": True,
                "routine_done": 2, "routine_total": 5,
                "tasks_done": 3,
            },
            "next_action": "Start with Bible Reading.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        response_lower = response.lower()
        for phrase in self.PROHIBITED:
            self.assertNotIn(
                phrase, response_lower,
                f"Prohibited coaching phrase found: {phrase!r}",
            )


# ---------------------------------------------------------------------------
# 4. Remaining items
# ---------------------------------------------------------------------------


class TestRemainingItems(SimpleTestCase):

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_remaining_domain_items_listed(self, mock_exec, mock_facts):
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": True,
                "workout_done": False, "workout_expected": True,
                "journal_done": False, "journal_expected": True,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Prayer.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn("• Prayer", response)
        self.assertIn("• Bible Reading", response)
        self.assertIn("• Workout", response)
        self.assertIn("• Journal", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_not_expected_items_excluded(self, mock_exec, mock_facts):
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Prayer.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn("• Prayer", response)
        self.assertNotIn("Bible Reading", response)
        self.assertNotIn("Workout", response)
        self.assertNotIn("Journal", response)


# ---------------------------------------------------------------------------
# 5. Completed items
# ---------------------------------------------------------------------------


class TestCompletedItems(SimpleTestCase):

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_completed_items_shown(self, mock_exec, mock_facts):
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": True, "prayer_expected": True,
                "bible_done": True, "bible_expected": True,
                "workout_done": False, "workout_expected": True,
                "journal_done": False, "journal_expected": True,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Workout.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn("Completed:", response)
        self.assertIn("Prayer", response)
        self.assertIn("Bible Reading", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_completed_uses_bullet_format(self, mock_exec, mock_facts):
        """Completed section must use bullet-per-line, not inline."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": True, "prayer_expected": True,
                "bible_done": True, "bible_expected": True,
                "workout_done": False, "workout_expected": True,
                "journal_done": False, "journal_expected": True,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Workout.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Each completed item must be on its own line with bullet
        self.assertIn("Completed:\n• Prayer\n• Bible Reading", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_completed_not_inline(self, mock_exec, mock_facts):
        """Completed items must NOT be comma-separated or inline."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": True, "prayer_expected": True,
                "bible_done": True, "bible_expected": True,
                "workout_done": False, "workout_expected": True,
                "journal_done": False, "journal_expected": True,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Workout.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Must NOT have inline bullet separation
        self.assertNotIn("• Prayer • Bible", response)
        self.assertNotIn("Prayer, Bible", response)


# ---------------------------------------------------------------------------
# 6. Next action
# ---------------------------------------------------------------------------


class TestNextAction(SimpleTestCase):

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_next_action_included(self, mock_exec, mock_facts):
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Prayer.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn("Next: Start with Prayer.", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_next_action_not_modified(self, mock_exec, mock_facts):
        """Next action must be passed through verbatim."""
        next_text = "Start with Spay Weeds. Then move to Shower."
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": next_text,
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn(f"Next: {next_text}", response)


# ---------------------------------------------------------------------------
# 7. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases(SimpleTestCase):

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_nothing_left(self, mock_exec, mock_facts):
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": True, "prayer_expected": True,
                "bible_done": True, "bible_expected": True,
                "workout_done": True, "workout_expected": True,
                "journal_done": True, "journal_expected": True,
                "routine_done": 5, "routine_total": 5,
                "tasks_done": 3,
            },
            "next_action": "All items are complete — nothing pending.",
        }
        mock_exec.return_value = {
            "items": [
                {"title": "Prayer Time", "completed_today": True, "is_actionable": False},
                {"title": "Bible Reading", "completed_today": True, "is_actionable": False},
            ],
            "summaries": {"domains": {}, "expected": {}},
        }

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn("You've completed everything for today.", response)
        self.assertIn("Next: You're all set. No remaining actions.", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_only_time_based_items(self, mock_exec, mock_facts):
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": True, "prayer_expected": True,
                "bible_done": True, "bible_expected": True,
                "workout_done": True, "workout_expected": True,
                "journal_done": True, "journal_expected": True,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Be ready for medications at 10:00 PM.",
        }
        mock_exec.return_value = {
            "items": [
                {
                    "title": "Medications",
                    "completed_today": False,
                    "is_actionable": True,
                    "scheduled_time": "22:00",
                    "importance": "high",
                    "time_status": "pending",
                },
            ],
            "summaries": {"domains": {}, "expected": {}},
        }

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn("Medications", response)
        self.assertIn("10:00 PM", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_execution_failure_fallback(self, mock_exec, mock_facts):
        """If today_execution fails, should still produce a response from raw facts."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Prayer.",
        }
        mock_exec.side_effect = Exception("DB down")

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn("• Prayer", response)
        self.assertIn("Next: Start with Prayer.", response)


# ---------------------------------------------------------------------------
# 8. Micro labels
# ---------------------------------------------------------------------------


class TestMicroLabels(SimpleTestCase):

    def test_time_label(self):
        item = {"scheduled_time": "22:00"}
        label = _format_micro_label(item)
        self.assertIn("10:00 PM", label)
        self.assertIn("time-critical", label)

    def test_importance_label(self):
        item = {"importance": "high"}
        label = _format_micro_label(item)
        self.assertIn("important", label)

    def test_overdue_label(self):
        item = {"time_status": "overdue"}
        label = _format_micro_label(item)
        self.assertIn("overdue", label)

    def test_no_label(self):
        item = {"importance": "normal"}
        label = _format_micro_label(item)
        self.assertEqual(label, "")

    def test_combined_labels(self):
        item = {"scheduled_time": "14:30", "importance": "high"}
        label = _format_micro_label(item)
        self.assertIn("2:30 PM", label)
        self.assertIn("important", label)


# ---------------------------------------------------------------------------
# 9. Time formatting
# ---------------------------------------------------------------------------


class TestTimeFormatting(SimpleTestCase):

    def test_morning(self):
        self.assertEqual(_format_time("09:00"), "9:00 AM")

    def test_afternoon(self):
        self.assertEqual(_format_time("14:30"), "2:30 PM")

    def test_midnight(self):
        self.assertEqual(_format_time("00:00"), "12:00 AM")

    def test_noon(self):
        self.assertEqual(_format_time("12:00"), "12:00 PM")

    def test_evening(self):
        self.assertEqual(_format_time("22:00"), "10:00 PM")

    def test_with_minutes(self):
        self.assertEqual(_format_time("08:15"), "8:15 AM")

    def test_always_includes_minutes(self):
        """All times must include minutes, even on the hour."""
        self.assertIn(":00", _format_time("09:00"))
        self.assertIn(":00", _format_time("22:00"))
        self.assertIn(":00", _format_time("12:00"))
        self.assertIn(":00", _format_time("00:00"))


# ---------------------------------------------------------------------------
# 10. Domain deduplication
# ---------------------------------------------------------------------------


class TestDomainDeduplication(SimpleTestCase):

    def test_prayer_covered_by_routine(self):
        existing = {"prayer time", "bible reading", "shower"}
        self.assertTrue(_is_covered(existing, "prayer"))

    def test_workout_not_covered(self):
        existing = {"prayer time", "shower"}
        self.assertFalse(_is_covered(existing, "workout"))

    def test_bible_covered(self):
        existing = {"bible reading"}
        self.assertTrue(_is_covered(existing, "bible"))

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_no_double_counting(self, mock_exec, mock_facts):
        """If routine has 'Prayer Time', don't also add domain 'Prayer'."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 1,
                "tasks_done": 0,
            },
            "next_action": "Start with Prayer Time.",
        }
        mock_exec.return_value = {
            "items": [
                {
                    "title": "Prayer Time",
                    "completed_today": False,
                    "is_actionable": True,
                    "source_type": "routine",
                },
            ],
            "summaries": {"domains": {}, "expected": {}},
        }

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Should have Prayer Time from execution items
        self.assertIn("Prayer Time", response)
        # Count "Prayer" occurrences — should not have a separate "Prayer" bullet
        lines = [l.strip() for l in response.split("\n") if l.strip().startswith("•")]
        prayer_lines = [l for l in lines if "prayer" in l.lower()]
        self.assertEqual(
            len(prayer_lines), 1,
            f"Expected 1 prayer line, got {len(prayer_lines)}: {prayer_lines}",
        )


# ---------------------------------------------------------------------------
# 11. Router integration
# ---------------------------------------------------------------------------


class TestRouterIntegration(SimpleTestCase):

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_router_routes_status_query(self, mock_exec, mock_facts):
        """Status query should route through deterministic router."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Start with Prayer.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        from apps.ai.deterministic_router import classify_and_route

        user = MagicMock()
        user.id = 1
        result = classify_and_route("what's left today", user)

        self.assertTrue(result.is_terminal)
        self.assertEqual(result.route_name, "status_query")
        self.assertIn("Here's what's left today:", result.response)
        self.assertIn("Next:", result.response)

    def test_router_does_not_route_coaching(self):
        """Coaching questions should NOT trigger status route."""
        from apps.ai.deterministic_router import classify_and_route

        user = MagicMock()
        user.id = 1
        result = classify_and_route("should i focus on prayer today", user)

        self.assertNotEqual(result.route_name, "status_query")
