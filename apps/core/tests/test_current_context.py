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


class TemplateCommentLeakTests(TestCase):
    """Regression: internal template comments must NEVER reach rendered HTML. A MULTI-LINE
    {# #} is not stripped by Django (single-line only) and leaks as literal text — the
    2026-07-06 production incident where '{# Current Context Contract … #}' rendered at the
    top of every page. Multi-line notes must use {% comment %}…{% endcomment %}."""

    def _render(self, template, ctx=None):
        from django.contrib.auth.models import AnonymousUser
        from django.template.loader import render_to_string
        from django.test import RequestFactory
        req = RequestFactory().get("/")
        req.user = AnonymousUser()
        return render_to_string(template, ctx or {}, request=req)

    def test_base_html_leaks_no_comments(self):
        html = self._render("base.html", {
            "current_context_descriptor": {"ref": "a.b:1", "kind": "k", "title": "t"}})
        for marker in ("{#", "#}", "{% comment", "{% endcomment", "Current Context Contract"):
            self.assertNotIn(marker, html, f"template comment leaked into HTML: {marker!r}")

    def test_no_multiline_hash_comments_in_touched_templates(self):
        # A multi-line {# … #} (opener and closer on different lines) leaks — forbid it in the
        # templates the Current Context Contract touches.
        import os
        import re
        from django.conf import settings
        base = settings.BASE_DIR
        for rel in ("templates/base.html", "templates/components/chat_widget.html"):
            path = os.path.join(base, rel)
            if not os.path.exists(path):
                continue
            text = open(path, encoding="utf-8").read()
            for m in re.finditer(r"\{#(.*?)#\}", text, re.DOTALL):
                self.assertNotIn("\n", m.group(1),
                                 f"{rel}: multi-line {{# #}} leaks — use {{% comment %}}")


def _onboarded(email):
    from django.conf import settings as s
    u = User.objects.create_user(email=email, password="x")
    try:
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=u, terms_version=s.WLJ_SETTINGS["TERMS_VERSION"])
    except Exception:
        pass
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class RenderTests(TestCase):
    """The page must actually EMIT the meta so the client can send the reference. Auto for
    DetailViews (via `object`); explicit for overview pages with one deterministic focus."""

    def test_detail_view_auto_declares(self):
        from django.test import Client
        from apps.journal.models import JournalEntry
        u = _onboarded("rd1@x.com")
        e = JournalEntry.objects.create(user=u, title="My entry", body="body")
        c = Client(); c.force_login(u)
        html = c.get(f"/journal/{e.pk}/").content.decode("utf-8", "ignore")
        self.assertIn(f'content="journal.journalentry:{e.pk}"', html)   # NO per-view mixin

    def _mission_goal(self, user):
        # REAL selection criteria — is_primary_mission=True + active (no mock), so the test
        # proves the actual production chain, not an artifact.
        from apps.purpose.models import LifeGoal
        return LifeGoal.objects.create(user=user, title="France 2027", status="active",
                                       is_primary_mission=True, target_date=date(2027, 1, 1))

    def test_goals_list_overview_declares_mission_goal(self):
        from django.test import Client
        u = _onboarded("rd2@x.com")
        g = self._mission_goal(u)
        c = Client(); c.force_login(u)
        html = c.get("/purpose/goals/").content.decode("utf-8", "ignore")
        self.assertIn(f'content="purpose.lifegoal:{g.pk}"', html)

    def test_purpose_home_declares_mission_goal(self):
        # The ACTUAL "Goals" page in the nav is /purpose/ (PurposeHomeView) — proven by the
        # cc-chain capture (url=/purpose/) to be where "Am I making progress?" was asked.
        from django.test import Client
        u = _onboarded("rd3@x.com")
        g = self._mission_goal(u)
        c = Client(); c.force_login(u)
        html = c.get("/purpose/").content.decode("utf-8", "ignore")
        self.assertIn(f'content="purpose.lifegoal:{g.pk}"', html)


