"""
Phase 19.1 — CoS tone refiner tests.

All tests are pure SimpleTestCase — the refiner is a string-in,
string-out pure function with no DB, no user, no state.
"""

from django.test import SimpleTestCase

from apps.ai.deterministic_router import (
    _format_cos_decision_response,
    refine_cos_response,
)


class RefinerDeterminismTests(SimpleTestCase):
    """Idempotence + purity."""

    def test_same_input_same_output(self):
        s = (
            "Take your Magnesium and your Metformin now — both are "
            "quick and overdue.\nThen start Work on WLJ.\n"
            "Work on WLJ (scheduled at 05:15) is overdue and 2 more "
            "item(s) are also behind: Prayer Time, Bible."
        )
        a = refine_cos_response(s)
        b = refine_cos_response(s)
        self.assertEqual(a, b)

    def test_refine_is_idempotent(self):
        s = (
            "Take your Magnesium and your Metformin now — both are "
            "quick and overdue.\nThen start Work on WLJ.\n"
            "Work on WLJ is overdue."
        )
        once = refine_cos_response(s)
        twice = refine_cos_response(once)
        self.assertEqual(once, twice)

    def test_empty_input_passes_through(self):
        self.assertEqual(refine_cos_response(""), "")
        self.assertEqual(refine_cos_response(None), None)


class RefinerTransformationTests(SimpleTestCase):
    """The six mandatory transformations."""

    def test_collapses_your_x_and_your_y(self):
        s = (
            "Take your Magnesium and your Metformin now — both "
            "are quick and overdue."
        )
        out = refine_cos_response(s)
        self.assertIn("your Magnesium and Metformin", out)
        self.assertNotIn("your Magnesium and your Metformin", out)

    def test_collapses_multi_word_titles(self):
        s = (
            "Take your Magnesium Glycinate and your Fish Oil now "
            "— both are quick and overdue."
        )
        out = refine_cos_response(s)
        self.assertIn("your Magnesium Glycinate and Fish Oil", out)

    def test_strips_scheduled_at_parenthetical(self):
        s = "Work on WLJ (scheduled at 05:15) is overdue."
        out = refine_cos_response(s)
        self.assertEqual(out, "Work on WLJ is overdue.")

    def test_n_more_items_becomes_along_with(self):
        s = (
            "Start Work on WLJ.\n"
            "Work on WLJ is overdue and 2 more item(s) are also "
            "behind: Prayer Time, Bible."
        )
        out = refine_cos_response(s)
        self.assertNotIn("item(s)", out)
        self.assertNotIn("are also behind", out)
        self.assertIn("along with Prayer Time and Bible", out)

    def test_n_more_items_single_drops_and(self):
        s = (
            "Start Work on WLJ.\n"
            "Work on WLJ is overdue and 1 more item(s) are also "
            "behind: Prayer Time."
        )
        out = refine_cos_response(s)
        self.assertIn("along with Prayer Time", out)
        self.assertNotIn("item(s)", out)

    def test_n_more_items_three_uses_oxford_comma(self):
        s = (
            "Start X.\n"
            "X is overdue and 3 more item(s) are also behind: "
            "A, B, C."
        )
        out = refine_cos_response(s)
        self.assertIn("along with A, B, and C", out)

    def test_merge_duplicate_title(self):
        s = (
            "Then start Work on WLJ.\n"
            "Work on WLJ is overdue."
        )
        out = refine_cos_response(s)
        # Merged into one line with "— it's already overdue".
        self.assertIn(
            "Then start Work on WLJ — it's already overdue", out,
        )
        # Title should appear exactly once now.
        self.assertEqual(out.count("Work on WLJ"), 1)

    def test_merge_with_along_with_tail(self):
        s = (
            "Take your Magnesium and your Metformin now — both "
            "are quick and overdue.\n"
            "Then start Work on WLJ.\n"
            "Work on WLJ (scheduled at 05:15) is overdue and 1 "
            "more item(s) are also behind: Prayer Time."
        )
        out = refine_cos_response(s)
        expected = (
            "Take your Magnesium and Metformin now — both are "
            "quick and overdue.\n"
            "Then start Work on WLJ — it's already overdue along "
            "with Prayer Time."
        )
        self.assertEqual(out, expected)

    def test_shutdown_phrase_softened(self):
        s = "Then shut it down for the night so tomorrow starts clean."
        out = refine_cos_response(s)
        self.assertIn(
            "shut it down for the night — tomorrow starts clean",
            out,
        )
        self.assertNotIn("so tomorrow", out)

    def test_consider_is_scrubbed(self):
        # Hypothetical stray "Consider" that shouldn't leak through.
        s = "Consider taking your Magnesium now — quick and overdue."
        out = refine_cos_response(s)
        self.assertNotIn("consider", out.lower())
        self.assertIn("taking your Magnesium", out)


