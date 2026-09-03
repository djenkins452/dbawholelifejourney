# ==============================================================================
# File: apps/core/tests/test_cos_telemetry_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Stage-0 turn telemetry measures the prompt without recording the user
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-03
# ==============================================================================
"""Measurement that costs a turn nothing and tells the user's life story to nobody.

Stage 0 exists because three confident hypotheses about this runtime have already been
overturned by measurement. So before anything is simplified, the turn is instrumented —
and instrumentation that reads a health value, a balance, a Personal Knowledge statement
or a line of conversation would be a privacy regression dressed up as engineering.

Two properties are therefore certified here, and they are the whole point:

  1. **It measures nothing it must not keep.** Every section of the prompt is fed a unique
     marker; none may appear anywhere in the record. That asserts on the DATA, not on the
     absence of a key name, so a future field that quietly carries text fails this file.
  2. **It changes nothing.** The prompt is now assembled from named sections instead of a
     concatenation; joining them must produce the identical string, byte for byte.

No provider calls.
"""

import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.model_interface import telemetry as tel

User = get_user_model()

# One marker per prompt section — nonsense strings that could only appear in the record
# if that section's TEXT were copied into it.
_MARKERS = {
    "constitution": "ZZMARKERCONSTITUTIONZZ",
    "current_situation": "ZZMARKERSITUATIONZZ",
    "structured_context": "ZZMARKERCONTEXTZZ",
    "grounding": "ZZMARKERGROUNDINGZZ",
    "completion_reminder": "ZZMARKERREMINDERZZ",
}


def _sections():
    return {name: f"some prose {marker} confirm the persona and retrieve the truth"
            for name, marker in _MARKERS.items()}


def _tools():
    return [
        {"type": "function", "function": {"name": "get_entity",
                                          "description": "x" * 300, "parameters": {}}},
        {"type": "function", "function": {"name": "log_food",
                                          "description": "y" * 50, "parameters": {}}},
    ]