class ObjectCenteredTests(TestCase):
    """Current Context is a Chief-of-Staff capability injected ONCE, before lane routing, at
    the shared LLM-call choke point — so EVERY reasoning lane's answer is grounded, not just
    the tool-loop and not gated by any phrase."""

    def test_choke_point_gating(self):
        # Every CoS reasoning ANSWER (cos_chat) is grounded; the sandbox (bypass_breaker),
        # non-answer calls (skip), page_reference (self-grounds) and non-CoS are NOT.
        from apps.ai.services import _ground_current_context
        from apps.core.current_context import set_current_focus
        set_current_focus({"title": "G", "kind": "goal", "content": "the goal body"})
        try:
            self.assertIn("the goal body", _ground_current_context("SYS", "cos_chat"))
            self.assertEqual(_ground_current_context("SYS", "cos_chat", bypass_breaker=True), "SYS")
            self.assertEqual(_ground_current_context("SYS", "cos_chat", skip=True), "SYS")
            self.assertEqual(_ground_current_context("SYS", "cos_page_reference"), "SYS")
            self.assertEqual(_ground_current_context("SYS", "general"), "SYS")
        finally:
            set_current_focus(None)

    def test_reasoning_planner_receives_focus_identity(self):
        # Regression #2: the reasoning lane's planner must receive the focused-object identity
        # (so it owns domain selection), not have it prepended after planning.
        from unittest import mock as _mock
        from apps.core.current_context import set_current_focus
        from apps.ai.chatgpt_cos.reasoning import engine
        u = _onboarded("rp@x.com")
        set_current_focus({"kind": "Life Goal", "title": "France 2027", "content": "the goal body"})
        seen = {}

        def _cap_planner(user, message, focus=None):
            seen["focus"] = focus
            return None  # decline; we only assert the planner got the focus

        try:
            with _mock.patch("apps.ai.chatgpt_cos.reasoning.engine.run_planner", side_effect=_cap_planner), \
                 _mock.patch("apps.ai.chatgpt_cos.reasoning.engine.preroute_named_goal", return_value=None), \
                 _mock.patch("apps.ai.chatgpt_cos.reasoning.engine.deterministic_health_intent", return_value=None):
                engine.answer_reasoning_question(u, "Am I making progress?")
            self.assertIsNotNone(seen.get("focus"))
            self.assertEqual(seen["focus"]["title"], "France 2027")
        finally:
            set_current_focus(None)

    def test_focus_set_before_routing_and_cleared_after(self):
        # The object is available to EVERY lane because it is set BEFORE route_message runs.
        from unittest import mock as _mock
        from apps.purpose.models import LifeGoal
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        from apps.core.current_context import get_current_focus
        u = _onboarded("oc@x.com")
        g = LifeGoal.objects.create(user=u, title="France 2027",
                                    description="Save and train for the family trip",
                                    target_date=date(2027, 1, 1))
        pc = {"module": "purpose", "focus_ref": f"purpose.lifegoal:{g.pk}"}
        seen = {}

        def _capture_route(user, message, conversation, page_context=None):
            f = get_current_focus() or {}
            seen["content"] = f.get("content", "")
            return {"answer": "ok", "lane": "x"}   # short-circuit generate

        with _mock.patch("apps.ai.chatgpt_cos.lanes.route_message", side_effect=_capture_route), \
             _mock.patch.object(ChatGPTCoSService, "_history", return_value=[]), \
             _mock.patch("apps.core.ai_state.state_engine.get_user_state", return_value={}):
            # A natural, non-deixis question.
            ChatGPTCoSService(u).generate(conversation=object(),
                                          message="Am I making progress?", page_context=pc)
        self.assertIn("Save and train for the family trip", seen["content"])   # every lane sees it
        self.assertIsNone(get_current_focus())                                 # cleared after the turn
