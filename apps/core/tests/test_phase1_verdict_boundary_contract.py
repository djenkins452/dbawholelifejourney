# ==============================================================================
# File: apps/core/tests/test_phase1_verdict_boundary_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: WLJ hands Phase 1 facts, never a pre-decided verdict
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-04
# ==============================================================================
"""Production, 2026-09-03, 9:38 PM. "How did I do today?"

The Chief of Staff answered: 16 tasks completed, no overdue tasks, strong momentum, focus
and execution spot on. A minute later, challenged, it established from the very same
prompt that a workout, a bike ride, pickleball and a supplement were all still
outstanding. Phase 2 never ran — one tool call is one evidence surface, and eligibility
needs two.

The data was right. `get_analysis(tasks, overall)` genuinely returned `overdue_count: 0`,
because a supplement and a workout are not tasks; and the canonical whole-day
`execution_state` was in the envelope the whole time, which the challenge turn proved by
answering it with zero tool calls.

What was wrong is that WLJ also handed over a CONCLUSION. `understanding` publishes
`momentum` and `strategic_summary` — the exact keys already listed in `_VERDICT_KEYS` as
judgments the model must form for itself — and `strip_verdicts` removed them from Phase 2
from the day it was written, while Phase 1 received them raw. Phase 1 answers most turns.
The protection had been applied to the phase that was frequently absent.

This file certifies the boundary, and just as importantly certifies what did NOT change:
the facts still arrive, Phase 2 keeps its protection, canonical truth and Action Safety are
untouched, and no rule was added telling the model to be more critical, balanced, negative
or positive. No provider calls.
"""

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.model_interface import synthesis
from apps.ai.model_interface import telemetry as tel

User = get_user_model()

# A realistic `understanding` payload: verdicts and the facts that sit underneath them.
UNDERSTANDING = {
    "schema_version": "1.0",
    "status": "ok",
    "executive": {
        "primary_challenge": "recovery",
        "challenge_reason": "three short nights",
        "biggest_risk": "missed strength sessions",
        "workload": "heavy",
        "workload_summary": "18 open commitments",
        "cognitive_load": "elevated",
        "health_read": "stable",
        "recovery_needed": True,
        "intervention_required": False,
    },
    "priority": {"executive": {"title": "Workout"}, "clinical": []},
    "patterns": [{"text": "evening sessions slip", "basis": "12 weeks"}],
    "wins": ["19 completions today"],
    "opportunity": {"text": "mornings are free", "basis": "calendar"},
    "predictions": [{"text": "likely to miss Friday"}],
    "confidence": 0.8,
    "direction": {
        "goal_pace": {"on_pace": 3, "behind": 1},
        "momentum": "strong",                       # VERDICT
        "strategic_summary": "Execution is spot on.",  # VERDICT
    },
    "continuity": {"mode": "steady", "material_changes": []},
}

FACTS_THAT_MUST_SURVIVE = (
    "primary_challenge", "biggest_risk", "workload", "cognitive_load", "wins",
    "patterns", "goal_pace", "opportunity", "predictions", "continuity", "priority",
)


def _walk_keys(node, out=None):
    out = set() if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            out.add(key)
            _walk_keys(value, out)
    elif isinstance(node, list):
        for item in node:
            _walk_keys(item, out)
    return out


class OneBoundaryTests(SimpleTestCase):
    """One list, one function, both phases. No second verdict list anywhere."""

    def test_the_strip_and_the_detector_read_the_same_list(self):
        stripped = synthesis.strip_verdicts(UNDERSTANDING)
        self.assertEqual(synthesis.verdict_keys_in(stripped), [])
        self.assertEqual(sorted(synthesis.verdict_keys_in(UNDERSTANDING)),
                         ["momentum", "strategic_summary"])

    def test_no_second_verdict_list_was_introduced(self):
        """A duplicated list is a list that drifts. There must be exactly one.

        Scoped to the CERTIFIED runtime — the legacy `chatgpt_cos` modules and the older
        goal-narration tests name these keys for their own reasons and are not governed by
        this boundary.
        """
        import pathlib
        hits = sorted(str(path)
                      for path in pathlib.Path("apps/ai/model_interface").rglob("*.py")
                      if '"momentum_summary"' in path.read_text(encoding="utf-8"))
        self.assertEqual(hits, ["apps/ai/model_interface/synthesis.py"],
                         f"the verdict vocabulary is defined in more than one place: {hits}")

    def test_the_legacy_private_name_still_resolves(self):
        self.assertIs(synthesis._strip_verdicts, synthesis.strip_verdicts)

    def test_stripping_is_recursive_and_leaves_lists_intact(self):
        out = synthesis.strip_verdicts(
            {"a": [{"momentum": "strong", "count": 3}, {"count": 4}]})
        self.assertEqual(out, {"a": [{"count": 3}, {"count": 4}]})


