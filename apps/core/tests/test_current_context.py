# ==============================================================================
# Current Context Contract — the platform capability behind Page Awareness.
# A page declares a canonical object reference; the server resolves its content, user-scoped,
# from the canonical model via the Narratable protocol. These tests are the CONTRACT: a
# future page becomes Beth-aware by following the same pattern (declare a ref → resolve).
# ==============================================================================
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.current_context import (
    CurrentContextMixin,
    NarratableMixin,
    resolve_current_context,
)

User = get_user_model()


class ResolverTests(TestCase):
    def setUp(self):
        self.u = User.objects.create_user(email="cc@x.com", password="x")

    def _goal(self, **kw):
        from apps.purpose.models import LifeGoal
        return LifeGoal.objects.create(user=self.u, target_date=date(2027, 1, 1), **kw)

    def test_resolves_owned_object_by_ref(self):
        g = self._goal(title="France 2027", description="Family trip",
                       why_it_matters="Memories", success_looks_like="We go")
        out = resolve_current_context(self.u, ref=f"purpose.lifegoal:{g.pk}")
        self.assertEqual(out["title"], "France 2027")
        self.assertIn("Family trip", out["content"])
        self.assertIn("Memories", out["content"])              # CONTEXT_FIELDS honored
        self.assertIn("We go", out["content"])
        self.assertEqual(out["ref"], f"purpose.lifegoal:{g.pk}")

    def test_ownership_enforced(self):
        g = self._goal(title="Private")
        other = User.objects.create_user(email="cc2@x.com", password="x")
        self.assertIsNone(resolve_current_context(other, ref=f"purpose.lifegoal:{g.pk}"))

    def test_malformed_or_missing_ref_returns_none(self):
        self.assertIsNone(resolve_current_context(self.u, ref="not-a-ref"))
        self.assertIsNone(resolve_current_context(self.u, ref="purpose.lifegoal:999999"))
        self.assertIsNone(resolve_current_context(self.u, ref=""))
        self.assertIsNone(resolve_current_context(self.u, ref="bogus.model:1"))

    def test_default_narratable_uses_common_fields(self):
        # JournalEntry declares CONTEXT_FIELDS=("body",); resolution is generic.
        from apps.journal.models import JournalEntry
        e = JournalEntry.objects.create(user=self.u, title="Gratitude", body="I felt grateful")
        out = resolve_current_context(self.u, ref=f"journal.journalentry:{e.pk}")
        self.assertEqual(out["title"], "Gratitude")
        self.assertIn("grateful", out["content"])


class NarratableProtocolTests(TestCase):
    def test_context_ref_and_kind(self):
        u = User.objects.create_user(email="np@x.com", password="x")
        from apps.purpose.models import LifeGoal
        g = LifeGoal.objects.create(user=u, title="G", target_date=date(2027, 1, 1))
        self.assertEqual(g.context_ref(), f"purpose.lifegoal:{g.pk}")
        self.assertEqual(g.context_title(), "G")
        self.assertTrue(g.is_owned_by(u))


class FaithSummaryTests(TestCase):
    """Faith overrides get_context_summary — the focus is the CURRENT DAY's reading, not the
    plan row. Proves a model can supply richer narration without any Beth/resolver change."""

    def test_current_day_reading_summary(self):
        from apps.faith.models import (
            ReadingPlanDay, ReadingPlanTemplate, UserReadingPlan,
        )
        u = User.objects.create_user(email="faith@x.com", password="x")
        tpl = ReadingPlanTemplate.objects.create(
            title="Gospel of John", description="Read John", category="", difficulty="",
            source="", source_abbreviation="", series="", duration_days=7)
        ReadingPlanDay.objects.create(
            plan=tpl, day_number=1, title="The Word",
            scripture_references=["John 1:1-18"],
            scripture_content=[{"reference": "John 1:1", "text": "In the beginning was the Word"}],
            context_summary="John's prologue", reflection_prompt="What does the Word mean?")
        plan = UserReadingPlan.objects.create(user=u, template=tpl, current_day=1)

        out = resolve_current_context(u, ref=f"faith.userreadingplan:{plan.pk}")
        self.assertEqual(out["kind"], "scripture reading")
        self.assertIn("The Word", out["content"])
        self.assertIn("John 1:1", out["content"])
        self.assertIn("In the beginning was the Word", out["content"])
        self.assertIn("prologue", out["content"])


class ViewMixinTests(TestCase):
    def test_mixin_emits_descriptor(self):
        u = User.objects.create_user(email="vm@x.com", password="x")
        from apps.purpose.models import LifeGoal
        g = LifeGoal.objects.create(user=u, title="Goal X", target_date=date(2027, 1, 1))

        class _Base:
            def get_context_data(self, **kwargs):
                return dict(kwargs)

        class _StubView(CurrentContextMixin, _Base):
            def __init__(self, obj):
                self.object = obj

        ctx = _StubView(g).get_context_data()
        desc = ctx["current_context_descriptor"]
        self.assertEqual(desc["ref"], f"purpose.lifegoal:{g.pk}")
        self.assertEqual(desc["title"], "Goal X")
