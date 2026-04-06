"""
Test suite for Unified AI Orchestrator (UAIO).
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytz
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.ai_memory.models import ContextSnapshot, LearnedMapping
from apps.core.ai_orchestrator.action_router import EnrichedAction, route_action
from apps.core.ai_orchestrator.audit_logger import log_interaction
from apps.core.ai_orchestrator.context_pipeline import resolve_context_pipeline
from apps.core.ai_orchestrator.intent_engine import (
    get_intent_module,
    is_context_aware,
    is_time_aware,
)
from apps.core.ai_orchestrator.learning_pipeline import learn_from_interaction
from apps.core.ai_orchestrator.orchestrator import (
    OrchestratorResult,
    enrich_and_execute,
    process_user_input,
)
from apps.core.ai_orchestrator.response_builder import build_response
from apps.core.ai_orchestrator.safety_engine import SafetyResult, validate_action
from apps.core.ai_orchestrator.time_pipeline import (
    enrich_parameters_with_time,
    resolve_time_pipeline,
)
from apps.core.time.resolver import ResolvedTime
from apps.users.models import User


REF_TIME = datetime(2026, 2, 14, 10, 0, 0, tzinfo=pytz.UTC)


class OrchestratorTestMixin:
    """Common setup for orchestrator tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="orchtest@example.com", password="testpass123"
        )


# ─── Intent Engine Tests ───


class IntentEngineTests(TestCase):
    def test_health_intents(self):
        self.assertEqual(get_intent_module("log_weight"), "health")
        self.assertEqual(get_intent_module("log_heart_rate"), "health")
        self.assertEqual(get_intent_module("log_glucose"), "health")

    def test_faith_intents(self):
        self.assertEqual(get_intent_module("log_prayer"), "faith")
        self.assertEqual(get_intent_module("save_verse"), "faith")

    def test_purpose_intents(self):
        self.assertEqual(get_intent_module("create_goal"), "purpose")

    def test_life_intents(self):
        self.assertEqual(get_intent_module("create_task"), "life")
        self.assertEqual(get_intent_module("create_event"), "life")

    def test_unknown_intent(self):
        self.assertEqual(get_intent_module("unknown_thing"), "unknown")

    def test_time_aware_intents(self):
        self.assertTrue(is_time_aware("log_weight"))
        self.assertTrue(is_time_aware("log_heart_rate"))
        self.assertTrue(is_time_aware("take_medication"))
        self.assertFalse(is_time_aware("create_task"))
        self.assertFalse(is_time_aware("create_event"))

    def test_context_aware_intents(self):
        self.assertTrue(is_context_aware("save_verse"))
        self.assertTrue(is_context_aware("complete_task"))
        self.assertFalse(is_context_aware("log_weight"))


# ─── Time Pipeline Tests ───


class TimePipelineTests(TestCase):
    @patch("apps.core.ai_orchestrator.time_pipeline.interpret_human_time")
    def test_resolve_time_success(self, mock_interpret):
        from apps.core.time.interpreter import InterpretationResult

        mock_interpret.return_value = InterpretationResult(
            success=True,
            resolved_time=ResolvedTime(REF_TIME, "3 days ago"),
            original_input="weight 250 3 days ago",
            time_expression="3 days ago",
            remaining_text="weight 250",
        )

        result = resolve_time_pipeline("weight 250 3 days ago")
        self.assertTrue(result.success)
        mock_interpret.assert_called_once()

    @patch("apps.core.ai_orchestrator.time_pipeline.interpret_human_time")
    def test_resolve_time_with_timezone(self, mock_interpret):
        from apps.core.time.interpreter import InterpretationResult

        mock_interpret.return_value = InterpretationResult(success=False)
        resolve_time_pipeline("test", user_timezone="America/New_York")
        mock_interpret.assert_called_with("test", user_timezone="America/New_York")

    def test_enrich_parameters_with_time(self):
        from apps.core.time.interpreter import InterpretationResult

        params = {"value": 250, "unit": "lb"}
        time_result = InterpretationResult(
            success=True,
            resolved_time=ResolvedTime(REF_TIME, "3 days ago"),
            time_expression="3 days ago",
        )

        enriched = enrich_parameters_with_time(params, time_result)
        self.assertEqual(enriched["recorded_at"], REF_TIME)
        self.assertEqual(enriched["_time_expression"], "3 days ago")
        self.assertTrue(enriched["_time_resolved"])

    def test_enrich_parameters_no_time(self):
        from apps.core.time.interpreter import InterpretationResult

        params = {"value": 250, "unit": "lb"}
        time_result = InterpretationResult(success=False)

        enriched = enrich_parameters_with_time(params, time_result)
        self.assertNotIn("recorded_at", enriched)
        self.assertNotIn("_time_resolved", enriched)


# ─── Context Pipeline Tests ───