class Phase1ReceivesFactsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="verdict@contract.test", password="x")

    def _envelope(self, understanding=None, **kw):
        from unittest import mock

        from apps.ai.model_interface.service import ModelInterfaceService
        with mock.patch("apps.ai.model_interface.understanding.read",
                        return_value=understanding if understanding is not None
                        else dict(UNDERSTANDING)):
            return ModelInterfaceService(self.user).build_standing_context(**kw)

    def test_phase1_no_longer_receives_any_verdict_key(self):
        ctx = self._envelope()
        self.assertEqual(synthesis.verdict_keys_in(ctx), [],
                         "a pre-decided judgment is still being handed to Phase 1")

    def test_the_verdict_is_gone_from_the_prompt_the_model_actually_reads(self):
        """The envelope is serialized straight into the system prompt; assert there.

        Note what is NOT asserted: the bare word "momentum". It legitimately appears in the
        capability index as a metric the model may RETRIEVE (`get_history(goals,
        "momentum")`). A catalogue entry naming a retrievable measure is the opposite of a
        supplied conclusion, and banning the substring would have deleted a capability while
        proving nothing. What must be absent is the verdict as a FIELD and its value.
        """
        from apps.ai.model_interface.service import ModelInterfaceService
        ctx = self._envelope()
        prompt = ModelInterfaceService(self.user)._prompt_sections(
            ctx)["structured_context"]
        self.assertNotIn('"strategic_summary"', prompt)
        self.assertNotIn('"momentum":', prompt)
        self.assertNotIn('"momentum_score":', prompt)
        self.assertNotIn("Execution is spot on", prompt)
        # the facts the verdict sat on top of are still in the prompt
        self.assertIn("goal_pace", prompt)
        self.assertIn("biggest_risk", prompt)

    def test_every_underlying_fact_survives(self):
        keys = _walk_keys((self._envelope() or {}).get("deterministic_understanding"))
        for fact in FACTS_THAT_MUST_SURVIVE:
            self.assertIn(fact, keys, f"the fact {fact!r} was removed with the verdicts")

    def test_the_facts_keep_their_values(self):
        du = (self._envelope() or {}).get("deterministic_understanding") or {}
        self.assertEqual(du["executive"]["primary_challenge"], "recovery")
        self.assertEqual(du["executive"]["biggest_risk"], "missed strength sessions")
        self.assertEqual(du["wins"], ["19 completions today"])
        self.assertEqual(du["direction"]["goal_pace"], {"on_pace": 3, "behind": 1})

    def test_a_verdict_is_stripped_whatever_section_carries_it(self):
        """The narrow version of this fix — stripping `deterministic_understanding` alone —
        was written first and was wrong within minutes: momentum verdicts were arriving from
        `missions[*].progress.momentum_score` and `momentum_7d_avg` as well. The boundary is
        the ENVELOPE, so a future section cannot reintroduce the class by forgetting."""
        ctx = self._envelope()
        ctx_missions = ctx.get("missions")
        self.assertEqual(synthesis.verdict_keys_in(ctx), [])
        # and the facts under the withdrawn score are still there
        for mission in (ctx_missions or {}).values():
            progress = (mission or {}).get("progress")
            if isinstance(progress, dict) and progress:
                self.assertNotIn("momentum_score", progress)

    def test_a_pending_understanding_is_passed_through_untouched(self):
        du = (self._envelope({"schema_version": "1.0", "status": "pending"})
              or {}).get("deterministic_understanding")
        self.assertEqual(du.get("status"), "pending")

    def test_canonical_execution_truth_is_untouched(self):
        """The verdict boundary must not touch the facts the day is judged from."""
        execution = (self._envelope() or {}).get("execution_state") or {}
        for bucket in ("overdue", "due_now", "coming_up", "later", "completed"):
            self.assertIn(bucket, execution,
                          f"canonical execution bucket {bucket!r} disappeared")

    def test_action_safety_surface_is_untouched(self):
        ctx = self._envelope(writes_enabled=True)
        self.assertIn("pending_confirmations", ctx)


class Phase2KeepsItsProtectionTests(SimpleTestCase):
    """Symmetry, not substitution — Phase 2 loses nothing."""

    def test_phase2_orientation_still_strips_verdicts(self):
        out = synthesis.build_orientation({"missions": dict(UNDERSTANDING)})
        self.assertNotIn("strategic_summary", out)
        self.assertNotIn("Execution is spot on", out)

    def test_understanding_is_still_declared_away_from_phase2(self):
        self.assertIn("deterministic_understanding", synthesis.INTENTIONALLY_OMITTED)

    def test_coverage_still_reports_it_as_omitted_not_lost(self):
        coverage = synthesis.orientation_coverage(
            {"deterministic_understanding": dict(UNDERSTANDING), "missions": {"a": 1}})
        self.assertIn("deterministic_understanding", coverage["intentionally_omitted"])
        self.assertEqual(coverage["silently_lost"], [])