class PrivacyTests(SimpleTestCase):
    """The record may hold sizes, counts and WLJ's own identifiers. Nothing else."""

    def _record(self):
        return tel.build_turn_telemetry(
            sections=_sections(), tools=_tools(), tools_called=["get_entity"],
            loop_metrics={"rounds_used": 2, "max_rounds": 6},
            synthesis_eligible=True, synthesis_used=True,
            answer_change=tel.answer_delta("PHASE ONE SECRET TEXT",
                                           "PHASE TWO SECRET TEXT"),
            coverage={"phase1_keys": ["a", "b"], "carried": ["a"],
                      "intentionally_omitted": [], "silently_lost": ["b"]},
        )

    def test_no_prompt_text_survives_into_the_record(self):
        blob = json.dumps(self._record())
        for section, marker in _MARKERS.items():
            self.assertNotIn(marker, blob,
                             f"the {section} section's text was copied into telemetry")

    def test_no_answer_text_survives_the_phase2_comparison(self):
        blob = json.dumps(self._record())
        for word in ("SECRET", "PHASE ONE", "PHASE TWO"):
            self.assertNotIn(word, blob, "answer text leaked through answer_delta")

    def test_the_record_is_json_serialisable(self):
        json.dumps(self._record())   # would raise on a model instance or a date

    def test_every_recorded_leaf_is_a_number_a_bool_or_a_known_identifier(self):
        """Strings are permitted ONLY where they are WLJ configuration."""
        from apps.ai.model_interface import constitution_map as cmap
        allowed = ({"get_entity", "log_food", "a", "b"}
                   | set(tel._THEMES) | set(_MARKERS) | set(cmap.PROTECTS))

        def walk(node, path=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    walk(v, f"{path}.{k}")
            elif isinstance(node, list):
                for item in node:
                    walk(item, path)
            elif isinstance(node, str):
                self.assertIn(node, allowed,
                              f"telemetry{path} carries free text: {node!r}")

        record = self._record()
        # section names are dict KEYS, which walk() does not treat as values
        walk(record)

    def test_the_record_fits_the_audit_digest_budget(self):
        """It rides an existing ToolCallLog row whose digest is capped at 4000 chars —
        overflowing would replace the whole digest with a truncation stub and destroy the
        turn's real audit fields as well."""
        from apps.ai.cos_services.audit import _MAX_JSON_CHARS
        size = len(json.dumps(self._record()))
        self.assertLess(size, _MAX_JSON_CHARS * 0.6,
                        f"telemetry is {size} chars — too large to share the audit digest")


class MeasurementTests(SimpleTestCase):
    def test_sections_are_measured_individually_and_totalled(self):
        sizes = tel.measure_sections(_sections())
        self.assertEqual(sizes["total"],
                         sum(v for k, v in sizes.items() if k != "total"))
        self.assertEqual(set(sizes) - {"total"}, set(_MARKERS))

    def test_tool_exposure_and_schema_cost_are_measured(self):
        out = tel.measure_tools(_tools())
        self.assertEqual(out["tools_exposed"], 2)
        self.assertGreater(out["tool_schema_chars"], 300)
        self.assertEqual(out["largest_tools"][0]["name"], "get_entity")

    def test_the_gap_between_exposed_and_called_is_recorded(self):
        """The tool-pruning evidence: schema paid for vs schema used."""
        rec = tel.build_turn_telemetry(sections=_sections(), tools=_tools(),
                                       tools_called=["log_food", "log_food"])
        self.assertEqual(rec["tools_called_count"], 2)
        self.assertEqual(rec["tools_called_distinct"], 1)
        self.assertEqual(rec["tools"]["tools_unused"], 1)

    def test_a_malformed_tool_schema_does_not_break_measurement(self):
        out = tel.measure_tools([{"function": {"name": "ok", "parameters": {}}}, None])
        self.assertEqual(out["tools_exposed"], 1)

    def test_duplicate_instruction_themes_are_counted(self):
        counts = tel.duplicate_instruction_counts(
            "confirm the persona, then retrieve; confirm again")
        self.assertEqual(counts["confirmation"], 2)
        self.assertEqual(counts["persona_voice"], 1)
        for value in counts.values():
            self.assertIsInstance(value, int)

    def test_an_empty_section_is_not_reported_as_duplication(self):
        self.assertEqual(tel.duplicate_instruction_counts(""), {})

    def test_the_round_cap_is_visible(self):
        hit = tel.build_turn_telemetry(sections={}, tools=[], tools_called=[],
                                       loop_metrics={"rounds_used": 7, "max_rounds": 6})
        self.assertTrue(hit["loop"]["hit_round_cap"])
        ok = tel.build_turn_telemetry(sections={}, tools=[], tools_called=[],
                                      loop_metrics={"rounds_used": 2, "max_rounds": 6})
        self.assertFalse(ok["loop"]["hit_round_cap"])

    def test_missing_loop_metrics_are_recorded_as_unknown_not_zero(self):
        rec = tel.build_turn_telemetry(sections={}, tools=[], tools_called=[])
        self.assertIsNone(rec["loop"]["rounds_used"])

    def test_the_constitution_split_is_carried_as_numbers(self):
        comp = tel.build_turn_telemetry(sections={}, tools=[],
                                        tools_called=[])["constitution"]
        self.assertGreater(comp["invariant_chars"], 0)
        self.assertGreater(comp["guidance_chars"], 0)


class Phase2MeasurementTests(SimpleTestCase):
    """Whether the second billable request earned itself."""

    def test_an_identical_rewrite_is_not_a_material_change(self):
        out = tel.answer_delta("the same words here", "the same words here")
        self.assertEqual(out["word_overlap"], 1.0)
        self.assertFalse(out["materially_changed"])

    def test_a_genuinely_different_answer_is_material(self):
        out = tel.answer_delta("sleep is the limiting factor this week",
                               "your spending on dining doubled since June")
        self.assertTrue(out["materially_changed"])

    def test_light_polishing_is_not_counted_as_material(self):
        base = "your weight is down four pounds since the start of August and holding"
        out = tel.answer_delta(base, base + " steadily")
        self.assertFalse(out["materially_changed"])

    def test_eligibility_is_recorded_even_when_phase_two_did_not_run(self):
        rec = tel.build_turn_telemetry(sections={}, tools=[], tools_called=[],
                                       synthesis_eligible=True, synthesis_used=False)
        self.assertTrue(rec["phase2"]["eligible"])
        self.assertFalse(rec["phase2"]["used"])

    def test_evidence_truncation_is_counted(self):
        """Phase 2 sees ONLY what render_evidence emits, and a cap once landed exactly on
        the decisive sentence of a retrieval. Truncations are therefore a first-class
        counter, not a footnote."""
        from apps.ai.model_interface import synthesis as syn

        class _NoProvider:
            """Has a client (so the function proceeds past its guard) that refuses to
            call one (so this test can never reach a provider)."""
            model = "test"

            @property
            def client(self):
                class _C:
                    def __getattr__(self, _):
                        raise RuntimeError("no provider call in tests")
                return _C()

        metrics = {}
        long_value = "x" * (syn._ENTITY_VALUE_CAP + 500)
        syn.run_executive_synthesis(
            _NoProvider(), message="q",
            evidence=[{"tool": "get_entity", "result": {"entity": {"standing": {
                "note": long_value}}}}],
            standing_context={}, metrics=metrics)
        self.assertGreaterEqual(metrics.get("truncations", 0), 1)
        self.assertGreater(metrics.get("evidence_chars", 0), 0)

    def test_lost_context_keys_are_named_because_they_are_actionable(self):
        rec = tel.build_turn_telemetry(
            sections={}, tools=[], tools_called=[],
            coverage={"phase1_keys": ["a", "b", "c"], "carried": ["a"],
                      "intentionally_omitted": ["c"], "silently_lost": ["b"]})
        self.assertEqual(rec["coverage"]["silently_lost"], ["b"])
        self.assertEqual(rec["coverage"]["phase1_keys"], 3)


class PromptAssemblyTests(TestCase):
    """The refactor that made measurement possible must not have changed the prompt."""

    def setUp(self):
        self.user = User.objects.create_user(email="tel@contract.test", password="x")

    def _svc(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        return ModelInterfaceService(self.user)

    def test_joining_the_sections_reproduces_the_system_prompt_exactly(self):
        svc = self._svc()
        ctx = svc.build_standing_context()
        self.assertEqual("".join(svc._prompt_sections(ctx).values()),
                         svc._system_prompt(ctx))

    def test_the_constitution_is_still_the_first_section(self):
        from apps.ai.model_interface.constitution import CONSTITUTION
        svc = self._svc()
        sections = svc._prompt_sections(svc.build_standing_context())
        self.assertEqual(list(sections)[0], "constitution")
        self.assertEqual(sections["constitution"], CONSTITUTION)

    def test_the_completion_reminder_is_still_last(self):
        svc = self._svc()
        sections = svc._prompt_sections(svc.build_standing_context())
        self.assertEqual(list(sections)[-1], "completion_reminder")


class TurnRecordingTests(TestCase):
    """A real turn writes the measurement onto the audit row it already writes."""

    def setUp(self):
        self.user = User.objects.create_user(email="telturn@contract.test", password="x")

    def test_a_turn_records_telemetry_on_its_response_audit_row(self):
        from unittest import mock
        from apps.ai.model_interface.service import ModelInterfaceService
        from apps.ai.models import AssistantConversation, ToolCallLog

        conv = AssistantConversation.get_or_create_active(self.user)
        svc = ModelInterfaceService(self.user)

        def _fake(*a, **kw):
            metrics = kw.get("metrics")
            if metrics is not None:
                metrics.update({"rounds_used": 1, "max_rounds": 6})
            return "an answer"

        with mock.patch.object(svc.ai, "_call_api_with_tools", side_effect=_fake):
            svc.generate(conv, "hello")

        row = ToolCallLog.objects.filter(user=self.user, kind="response").latest("id")
        record = (row.result_digest or {}).get("telemetry") or {}
        self.assertGreater(record["prompt_chars"]["constitution"], 10000,
                           "the prompt was not measured")
        self.assertGreater(record["tools"]["tools_exposed"], 10)
        self.assertEqual(record["loop"]["rounds_used"], 1)
        self.assertFalse(record["phase2"]["used"])

    def test_a_broken_measurement_never_breaks_a_turn(self):
        from unittest import mock
        from apps.ai.model_interface.service import ModelInterfaceService
        from apps.ai.models import AssistantConversation

        conv = AssistantConversation.get_or_create_active(self.user)
        svc = ModelInterfaceService(self.user)
        with mock.patch.object(svc.ai, "_call_api_with_tools", return_value="an answer"), \
             mock.patch("apps.ai.model_interface.telemetry.build_turn_telemetry",
                        side_effect=RuntimeError("measurement exploded")):
            out = svc.generate(conv, "hello")
        self.assertEqual(out["answer"], "an answer")
