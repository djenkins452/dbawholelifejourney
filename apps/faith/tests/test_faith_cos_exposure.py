"""Faith CoS Domain Certification — Step 2 (Expose existing truth) regression tests.

Locks in the EXPOSURE work: the `studying` email-leak fix, the new entity surfaces
(milestone / saved_verse / study_note / highlight / bookmark), faith analysis participation,
faith freshness registration, and the Current Context page-summary providers. All exposure of
existing truth — no new deterministic truth, no reasoning, WLJ renders no verdict.
"""
import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.faith.models import (
    BibleBookmark, BibleHighlight, BibleStudyNote, FaithMilestone, PrayerRequest,
    ReadingPlanDay, ReadingPlanTemplate, SavedVerse, UserReadingPlan, UserReadingProgress,
)
from apps.core.truth.domain import get_domain_truth

User = get_user_model()


class FaithExposureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="faithexpose@example.com", password="x")
        cls.tmpl = ReadingPlanTemplate.objects.create(
            title="Gospel of Mark", slug="faithexpose-mark", description="d",
            category="book", difficulty="beginner", duration_days=4, is_active=True)
        day1 = ReadingPlanDay.objects.create(
            plan=cls.tmpl, day_number=1, title="Day 1", scripture_references=["Mark 1"])
        cls.plan = UserReadingPlan.objects.create(
            user=cls.user, template=cls.tmpl, plan_status="active", current_day=2,
            started_at=timezone.now() - dt.timedelta(days=3))
        UserReadingProgress.objects.create(
            user=cls.user, user_plan=cls.plan, plan_day=day1, is_completed=True,
            completed_at=timezone.now() - dt.timedelta(days=1), notes="n")
        PrayerRequest.objects.create(user=cls.user, title="Job search", priority="urgent")
        PrayerRequest.objects.create(
            user=cls.user, title="Thanks", is_answered=True, answered_at=timezone.now())
        FaithMilestone.objects.create(
            user=cls.user, title="My Baptism", milestone_type="baptism",
            date=dt.date(2020, 6, 1), scripture_reference="Romans 6:4")
        SavedVerse.objects.create(
            user=cls.user, reference="Philippians 4:6", text="Do not be anxious",
            translation="ESV", book_name="Philippians", book_order=50, chapter=4,
            verse_start=6, is_memory_verse=True)
        BibleStudyNote.objects.create(
            user=cls.user, reference="Romans 8:28", translation="ESV", book_name="Romans",
            book_order=45, chapter=8, verse_start=28, title="On providence",
            content="God works all things")
        BibleHighlight.objects.create(
            user=cls.user, reference="John 3:16", text="For God so loved", translation="ESV",
            book_name="John", book_order=43, chapter=3, verse_start=16, color="yellow")
        BibleBookmark.objects.create(
            user=cls.user, reference="Psalm 23", translation="ESV", book_name="Psalms",
            book_order=19, chapter=23, title="Comfort")

    # ── Finding B: studying must not leak the email / mis-name the plan ──────────
    def test_studying_uses_template_title_no_email_leak(self):
        ct = get_domain_truth(self.user, "faith").current("studying")
        self.assertTrue(ct.present)
        self.assertEqual(ct.value, "Gospel of Mark")
        self.assertNotIn("@", ct.value)

    # ── Finding E: new entity surfaces ──────────────────────────────────────────
    def test_new_entity_types_advertised(self):
        ents = get_domain_truth(self.user, "faith").entity_types
        for et in ("milestone", "saved_verse", "study_note", "highlight", "bookmark"):
            self.assertIn(et, ents)

    def test_describe_each_new_entity_returns_records(self):
        ft = get_domain_truth(self.user, "faith")
        self.assertEqual(ft.describe("milestone")[0].identity, "My Baptism")
        v = ft.describe("saved_verse")[0]
        self.assertEqual(v.identity, "Philippians 4:6")
        self.assertEqual(v.status, "memory_verse")
        self.assertEqual(ft.describe("study_note")[0].identity, "On providence")
        self.assertEqual(ft.describe("highlight")[0].identity, "John 3:16")
        self.assertEqual(ft.describe("bookmark")[0].identity, "Comfort")

    def test_describe_one_resolves_new_types_by_name(self):
        ft = get_domain_truth(self.user, "faith")
        self.assertEqual(ft.describe_one("My Baptism").kind, "faith_milestone")
        self.assertEqual(ft.describe_one("Philippians 4:6").kind, "saved_verse")
        # existing types still resolve (regression)
        self.assertEqual(ft.describe_one("Gospel of Mark").kind, "reading_plan")
        self.assertEqual(ft.describe_one("Job search").kind, "prayer")

    def test_unknown_entity_type_still_rejected(self):
        with self.assertRaises(KeyError):
            get_domain_truth(self.user, "faith").describe("sermon")

    # ── Finding C: analysis participation (pure composition) ────────────────────
    def test_faith_declares_analysis_subjects(self):
        subjects = get_domain_truth(self.user, "faith").analysis_subjects
        self.assertIn("prayer_life", subjects)
        self.assertIn("bible_reading", subjects)
        # every subject maps only to the existing reading history + an existing entity
        for cfg in subjects.values():
            self.assertEqual(cfg["history_metric"], "reading")
            self.assertIn(cfg["entity_type"], ("prayer", "reading_plan"))

    def test_get_domain_analysis_composes_evidence(self):
        from apps.ai.cos_services.domain_analysis import get_domain_analysis
        a = get_domain_analysis(self.user, "faith", "prayer_life")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])

    # ── Finding A: faith participates in request-path freshness ─────────────────
    def test_faith_registered_for_freshness(self):
        from apps.core.ai_state.state_freshness import _MANUAL_MODULE_SOURCES
        self.assertIn("faith", _MANUAL_MODULE_SOURCES)

    # ── Finding D: Current Context page summaries ───────────────────────────────
    def test_page_summaries_registered_and_factual(self):
        from apps.core.current_context import resolve_current_context
        import apps.faith.page_summaries  # noqa: F401  (ensure registered)
        for key, needle in (
            ("summary:faith.prayers", "Answered prayers: 1"),
            ("summary:faith.reading_plans", "Gospel of Mark"),
            ("summary:faith.home", "Active prayers: 1"),
        ):
            summ = resolve_current_context(self.user, ref=key)
            self.assertIsNotNone(summ, key)
            self.assertIn(needle, summ["content"])