class NoReplacementRuleTests(SimpleTestCase):
    """The point was to REMOVE a pre-decided answer, not to prescribe a different one."""

    def test_no_balancing_or_tone_instruction_was_added(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        lowered = CONSTITUTION.lower()
        for planted in ("be more critical", "be more balanced", "be more negative",
                        "temper your praise", "avoid praise", "be harsher",
                        "do not say strong momentum", "weigh the negatives"):
            self.assertNotIn(planted, lowered,
                             f"a substitute judgment rule was added: {planted!r}")

    def test_block_17_got_smaller_not_larger(self):
        from apps.ai.model_interface import constitution_map as cmap
        block = next(b for b in cmap.BLOCKS
                     if b.heading.startswith("DETERMINISTIC UNDERSTANDING"))
        self.assertLess(block.chars, 1122,
                        "block 17 did not shrink when its verdicts were withdrawn")

    def test_the_deference_instructions_are_gone(self):
        """They existed only because a conclusion was supplied."""
        from apps.ai.model_interface.constitution import CONSTITUTION
        for withdrawn in ("REASON FROM THIS", "do not re-rank the priority",
                          "speak to what it MEANS"):
            self.assertNotIn(withdrawn, CONSTITUTION)

    def test_the_protections_that_had_nothing_to_do_with_verdicts_remain(self):
        """Simplification must not quietly drop the unrelated guard in the same block."""
        from apps.ai.model_interface.constitution import CONSTITUTION
        for kept in ("NOT the authority on any one subject",
                     "never conclude 'insufficient' for the subject",
                     "it is warming"):
            self.assertIn(kept, CONSTITUTION)

    def test_the_constitution_still_has_every_block(self):
        from apps.ai.model_interface import constitution_map as cmap
        self.assertEqual(len(cmap.BLOCKS), 34)
        self.assertEqual(cmap.UNCLASSIFIED, [])
        self.assertEqual(cmap.reconstruct(), cmap.CONSTITUTION)


class TelemetryTests(SimpleTestCase):
    """Prove, on future turns, that the whole-day truth was actually available."""

    ENVELOPE = {
        "current_context": {"clock": {}},
        "deterministic_understanding": {"status": "ok"},
        "execution_state": {"overdue": [1, 2], "due_now": [3], "coming_up": [],
                            "later": [4, 5, 6], "completed": list(range(16))},
        "missions": {},          # falsy — absent sections are not reported as present
    }

    def test_envelope_key_names_are_recorded(self):
        keys = tel.envelope_state(self.ENVELOPE)["keys"]
        self.assertIn("execution_state", keys)
        self.assertNotIn("missions", keys, "an empty section was reported as present")

    def test_understanding_status_is_recorded(self):
        self.assertEqual(
            tel.envelope_state(self.ENVELOPE)["understanding_status"], "ok")
        self.assertEqual(
            tel.envelope_state({"deterministic_understanding":
                                {"status": "pending"}})["understanding_status"],
            "pending")

    def test_execution_buckets_are_counted_not_listed(self):
        buckets = tel.envelope_state(self.ENVELOPE)["execution_buckets"]
        self.assertEqual(buckets, {"overdue": 2, "due_now": 1, "coming_up": 0,
                                   "later": 3, "completed": 16})
        for value in buckets.values():
            self.assertIsInstance(value, int)

    def test_a_leaked_verdict_would_be_reported_by_name(self):
        leaked = dict(self.ENVELOPE)
        leaked["deterministic_understanding"] = {"status": "ok", "momentum": "strong"}
        self.assertEqual(tel.envelope_state(leaked)["verdict_keys_present"], ["momentum"])

    def test_a_clean_envelope_reports_no_verdicts(self):
        self.assertEqual(tel.envelope_state(self.ENVELOPE)["verdict_keys_present"], [])

    def test_no_item_title_or_value_reaches_the_record(self):
        import json
        blob = json.dumps(tel.envelope_state({
            "execution_state": {"overdue": [{"title": "SECRET WORKOUT",
                                             "time": "18:00"}]},
            "deterministic_understanding": {"status": "ok",
                                            "strategic_summary": "SECRET VERDICT TEXT"},
        }))
        for leak in ("SECRET WORKOUT", "18:00", "SECRET VERDICT TEXT"):
            self.assertNotIn(leak, blob)

    def test_the_record_still_fits_the_audit_digest_budget(self):
        import json
        from apps.ai.cos_services.audit import _MAX_JSON_CHARS
        record = tel.build_turn_telemetry(
            sections={"constitution": "x" * 100}, tools=[], tools_called=[],
            standing_context=self.ENVELOPE)
        self.assertLess(len(json.dumps(record)), _MAX_JSON_CHARS * 0.6)
