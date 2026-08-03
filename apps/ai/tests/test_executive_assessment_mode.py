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
    def test_dominant_identity_is_established_first(self):
        # The identity must be the FIRST thing the model reads and must subordinate every
        # other rule to it — so the model's self-concept is "chief of staff", not
        # "mistake-avoider". (Everything below is preserved; nothing removed.)
        low = CONSTITUTION.lower()
        head = low[:1400]
        self.assertIn("who you are", head)
        self.assertIn("you are the user's chief of staff", head)
        self.assertIn("guardrails on your judgment", head)
        self.assertIn("primary job is not to avoid mistakes", head)
        # and it comes BEFORE the truth/grounding rules
        self.assertLess(low.index("who you are"), low.index("truth:"))

    def test_broad_assessment_section_present(self):
        low = CONSTITUTION.lower()
        self.assertIn("executive assessment", low)
        # The core inversion: facts SUPPORT the answer, they are not the answer.
        self.assertIn("they are not the answer", low)
        self.assertIn("not a report with sections", low)
        self.assertIn("one synthesized narrative", low)

    def test_answer_is_one_narrative_not_a_template(self):
        # The whole point of the fix: tell ONE coherent story, not fill in a template that
        # renders as sections / an improving list / a declining list / a metric walk.
        low = CONSTITUTION.lower()
        self.assertIn("one synthesized narrative", low)            # a single coherent story
        self.assertIn("lead with your executive read", low)        # judgment first
        self.assertIn("flowing prose", low)                        # prose, not sections
        self.assertIn("one prioritized judgment in connected prose", low)
        # explicitly bans the dashboard shapes
        self.assertIn("do not produce sections", low)
        self.assertIn("a bullet per metric", low)
        self.assertIn("walk through each facet", low)
        # and the old list-inducing phrasing is GONE (regression guard)
        self.assertNotIn("meaningfully improving", low)
        self.assertNotIn("put supporting evidence last", low)

    def test_reasoning_flow_thinks_before_writing(self):
        # Blocker #2 root cause: the model was told what to OUTPUT but not how to THINK, so it
        # mirrored the category-keyed evidence. The fix is a private reasoning procedure:
        # rank by significance/surprise, connect ACROSS facets, decide meaning, then write.
        low = CONSTITUTION.lower()
        self.assertIn("think before you write", low)
        self.assertIn("significance and surprise", low)
        self.assertIn("relationships across facets", low)
        self.assertIn("body recomposition", low)                    # the cross-facet archetype
        # the facet keys are lookup, NOT the answer's structure
        self.assertIn("not the structure of", low)
        self.assertIn("do not walk them one by one", low)

    def test_broad_assessment_examples_named(self):
        low = CONSTITUTION.lower()
        for phrase in ("how am i doing", "how was my week", "how are my relationships",
                       "what should i focus on", "what concerns you"):
            self.assertIn(phrase, low)

    def test_platform_behavior_not_health_specific(self):
        low = CONSTITUTION.lower()
        # Explicitly one behavior across domains — never a Health special-case.
        self.assertIn("never per-domain, never health-specific", low)
        for domain in ("health", "relationships", "journal/moods", "faith", "goals",
                       "finance"):
            self.assertIn(domain, low)

    def test_missing_data_is_not_a_decline(self):
        low = CONSTITUTION.lower()
        self.assertIn("missing data, never a decline", low)

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
        self.assertIn("one synthesized narrative", low)
        self.assertIn("never sections", low)
        self.assertIn("metric-by-metric readout", low)

    def test_directive_reaches_the_assembled_system_prompt(self):
        user = get_user_model().objects.create_user(email="exec@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        low = svc._system_prompt({"current_context": {}}).lower()
        self.assertIn("executive assessment", low)
        self.assertIn("one synthesized narrative", low)
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
