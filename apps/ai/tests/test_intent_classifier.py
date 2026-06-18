"""Shared deterministic intent classifier (Phase 0, 2026-06-18).

`classify_query_intent(msg_lower)` returns the single intent CATEGORY of a
message so domain routes can recognise WHAT KIND of question is being asked
before deciding HOW to answer it. These tests pin the six categories and the
approved precedence rules using PARAPHRASES (not the literal cue strings where
possible) so the classifier recognises the category, not memorised wording.
"""
from django.test import SimpleTestCase

from apps.ai.deterministic_router import classify_query_intent as clf


class IntentMatrix(SimpleTestCase):
    def test_status_is_the_floor(self):
        for q in (
            "what's my sleep score",
            "how many hours did i sleep last night",
            "what is my glucose right this second",   # 'right now' absent
            "my weight this week",
            "how is my sleep this week",               # 'this week' is NOT planning
            "show me my nutrition today",
        ):
            self.assertEqual(clf(q), 'status', q)

    def test_coaching_action_verbs(self):
        for q in (
            "how can i improve my sleep",
            "what's the best way to lower my glucose",
            "any tips for getting more consistent",
            "recommend something for my recovery",
            "help me get my nutrition on track",
            "what should i change about my evenings",
        ):
            self.assertEqual(clf(q), 'coaching', q)

    def test_diagnostic_cause_seeking(self):
        for q in (
            "why is my sleep so poor lately",
            "what's causing my low energy",
            "what's behind my weight stall",
            "root cause of my afternoon crashes",
            "what's limiting my progress",
        ):
            self.assertEqual(clf(q), 'diagnostic', q)

    def test_recognition_factual_acknowledgement(self):
        for q in (
            "do you see i've been reading every day",
            "do you notice i'm more consistent",
            "have i been staying on track this month",
            "how consistent have i been with prayer",
        ):
            self.assertEqual(clf(q), 'recognition', q)

    def test_planning_future_horizon(self):
        for q in (
            "what should i focus on next month",
            "what should i work on over the next few weeks",
            "what should i prioritize this quarter",
            "what should i be building toward",
            "where should i be going forward",
        ):
            self.assertEqual(clf(q), 'planning', q)

    def test_execution_immediate_next_step(self):
        for q in (
            "what should i do next",
            "what's my next step",
            "what should i do right now",
            "what should i tackle first",
            "where should i start today",
        ):
            self.assertEqual(clf(q), 'execution', q)


class IntentPrecedence(SimpleTestCase):
    """The four approved precedence rules."""

    def test_planning_beats_execution_with_horizon(self):
        # Same "what should I do/work on" stem, but a future horizon flips it
        # from EXECUTION (today) to PLANNING.
        self.assertEqual(clf("what should i work on"), 'execution')
        self.assertEqual(clf("what should i work on over the next few weeks"),
                         'planning')
        self.assertEqual(clf("what should i do next month"), 'planning')

    def test_coaching_action_verb_beats_diagnostic(self):
        # Contains BOTH a cause cue ("why") and an action verb ("how can i") →
        # coaching wins (actionable over explanatory).
        self.assertEqual(clf("why is my sleep bad and how can i fix it"),
                         'coaching')
        self.assertEqual(clf("why am i tired — what's the best way to fix it"),
                         'coaching')

    def test_recognition_beats_status(self):
        # A bare lookup is status; a recognition framing of the same is not.
        self.assertEqual(clf("my bible reading this week"), 'status')
        self.assertEqual(clf("do you see i've been reading this week"),
                         'recognition')

    def test_status_floor_for_unmatched(self):
        self.assertEqual(clf(""), 'status')
        self.assertEqual(clf("tell me about my day"), 'status')
        self.assertEqual(clf(None), 'status')

    def test_each_message_classifies_to_exactly_one(self):
        # The function returns a single label by construction; assert the label
        # set is exactly the six categories across a representative sweep.
        labels = {clf(q) for q in (
            "what's my sleep score", "how can i improve my sleep",
            "why is my sleep poor", "do you see i've been consistent",
            "what should i focus on next month", "what's my next step",
        )}
        self.assertEqual(
            labels,
            {'status', 'coaching', 'diagnostic', 'recognition',
             'planning', 'execution'})
