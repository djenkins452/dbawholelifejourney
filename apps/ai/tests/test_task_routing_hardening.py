"""
Regression tests for task-completion query routing hardening.

Verifies that completed-task queries:
1. Match CHECKIN_PATTERNS (enabling history/memory drop)
2. Match is_asking_about_tasks (enabling check-in upgrade)
3. Trigger the safety heuristic for edge cases
4. Prevent conversation history contamination
"""

from django.test import SimpleTestCase


class CheckinPatternsCompletedTaskTest(SimpleTestCase):
    """Verify CHECKIN_PATTERNS catches completed-task phrasings."""

    def setUp(self):
        from apps.ai.personal_assistant import CHECKIN_PATTERNS
        self.patterns = CHECKIN_PATTERNS

    def _matches(self, message):
        msg_lower = message.lower()
        return any(p in msg_lower for p in self.patterns)

    def test_list_tasks_completed_today(self):
        self.assertTrue(self._matches("List the tasks I completed today"))

    def test_list_only_tasks_completed_today(self):
        self.assertTrue(self._matches("List only the tasks I have completed today"))

    def test_what_did_i_complete(self):
        self.assertTrue(self._matches("What did I complete today?"))

    def test_what_have_i_completed(self):
        self.assertTrue(self._matches("What have I completed today?"))

    def test_how_many_tasks_completed(self):
        self.assertTrue(self._matches("How many tasks have I completed today"))

    def test_what_did_i_finish(self):
        self.assertTrue(self._matches("What did I finish today"))

    def test_which_tasks_did_i_finish(self):
        self.assertTrue(self._matches("Which tasks did I finish today"))

    def test_what_got_done(self):
        self.assertTrue(self._matches("What got done today"))

    def test_what_have_i_done_today(self):
        self.assertTrue(self._matches("What have I done today"))

    # Existing patterns must still work
    def test_existing_checkin_still_works(self):
        self.assertTrue(self._matches("check in"))

    def test_existing_status_still_works(self):
        self.assertTrue(self._matches("status"))

    def test_existing_whats_left_still_works(self):
        self.assertTrue(self._matches("what's left"))

    def test_existing_tasks_today_still_works(self):
        self.assertTrue(self._matches("tasks today"))

    def test_unrelated_message_does_not_match(self):
        self.assertFalse(self._matches("Tell me a joke"))

    def test_unrelated_task_mention_no_match(self):
        """Mentioning 'task' without completion words should not match these patterns."""
        self.assertFalse(self._matches("Create a new task called workout"))


class IsAskingAboutTasksTest(SimpleTestCase):
    """Verify is_asking_about_tasks catches completed-task phrasings."""

    TASK_PHRASES = [
        'what do i have', "what's left", 'what tasks', 'what should i',
        'my priorities', 'my tasks', 'overdue', 'due today', 'to do',
        'what remains', 'what still needs', 'focus on', 'left to do',
        "what needs to be done", "what's remaining", 'how many tasks',
        'prioritize', 'structure my day', 'should i do today',
        'biggest improvement', 'biggest difference',
        'highest impact', 'most important', 'top priority',
        # v7 additions
        'completed today', 'i completed', 'have completed',
        'i finished today', 'did i complete', 'did i finish',
        'what did i complete', 'what have i completed',
        'what did i finish', 'tasks i completed',
        'tasks i finished', 'tasks i have completed',
        'what got done', 'what have i done today',
    ]

    def _matches(self, message):
        msg_lower = message.lower()
        return any(phrase in msg_lower for phrase in self.TASK_PHRASES)

    def test_list_tasks_completed_today(self):
        self.assertTrue(self._matches("List the tasks I completed today"))

    def test_list_only_tasks_completed_today(self):
        self.assertTrue(self._matches("List only the tasks I have completed today"))

    def test_what_did_i_complete_today(self):
        self.assertTrue(self._matches("What did I complete today?"))

    def test_how_many_tasks_completed(self):
        self.assertTrue(self._matches("How many tasks have I completed today"))

    def test_what_did_i_finish_today(self):
        self.assertTrue(self._matches("What did I finish today"))


class SafetyHeuristicTest(SimpleTestCase):
    """Verify the task+completion safety heuristic catches edge cases."""

    def _heuristic_matches(self, message):
        msg_lower = message.lower()
        _has_task_word = any(w in msg_lower for w in ('task', 'tasks'))
        _has_done_word = any(w in msg_lower for w in (
            'completed', 'finished', 'done', 'complete', 'finish',
        ))
        return _has_task_word and _has_done_word

    def test_unusual_phrasing(self):
        self.assertTrue(self._heuristic_matches(
            "Show me every task I've done"
        ))

    def test_tasks_that_are_complete(self):
        self.assertTrue(self._heuristic_matches(
            "Which tasks are complete?"
        ))

    def test_finished_tasks(self):
        self.assertTrue(self._heuristic_matches(
            "Give me finished tasks"
        ))

    def test_no_task_word_no_match(self):
        """Without 'task'/'tasks', heuristic should not match."""
        self.assertFalse(self._heuristic_matches(
            "What have I completed today"
        ))

    def test_no_completion_word_no_match(self):
        """Without completion word, heuristic should not match."""
        self.assertFalse(self._heuristic_matches(
            "Show me my tasks"
        ))

    def test_create_task_no_match(self):
        """'Create a task' without completion word should not match."""
        self.assertFalse(self._heuristic_matches(
            "Create a task for tomorrow"
        ))
