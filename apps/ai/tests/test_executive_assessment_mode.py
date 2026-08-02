# ==============================================================================
# File: apps/ai/tests/test_executive_assessment_mode.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt instructs the model to answer BROAD
#   whole-picture questions ("how am I doing / how was my week / how are my relationships")
#   like a Chief of Staff — an executive assessment (takeaway → what improved / declined →
#   the ONE highest-leverage focus → supporting evidence LAST) — while SPECIFIC data
#   requests stay precise. Platform behavior, domain-agnostic; deterministic prompt-contract
#   only (no live-model assertions). WLJ still only owns truth; the model owns interpretation.
# ==============================================================================
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.model_interface.constitution import (
    CONSTITUTION,
    RESPONSE_COMPLETION_REMINDER,
    truth_tools,
)
from apps.ai.model_interface.service import ModelInterfaceService


class ExecutiveAssessmentContractTests(TestCase):
    def test_broad_assessment_section_present(self):
        low = CONSTITUTION.lower()
        self.assertIn("executive assessment", low)
        # The core inversion: facts SUPPORT the answer, they are not the answer.
        self.assertIn("they are not the answer", low)
        self.assertIn("not like a dashboard", low)
        self.assertIn("never open by walking through the metrics", low)

    def test_executive_structure_is_specified(self):
        low = CONSTITUTION.lower()
        self.assertIn("open with your executive read", low)         # takeaway first
        self.assertIn("meaningfully improving", low)                # improvements
        self.assertIn("meaningfully declining", low)                # declines
        self.assertIn("highest-leverage focus", low)                # the ONE action
        self.assertIn("put supporting evidence last", low)          # evidence last

    def test_broad_assessment_examples_named(self):
        low = CONSTITUTION.lower()
        for phrase in ("how am i doing", "how was my week", "how are my relationships",
                       "what should i focus on", "what concerns you"):
            self.assertIn(phrase, low)

    def test_platform_behavior_not_health_specific(self):
        low = CONSTITUTION.lower()
        # Explicitly one behavior across domains — never a Health special-case.
        self.assertIn("never a per-domain template and never health-specific", low)
        for domain in ("health", "relationships", "journal/moods", "faith", "goals",
                       "finance"):
            self.assertIn(domain, low)

    def test_missing_data_is_not_a_decline(self):
        low = CONSTITUTION.lower()
        self.assertIn("distinguish missing data from a negative finding", low)

    def test_broad_assessment_does_not_force_the_full_why_investigation(self):
        # A broad "how am I doing" leads with the prioritized read; the deep
        # competing-hypotheses workup is reserved for a "why" / specific-cause request.
        low = CONSTITUTION.lower()
        self.assertIn("does not require the full competing-hypotheses workup", low)

    def test_mode_1_information_requests_preserved(self):
        # The two modes coexist: specific/factual requests stay terse and precise.
        low = CONSTITUTION.lower()
        self.assertIn("the deterministic truth is the answer", low)   # retrieval bullet
        self.assertIn("return it plainly and stop", low)

    def test_reminder_carries_broad_assessment_restatement(self):
        low = RESPONSE_COMPLETION_REMINDER.lower()
        self.assertIn("like a chief of staff, not a dashboard", low)
        self.assertIn("single most important takeaway", low)
        self.assertIn("never a metric-by-metric readout", low)

    def test_directive_reaches_the_assembled_system_prompt(self):
        user = get_user_model().objects.create_user(email="exec@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        low = svc._system_prompt({"current_context": {}}).lower()
        self.assertIn("executive assessment", low)
        self.assertIn("open with your executive read", low)
        # …and the high-salience tail restatement is there too.
        self.assertIn("like a chief of staff, not a dashboard", low)

    def test_prompt_only_change_no_tool_surface_touched(self):
        # No truth authority added/removed — the model consumes the SAME deterministic tools.
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertEqual(names, {
            "get_domain_state", "search_history", "get_history", "get_readings",
            "get_event_frequency", "get_comparison", "get_adherence", "get_entity",
            "get_analysis", "get_user_truth", "get_foundational_health_facts",
        })
