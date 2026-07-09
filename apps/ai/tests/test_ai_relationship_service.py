# ==============================================================================
# File: apps/ai/tests/test_ai_relationship_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: AIRelationshipService (Pillar 3) — projection over existing prefs.
# ==============================================================================
"""
Tests for the AI Relationship projection (docs/WLJ_MODEL_INTERFACE_DESIGN.md Pillar 3).

This slice is a READ-ONLY projection over existing preference data — no schema change,
no reasoning, no LLM. These tests lock in:
  * existing user config is projected (with source='user'),
  * not-yet-stored concepts fall back to safe defaults (source='default'),
  * a blank assistant name resolves gracefully,
  * the truth contract constants are present and safe,
  * output is deterministic + JSON-safe,
  * preference-learning is NOT conflated with Learning Mode.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.ai_relationship import (
    AI_RELATIONSHIP_SCHEMA_VERSION,
    DEFAULT_RELATIONSHIP,
    get_ai_relationship,
)

User = get_user_model()


class AIRelationshipProjectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="airel@example.com", password="x")
        if not hasattr(cls.user, "preferences") or cls.user.preferences is None:
            from apps.users.models import UserPreferences
            UserPreferences.objects.get_or_create(user=cls.user)

    # --- projection of existing configuration ---------------------------------
    def test_projects_configured_preferences_with_user_source(self):
        prefs = self.user.preferences
        prefs.cos_display_name = "Beth"
        prefs.cos_response_style = "strategic"
        prefs.assistant_confirm_actions = True
        prefs.save()

        from apps.core.blueprint.engine import get_blueprint
        bp = get_blueprint(self.user)
        bp.accountability_style = "firm"
        bp.question_frequency = "low"
        bp.save()

        rel = get_ai_relationship(self.user)

        self.assertEqual(rel["assistant"]["display_name"], "Beth")
        self.assertEqual(rel["communication"]["detail_level"], "strategic")
        self.assertEqual(rel["accountability"]["level"], "firm")
        self.assertEqual(rel["accountability"]["question_frequency"], "low")
        self.assertTrue(rel["action_preferences"]["confirm_actions"])

        # Provenance: explicitly-configured fields are tagged 'user'.
        self.assertEqual(rel["_sources"]["assistant.display_name"], "user")
        self.assertEqual(rel["_sources"]["communication.detail_level"], "user")
        self.assertEqual(rel["_sources"]["accountability.level"], "user")

    # --- safe defaults for not-yet-stored concepts ----------------------------
    def test_unconfigured_concepts_use_safe_defaults(self):
        rel = get_ai_relationship(self.user)

        self.assertEqual(rel["assistant"]["default_relationship"], DEFAULT_RELATIONSHIP)
        self.assertEqual(rel["_sources"]["assistant.default_relationship"], "default")
        self.assertIsNone(rel["personality_overlay"]["name"])
        self.assertEqual(rel["learned_preferences"], [])
        self.assertTrue(rel["learning"]["enabled"])

    def test_blank_display_name_resolves_to_neutral_default(self):
        prefs = self.user.preferences
        prefs.cos_display_name = ""
        prefs.save()

        rel = get_ai_relationship(self.user)
        self.assertEqual(rel["assistant"]["display_name"], "Chief of Staff")
        self.assertEqual(rel["_sources"]["assistant.display_name"], "default")

    # --- truth contract constants ---------------------------------------------
    def test_truth_preferences_are_safe_constants(self):
        rel = get_ai_relationship(self.user)
        tp = rel["truth_preferences"]
        self.assertFalse(tp["may_invent_facts"])          # never invent WLJ facts
        self.assertTrue(tp["may_derive_conclusions"])     # reasoning is encouraged
        self.assertTrue(tp["may_state_hypotheses"])
        self.assertEqual(tp["authoritative_source"], "WLJ")

    # --- preference-learning is NOT Learning Mode -----------------------------
    def test_learning_enabled_is_not_learning_mode(self):
        # Learning Mode OFF must not force preference-learning OFF — they are
        # independent concepts (this slice defaults preference-learning ON).
        from apps.core.blueprint.engine import get_blueprint
        bp = get_blueprint(self.user)
        bp.cos_learning_mode_active = False
        bp.save()

        rel = get_ai_relationship(self.user)
        self.assertTrue(rel["learning"]["enabled"])

    # --- determinism + JSON-safety --------------------------------------------
    def test_output_is_deterministic_and_json_safe(self):
        a = get_ai_relationship(self.user)
        b = get_ai_relationship(self.user)
        self.assertEqual(a, b)  # deterministic, read-only
        json.dumps(a)           # must be JSON-serializable (raises if not)
        self.assertEqual(a["schema_version"], AI_RELATIONSHIP_SCHEMA_VERSION)

    # --- resilience ------------------------------------------------------------
    def test_does_not_raise_when_blueprint_absent(self):
        # get_ai_relationship uses get_blueprint (get-or-create); even a brand-new
        # user with no blueprint yet must project cleanly with defaults.
        fresh = User.objects.create_user(email="fresh@example.com", password="x")
        from apps.users.models import UserPreferences
        UserPreferences.objects.get_or_create(user=fresh)
        rel = get_ai_relationship(fresh)
        self.assertEqual(rel["accountability"]["level"], "standard")
        self.assertEqual(rel["accountability"]["question_frequency"], "medium")