class ContextPipelineTests(OrchestratorTestMixin, TestCase):
    def test_resolve_without_page_context(self):
        result = resolve_context_pipeline(self.user, "test input")
        self.assertFalse(result.resolved)

    def test_stores_page_context(self):
        page_context = {
            "url": "/faith/scripture/john-3/",
            "module": "faith",
            "page_title": "John 3",
        }
        resolve_context_pipeline(self.user, "test", page_context=page_context)
        snapshot = ContextSnapshot.objects.filter(user=self.user).first()
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.context_type, "scripture_page")

    def test_resolves_from_learned_mapping(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="test input",
            meaning_type="scripture",
            meaning_identifier="John 3:16",
            confidence_score=0.9,
            usage_count=5,
        )
        result = resolve_context_pipeline(self.user, "test input")
        self.assertTrue(result.resolved)


# ─── Action Router Tests ───


class ActionRouterTests(TestCase):
    def test_route_with_time(self):
        from apps.core.time.interpreter import InterpretationResult

        time_result = InterpretationResult(
            success=True,
            resolved_time=ResolvedTime(REF_TIME, "3 days ago"),
            time_expression="3 days ago",
        )

        action = route_action(
            "log_weight",
            {"value": 250, "unit": "lb"},
            time_result=time_result,
        )
        self.assertEqual(action.intent_type, "log_weight")
        self.assertEqual(action.module, "health")
        self.assertTrue(action.time_resolved)
        self.assertEqual(action.parameters["recorded_at"], REF_TIME)

    def test_route_without_time(self):
        action = route_action(
            "log_weight",
            {"value": 250, "unit": "lb"},
        )
        self.assertFalse(action.time_resolved)
        self.assertNotIn("recorded_at", action.parameters)

    def test_route_non_time_aware_intent(self):
        from apps.core.time.interpreter import InterpretationResult

        time_result = InterpretationResult(
            success=True,
            resolved_time=ResolvedTime(REF_TIME, "tomorrow"),
            time_expression="tomorrow",
        )

        # create_task is NOT time_aware, so time should not be enriched
        action = route_action(
            "create_task",
            {"title": "test"},
            time_result=time_result,
        )
        self.assertNotIn("recorded_at", action.parameters)

    def test_to_dict_excludes_internal_keys(self):
        action = EnrichedAction(
            "log_weight",
            {"value": 250, "_time_resolved": True, "_internal": "hidden"},
        )
        d = action.to_dict()
        self.assertIn("value", d["parameters"])
        self.assertNotIn("_time_resolved", d["parameters"])
        self.assertNotIn("_internal", d["parameters"])


# ─── Safety Engine Tests ───


class SafetyEngineTests(TestCase):
    def test_safe_action(self):
        action = EnrichedAction("log_weight", {"value": 250, "unit": "lb"})
        result = validate_action(action)
        self.assertTrue(result.is_safe)

    def test_too_old_timestamp(self):
        old_time = timezone.now() - timedelta(days=400)
        action = EnrichedAction(
            "log_weight",
            {"value": 250, "recorded_at": old_time, "_time_resolved": True},
        )
        result = validate_action(action)
        self.assertFalse(result.is_safe)
        self.assertEqual(result.reason, "timestamp_too_old")

    def test_future_timestamp_for_log(self):
        future_time = timezone.now() + timedelta(days=5)
        action = EnrichedAction(
            "log_weight",
            {"value": 250, "recorded_at": future_time, "_time_resolved": True},
        )
        result = validate_action(action)
        self.assertFalse(result.is_safe)
        self.assertEqual(result.reason, "future_timestamp_for_log")

    def test_future_timestamp_ok_for_scheduling(self):
        future_time = timezone.now() + timedelta(days=5)
        action = EnrichedAction(
            "create_event",
            {"title": "test", "recorded_at": future_time, "_time_resolved": True},
        )
        result = validate_action(action)
        self.assertTrue(result.is_safe)


# ─── Learning Pipeline Tests ───


class LearningPipelineTests(OrchestratorTestMixin, TestCase):
    def test_learn_from_clarification(self):
        from apps.ai.intent_service import ActionResult

        action_result = ActionResult(success=True, message="Done")
        clarification = {
            "phrase": "the scripture",
            "meaning_type": "scripture",
            "meaning_identifier": "John 3:16",
            "question": "Which scripture?",
            "response": "John 3:16",
        }

        learn_from_interaction(
            self.user, "explain the scripture", action_result,
            clarification_data=clarification,
        )

        mapping = LearnedMapping.objects.filter(user=self.user).first()
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.meaning_identifier, "John 3:16")

    def test_no_clarification_no_mapping(self):
        from apps.ai.intent_service import ActionResult

        action_result = ActionResult(success=True, message="Done")
        learn_from_interaction(self.user, "log weight 250", action_result)

        self.assertEqual(
            LearnedMapping.objects.filter(user=self.user).count(), 0
        )


# ─── Response Builder Tests ───


