"""Faith CoS certification — production-validation cleanup regressions.

Locks the fixes for the five prod findings (all runtime-traced, not guessed):
  #1 "most recent prayer request" — a chronological single-object retrieval path
     (describe_one) + the `prayer_request` entity-type alias the model naturally uses.
  #2 family search — keyword search returns the family prayer (not a truth defect).
  #3 study notes — search covers study notes; reading-plan search matches TITLE only, so a
     notes query is not answered with reading plans.
  #4 analysis grounding — abandoned reading plans are excluded from the entity/analysis feed.
  #5 Current Context — the model_interface focus lead INLINES the on-screen content, and the
     chatgpt_cos page-reference gate recognizes page-summary phrasings.
"""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.faith.models import (
    BibleStudyNote, PrayerRequest, ReadingPlanTemplate, UserReadingPlan,
)
from apps.core.truth.domain import get_domain_truth
from apps.ai.search_service import SearchService

User = get_user_model()


class FaithCleanupTruthTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="faithcleanup@example.com", password="x")
        now = timezone.now()
        # Older prayers first (backdated), then "Dad's health" LAST so it is unambiguously
        # the most recent by created_at.
        PrayerRequest.objects.create(user=cls.user, title="Older prayer")
        # A family-referencing prayer (literal token) — also older than Dad's health.
        PrayerRequest.objects.create(user=cls.user, title="Praying for my family",
                                     person_or_situation="my family")
        PrayerRequest.objects.filter(user=cls.user).update(
            created_at=now - dt.timedelta(days=10))
        cls.recent = PrayerRequest.objects.create(
            user=cls.user, title="Dad's health", priority="urgent")
        BibleStudyNote.objects.create(
            user=cls.user, reference="Romans 8:28", translation="ESV", book_name="Romans",
            book_order=45, chapter=8, verse_start=28, title="On providence",
            content="God works all things")
        # A reading plan whose DESCRIPTION contains 'family' but whose TITLE does not.
        tmpl = ReadingPlanTemplate.objects.create(
            title="Noah", slug="faithcleanup-noah", description="a family preserved",
            category="book", difficulty="beginner", duration_days=7, is_active=True)
        UserReadingPlan.objects.create(user=cls.user, template=tmpl, plan_status="completed",
                                       started_at=now - dt.timedelta(days=5))
        ab = ReadingPlanTemplate.objects.create(
            title="Abandoned Attempt", slug="faithcleanup-ab", description="x",
            category="book", difficulty="beginner", duration_days=5, is_active=True)
        UserReadingPlan.objects.create(user=cls.user, template=ab, plan_status="abandoned",
                                       started_at=now - dt.timedelta(days=1))

    # #1 --------------------------------------------------------------------
    def test_describe_one_resolves_most_recent_prayer(self):
        ft = get_domain_truth(self.user, "faith")
        for phrase in ("most recent prayer request", "my latest prayer", "last prayer"):
            self.assertEqual(ft.describe_one(phrase).identity, "Dad's health", phrase)

    def test_prayer_request_alias(self):
        from apps.ai.cos_services.domain_entity import get_domain_entity
        env = get_domain_entity(self.user, "faith", entity_type="prayer_request")
        self.assertEqual(env["status"], "ready", env.get("reason"))
        # newest-first — the most recent prayer leads
        self.assertEqual(env["entities"][0]["identity"], "Dad's health")

    # #3 --------------------------------------------------------------------
    def test_search_faith_covers_study_notes(self):
        svc = SearchService(self.user)
        res = svc.search_faith(content_type="study_note")
        self.assertEqual(res["count"], 1)
        self.assertIn("On providence", res["results"][0]["title"])

    def test_reading_plan_search_matches_title_not_description(self):
        # 'family' appears only in the plan DESCRIPTION → the plan must NOT match, so a
        # notes/family query is never answered with a reading plan.
        plans = SearchService(self.user)._search_faith_reading_plan(["family"], 10)
        self.assertEqual(plans, [], "reading-plan search must not match on description")

    # #4 --------------------------------------------------------------------
    def test_describe_plans_excludes_abandoned(self):
        ft = get_domain_truth(self.user, "faith")
        ids = [e.identity for e in ft.describe("reading_plan")]
        self.assertIn("Noah", ids)
        self.assertNotIn("Abandoned Attempt", ids)


class FaithCleanupRoutingTests(TestCase):
    # #5 (chatgpt_cos runtime) ---------------------------------------------
    def test_is_page_reference_recognizes_page_summary_phrasings(self):
        from apps.ai.chatgpt_cos.page_reference import is_page_reference
        for q in ("What am I looking at here?",
                  "Summarize what is on this page.",
                  "What is the most important thing for me to know from this page?"):
            self.assertTrue(is_page_reference(q), q)
        # A genuine life-priority question (no page reference) must NOT be captured.
        self.assertFalse(is_page_reference("What is the most important thing right now?"))

    # #5 (model_interface runtime) -----------------------------------------
    def test_focus_lead_inlines_on_screen_content(self):
        from apps.ai.model_interface.service import ModelInterfaceService
        ctx = {"current_context": {"current_screen": {"focus": {
            "title": "Prayers", "kind": "prayers overview", "authority": "current_request",
            "content": "Prayers overview\nActive (unanswered) prayers: 9 — 3 urgent"}}}}
        lead = ModelInterfaceService._focus_lead(ctx)
        self.assertIn("ON SCREEN RIGHT NOW", lead)
        # The CONTENT itself must be inline (not merely a pointer to the JSON path).
        self.assertIn("Active (unanswered) prayers: 9", lead)
