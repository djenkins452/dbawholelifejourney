"""Regression: the Truth Validation Center must resolve the FAITH object the app itself
considers current — through the REAL FaithDomainTruth provider, not describe()[0].

Reproduces the operator's exact scenario: the ACTIVE reading plan ("Walking With God
Through Scripture") was STARTED earlier than a since-completed plan ("Journey Through
Matthew"). describe_plans orders by -started_at, so [0] is the completed plan — the old
validator's bug. The fixed resolver selects by the app's active marker (plan_status='active').
"""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.faith.models import ReadingPlanTemplate, UserReadingPlan
from apps.core.truth.discovery_suite import DISCOVERY_PROMPTS
from apps.core.truth.validation.surface import resolve_expected_object

User = get_user_model()


def _template(title, slug):
    return ReadingPlanTemplate.objects.create(
        title=title, slug=slug, description="x", category="topical",
        difficulty="beginner", duration_days=9, is_active=True, is_featured=False)


class FaithActivePlanResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="faithtv@example.com", password="x")
        now = timezone.now()
        active_tmpl = _template("Walking With God Through Scripture", "walking-with-god")
        completed_tmpl = _template("Journey Through Matthew", "journey-through-matthew")
        # ACTIVE plan started EARLIER
        UserReadingPlan.objects.create(
            user=cls.user, template=active_tmpl, plan_status="active",
            current_day=2, started_at=now - dt.timedelta(days=10))
        # COMPLETED plan started LATER (so it sorts first under -started_at)
        UserReadingPlan.objects.create(
            user=cls.user, template=completed_tmpl, plan_status="completed",
            current_day=9, started_at=now - dt.timedelta(days=1))

    def _prompt(self):
        return next(p for p in DISCOVERY_PROMPTS if p["id"] == "faith.reading_plan")

    def test_resolves_active_plan_not_most_recently_started(self):
        obj = resolve_expected_object(self.user, self._prompt())
        self.assertTrue(obj.present, obj.reason)
        self.assertEqual(obj.resolved_identity, "Walking With God Through Scripture")
        self.assertNotEqual(obj.resolved_identity, "Journey Through Matthew")
        self.assertEqual(obj.object_status, "active")

    def test_resolution_card_names_rule_and_provider(self):
        card = resolve_expected_object(self.user, self._prompt()).resolution()
        self.assertEqual(card["resolved_object"], "Walking With God Through Scripture")
        self.assertIn("active", card["selection_rule"].lower())
        self.assertEqual(card["provider"], "faith.entity(reading_plan)")

    def test_no_active_plan_resolves_absent(self):
        UserReadingPlan.objects.filter(user=self.user).update(plan_status="completed")
        obj = resolve_expected_object(self.user, self._prompt())
        self.assertFalse(obj.present)
        self.assertIn("active", obj.reason.lower())
