# ==============================================================================
# File: apps/ai/tests/test_understanding.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic Understanding (Truth's assessment tier) — whole-life scope.
# ==============================================================================
"""
Tests for apps/ai/model_interface/understanding.py.

Locks in: read() is cache-first (pending when cold, never live-computes); warm() composes
from EXISTING deterministic computation and exposes ASSESSMENTS only — never prescriptions
(disposition / recommendation_levers / composed prose) which are Reasoning; output is
JSON-safe.
"""

import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.model_interface import understanding

User = get_user_model()


class UnderstandingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="und@example.com", password="x")

    def setUp(self):
        cache.delete(understanding._key(self.user.id))

    def test_read_is_pending_when_cold(self):
        out = understanding.read(self.user)
        self.assertEqual(out["status"], "pending")
        # request-path-safe: read never populates the cache itself
        self.assertIsNone(cache.get(understanding._key(self.user.id)))

    def test_warm_then_read_returns_structured_assessment(self):
        understanding.warm(self.user)
        out = understanding.read(self.user)
        self.assertEqual(out["status"], "ok")
        self.assertIn("executive", out)                 # the assessment tier
        json.dumps(out)                                 # JSON-safe

    def test_exposes_assessments_not_prescriptions(self):
        understanding.warm(self.user)
        blob = json.dumps(understanding.read(self.user)).lower()
        # Reasoning/prescriptions must NOT leak into deterministic understanding.
        for prescription in ("disposition", "recommendation_levers",
                             "executive_picture", "headline"):
            self.assertNotIn(prescription, blob)

    def test_read_never_raises(self):
        # A totally fresh user with nothing cached still returns a clean pending marker.
        fresh = User.objects.create_user(email="und2@example.com", password="x")
        self.assertEqual(understanding.read(fresh)["status"], "pending")
