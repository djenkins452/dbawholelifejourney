# ==============================================================================
# File: apps/ai/tests/test_medical_information_policy.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Model Interface governing prompt (CONSTITUTION) carries the
#   permanent Medical Information Policy — WLJ interprets deterministic health
#   truth and explains established medical knowledge, but never diagnoses,
#   prescribes, or gives personalized medical advice. Deterministic contract
#   only (the prompt carries the rule); no brittle live-model wording assertions.
# ==============================================================================
from django.test import TestCase

from apps.ai.model_interface.constitution import CONSTITUTION


class MedicalInformationPolicyContractTests(TestCase):
    def test_policy_section_present_and_non_clinician(self):
        self.assertIn("MEDICAL INFORMATION POLICY", CONSTITUTION)
        low = CONSTITUTION.lower()
        self.assertIn("not the", low)
        self.assertIn("healthcare provider", low)
        for verb in ("never diagnose", "never prescribe"):
            self.assertIn(verb, low)
        # never directs the user to change meds themselves
        self.assertIn("start, stop, increase, or decrease", low)

    def test_three_levels_are_defined(self):
        low = CONSTITUTION.lower()
        self.assertIn("level 1", low)
        self.assertIn("level 2", low)
        self.assertIn("level 3", low)
        # L1 = answer directly, no disclaimer / no medical commentary; L2 = attribute; L3 = defer
        self.assertIn("no disclaimer", low)
        self.assertIn("no medical commentary", low)
        self.assertIn("attribute", low)

    def test_level2_names_authoritative_sources(self):
        # At least the canonical bodies must be advertised as attribution anchors.
        for org in ("american diabetes association", "cdc", "nih", "who", "fda", "ada"):
            self.assertIn(org, CONSTITUTION.lower())

    def test_level3_defers_to_healthcare_professional_not_boilerplate(self):
        low = CONSTITUTION.lower()
        self.assertIn("should i", low)                       # recognizes the decision question
        self.assertIn("healthcare professional", low)        # deferral target
        self.assertIn("do not give personalized medical advice", low)
        self.assertIn("non-boilerplate", low)                # natural, not repeated disclaimers

    def test_level3_answers_ordinary_wellness_without_referral(self):
        low = CONSTITUTION.lower()
        self.assertIn("wellness", low)
        self.assertIn("no clinician referral", low)          # do NOT reflexively refer
        self.assertIn("do not reflexively", low)
        # a concrete ordinary-wellness example is present
        self.assertTrue("stretch after lifting" in low or "walk more" in low
                        or "more vegetables" in low)

    def test_level3_reserves_referral_for_individualized_decisions(self):
        low = CONSTITUTION.lower()
        self.assertIn("reserve", low)
        for item in ("medications", "supplements", "chronic-disease",
                     "abnormal lab", "sustained abnormal"):
            self.assertIn(item, low)

    def test_outside_normal_range_is_calm_not_alarmist(self):
        low = CONSTITUTION.lower()
        self.assertIn("outside normal range", low)
        self.assertIn("calm", low)
        self.assertIn("never alarmist", low)
        # the alarmist phrases are named as things NOT to say (unless safety requires)
        self.assertIn("do not say", low)
        for banned in ("this is dangerous", "this is an emergency", "seek emergency care"):
            self.assertIn(banned, low)
        self.assertIn("outside the normal range", low)       # the calm factual framing

    def test_truth_vs_guidance_never_blurred(self):
        low = CONSTITUTION.lower()
        self.assertIn("never blur", low)
        self.assertIn("interpreter", low)                    # the goal framing
        self.assertIn("explainer", low)

    def test_policy_survives_into_the_system_prompt(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="mip@test.com", password="x")
        svc = ModelInterfaceService(user, ai_service=object())
        prompt = svc._system_prompt({"current_context": {}})
        self.assertIn("MEDICAL INFORMATION POLICY", prompt)


