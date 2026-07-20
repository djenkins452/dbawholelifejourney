"""Faith certification close-out — production-validation cleanup (round 2) regressions.

Data-independent LOGIC fixes (values come from PRODUCTION, which is the authoritative gate;
these lock the ranking/window/scoping rules, not any specific record):
  #1 unqualified prayer search ranks ACTIVE before answered (answered not excluded).
  #2 "most recent prayer" = newest by created_at; provider is strictly user-scoped.
  #3 study-note retrieval returns an honest empty state; a notes query is never answered
     with a reading plan.
  #4 the analysis reading-plan evidence is bounded to CURRENT/RECENT study (no long-completed).
  #5 Conversation State (Milestone 1) integrates with — does not break — Current Context.
"""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.faith.models import (
    BibleStudyNote, PrayerRequest, ReadingPlanTemplate, UserReadingPlan,
)
from apps.faith.services.faith_queries import FaithQueries
from apps.ai.search_service import SearchService
from apps.core.truth.domain import get_domain_truth

User = get_user_model()


def _mk_plan(user, title, slug, status, *, started_days_ago, completed_days_ago=None):
    now = timezone.now()
    t = ReadingPlanTemplate.objects.create(
        title=title, slug=slug, description="a study through the Bible", category="book",
        difficulty="beginner", duration_days=7, is_active=True)
    pl = UserReadingPlan.objects.create(
        user=user, template=t, plan_status=status,
        started_at=now - dt.timedelta(days=started_days_ago))
    if completed_days_ago is not None:
        pl.completed_at = now - dt.timedelta(days=completed_days_ago)
        pl.save(update_fields=["completed_at"])
    return pl


class FaithCloseoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="faithclose@example.com", password="x")
        cls.other = User.objects.create_user(email="faithother@example.com", password="x")
        now = timezone.now()
        # #1: an ACTIVE prayer created EARLIER than an ANSWERED one, both matching "family".
        cls.active_fam = PrayerRequest.objects.create(
            user=cls.user, title="Pray for family reunion", person_or_situation="my family")
        PrayerRequest.objects.filter(pk=cls.active_fam.pk).update(
            created_at=now - dt.timedelta(days=30))
        cls.answered_fam = PrayerRequest.objects.create(
            user=cls.user, title="Family health", is_answered=True, answered_at=now)
        PrayerRequest.objects.filter(pk=cls.answered_fam.pk).update(
            created_at=now - dt.timedelta(days=5))       # newer, but answered
        # #2: newest prayer overall + another user's even-newer prayer (leakage guard).
        cls.newest = PrayerRequest.objects.create(user=cls.user, title="Newest concern")
        PrayerRequest.objects.create(user=cls.other, title="Other user newest")
        # #4: an active plan + a recently-completed plan + a long-completed plan. Realistic
        # plan titles (like Danny's real plans) — no generic word like "study" in the title,
        # so a "study notes" keyword search does not legitimately title-match a plan.
        _mk_plan(cls.user, "Journey Through Mark", "close-active", "active", started_days_ago=10)
        _mk_plan(cls.user, "Book of Jonah", "close-recent", "completed",
                 started_days_ago=30, completed_days_ago=20)
        _mk_plan(cls.user, "Journey Through Matthew", "close-ancient", "completed",
                 started_days_ago=300, completed_days_ago=250)

    # #1 ---------------------------------------------------------------------
    def test_prayer_search_ranks_active_before_answered(self):
        res = SearchService(self.user)._search_faith_prayer(["family"], 10)
        titles = [r["title"] for r in res]
        self.assertEqual(len(res), 2, "both family prayers should be found (answered included)")
        # the ACTIVE one leads despite being OLDER than the answered one.
        self.assertIn("Pray for family reunion", titles[0])
        self.assertFalse(res[0]["metadata"]["is_answered"])
        self.assertTrue(res[1]["metadata"]["is_answered"])

    # #2 ---------------------------------------------------------------------
    def test_most_recent_prayer_is_newest_created_and_user_scoped(self):
        ft = get_domain_truth(self.user, "faith")
        self.assertEqual(ft.describe_one("my most recent prayer").identity, "Newest concern")
        # strictly user-scoped: the other user's (newer) prayer is never returned.
        labels = [e.identity for e in FaithQueries.describe(self.user, limit=50)]
        self.assertNotIn("Other user newest", labels)

    # #3 ---------------------------------------------------------------------
    def test_study_notes_empty_state_is_honest_no_reading_plan_substitution(self):
        from apps.ai.cos_services.domain_entity import get_domain_entity
        env = get_domain_entity(self.user, "faith", entity_type="study_note")
        self.assertEqual(env["status"], "empty")        # user has no notes → say so
        # a keyword search for study notes must NOT return a reading plan (title-only match).
        res = SearchService(self.user).search_faith(keywords=["study", "notes"])
        kinds = {r["metadata"].get("content_type") for r in res["results"]}
        self.assertNotIn("reading_plan", kinds, "notes query must not surface reading plans")

    def test_study_notes_returned_when_they_exist(self):
        BibleStudyNote.objects.create(
            user=self.user, reference="Romans 8:28", translation="ESV", book_name="Romans",
            book_order=45, chapter=8, verse_start=28, title="Providence", content="notes")
        from apps.ai.cos_services.domain_entity import get_domain_entity
        env = get_domain_entity(self.user, "faith", entity_type="study_note")
        self.assertEqual(env["status"], "ready")
        self.assertEqual(env["entities"][0]["identity"], "Providence")

    # #4 ---------------------------------------------------------------------
    def test_analysis_plan_evidence_is_recent_only(self):
        ids = [e.identity for e in FaithQueries.describe_plans(self.user)]
        self.assertIn("Journey Through Mark", ids)
        self.assertIn("Book of Jonah", ids)             # completed 20 days ago → recent
        self.assertNotIn("Journey Through Matthew", ids)  # completed 250 days ago → excluded
        # active leads the ordering.
        self.assertEqual(ids[0], "Journey Through Mark")

    def test_long_completed_plan_still_retrievable_by_name(self):
        # bounding the LIST to recent must NOT hide a historical plan from a by-name lookup.
        ft = get_domain_truth(self.user, "faith")
        self.assertEqual(ft.describe_one("Journey Through Matthew").identity,
                         "Journey Through Matthew")

    # #5 --------------------------------------------------------------------
    def test_conversation_state_and_current_context_coexist(self):
        from apps.ai.models import AssistantConversation
        from apps.ai.model_interface import conversation_state as cs
        from apps.ai.model_interface.service import ModelInterfaceService
        conv = AssistantConversation.objects.create(user=self.user, session_type="chat")
        cs.record_turn(conv, attachments=[{"artifact_id": 5, "kind": "video",
                                           "filename": "clip.mp4"}])
        svc = ModelInterfaceService(self.user)
        ctx = svc.build_standing_context(
            conversation=conv, writes_enabled=True,
            page_context={"focus_ref": "summary:faith.prayers", "module": "faith",
                          "url": "/faith/prayers/"})
        # BOTH truths present — Conversation State did not displace Current Context.
        self.assertIn("conversation_state", ctx)
        self.assertIn("focus", (ctx.get("current_context") or {}).get("current_screen", {}))
        sp = svc._system_prompt(ctx)
        self.assertIn("ACTIVE CONVERSATION STATE", sp)   # conversation-state lead
        self.assertIn("ON SCREEN RIGHT NOW", sp)         # current-context focus lead
