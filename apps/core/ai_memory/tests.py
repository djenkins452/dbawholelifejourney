"""
Test suite for Self-Learning Context Memory Engine (SLCME).
"""

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_memory.confidence_engine import (
    CONFIDENCE_THRESHOLD,
    get_confidence_level,
    is_safe_to_use,
    needs_confirmation,
)
from apps.core.ai_memory.context_resolver import (
    clear_context,
    get_all_current_contexts,
    get_current_context,
    store_context_snapshot,
)
from apps.core.ai_memory.learning_engine import (
    INITIAL_CONFIDENCE,
    deactivate_mapping,
    log_clarification,
    record_usage,
    store_learned_mapping,
)
from apps.core.ai_memory.memory_engine import MemoryResolution, resolve_context
from apps.core.ai_memory.models import (
    ClarificationLog,
    ContextSnapshot,
    LearnedMapping,
)
from apps.core.ai_memory.retrieval_engine import (
    find_learned_mapping,
    find_mappings_by_type,
    find_similar_mappings,
)
from apps.users.models import User


class SLCMETestMixin:
    """Common setup for SLCME tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="testuser@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            email="otheruser@example.com", password="testpass123"
        )


# ─── Model Tests ───


class LearnedMappingModelTests(SLCMETestMixin, TestCase):
    def test_create_mapping(self):
        mapping = LearnedMapping.objects.create(
            user=self.user,
            phrase="the scripture",
            meaning_type="scripture",
            meaning_identifier="John 3:16",
        )
        self.assertEqual(mapping.confidence_score, 0.8)
        self.assertEqual(mapping.usage_count, 1)
        self.assertTrue(mapping.is_active)

    def test_str_representation(self):
        mapping = LearnedMapping.objects.create(
            user=self.user,
            phrase="my goal",
            meaning_type="goal",
            meaning_identifier="goal:42",
        )
        self.assertIn("my goal", str(mapping))
        self.assertIn("goal:42", str(mapping))

    def test_ordering(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="test1",
            meaning_type="test",
            meaning_identifier="1",
            confidence_score=0.5,
        )
        LearnedMapping.objects.create(
            user=self.user,
            phrase="test2",
            meaning_type="test",
            meaning_identifier="2",
            confidence_score=0.9,
        )
        mappings = list(LearnedMapping.objects.filter(user=self.user))
        self.assertEqual(mappings[0].phrase, "test2")  # Higher confidence first


class ContextSnapshotModelTests(SLCMETestMixin, TestCase):
    def test_create_snapshot(self):
        snapshot = ContextSnapshot.objects.create(
            user=self.user,
            context_type="scripture_page",
            context_identifier="John 3",
            metadata={"chapter": 3, "book": "John"},
        )
        self.assertEqual(snapshot.context_type, "scripture_page")
        self.assertEqual(snapshot.metadata["book"], "John")

    def test_str_representation(self):
        snapshot = ContextSnapshot.objects.create(
            user=self.user,
            context_type="goal",
            context_identifier="goal:42",
        )
        self.assertIn("goal:42", str(snapshot))


class ClarificationLogModelTests(SLCMETestMixin, TestCase):
    def test_create_log(self):
        log = ClarificationLog.objects.create(
            user=self.user,
            original_input="explain the scripture",
            clarification_question="Which scripture?",
            user_response="John 3:16",
            resolved_meaning="scripture:John 3:16",
        )
        self.assertIsNotNone(log.created_at)

    def test_log_with_mapping(self):
        mapping = LearnedMapping.objects.create(
            user=self.user,
            phrase="the scripture",
            meaning_type="scripture",
            meaning_identifier="John 3:16",
        )
        log = ClarificationLog.objects.create(
            user=self.user,
            original_input="explain the scripture",
            clarification_question="Which scripture?",
            user_response="John 3:16",
            resolved_meaning="scripture:John 3:16",
            learned_mapping=mapping,
        )
        self.assertEqual(log.learned_mapping, mapping)


# ─── Retrieval Engine Tests ───


class RetrievalEngineTests(SLCMETestMixin, TestCase):
    def test_find_exact_match(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="the scripture",
            meaning_type="scripture",
            meaning_identifier="John 3:16",
        )
        result = find_learned_mapping(self.user, "the scripture")
        self.assertIsNotNone(result)
        self.assertEqual(result.meaning_identifier, "John 3:16")

    def test_case_insensitive_match(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="The Scripture",
            meaning_type="scripture",
            meaning_identifier="John 3:16",
        )
        result = find_learned_mapping(self.user, "the scripture")
        self.assertIsNotNone(result)

    def test_no_match(self):
        result = find_learned_mapping(self.user, "nonexistent phrase")
        self.assertIsNone(result)

    def test_empty_phrase(self):
        result = find_learned_mapping(self.user, "")
        self.assertIsNone(result)

    def test_none_phrase(self):
        result = find_learned_mapping(self.user, None)
        self.assertIsNone(result)

    def test_user_isolation(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="my goal",
            meaning_type="goal",
            meaning_identifier="goal:42",
        )
        # Other user should not find this mapping
        result = find_learned_mapping(self.other_user, "my goal")
        self.assertIsNone(result)

    def test_inactive_not_returned(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="old phrase",
            meaning_type="test",
            meaning_identifier="test:1",
            is_active=False,
        )
        result = find_learned_mapping(self.user, "old phrase")
        self.assertIsNone(result)

    def test_highest_confidence_returned(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="the goal",
            meaning_type="goal",
            meaning_identifier="goal:1",
            confidence_score=0.6,
        )
        LearnedMapping.objects.create(
            user=self.user,
            phrase="the goal",
            meaning_type="goal",
            meaning_identifier="goal:2",
            confidence_score=0.9,
        )
        result = find_learned_mapping(self.user, "the goal")
        self.assertEqual(result.meaning_identifier, "goal:2")

    def test_find_by_type(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="test1",
            meaning_type="scripture",
            meaning_identifier="Gen 1:1",
        )
        LearnedMapping.objects.create(
            user=self.user,
            phrase="test2",
            meaning_type="goal",
            meaning_identifier="goal:1",
        )
        results = find_mappings_by_type(self.user, "scripture")
        self.assertEqual(results.count(), 1)

    def test_find_similar(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="morning scripture",
            meaning_type="scripture",
            meaning_identifier="Psalm 23",
        )
        results = find_similar_mappings(self.user, "scripture")
        self.assertEqual(len(results), 1)


# ─── Learning Engine Tests ───


class LearningEngineTests(SLCMETestMixin, TestCase):
    def test_store_new_mapping(self):
        mapping = store_learned_mapping(
            self.user, "the scripture", "scripture", "John 3:16"
        )
        self.assertEqual(mapping.confidence_score, INITIAL_CONFIDENCE)
        self.assertEqual(mapping.usage_count, 1)
        self.assertIsNotNone(mapping.last_used_at)

    def test_reinforce_same_meaning(self):
        mapping1 = store_learned_mapping(
            self.user, "the scripture", "scripture", "John 3:16"
        )
        original_confidence = mapping1.confidence_score
        mapping2 = store_learned_mapping(
            self.user, "the scripture", "scripture", "John 3:16"
        )
        self.assertEqual(mapping2.pk, mapping1.pk)  # Same record
        self.assertEqual(mapping2.usage_count, 2)
        self.assertGreater(mapping2.confidence_score, original_confidence)

    def test_correct_meaning_resets_confidence(self):
        mapping1 = store_learned_mapping(
            self.user, "the scripture", "scripture", "John 3:16"
        )
        # User corrects — different meaning
        mapping2 = store_learned_mapping(
            self.user, "the scripture", "scripture", "Psalm 23"
        )
        self.assertEqual(mapping2.pk, mapping1.pk)
        self.assertEqual(mapping2.meaning_identifier, "Psalm 23")
        self.assertEqual(mapping2.confidence_score, INITIAL_CONFIDENCE)
        self.assertEqual(mapping2.usage_count, 1)

    def test_confidence_caps_at_max(self):
        mapping = store_learned_mapping(
            self.user, "test", "test", "test:1"
        )
        mapping.confidence_score = 0.99
        mapping.save()
        mapping = store_learned_mapping(
            self.user, "test", "test", "test:1"
        )
        self.assertLessEqual(mapping.confidence_score, 1.0)

    def test_record_usage(self):
        mapping = LearnedMapping.objects.create(
            user=self.user,
            phrase="test",
            meaning_type="test",
            meaning_identifier="test:1",
            confidence_score=0.8,
            usage_count=5,
        )
        record_usage(mapping)
        mapping.refresh_from_db()
        self.assertEqual(mapping.usage_count, 6)
        self.assertGreater(mapping.confidence_score, 0.8)
        self.assertIsNotNone(mapping.last_used_at)

    def test_deactivate_mapping(self):
        mapping = LearnedMapping.objects.create(
            user=self.user,
            phrase="old",
            meaning_type="test",
            meaning_identifier="test:1",
        )
        deactivate_mapping(mapping)
        mapping.refresh_from_db()
        self.assertFalse(mapping.is_active)

    def test_log_clarification(self):
        log = log_clarification(
            user=self.user,
            original_input="explain the scripture",
            question="Which scripture?",
            response="John 3:16",
            resolved="scripture:John 3:16",
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(
            ClarificationLog.objects.filter(user=self.user).count(), 1
        )

    def test_log_clarification_with_mapping(self):
        mapping = store_learned_mapping(
            self.user, "the scripture", "scripture", "John 3:16"
        )
        log = log_clarification(
            user=self.user,
            original_input="explain the scripture",
            question="Which scripture?",
            response="John 3:16",
            resolved="scripture:John 3:16",
            mapping=mapping,
        )
        self.assertEqual(log.learned_mapping, mapping)


# ─── Context Resolver Tests ───


class ContextResolverTests(SLCMETestMixin, TestCase):
    def test_store_and_retrieve_context(self):
        store_context_snapshot(
            self.user, "scripture_page", "John 3", {"chapter": 3}
        )
        result = get_current_context(self.user, "scripture_page")
        self.assertIsNotNone(result)
        self.assertEqual(result.context_identifier, "John 3")
        self.assertEqual(result.metadata["chapter"], 3)

    def test_latest_context_returned(self):
        store_context_snapshot(self.user, "scripture_page", "John 2")
        store_context_snapshot(self.user, "scripture_page", "John 3")
        result = get_current_context(self.user, "scripture_page")
        self.assertEqual(result.context_identifier, "John 3")

    def test_no_context_returns_none(self):
        result = get_current_context(self.user, "nonexistent")
        self.assertIsNone(result)

    def test_user_isolation(self):
        store_context_snapshot(self.user, "scripture_page", "John 3")
        result = get_current_context(self.other_user, "scripture_page")
        self.assertIsNone(result)

    def test_get_all_contexts(self):
        store_context_snapshot(self.user, "scripture_page", "John 3")
        store_context_snapshot(self.user, "goal", "goal:42")
        contexts = get_all_current_contexts(self.user)
        self.assertIn("scripture_page", contexts)
        self.assertIn("goal", contexts)

    def test_clear_context(self):
        store_context_snapshot(self.user, "scripture_page", "John 3")
        clear_context(self.user, "scripture_page")
        result = get_current_context(self.user, "scripture_page")
        self.assertIsNone(result)

    def test_clear_only_affects_specified_type(self):
        store_context_snapshot(self.user, "scripture_page", "John 3")
        store_context_snapshot(self.user, "goal", "goal:42")
        clear_context(self.user, "scripture_page")
        self.assertIsNone(get_current_context(self.user, "scripture_page"))
        self.assertIsNotNone(get_current_context(self.user, "goal"))


# ─── Confidence Engine Tests ───


class ConfidenceEngineTests(SLCMETestMixin, TestCase):
    def test_high_confidence_safe_to_use(self):
        mapping = LearnedMapping(
            confidence_score=0.9, usage_count=3, is_active=True
        )
        self.assertTrue(is_safe_to_use(mapping))

    def test_below_threshold_not_safe(self):
        mapping = LearnedMapping(
            confidence_score=0.5, usage_count=3, is_active=True
        )
        self.assertFalse(is_safe_to_use(mapping))

    def test_inactive_not_safe(self):
        mapping = LearnedMapping(
            confidence_score=0.9, usage_count=3, is_active=False
        )
        self.assertFalse(is_safe_to_use(mapping))

    def test_none_not_safe(self):
        self.assertFalse(is_safe_to_use(None))

    def test_needs_confirmation_medium(self):
        mapping = LearnedMapping(
            confidence_score=0.6, usage_count=2, is_active=True
        )
        self.assertTrue(needs_confirmation(mapping))

    def test_high_confidence_no_confirmation(self):
        mapping = LearnedMapping(
            confidence_score=0.9, usage_count=5, is_active=True
        )
        self.assertFalse(needs_confirmation(mapping))

    def test_low_confidence_no_confirmation(self):
        mapping = LearnedMapping(
            confidence_score=0.3, usage_count=1, is_active=True
        )
        self.assertFalse(needs_confirmation(mapping))

    def test_confidence_levels(self):
        high = LearnedMapping(confidence_score=0.9, is_active=True)
        medium = LearnedMapping(confidence_score=0.6, is_active=True)
        low = LearnedMapping(confidence_score=0.3, is_active=True)
        self.assertEqual(get_confidence_level(high), "high")
        self.assertEqual(get_confidence_level(medium), "medium")
        self.assertEqual(get_confidence_level(low), "low")
        self.assertEqual(get_confidence_level(None), "none")


# ─── Memory Engine Orchestrator Tests ───


class MemoryEngineTests(SLCMETestMixin, TestCase):
    def test_resolve_from_context(self):
        store_context_snapshot(
            self.user, "scripture_page", "John 3", {"book": "John"}
        )
        result = resolve_context(
            self.user, "the scripture", context_type_hint="scripture_page"
        )
        self.assertTrue(result.resolved)
        self.assertEqual(result.source, "context")
        self.assertEqual(result.meaning_identifier, "John 3")
        self.assertEqual(result.metadata["book"], "John")

    def test_resolve_from_learned_mapping(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="the scripture",
            meaning_type="scripture",
            meaning_identifier="John 3:16",
            confidence_score=0.9,
            usage_count=5,
        )
        result = resolve_context(self.user, "the scripture")
        self.assertTrue(result.resolved)
        self.assertEqual(result.source, "learned")
        self.assertEqual(result.meaning_identifier, "John 3:16")

    def test_learned_mapping_usage_incremented(self):
        mapping = LearnedMapping.objects.create(
            user=self.user,
            phrase="the scripture",
            meaning_type="scripture",
            meaning_identifier="John 3:16",
            confidence_score=0.9,
            usage_count=5,
        )
        resolve_context(self.user, "the scripture")
        mapping.refresh_from_db()
        self.assertEqual(mapping.usage_count, 6)

    def test_medium_confidence_needs_confirmation(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="the goal",
            meaning_type="goal",
            meaning_identifier="goal:42",
            confidence_score=0.6,
            usage_count=2,
        )
        result = resolve_context(self.user, "the goal")
        self.assertFalse(result.resolved)
        self.assertTrue(result.needs_confirmation)
        self.assertIsNotNone(result.confirmation_question)

    def test_no_mapping_returns_unresolved(self):
        result = resolve_context(self.user, "something unknown")
        self.assertFalse(result.resolved)
        self.assertIsNone(result.source)
        self.assertEqual(result.confidence, "none")

    def test_context_takes_priority_over_learned(self):
        # Both context and learned mapping exist
        store_context_snapshot(self.user, "scripture_page", "Psalm 23")
        LearnedMapping.objects.create(
            user=self.user,
            phrase="the scripture",
            meaning_type="scripture",
            meaning_identifier="John 3:16",
            confidence_score=0.9,
            usage_count=10,
        )
        result = resolve_context(
            self.user, "the scripture", context_type_hint="scripture_page"
        )
        # Context should win
        self.assertTrue(result.resolved)
        self.assertEqual(result.source, "context")
        self.assertEqual(result.meaning_identifier, "Psalm 23")

    def test_user_isolation(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="my goal",
            meaning_type="goal",
            meaning_identifier="goal:42",
            confidence_score=0.9,
            usage_count=5,
        )
        result = resolve_context(self.other_user, "my goal")
        self.assertFalse(result.resolved)

    def test_to_dict_resolved(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="test",
            meaning_type="test",
            meaning_identifier="test:1",
            confidence_score=0.9,
            usage_count=5,
        )
        result = resolve_context(self.user, "test")
        d = result.to_dict()
        self.assertTrue(d["resolved"])
        self.assertIn("meaning_type", d)
        self.assertIn("meaning_identifier", d)

    def test_to_dict_confirmation(self):
        LearnedMapping.objects.create(
            user=self.user,
            phrase="test",
            meaning_type="test",
            meaning_identifier="test:1",
            confidence_score=0.6,
            usage_count=2,
        )
        result = resolve_context(self.user, "test")
        d = result.to_dict()
        self.assertFalse(d["resolved"])
        self.assertTrue(d["needs_confirmation"])

    def test_to_dict_unresolved(self):
        result = resolve_context(self.user, "unknown")
        d = result.to_dict()
        self.assertFalse(d["resolved"])
        self.assertEqual(d["confidence"], "none")


# ─── Full Learning Loop Tests ───


class LearningLoopTests(SLCMETestMixin, TestCase):
    """Test the complete learn → remember → reuse cycle."""

    def test_full_learning_cycle(self):
        # Step 1: First time — no mapping exists
        result = resolve_context(self.user, "the scripture")
        self.assertFalse(result.resolved)

        # Step 2: After clarification, store the learned mapping
        mapping = store_learned_mapping(
            self.user, "the scripture", "scripture", "John 3:16"
        )
        self.assertEqual(mapping.confidence_score, INITIAL_CONFIDENCE)

        # Step 3: Log the clarification
        log = log_clarification(
            user=self.user,
            original_input="explain the scripture",
            question="Which scripture?",
            response="John 3:16",
            resolved="scripture:John 3:16",
            mapping=mapping,
        )
        self.assertIsNotNone(log.pk)

        # Step 4: Next time — mapping resolves automatically
        result = resolve_context(self.user, "the scripture")
        self.assertTrue(result.resolved)
        self.assertEqual(result.meaning_identifier, "John 3:16")
        self.assertEqual(result.source, "learned")

    def test_confidence_grows_over_time(self):
        mapping = store_learned_mapping(
            self.user, "my goal", "goal", "goal:42"
        )
        initial = mapping.confidence_score

        # Reuse multiple times
        for _ in range(5):
            resolve_context(self.user, "my goal")

        mapping.refresh_from_db()
        self.assertGreater(mapping.confidence_score, initial)
        self.assertEqual(mapping.usage_count, 6)  # 1 initial + 5 reuses

    def test_user_correction_relearns(self):
        # Learn initial meaning
        store_learned_mapping(
            self.user, "the scripture", "scripture", "John 3:16"
        )

        # User corrects — different scripture
        mapping = store_learned_mapping(
            self.user, "the scripture", "scripture", "Psalm 23"
        )
        self.assertEqual(mapping.meaning_identifier, "Psalm 23")
        self.assertEqual(mapping.confidence_score, INITIAL_CONFIDENCE)

        # Future lookups use corrected meaning
        result = resolve_context(self.user, "the scripture")
        self.assertTrue(result.resolved)
        self.assertEqual(result.meaning_identifier, "Psalm 23")
