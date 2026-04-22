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
        # Phase 19.2: "Then start X" → "Then go straight into X";
        # "it's already overdue" → "you're behind on it already".
        self.assertIn(
            "Then go straight into Work on WLJ — you're behind "
            "on it already",
            out,
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
            "Then go straight into Work on WLJ — you're behind "
            "on it already along with Prayer Time."
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
        # Phase 19.2: verb strengthened.
        self.assertTrue(
            lines[1].startswith("Then go straight into Work on WLJ"),
            f"unexpected line 2: {lines[1]!r}",
        )

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
        """The classic brief example (Phase 19 + 19.1 + 19.2)
        produces the expected refined output."""
        out = _format_cos_decision_response(
            quick_wins=["your Magnesium", "your Metformin"],
            primary_action="Start Work on WLJ",
            context_reason=(
                "Work on WLJ (scheduled at 05:15) is overdue and "
                "1 more item(s) are also behind: Prayer Time"
            ),
        )
        # Phase 19.1: quick-wins collapse, scheduled-at strip,
        # items-list rewrite, primary+context merge.
        # Phase 19.2: verb strengthened, leadership framing.
        self.assertIn("Take your Magnesium and Metformin now", out)
        self.assertIn(
            "Then go straight into Work on WLJ — you're behind on "
            "it already along with Prayer Time",
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


# ═══════════════════════════════════════════════════════════════════
# Phase 19.2 — leadership-voice polish
# ═══════════════════════════════════════════════════════════════════

class Phase19_2VerbStrengthTests(SimpleTestCase):
    """Rule 7 — Strengthen weak verbs at line start / after 'Then '."""

    def test_line_start_start_becomes_go_straight_into(self):
        out = refine_cos_response("Start Workout.")
        self.assertEqual(out, "Go straight into Workout.")

    def test_then_start_becomes_then_go_straight_into(self):
        out = refine_cos_response("Then start Workout.")
        self.assertEqual(out, "Then go straight into Workout.")

    def test_line_start_begin_becomes_move_into(self):
        out = refine_cos_response("Begin your routine.")
        self.assertEqual(out, "Move into your routine.")

    def test_then_begin_becomes_then_move_into(self):
        out = refine_cos_response("Then begin your routine.")
        self.assertEqual(out, "Then move into your routine.")

    def test_start_inside_title_not_rewritten(self):
        # A title literally containing the word "Start" must NOT be
        # rewritten (narrow anchoring prevents this).
        out = refine_cos_response("Then finish the Start of Day form.")
        self.assertEqual(out, "Then finish the Start of Day form.")

    def test_starts_clean_phrase_not_rewritten(self):
        # "starts" (with -s) is a different word and must be left alone.
        out = refine_cos_response(
            "Shut it down for the night — tomorrow starts clean."
        )
        self.assertIn("tomorrow starts clean", out)

    def test_starting_not_rewritten(self):
        # "starting" (participle) is a different word.
        out = refine_cos_response(
            "Get back on track by starting Work on WLJ."
        )
        self.assertIn("starting Work on WLJ", out)
        self.assertNotIn("go straight into Work on WLJ", out)


class Phase19_2LeadershipFramingTests(SimpleTestCase):
    """Rule 8 — system voice → leadership voice."""

    def test_its_already_overdue_swaps_subject(self):
        s = "Go straight into Workout — it's already overdue."
        out = refine_cos_response(s)
        self.assertIn("you're behind on it already", out)
        self.assertNotIn("it's already overdue", out)

    def test_leadership_framing_preserves_along_with_tail(self):
        s = (
            "Then start X — it's already overdue along with Y."
        )
        out = refine_cos_response(s)
        self.assertIn("you're behind on it already along with Y", out)


class Phase19_2ItemPluralTests(SimpleTestCase):
    """Rule 9 — normalize 'N item(s)' to proper English."""

    def test_single_item_uses_singular(self):
        out = refine_cos_response("Clear your 1 overdue item(s) now.")
        self.assertIn("1 overdue item now", out)
        self.assertNotIn("item(s)", out)

    def test_plural_items_uses_plural(self):
        out = refine_cos_response("Clear your 3 overdue item(s) now.")
        self.assertIn("3 overdue items now", out)
        self.assertNotIn("item(s)", out)

    def test_bare_item_parenthetical_defaults_to_plural(self):
        out = refine_cos_response("Several item(s) are overdue.")
        self.assertEqual(out, "Several items are overdue.")


class Phase19_2ConsequenceFramingTests(SimpleTestCase):
    """Rule 10 — append consequence tags on biggest-risk fallback
    phrases, only when not already present (idempotent)."""

    def test_falling_behind_gets_compounds_tag(self):
        s = (
            "Clear your 3 overdue items now — falling behind is "
            "your biggest risk today."
        )
        out = refine_cos_response(s)
        self.assertIn(
            "falling behind is your biggest risk today — "
            "this compounds quickly",
            out,
        )

    def test_skipping_foundational_gets_slip_further_tag(self):
        s = (
            "No critical health risks surfaced. Skipping "
            "foundational commitments is your biggest risk."
        )
        out = refine_cos_response(s)
        self.assertIn(
            "Skipping foundational commitments is your biggest risk — "
            "it'll slip further if you leave it",
            out,
        )

    def test_consequence_tags_are_idempotent(self):
        s = (
            "Clear your 3 overdue items now — falling behind is "
            "your biggest risk today."
        )
        once = refine_cos_response(s)
        twice = refine_cos_response(once)
        self.assertEqual(once, twice)
        # "this compounds quickly" appears exactly once.
        self.assertEqual(once.count("this compounds quickly"), 1)

    def test_generic_response_is_untouched_by_consequence_rules(self):
        s = (
            "Take your Magnesium now — quick and overdue.\n"
            "Then go straight into Workout."
        )
        out = refine_cos_response(s)
        self.assertNotIn("compounds", out)
        self.assertNotIn("slip further", out)


class Phase19_2IntegrationTests(SimpleTestCase):
    """End-to-end with the formatter — full Phase 19 + 19.1 + 19.2."""

    def test_classic_morning_example(self):
        out = _format_cos_decision_response(
            quick_wins=["your Magnesium", "your Metformin"],
            primary_action="Start Work on WLJ",
            context_reason=(
                "Work on WLJ (scheduled at 05:15) is overdue and "
                "1 more item(s) are also behind: Prayer Time"
            ),
        )
        expected = (
            "Take your Magnesium and Metformin now — both are "
            "quick and overdue.\n"
            "Then go straight into Work on WLJ — you're behind on "
            "it already along with Prayer Time."
        )
        self.assertEqual(out, expected)

    def test_biggest_risk_fallback_with_consequence(self):
        out = _format_cos_decision_response(
            primary_action=(
                "Clear your 3 overdue item(s) now — "
                "falling behind is your biggest risk today"
            ),
            context_reason=(
                "No critical health risks surfaced, but 3 "
                "item(s) are overdue. Letting them accumulate "
                "erodes consistency"
            ),
        )
        # "item(s)" gone, consequence tag appended.
        self.assertNotIn("item(s)", out)
        self.assertIn("this compounds quickly", out)
        self.assertIn("3 overdue items now", out)

    def test_refine_is_idempotent_on_all_rules(self):
        s = (
            "Take your A and your B now — both are quick and overdue.\n"
            "Then start Work on WLJ.\n"
            "Work on WLJ (scheduled at 05:15) is overdue and 2 more "
            "item(s) are also behind: Prayer Time, Bible."
        )
        once = refine_cos_response(s)
        twice = refine_cos_response(once)
        thrice = refine_cos_response(twice)
        self.assertEqual(once, twice)
        self.assertEqual(twice, thrice)
