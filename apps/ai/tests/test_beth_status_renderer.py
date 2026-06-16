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
    _group_medication_items,
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

        # Section 1: STATE (remaining items)
        self.assertIn("Here's what's left today:", response)
        # Section 2: NEXT
        self.assertIn("Next:", response)
        # Completed section should NOT appear
        self.assertNotIn("Completed:", response)

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
    def test_completed_items_not_shown(self, mock_exec, mock_facts):
        """Status response should NOT include completed items list."""
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

        # Completed section should NOT appear — user wants remaining, not done
        self.assertNotIn("Completed:", response)
        # Remaining items and next action should still be present
        self.assertIn("Workout", response)
        self.assertIn("Next:", response)

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
            "next_action": "Next: Prayer. Do this now.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Canonical directive printed verbatim — never re-prefixed ("Next: Next:").
        self.assertIn("Next: Prayer. Do this now.", response)
        self.assertNotIn("Next: Next:", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_next_action_not_modified(self, mock_exec, mock_facts):
        """Next action must be passed through verbatim."""
        next_text = "Next: Spay Weeds. Do this now."
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

        self.assertIn(next_text, response)
        self.assertNotIn("Next: Next:", response)


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


# ---------------------------------------------------------------------------
# 12. Medication grouping — summary by window
# ---------------------------------------------------------------------------


class TestMedicationGrouping(SimpleTestCase):
    """Test _group_medication_items groups medications by window."""

    def _make_med_item(self, name, window, completed=False, status='upcoming',
                       time_status='upcoming'):
        return {
            'source_type': 'medication_dose',
            'title': name,
            'execution_group_id': window,
            'completed_today': completed,
            'completion_status': status,
            'time_status': time_status,
            'scheduled_time': '08:00',
            'is_actionable': not completed,
        }

    def test_all_completed_on_time(self):
        """All meds in a window completed → completed summary."""
        items = [
            self._make_med_item('Metformin', 'morning', completed=True, status='completed'),
            self._make_med_item('Lantus', 'morning', completed=True, status='completed'),
            self._make_med_item('Atorvastatin', 'morning', completed=True, status='completed'),
        ]
        remaining, completed = _group_medication_items(items)
        self.assertEqual(len(remaining), 0)
        self.assertEqual(len(completed), 1)
        self.assertIn("Morning medicines", completed[0])
        self.assertIn("completed on time", completed[0])

    def test_partial_completion(self):
        """Some meds taken, some not → partial summary in remaining."""
        items = [
            self._make_med_item('Metformin', 'morning', completed=True, status='completed'),
            self._make_med_item('Lantus', 'morning', completed=True, status='completed'),
            self._make_med_item('Atorvastatin', 'morning', completed=False, status='upcoming'),
        ]
        remaining, completed = _group_medication_items(items)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(len(completed), 0)
        self.assertIn("Morning medicines", remaining[0])
        self.assertIn("partially complete (2/3)", remaining[0])

    def test_none_completed(self):
        """No meds taken → pending summary."""
        items = [
            self._make_med_item('Metformin', 'morning'),
            self._make_med_item('Lantus', 'morning'),
        ]
        remaining, completed = _group_medication_items(items)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(len(completed), 0)
        self.assertIn("Morning medicines", remaining[0])
        self.assertIn("pending", remaining[0])

    def test_none_completed_overdue(self):
        """No meds taken and overdue → overdue in remaining."""
        items = [
            self._make_med_item('Metformin', 'morning', status='overdue', time_status='overdue'),
            self._make_med_item('Lantus', 'morning', status='overdue', time_status='overdue'),
        ]
        remaining, completed = _group_medication_items(items)
        self.assertEqual(len(remaining), 1)
        self.assertIn("overdue", remaining[0])

    def test_multiple_windows(self):
        """Meds in different windows produce separate summaries."""
        items = [
            self._make_med_item('Metformin', 'morning', completed=True, status='completed'),
            self._make_med_item('Lantus', 'morning', completed=True, status='completed'),
            self._make_med_item('Melatonin', 'nightly'),
        ]
        remaining, completed = _group_medication_items(items)
        self.assertEqual(len(completed), 1)
        self.assertIn("Morning medicines", completed[0])
        self.assertEqual(len(remaining), 1)
        self.assertIn("Night medicines", remaining[0])

    def test_non_med_items_ignored(self):
        """Non-medication items are not grouped."""
        items = [
            {'source_type': 'routine_item', 'title': 'Prayer Time', 'completed_today': False},
            {'source_type': 'routine_item', 'title': 'Workout', 'completed_today': False},
        ]
        remaining, completed = _group_medication_items(items)
        self.assertEqual(remaining, [])
        self.assertEqual(completed, [])

    def test_empty_items(self):
        """No items → empty lists."""
        remaining, completed = _group_medication_items([])
        self.assertEqual(remaining, [])
        self.assertEqual(completed, [])

    def test_completed_late(self):
        """All meds completed but some were overdue → 'completed late'."""
        items = [
            self._make_med_item('Metformin', 'morning', completed=True, status='completed',
                                time_status='overdue'),
            self._make_med_item('Lantus', 'morning', completed=True, status='completed'),
        ]
        remaining, completed = _group_medication_items(items)
        self.assertEqual(len(completed), 1)
        self.assertIn("completed late", completed[0])


class TestMedicationGroupingIntegration(SimpleTestCase):
    """Integration: medication grouping within build_status_response."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_medications_shown_as_group(self, mock_exec, mock_facts):
        """Status response groups medications instead of listing individually."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
            },
            "next_action": "Take your morning medicines.",
        }
        mock_exec.return_value = {
            "items": [
                {
                    "source_type": "medication_dose",
                    "title": "Metformin",
                    "execution_group_id": "morning",
                    "completed_today": False,
                    "is_actionable": True,
                    "completion_status": "upcoming",
                    "time_status": "upcoming",
                    "scheduled_time": "08:00",
                },
                {
                    "source_type": "medication_dose",
                    "title": "Lantus",
                    "execution_group_id": "morning",
                    "completed_today": False,
                    "is_actionable": True,
                    "completion_status": "upcoming",
                    "time_status": "upcoming",
                    "scheduled_time": "08:00",
                },
            ],
            "summaries": {"domains": {}, "expected": {}},
        }

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Should show grouped summary, not individual med names
        self.assertIn("Morning medicines", response)
        self.assertNotIn("• Metformin", response)
        self.assertNotIn("• Lantus", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_routines_not_grouped_as_meds(self, mock_exec, mock_facts):
        """Non-medication items (routines, faith) remain individual."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": True,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 2,
                "tasks_done": 0,
            },
            "next_action": "Start with Prayer.",
        }
        mock_exec.return_value = {
            "items": [
                {
                    "source_type": "routine_item",
                    "title": "Wake Up",
                    "completed_today": False,
                    "is_actionable": True,
                    "scheduled_time": "06:00",
                    "importance": "normal",
                    "time_status": "upcoming",
                },
                {
                    "source_type": "routine_item",
                    "title": "Shower",
                    "completed_today": False,
                    "is_actionable": True,
                    "scheduled_time": None,
                    "importance": "normal",
                    "time_status": "upcoming",
                },
            ],
            "summaries": {"domains": {}, "expected": {}},
        }

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Routines should still be listed individually
        self.assertIn("• Wake Up", response)
        self.assertIn("• Shower", response)


# ---------------------------------------------------------------------------
# 13. Medication fallback from raw data
# ---------------------------------------------------------------------------


class TestMedicationRawFallback(SimpleTestCase):
    """Medications must appear from raw data when execution items are missing."""

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_meds_pending_shown_from_raw_when_no_exec_items(self, mock_exec, mock_facts):
        """Pending medications appear from raw even without execution items."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": True, "prayer_expected": True,
                "bible_done": True, "bible_expected": True,
                "workout_done": True, "workout_expected": True,
                "journal_done": True, "journal_expected": True,
                "routine_done": 3, "routine_total": 3,
                "tasks_done": 2,
                "meds_taken": 4, "meds_expected": 6, "meds_skipped": 0,
                "meds_all_taken": False,
            },
            "next_action": "Take your evening medications.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn("Medications", response)
        self.assertIn("4/6", response)
        self.assertIn("2 remaining", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_meds_completed_not_in_response(self, mock_exec, mock_facts):
        """Completed medications should NOT appear in status response."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": True, "prayer_expected": True,
                "bible_done": True, "bible_expected": True,
                "workout_done": True, "workout_expected": True,
                "journal_done": True, "journal_expected": True,
                "routine_done": 3, "routine_total": 3,
                "tasks_done": 2,
                "meds_taken": 6, "meds_expected": 6, "meds_skipped": 0,
                "meds_all_taken": True,
            },
            "next_action": "All items are complete — nothing pending.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Completed items should NOT be listed
        self.assertNotIn("Completed:", response)
        # All-done message should still appear
        self.assertIn("completed everything", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_meds_with_skipped_shown_from_raw(self, mock_exec, mock_facts):
        """Skipped medications noted in remaining line."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": True, "prayer_expected": True,
                "bible_done": True, "bible_expected": True,
                "workout_done": True, "workout_expected": True,
                "journal_done": True, "journal_expected": True,
                "routine_done": 3, "routine_total": 3,
                "tasks_done": 2,
                "meds_taken": 3, "meds_expected": 6, "meds_skipped": 1,
                "meds_all_taken": False,
            },
            "next_action": "Take your evening medications.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertIn("Medications", response)
        self.assertIn("3/6", response)
        self.assertIn("2 remaining", response)
        self.assertIn("1 skipped", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_meds_fallback_when_execution_fails(self, mock_exec, mock_facts):
        """Medications appear even when today_execution raises an exception."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
                "meds_taken": 2, "meds_expected": 6, "meds_skipped": 0,
                "meds_all_taken": False,
            },
            "next_action": "Start with Prayer.",
        }
        mock_exec.side_effect = Exception("DB down")

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Both prayer AND medications should appear
        self.assertIn("• Prayer", response)
        self.assertIn("Medications", response)
        self.assertIn("2/6", response)

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_no_meds_when_none_expected(self, mock_exec, mock_facts):
        """No medication line when meds_expected is 0."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
                "meds_taken": 0, "meds_expected": 0, "meds_skipped": 0,
                "meds_all_taken": True,
            },
            "next_action": "Start with Prayer.",
        }
        mock_exec.return_value = {"items": [], "summaries": {"domains": {}, "expected": {}}}

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        self.assertNotIn("Medications", response)
        self.assertNotIn("medication", response.lower())

    @patch("apps.ai.cos_fact_statements.build_locked_facts")
    @patch("apps.core.execution.today_execution.build_today_execution")
    def test_no_double_counting_with_grouped_meds(self, mock_exec, mock_facts):
        """When execution items have medication_dose items, raw fallback
        should NOT add a duplicate medication line."""
        mock_facts.return_value = {
            "_raw": {
                "prayer_done": False, "prayer_expected": True,
                "bible_done": False, "bible_expected": False,
                "workout_done": False, "workout_expected": False,
                "journal_done": False, "journal_expected": False,
                "routine_done": 0, "routine_total": 0,
                "tasks_done": 0,
                "meds_taken": 0, "meds_expected": 2, "meds_skipped": 0,
                "meds_all_taken": False,
            },
            "next_action": "Take your morning medicines.",
        }
        mock_exec.return_value = {
            "items": [
                {
                    "source_type": "medication_dose",
                    "title": "Metformin",
                    "execution_group_id": "morning",
                    "completed_today": False,
                    "is_actionable": True,
                    "completion_status": "upcoming",
                    "time_status": "upcoming",
                    "scheduled_time": "08:00",
                },
                {
                    "source_type": "medication_dose",
                    "title": "Lantus",
                    "execution_group_id": "morning",
                    "completed_today": False,
                    "is_actionable": True,
                    "completion_status": "upcoming",
                    "time_status": "upcoming",
                    "scheduled_time": "08:00",
                },
            ],
            "summaries": {"domains": {}, "expected": {}},
        }

        user = MagicMock()
        user.id = 1
        response = build_status_response(user)

        # Should have grouped medication summary
        self.assertIn("Morning medicines", response)
        # Count medication-related bullets
        lines = [l.strip() for l in response.split("\n") if l.strip().startswith("•")]
        med_lines = [l for l in lines if "medic" in l.lower() or "medicine" in l.lower()]
        self.assertEqual(
            len(med_lines), 1,
            f"Expected 1 medication line, got {len(med_lines)}: {med_lines}",
        )
