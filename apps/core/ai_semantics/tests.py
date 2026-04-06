"""
SUE -- Semantic Understanding Engine Tests.

Tests cover:
- Semantic parser (intent detection, entity extraction, time detection)
- Entity resolver (priority chain: context → SLCME → SAE → DB)
- Ambiguity engine (intent, entity, multi-intent, missing entities)
- Confidence engine (composite scoring, thresholds)
- Semantic engine (full interpret() pipeline)
- Semantic logger (decision logging)
- Model creation and admin
- UAIO integration (SUE in orchestrator pipeline)
"""

from datetime import date

from django.conf import settings
from django.test import TestCase

from apps.users.models import User


class SemanticParserTest(TestCase):
    """Test the semantic parser (pure function, no DB)."""

    def test_parse_empty_input(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("")
        self.assertEqual(result.intent_candidates, [])
        self.assertEqual(result.entities, {})
        self.assertFalse(result.has_time)

    def test_parse_none_input(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse(None)
        self.assertEqual(result.intent_candidates, [])

    def test_parse_weight_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log my weight to 175 lbs")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "log_weight")
        self.assertEqual(result.primary_intent.domain, "health")
        self.assertGreaterEqual(result.primary_intent.confidence, 0.70)

    def test_parse_weight_with_unit_entity(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("I weighed 175 lbs yesterday")
        self.assertIn("value", result.entities)
        self.assertEqual(result.entities["value"], 175.0)
        self.assertEqual(result.entities["unit"], "lb")

    def test_parse_weight_kg(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log weight 80 kg")
        self.assertIn("value", result.entities)
        self.assertEqual(result.entities["value"], 80.0)
        self.assertEqual(result.entities["unit"], "kg")

    def test_parse_blood_pressure_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log blood pressure 120/80")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "log_blood_pressure")
        self.assertIn("systolic", result.entities)
        self.assertEqual(result.entities["systolic"], 120)
        self.assertEqual(result.entities["diastolic"], 80)

    def test_parse_prayer_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log a prayer for my family")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "log_prayer")
        self.assertEqual(result.primary_intent.domain, "faith")

    def test_parse_goal_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("create a goal to lose 20 pounds")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "create_goal")
        self.assertEqual(result.primary_intent.domain, "purpose")

    def test_parse_habit_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("mark my habit as completed")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "log_habit")

    def test_parse_task_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("create a task to buy groceries")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "create_task")
        self.assertEqual(result.primary_intent.domain, "life")

    def test_parse_journal_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("write a journal entry about my day")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "create_journal_entry")
        self.assertEqual(result.primary_intent.domain, "journal")

    def test_parse_medicine_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("I took my medicine this morning")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "take_medication")

    def test_parse_fasting_start(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("start a fast")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "start_fast")

    def test_parse_fasting_end(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("end my fast")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "end_fast")

    def test_parse_save_verse(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("save this verse from Psalm 23")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "save_verse")

    def test_parse_workout_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log my workout for today")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "log_workout")

    def test_parse_time_expression_yesterday(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log weight 175 yesterday")
        self.assertTrue(result.has_time)
        self.assertEqual(result.time_expression.lower(), "yesterday")

    def test_parse_time_expression_last_monday(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("I weighed 175 last Monday")
        self.assertTrue(result.has_time)
        self.assertIn("last monday", result.time_expression.lower())

    def test_parse_time_expression_date(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log weight 175 on 2/10")
        self.assertTrue(result.has_time)

    def test_parse_no_time(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log weight 175")
        self.assertFalse(result.has_time)

    def test_parse_contextual_reference_that_goal(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("update that goal")
        self.assertTrue(result.has_contextual_reference)
        self.assertIn("that goal", [r.lower() for r in result.contextual_references])

    def test_parse_contextual_reference_it(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("complete it")
        self.assertTrue(result.has_contextual_reference)

    def test_parse_no_contextual_reference(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log weight 175 lbs")
        self.assertFalse(result.has_contextual_reference)

    def test_parse_multiple_candidates(self):
        """Text that matches multiple intents returns multiple candidates."""
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("record my weight and log a prayer")
        self.assertGreater(len(result.intent_candidates), 1)

    def test_parse_domain_hint(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log weight 175 lbs")
        self.assertEqual(result.domain_hint, "health")

    def test_parse_percentage_entity(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("body fat is 15.5%")
        self.assertIn("percentage", result.entities)
        self.assertEqual(result.entities["percentage"], 15.5)

    def test_parse_duration_minutes(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log workout 45 minutes")
        self.assertIn("duration_minutes", result.entities)
        self.assertEqual(result.entities["duration_minutes"], 45)

    def test_parse_heart_rate_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log heart rate 72 bpm")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "log_heart_rate")

    def test_parse_glucose_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log blood sugar 110")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "log_glucose")

    def test_parse_food_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("I ate a chicken sandwich for lunch")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "log_food")

    def test_parse_gratitude_intent(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("add gratitude for my health")
        self.assertIsNotNone(result.primary_intent)
        self.assertEqual(result.primary_intent.intent_type, "add_gratitude")

    def test_parse_result_to_dict(self):
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("log weight 175 lbs yesterday")
        d = result.to_dict()
        self.assertIn("primary_intent", d)
        self.assertIn("entities", d)
        self.assertIn("time_expression", d)

    def test_conversational_input_no_intent(self):
        """Conversational text should not match any intent."""
        from apps.core.ai_semantics.semantic_parser import parse

        result = parse("how are you today?")
        # May or may not have candidates, but primary should be None or low confidence
        if result.primary_intent:
            self.assertLess(result.primary_intent.confidence, 0.85)


class EntityResolverTest(TestCase):
    """Test entity resolution priority chain."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sue_entity@test.com",
            password="testpass123",
            date_of_birth=date(1990, 1, 1),
        )

    def test_resolve_empty_references(self):
        from apps.core.ai_semantics.entity_resolver import resolve_entities

        result = resolve_entities(self.user, [])
        self.assertEqual(result.resolved_entities, [])
        self.assertEqual(result.unresolved_references, [])

    def test_resolve_from_context_generic_ref(self):
        from apps.core.ai_semantics.entity_resolver import resolve_entities

        context = {
            "module": "purpose",
            "object_id": "42",
            "page_title": "My Big Goal",
        }
        result = resolve_entities(
            self.user, ["that one"], domain_hint="purpose", context=context
        )
        self.assertEqual(len(result.resolved_entities), 1)
        entity = result.resolved_entities[0]
        self.assertEqual(entity.entity_id, "42")
        self.assertEqual(entity.source, "context")
        self.assertTrue(result.used_context)

    def test_resolve_from_context_domain_ref(self):
        from apps.core.ai_semantics.entity_resolver import resolve_entities

        context = {
            "module": "purpose",
            "object_id": "99",
            "page_title": "Fitness Goal",
        }
        result = resolve_entities(
            self.user, ["that goal"], domain_hint="purpose", context=context
        )
        self.assertEqual(len(result.resolved_entities), 1)
        self.assertEqual(result.resolved_entities[0].entity_type, "goal")

    def test_resolve_prayer_from_context(self):
        from apps.core.ai_semantics.entity_resolver import resolve_entities

        context = {
            "module": "faith",
            "object_id": "7",
            "page_title": "Prayer for family",
        }
        result = resolve_entities(
            self.user, ["that prayer"], domain_hint="faith", context=context
        )
        self.assertEqual(len(result.resolved_entities), 1)
        self.assertEqual(result.resolved_entities[0].entity_type, "prayer")

    def test_unresolved_reference_no_context(self):
        from apps.core.ai_semantics.entity_resolver import resolve_entities

        result = resolve_entities(
            self.user, ["that goal"], domain_hint="purpose", context=None
        )
        # Without context, SLCME, or SAE data, should be unresolved
        # (SLCME will also fail since no learned mappings exist)
        self.assertGreater(len(result.unresolved_references), 0)

    def test_resolution_result_to_dict(self):
        from apps.core.ai_semantics.entity_resolver import resolve_entities

        result = resolve_entities(self.user, [])
        d = result.to_dict()
        self.assertIn("resolved", d)
        self.assertIn("unresolved", d)
        self.assertIn("sources", d)


class AmbiguityEngineTest(TestCase):
    """Test ambiguity detection."""

    def test_no_ambiguity_clear_intent(self):
        from apps.core.ai_semantics.ambiguity_engine import detect_ambiguity
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import parse

        parse_result = parse("log weight 175 lbs")
        entity_resolution = EntityResolutionResult()
        result = detect_ambiguity(parse_result, entity_resolution)
        self.assertFalse(result.is_ambiguous)

    def test_no_ambiguity_no_intent(self):
        from apps.core.ai_semantics.ambiguity_engine import detect_ambiguity
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import parse

        parse_result = parse("hello there")
        entity_resolution = EntityResolutionResult()
        result = detect_ambiguity(parse_result, entity_resolution)
        self.assertFalse(result.is_ambiguous)

    def test_entity_ambiguity_unresolved_reference(self):
        from apps.core.ai_semantics.ambiguity_engine import detect_ambiguity
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import IntentCandidate, ParseResult

        # Simulate a context-aware intent with unresolved reference
        parse_result = ParseResult()
        parse_result.intent_candidates = [
            IntentCandidate("mark_prayer_answered", "faith", 0.85)
        ]
        parse_result.contextual_references = ["that prayer"]
        parse_result.raw_text = "mark that prayer answered"

        entity_resolution = EntityResolutionResult()
        entity_resolution.unresolved_references = ["that prayer"]

        result = detect_ambiguity(parse_result, entity_resolution)
        self.assertTrue(result.is_ambiguous)
        self.assertEqual(result.ambiguity_type, "entity")

    def test_missing_entity_detection(self):
        from apps.core.ai_semantics.ambiguity_engine import detect_ambiguity
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import IntentCandidate, ParseResult

        parse_result = ParseResult()
        parse_result.intent_candidates = [
            IntentCandidate("log_weight", "health", 0.85)
        ]
        parse_result.entities = {}  # No value extracted
        parse_result.raw_text = "log my weight"

        entity_resolution = EntityResolutionResult()
        result = detect_ambiguity(parse_result, entity_resolution)
        self.assertTrue(result.is_ambiguous)
        self.assertEqual(result.ambiguity_type, "insufficient_info")
        self.assertIn("value", result.missing_entities)

    def test_multi_intent_detection(self):
        from apps.core.ai_semantics.ambiguity_engine import detect_ambiguity
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import IntentCandidate, ParseResult

        # Use wider confidence gap so intent ambiguity doesn't trigger first
        parse_result = ParseResult()
        parse_result.intent_candidates = [
            IntentCandidate("log_weight", "health", 0.85),
            IntentCandidate("log_prayer", "faith", 0.70),
        ]
        parse_result.raw_text = "log weight and log a prayer"

        entity_resolution = EntityResolutionResult()
        result = detect_ambiguity(parse_result, entity_resolution)
        self.assertTrue(result.is_ambiguous)
        self.assertEqual(result.ambiguity_type, "multi_intent")

    def test_ambiguity_result_to_dict(self):
        from apps.core.ai_semantics.ambiguity_engine import AmbiguityResult

        result = AmbiguityResult()
        result.is_ambiguous = True
        result.ambiguity_type = "intent"
        d = result.to_dict()
        self.assertTrue(d["is_ambiguous"])
        self.assertEqual(d["ambiguity_type"], "intent")


class ConfidenceEngineTest(TestCase):
    """Test confidence scoring."""

    def test_high_confidence_clear_intent(self):
        from apps.core.ai_semantics.ambiguity_engine import AmbiguityResult
        from apps.core.ai_semantics.confidence_engine import compute_confidence
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import parse

        parse_result = parse("log weight 175 lbs")
        entity_resolution = EntityResolutionResult()
        ambiguity = AmbiguityResult()

        score = compute_confidence(parse_result, entity_resolution, ambiguity)
        self.assertGreater(score.overall, 0.60)
        self.assertTrue(score.intent_score > 0)

    def test_low_confidence_no_intent(self):
        from apps.core.ai_semantics.ambiguity_engine import AmbiguityResult
        from apps.core.ai_semantics.confidence_engine import compute_confidence
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import parse

        parse_result = parse("hello world")
        entity_resolution = EntityResolutionResult()
        ambiguity = AmbiguityResult()

        score = compute_confidence(parse_result, entity_resolution, ambiguity)
        self.assertLess(score.overall, 0.50)

    def test_ambiguity_reduces_confidence(self):
        from apps.core.ai_semantics.ambiguity_engine import AmbiguityResult
        from apps.core.ai_semantics.confidence_engine import compute_confidence
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import parse

        parse_result = parse("log weight 175 lbs")
        entity_resolution = EntityResolutionResult()

        # Without ambiguity
        no_ambiguity = AmbiguityResult()
        score_clear = compute_confidence(parse_result, entity_resolution, no_ambiguity)

        # With ambiguity
        with_ambiguity = AmbiguityResult()
        with_ambiguity.is_ambiguous = True
        with_ambiguity.ambiguity_type = "intent"
        score_ambiguous = compute_confidence(parse_result, entity_resolution, with_ambiguity)

        self.assertGreater(score_clear.overall, score_ambiguous.overall)

    def test_safe_to_execute_threshold(self):
        from apps.core.ai_semantics.ambiguity_engine import AmbiguityResult
        from apps.core.ai_semantics.confidence_engine import (
            SAFE_EXECUTION_THRESHOLD,
            compute_confidence,
        )
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import parse

        parse_result = parse("log weight 175 lbs")
        entity_resolution = EntityResolutionResult()
        ambiguity = AmbiguityResult()

        score = compute_confidence(parse_result, entity_resolution, ambiguity)
        # If overall >= threshold and not ambiguous, should be safe
        if score.overall >= SAFE_EXECUTION_THRESHOLD:
            self.assertTrue(score.is_safe_to_execute)

    def test_ambiguous_never_safe(self):
        from apps.core.ai_semantics.ambiguity_engine import AmbiguityResult
        from apps.core.ai_semantics.confidence_engine import compute_confidence
        from apps.core.ai_semantics.entity_resolver import EntityResolutionResult
        from apps.core.ai_semantics.semantic_parser import parse

        parse_result = parse("log weight 175 lbs")
        entity_resolution = EntityResolutionResult()
        ambiguity = AmbiguityResult()
        ambiguity.is_ambiguous = True
        ambiguity.ambiguity_type = "intent"

        score = compute_confidence(parse_result, entity_resolution, ambiguity)
        self.assertFalse(score.is_safe_to_execute)

    def test_confidence_to_dict(self):
        from apps.core.ai_semantics.confidence_engine import ConfidenceScore

        score = ConfidenceScore()
        score.overall = 0.85
        score.is_safe_to_execute = True
        d = score.to_dict()
        self.assertIn("overall", d)
        self.assertIn("is_safe_to_execute", d)


class SemanticEngineTest(TestCase):
    """Test the full interpret() pipeline."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sue_engine@test.com",
            password="testpass123",
            date_of_birth=date(1990, 1, 1),
        )

    def test_interpret_clear_weight_log(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        result = interpret(self.user, "log weight 175 lbs")
        self.assertEqual(result.intent, "log_weight")
        self.assertEqual(result.domain, "health")
        self.assertIn("value", result.entities)
        self.assertGreater(result.confidence.overall, 0)

    def test_interpret_with_time(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        result = interpret(self.user, "log weight 175 yesterday")
        self.assertEqual(result.time_expression.lower(), "yesterday")

    def test_interpret_empty_input(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        result = interpret(self.user, "")
        self.assertEqual(result.intent, "")
        self.assertEqual(result.domain, "")

    def test_interpret_conversational(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        result = interpret(self.user, "how are you doing?")
        # Should either have no intent or low confidence
        self.assertLess(result.confidence.overall, 0.80)

    def test_interpret_with_context(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        context = {
            "module": "purpose",
            "object_id": "42",
            "page_title": "My Big Goal",
        }
        result = interpret(self.user, "update that goal", context=context)
        self.assertEqual(result.intent, "update_goal_progress")

    def test_interpret_result_to_dict(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        result = interpret(self.user, "log weight 175 lbs")
        d = result.to_dict()
        self.assertIn("intent", d)
        self.assertIn("domain", d)
        self.assertIn("confidence", d)
        self.assertIn("is_ambiguous", d)

    def test_interpret_prayer_log(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        result = interpret(self.user, "log a prayer for healing")
        self.assertEqual(result.intent, "log_prayer")
        self.assertEqual(result.domain, "faith")

    def test_interpret_create_task(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        result = interpret(self.user, "create a task to call the doctor")
        self.assertEqual(result.intent, "create_task")
        self.assertEqual(result.domain, "life")

    def test_interpret_blood_pressure(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        result = interpret(self.user, "log bp 120/80")
        self.assertEqual(result.intent, "log_blood_pressure")
        self.assertIn("systolic", result.entities)

    def test_interpret_logs_decision(self):
        """interpret() should create a SemanticDecisionLog entry."""
        from apps.core.ai_semantics.semantic_engine import interpret
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        initial_count = SemanticDecisionLog.objects.count()
        interpret(self.user, "log weight 175 lbs")
        self.assertEqual(SemanticDecisionLog.objects.count(), initial_count + 1)

    def test_interpret_sets_decision_log_id(self):
        from apps.core.ai_semantics.semantic_engine import interpret

        result = interpret(self.user, "log weight 175 lbs")
        self.assertIsNotNone(result.decision_log_id)


class SemanticLoggerTest(TestCase):
    """Test semantic decision logging."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sue_logger@test.com",
            password="testpass123",
            date_of_birth=date(1990, 1, 1),
        )

    def test_log_decision(self):
        from apps.core.ai_semantics.semantic_engine import interpret
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        result = interpret(self.user, "log weight 180 lbs")
        log = SemanticDecisionLog.objects.filter(user=self.user).latest("created_at")
        self.assertEqual(log.parsed_intent, "log_weight")
        self.assertEqual(log.parsed_domain, "health")
        self.assertGreater(log.overall_confidence, 0)

    def test_mark_decision_correct(self):
        from apps.core.ai_semantics.semantic_engine import interpret
        from apps.core.ai_semantics.semantic_logger import mark_decision_correct
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        result = interpret(self.user, "log weight 180 lbs")
        mark_decision_correct(result.decision_log_id, was_correct=True)
        log = SemanticDecisionLog.objects.get(id=result.decision_log_id)
        self.assertTrue(log.was_correct)

    def test_mark_decision_incorrect_with_correction(self):
        from apps.core.ai_semantics.semantic_engine import interpret
        from apps.core.ai_semantics.semantic_logger import mark_decision_correct
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        result = interpret(self.user, "log weight 180 lbs")
        mark_decision_correct(
            result.decision_log_id,
            was_correct=False,
            correction="log_heart_rate",
        )
        log = SemanticDecisionLog.objects.get(id=result.decision_log_id)
        self.assertFalse(log.was_correct)
        self.assertEqual(log.correction_applied, "log_heart_rate")


class SemanticModelTest(TestCase):
    """Test SemanticDecisionLog model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sue_model@test.com",
            password="testpass123",
            date_of_birth=date(1990, 1, 1),
        )

    def test_create_log_entry(self):
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        log = SemanticDecisionLog.objects.create(
            user=self.user,
            raw_text="log weight 175 lbs",
            parsed_intent="log_weight",
            parsed_domain="health",
            overall_confidence=0.85,
            intent_confidence=0.90,
            entity_confidence=0.80,
        )
        self.assertIsNotNone(log.id)
        self.assertEqual(log.parsed_intent, "log_weight")

    def test_str_representation(self):
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        log = SemanticDecisionLog.objects.create(
            user=self.user,
            raw_text="log weight 175 lbs",
            parsed_intent="log_weight",
            overall_confidence=0.85,
        )
        s = str(log)
        self.assertIn("log_weight", s)
        self.assertIn("85%", s)

    def test_model_indexes(self):
        """Verify model has expected indexes."""
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        meta = SemanticDecisionLog._meta
        index_field_names = []
        for index in meta.indexes:
            index_field_names.append(tuple(index.fields))
        self.assertIn(("user", "-created_at"), index_field_names)
        self.assertIn(("parsed_intent", "-created_at"), index_field_names)

    def test_default_values(self):
        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        log = SemanticDecisionLog.objects.create(
            user=self.user,
            raw_text="test input",
        )
        self.assertEqual(log.overall_confidence, 0.0)
        self.assertFalse(log.is_ambiguous)
        self.assertIsNone(log.was_correct)
        self.assertEqual(log.parsed_entities, {})
        self.assertEqual(log.alternative_intents, [])


class AdminTest(TestCase):
    """Test admin registration."""

    def test_semantic_decision_log_registered(self):
        from django.contrib import admin

        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        self.assertIn(SemanticDecisionLog, admin.site._registry)

    def test_admin_is_read_only(self):
        from django.contrib import admin

        from apps.core.ai_semantics.semantic_models import SemanticDecisionLog

        model_admin = admin.site._registry[SemanticDecisionLog]
        self.assertFalse(model_admin.has_add_permission(None))
        self.assertFalse(model_admin.has_change_permission(None))
        self.assertFalse(model_admin.has_delete_permission(None))


class UaioIntegrationTest(TestCase):
    """Test SUE integration with UAIO orchestrator."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sue_uaio@test.com",
            password="testpass123",
            date_of_birth=date(1990, 1, 1),
        )
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_process_user_input_includes_semantic_result(self):
        from apps.core.ai_orchestrator.orchestrator import process_user_input

        result = process_user_input(self.user, "log weight 175 lbs")
        self.assertIsNotNone(result._semantic_result)
        self.assertEqual(result._semantic_result.intent, "log_weight")

    def test_process_user_input_no_semantic_for_empty(self):
        from apps.core.ai_orchestrator.orchestrator import process_user_input

        result = process_user_input(self.user, "hello there")
        # Should still succeed -- SUE not finding an intent doesn't fail the pipeline
        # The pipeline returns success=True because time/context didn't need clarification
        self.assertIsNotNone(result._semantic_result)

    def test_orchestrator_result_has_semantic_slot(self):
        from apps.core.ai_orchestrator.orchestrator import OrchestratorResult

        result = OrchestratorResult()
        self.assertIsNone(result._semantic_result)

    def test_sue_failure_does_not_break_pipeline(self):
        """If SUE throws an exception, the pipeline should still work."""
        from unittest.mock import patch

        from apps.core.ai_orchestrator.orchestrator import process_user_input

        with patch(
            "apps.core.ai_orchestrator.orchestrator._run_semantic_understanding",
            side_effect=Exception("SUE crashed"),
        ):
            # Should not raise
            result = process_user_input(self.user, "log weight 175")
            # Pipeline continues without SUE
            self.assertTrue(result.success or result.needs_clarification or result.error)


class PublicApiTest(TestCase):
    """Test the public API exposed via __init__.py."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sue_api@test.com",
            password="testpass123",
            date_of_birth=date(1990, 1, 1),
        )

    def test_import_interpret(self):
        from apps.core.ai_semantics import interpret

        self.assertTrue(callable(interpret))

    def test_interpret_returns_semantic_result(self):
        from apps.core.ai_semantics import interpret
        from apps.core.ai_semantics.semantic_engine import SemanticResult

        result = interpret(self.user, "log weight 175 lbs")
        self.assertIsInstance(result, SemanticResult)
