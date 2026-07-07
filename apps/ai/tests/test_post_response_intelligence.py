# ==============================================================================
# File: apps/ai/tests/test_post_response_intelligence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 0A — canonical post-response evidence-writer contract tests
# ==============================================================================
"""
Scoped tests for the Phase 0A reconnection: the single canonical post-response
evidence-writer used by all conversational runtimes.

These verify the reconnection CONTRACT, not the individual extractors:
  - fail-open (one extractor raising never propagates or suppresses the rest)
  - correct delegation to each extractor with the expected arguments
  - correction is RECORDED only when detected (evidence-only; no read-back)
  - the legacy streaming shim and the CoS Celery task both delegate here
  - no references to the removed dead modules remain
"""

from unittest import mock

from django.test import SimpleTestCase


PRI = "apps.ai.post_response_intelligence"


def _fake_user():
    u = mock.MagicMock()
    u.id = 1
    return u


def _fake_conversation(prev_content="I recommended strength.", prev_id=42):
    conv = mock.MagicMock()
    prev = mock.MagicMock()
    prev.content = prev_content
    prev.id = prev_id
    conv.messages.filter.return_value.order_by.return_value.first.return_value = prev
    return conv, prev


class RunPostResponseIntelligenceTests(SimpleTestCase):
    def _patchers(self, detect_correction=False):
        """Patch every downstream extractor at its source module."""
        return {
            "extract_learning": mock.patch(
                "apps.core.ai_learning.learning_extractor.extract_learning"),
            "evolve_profile": mock.patch(
                "apps.core.ai_learning.learning_extractor.evolve_profile"),
            "detect_correction": mock.patch(
                "apps.ai.correction_service.detect_correction",
                return_value=detect_correction),
            "store_correction": mock.patch(
                "apps.ai.correction_service.store_correction"),
            "detect_patterns": mock.patch(
                "apps.ai.pattern_detector.detect_patterns"),
            "extract_life_facts": mock.patch(
                "apps.core.ai_memory.life_fact_extractor."
                "extract_life_facts_from_message"),
        }

    def test_noop_without_message(self):
        from apps.ai.post_response_intelligence import run_post_response_intelligence
        with self._patchers()["extract_learning"] as m:
            run_post_response_intelligence(_fake_user(), "", "resp", None)
            m.assert_not_called()

    def test_all_extractors_called_no_correction(self):
        from apps.ai.post_response_intelligence import run_post_response_intelligence
        ctx = self._patchers(detect_correction=False)
        with ctx["extract_learning"] as m_learn, \
                ctx["evolve_profile"] as m_evolve, \
                ctx["detect_correction"] as m_detect, \
                ctx["store_correction"] as m_store, \
                ctx["detect_patterns"] as m_pat, \
                ctx["extract_life_facts"] as m_lf:
            user = _fake_user()
            conv, _ = _fake_conversation()
            run_post_response_intelligence(user, "how am I doing?", "You're good.", conv)

            m_learn.assert_called_once_with(user, "how am I doing?", "You're good.")
            m_evolve.assert_called_once_with(user)
            m_detect.assert_called_once_with("how am I doing?")
            m_store.assert_not_called()  # not a correction -> recorded nothing
            m_pat.assert_called_once_with(user)
            m_lf.assert_called_once_with(user, "how am I doing?", "You're good.")

    def test_correction_recorded_when_detected(self):
        from apps.ai.post_response_intelligence import run_post_response_intelligence
        ctx = self._patchers(detect_correction=True)
        with ctx["extract_learning"], ctx["evolve_profile"], \
                ctx["detect_correction"], ctx["store_correction"] as m_store, \
                ctx["detect_patterns"], ctx["extract_life_facts"]:
            user = _fake_user()
            conv, prev = _fake_conversation(prev_content="I recommended strength.")
            run_post_response_intelligence(
                user, "no, today is cardio", "Understood.", conv)

            m_store.assert_called_once()
            kwargs = m_store.call_args.kwargs
            self.assertEqual(kwargs["user"], user)
            self.assertEqual(kwargs["user_message"], "no, today is cardio")
            self.assertEqual(kwargs["original_response"], "I recommended strength.")
            self.assertEqual(kwargs["original_message_id"], prev.id)

    def test_fail_open_when_extractor_raises(self):
        """One extractor raising must neither propagate nor stop the others."""
        from apps.ai.post_response_intelligence import run_post_response_intelligence
        ctx = self._patchers(detect_correction=False)
        with ctx["extract_learning"] as m_learn, ctx["evolve_profile"], \
                ctx["detect_correction"], ctx["store_correction"], \
                ctx["detect_patterns"] as m_pat, ctx["extract_life_facts"] as m_lf:
            m_learn.side_effect = RuntimeError("boom")
            user = _fake_user()
            conv, _ = _fake_conversation()
            # Must not raise.
            run_post_response_intelligence(user, "hello there", "hi", conv)
            # Downstream extractors still ran despite the earlier failure.
            m_pat.assert_called_once_with(user)
            m_lf.assert_called_once()


class DelegationAndDeadCodeTests(SimpleTestCase):
    def test_legacy_streaming_shim_delegates(self):
        with mock.patch(
            f"{PRI}.run_post_response_intelligence"
        ) as m_run:
            from apps.ai.tasks import _run_chat_post_response
            user = _fake_user()
            _run_chat_post_response(user, "msg", "resp", None)
            m_run.assert_called_once_with(user, "msg", "resp", None)

    def test_cos_post_response_task_exists(self):
        from apps.ai.tasks import post_response_intelligence_task
        self.assertEqual(
            post_response_intelligence_task.name,
            "apps.ai.tasks.post_response_intelligence_task",
        )

    def test_no_dead_module_imports_remain(self):
        """The removed dead IMPORTS must not reappear (docstring mentions are ok)."""
        import inspect
        from apps.ai import tasks
        src = inspect.getsource(tasks)
        self.assertNotIn("from apps.ai.learning_extraction import", src)
        self.assertNotIn("import apps.ai.learning_extraction", src)
        self.assertNotIn("from apps.ai.correction_detector import", src)
        self.assertNotIn("import apps.ai.correction_detector", src)