class RefinerStructureTests(SimpleTestCase):
    """Structure preservation: primary-line is never removed, no
    section reordering, output still matches the 4-part shape."""

    def test_primary_still_present_after_merge(self):
        s = (
            "Take your Magnesium and your Metformin now — both "
            "are quick and overdue.\n"
            "Then start Work on WLJ.\n"
            "Work on WLJ is overdue."
        )
        out = refine_cos_response(s)
        lines = [ln for ln in out.splitlines() if ln.strip()]
        # Quick wins line + merged primary+context line = 2 lines.
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("Take "))
        self.assertTrue(lines[1].startswith("Then start Work on WLJ"))

    def test_no_legacy_markers_after_refine(self):
        s = (
            "Take your A and your B now — both are quick and "
            "overdue.\nThen start X.\nX is overdue."
        )
        out = refine_cos_response(s)
        for marker in ("Do this next:", "Reason:", "Priority:"):
            self.assertNotIn(marker, out)

    def test_no_weak_verbs_or_hedging(self):
        s = (
            "Then take your overdue medications now.\n"
            "Medication adherence is low."
        )
        out = refine_cos_response(s).lower()
        for weak in ("you may want to", "you might want to", "perhaps",
                     "if you'd like"):
            self.assertNotIn(weak, out)


class RefinerEndToEndTests(SimpleTestCase):
    """Full formatter + refiner pipeline — the actual shape the
    handlers produce."""

    def test_formatter_produces_brief_after_example(self):
        """The classic brief example (Phase 19 + 19.1) produces the
        expected refined output."""
        out = _format_cos_decision_response(
            quick_wins=["your Magnesium", "your Metformin"],
            primary_action="Start Work on WLJ",
            context_reason=(
                "Work on WLJ (scheduled at 05:15) is overdue and "
                "1 more item(s) are also behind: Prayer Time"
            ),
        )
        # The formatter assembles quick-wins + "Then start …" +
        # context line; the refiner then merges primary+context
        # and tightens the wording.
        self.assertIn("Take your Magnesium and Metformin now", out)
        self.assertIn(
            "Then start Work on WLJ — it's already overdue along "
            "with Prayer Time",
            out,
        )
        self.assertNotIn("scheduled at", out)
        self.assertNotIn("item(s)", out)

    def test_formatter_shutdown_refined(self):
        out = _format_cos_decision_response(
            quick_wins=["your Magnesium"],
            primary_action=(
                "shut it down for the night so tomorrow starts clean"
            ),
        )
        self.assertIn(
            "Then shut it down for the night — tomorrow starts clean",
            out,
        )

    def test_formatter_is_deterministic_end_to_end(self):
        kwargs = dict(
            quick_wins=["your A", "your B"],
            primary_action="Start X",
            context_reason="X is overdue and 1 more item(s) are also behind: Y",
        )
        a = _format_cos_decision_response(**kwargs)
        b = _format_cos_decision_response(**kwargs)
        self.assertEqual(a, b)
