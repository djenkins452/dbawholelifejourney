"""
Phase A.5 — Current Context Certification (increment 1).

Governing investigation: docs/WLJ_COS_PLATFORM_EVOLUTION_INVESTIGATION.md (Part V).
Constitution: Article II (Current Context Authority).

Locks the new deterministic Current Context declarations added this increment:
- `journal.home` OVERVIEW page summary (provider + view read ONE shared source).
- `health.IntakeDetailView` (medication detail) declares its focused object.
- `legacy.EditorView` (story) declares its focused Memory, and emits nothing for a
  brand-new story (no object).

These strengthen the deterministic foundation only — no CoS behavior, routing,
navigation, or presentation change.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

User = get_user_model()


class JournalHomeSummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cc_journal@test.wlj", password="x")

    def test_builder_and_provider_share_one_source(self):
        from apps.journal.models import JournalEntry
        from apps.journal.services.journal_home_summary import build_journal_home_summary
        from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS

        JournalEntry.objects.create(user=self.user, title="A", body="a", entry_date=date.today())
        JournalEntry.objects.create(user=self.user, title="B", body="b", entry_date=date.today())

        facts = build_journal_home_summary(self.user)
        self.assertEqual(facts["total"], 2)
        self.assertIn("streak", facts)

        # The provider is registered and composes from the SAME builder facts.
        provider = _PAGE_SUMMARY_PROVIDERS.get("journal.home")
        self.assertIsNotNone(provider)
        summ = provider(self.user, {})
        self.assertEqual(summ["title"], "Journal")
        self.assertIn("Total entries: 2", summ["content"])

    def test_provider_empty_state_is_deterministic(self):
        from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS

        summ = _PAGE_SUMMARY_PROVIDERS["journal.home"](self.user, {})
        self.assertIn("no journal entries", summ["content"].lower())


class IntakeDetailContextTests(TestCase):
    def test_medication_detail_declares_focused_object(self):
        from apps.health.models import Intake
        from apps.health.views import IntakeDetailView
        from apps.core.current_context import resolve_current_context

        user = User.objects.create_user(email="cc_intake@test.wlj", password="x")
        intake = Intake.objects.create(
            user=user, name="Vitamin D", dose="1000 IU", start_date=date.today()
        )

        view = IntakeDetailView()
        view.request = RequestFactory().get("/")
        view.request.user = user
        view.kwargs = {"pk": intake.pk}

        # The view declares the intake as its Current Context object...
        self.assertEqual(view.get_current_context_object(), intake)
        # ...and that object's ref resolves deterministically for the assistant.
        resolved = resolve_current_context(user, intake.context_ref())
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["ref"], intake.context_ref())


class LegacyEditorContextTests(TestCase):
    def test_story_editor_declares_focused_memory(self):
        from apps.legacy.models import Memory
        from apps.legacy.views import EditorView
        from apps.core.current_context import resolve_current_context

        user = User.objects.create_user(email="cc_legacy@test.wlj", password="x")
        memory = Memory.objects.create(user=user, title="My first car")

        view = EditorView()
        view.request = RequestFactory().get("/")
        view.request.user = user
        view.kwargs = {"pk": memory.pk}

        self.assertEqual(view.get_current_context_object(), memory)
        resolved = resolve_current_context(user, memory.context_ref())
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["ref"], memory.context_ref())

    def test_new_story_emits_no_context(self):
        from apps.legacy.views import EditorView

        user = User.objects.create_user(email="cc_legacy2@test.wlj", password="x")
        view = EditorView()
        view.request = RequestFactory().get("/")
        view.request.user = user
        view.kwargs = {}  # composing a new story — no pk, no focused object

        self.assertIsNone(view.get_current_context_object())