class ResponseBuilderTests(TestCase):
    def test_clarification_response(self):
        result = OrchestratorResult(
            needs_clarification=True,
            clarification_question="Which date did you mean?",
        )
        response = build_response(result)
        self.assertEqual(response, "Which date did you mean?")

    def test_no_actions_returns_none(self):
        result = OrchestratorResult(success=True)
        response = build_response(result)
        self.assertIsNone(response)

    def test_action_with_time_context(self):
        from apps.ai.intent_service import ActionResult

        action_result = ActionResult(
            success=True, message="Logged weight: 250 lb"
        )
        enriched = EnrichedAction(
            "log_weight",
            {
                "_time_expression": "3 days ago",
                "recorded_at": datetime(2026, 2, 11, 10, 0, 0, tzinfo=pytz.UTC),
                "_time_resolved": True,
            },
        )

        result = OrchestratorResult(
            success=True,
            actions_enriched=[enriched],
            action_results=[action_result],
        )
        response = build_response(result)
        self.assertIn("February 11, 2026", response)


# ─── Orchestrator Integration Tests ───


class OrchestratorTests(OrchestratorTestMixin, TestCase):
    @patch("apps.core.ai_orchestrator.orchestrator.resolve_time_pipeline")
    @patch("apps.core.ai_orchestrator.orchestrator.resolve_context_pipeline")
    def test_process_simple_input(self, mock_context, mock_time):
        from apps.core.ai_memory.memory_engine import MemoryResolution
        from apps.core.time.interpreter import InterpretationResult

        mock_context.return_value = MemoryResolution(resolved=False)
        mock_time.return_value = InterpretationResult(
            success=False, error="No time expression"
        )

        result = process_user_input(self.user, "hello there")
        self.assertTrue(result.success)
        self.assertFalse(result.time_resolved)
        self.assertFalse(result.context_resolved)

    @patch("apps.core.ai_orchestrator.orchestrator.resolve_time_pipeline")
    @patch("apps.core.ai_orchestrator.orchestrator.resolve_context_pipeline")
    def test_process_with_time(self, mock_context, mock_time):
        from apps.core.ai_memory.memory_engine import MemoryResolution
        from apps.core.time.interpreter import InterpretationResult

        mock_context.return_value = MemoryResolution(resolved=False)
        mock_time.return_value = InterpretationResult(
            success=True,
            resolved_time=ResolvedTime(REF_TIME, "3 days ago"),
            time_expression="3 days ago",
        )

        result = process_user_input(self.user, "weight 250 3 days ago")
        self.assertTrue(result.success)
        self.assertTrue(result.time_resolved)

    @patch("apps.core.ai_orchestrator.orchestrator.resolve_time_pipeline")
    @patch("apps.core.ai_orchestrator.orchestrator.resolve_context_pipeline")
    def test_process_ambiguous_time(self, mock_context, mock_time):
        from apps.core.ai_memory.memory_engine import MemoryResolution
        from apps.core.time.interpreter import InterpretationResult

        mock_context.return_value = MemoryResolution(resolved=False)
        mock_time.return_value = InterpretationResult(
            success=False,
            is_ambiguous=True,
            clarification_question="Did you mean today or next week?",
        )

        result = process_user_input(self.user, "next saturday")
        self.assertFalse(result.success)
        self.assertTrue(result.needs_clarification)
        self.assertEqual(result.clarification_source, "time")

    @patch("apps.core.ai_orchestrator.orchestrator.resolve_time_pipeline")
    @patch("apps.core.ai_orchestrator.orchestrator.resolve_context_pipeline")
    def test_process_context_confirmation(self, mock_context, mock_time):
        from apps.core.ai_memory.memory_engine import MemoryResolution
        from apps.core.time.interpreter import InterpretationResult

        mock_context.return_value = MemoryResolution(
            resolved=False,
            needs_confirmation=True,
            confirmation_question='Did you mean "John 3:16"?',
        )
        mock_time.return_value = InterpretationResult(success=False)

        result = process_user_input(self.user, "explain the scripture")
        self.assertFalse(result.success)
        self.assertTrue(result.needs_clarification)
        self.assertEqual(result.clarification_source, "context")

    def test_to_dict_success(self):
        result = OrchestratorResult(
            success=True,
            time_resolved=True,
            context_resolved=False,
        )
        d = result.to_dict()
        self.assertTrue(d["success"])
        self.assertTrue(d["time_resolved"])

    def test_to_dict_clarification(self):
        result = OrchestratorResult(
            success=False,
            needs_clarification=True,
            clarification_question="Which date?",
            clarification_source="time",
        )
        d = result.to_dict()
        self.assertTrue(d["needs_clarification"])
        self.assertEqual(d["clarification_source"], "time")


# ─── Audit Logger Tests ───


class AuditLoggerTests(OrchestratorTestMixin, TestCase):
    def test_log_interaction_no_errors(self):
        """Audit logging should never raise exceptions."""
        result = OrchestratorResult(
            success=True,
            time_resolved=False,
            context_resolved=False,
            needs_clarification=False,
        )
        # Should not raise
        log_interaction(self.user, "test input", result)

    def test_log_interaction_with_clarification(self):
        result = OrchestratorResult(
            success=False,
            needs_clarification=True,
            clarification_question="Which date?",
        )
        # Should not raise
        log_interaction(self.user, "test", result)