class UnnecessaryDeflectionContractTests(TestCase):
    """The CLASS this contract exists to prevent (production friction, 2026-08-21):

    the Chief of Staff replaced a safely-answerable medication-administration question
    with a content-free 'talk with your healthcare provider' deflection, retrieving
    NOTHING first (proven from ToolCallLog: `tools_called: []`, answer_len 247).

    The architectural CONDITION that made the class possible was that Level 3 keyed
    escalation on the TOPIC a question mentions ('medications, supplements,
    chronic-disease management, fasting…') rather than on whether the question actually
    requires individualized clinical judgment — so ANY question naming a medicine
    qualified for a punt. These tests assert the invariant, never a drug, a phrasing,
    or an answer.
    """

    def setUp(self):
        self.low = CONSTITUTION.lower()

    # -- 1. escalation is keyed on the DECISION, never the subject matter ------
    def test_deferral_is_keyed_on_decision_not_topic(self):
        self.assertIn("what decides is the decision, never the topic", self.low)
        # the negative is stated explicitly, so a bare topic match cannot trigger a punt
        self.assertIn("not individualized merely because it names", self.low)

    def test_topic_only_reserve_list_is_gone(self):
        # The exact defect: a bare enumeration of SUBJECTS as the deferral trigger.
        self.assertNotIn(
            "for genuinely individualized medical decisions: medications, supplements",
            self.low,
        )
        # What replaced it names the JUDGMENT required, not the subject.
        self.assertIn("depends on individualized", self.low)
        self.assertIn("clinical judgment", self.low)

    # -- 2. answerable questions must actually be answered ---------------------
    def test_answerable_health_questions_must_be_answered(self):
        self.assertIn("answerable health questions", self.low)
        # established published instruction that applies to everyone => answer it
        self.assertIn("published", self.low)
        self.assertIn("labelled to be used", self.low)
        # administration/timing/missed-or-late dosing is named as ANSWERABLE, generically
        for concept in ("timing", "administration", "missed"):
            self.assertIn(concept, self.low)
        # and the rule carries equal force to the deferral rule
        self.assertIn("equal in force", self.low)

    def test_answerable_rule_still_names_its_boundary(self):
        # answering is not unconditional: the exceptions must be stated, and only the
        # residue escalated.
        self.assertIn("would not apply", self.low)
        self.assertIn("a clinician's judgment would be required", self.low)
        self.assertIn("escalate only that residue", self.low)

    # -- 3. the floor: a referral alone is never an answer ---------------------
    def test_bare_referral_is_forbidden(self):
        self.assertIn("a referral is never a complete answer", self.low)
        self.assertIn("must never be sent", self.low)
        # deferral must be specific about WHAT the clinician decides
        self.assertIn("what the clinician needs to decide", self.low)

    # -- 4. their own truth is retrieved before answering ---------------------
    def test_user_specific_record_is_retrieved_before_answering(self):
        self.assertIn("retrieve their own record first", self.low)
        self.assertIn("before answering", self.low)
        self.assertIn("never a substitute for retrieving", self.low)

    # -- 5. the safety boundary is NOT weakened -------------------------------
    def test_escalation_boundary_remains_intact(self):
        # the hard prohibitions survive verbatim
        for rule in ("never diagnose", "never prescribe",
                     "start, stop, increase, or decrease"):
            self.assertIn(rule, self.low)
        # and the genuinely-individualized triggers are all still mandated
        for trigger in ("diagnosis",
                        "changing the dose",
                        "treatment plan",
                        "chronic-disease",
                        "abnormal lab",
                        "sustained abnormal",
                        "contraindications",
                        "red-flag symptoms",
                        "uncertain or conflicting",
                        "should i be worried"):
            self.assertIn(trigger, self.low)

    def test_no_drug_or_phrase_hardcoding(self):
        """The fix must be a class fix — never this medication or this sentence."""
        for banned in ("mounjaro", "tirzepatide", "ozempic", "semaglutide",
                       "forgot my dose", "forgot to take"):
            self.assertNotIn(banned, self.low)

    # -- 6. it reaches the real certified runtime prompt ----------------------
    def test_new_rules_survive_into_the_system_prompt(self):
        from django.contrib.auth import get_user_model

        from apps.ai.model_interface.service import ModelInterfaceService
        user = get_user_model().objects.create_user(email="mip2@test.com", password="x")
        prompt = ModelInterfaceService(user, ai_service=object())._system_prompt(
            {"current_context": {}})
        low = prompt.lower()
        self.assertIn("answerable health questions", low)
        self.assertIn("a referral is never a complete answer", low)
        self.assertIn("what decides is the decision, never the topic", low)
