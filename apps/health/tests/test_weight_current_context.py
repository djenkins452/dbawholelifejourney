"""Current Context for OVERVIEW pages — the page-summary pattern, proven on Weight.

Detail pages declare a focused OBJECT (app.model:pk). Overview/dashboard pages declare a
deterministic PAGE SUMMARY (summary:<key>) that a registered, user-scoped, server-side
provider resolves into the SAME {title, content, kind} shape. The Weight page adopts it via
PageSummaryMixin so "Tell me about what I'm looking at" is answered from the same
deterministic summary the page renders — no retrieval, no contradiction.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from apps.ai.cos_services.current_context import get_current_context_baseline
from apps.core.current_context import (
    PageSummaryMixin,
    register_page_summary,
    resolve_current_context,
)
from apps.health.models import WeightEntry

User = get_user_model()

WEIGHT_URL = "/health/physical/weight/"
WEIGHT_REF = "summary:health.weight"


class WeightCurrentContextTests(TestCase):
    def setUp(self):
        self.user = self._mk_user("wcc@example.com")
        self.now = timezone.now()
        # 40 days of near-daily entries trending down (spans the 30-day window).
        for i in range(40):
            WeightEntry.objects.create(
                user=self.user, value=311 - i * 0.6, unit="lb",
                recorded_at=self.now - timedelta(days=39 - i),
            )
        self.client = Client()
        self.client.force_login(self.user)

    def _mk_user(self, email):
        u = User.objects.create_user(email=email, password="pw12345!")
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=u, terms_version=settings.WLJ_SETTINGS["TERMS_VERSION"])
        u.preferences.has_completed_onboarding = True
        u.preferences.save()
        return u

    # -- the page declares the overview summary reference --------------------
    def test_weight_page_emits_page_summary_meta(self):
        resp = self.client.get(WEIGHT_URL)
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('name="wlj-context"', html)
        self.assertIn(f'content="{WEIGHT_REF}"', html)

    # -- the reference resolves to the deterministic summary -----------------
    def test_summary_ref_resolves_to_deterministic_facts(self):
        summ = resolve_current_context(self.user, ref=WEIGHT_REF)
        self.assertIsNotNone(summ)
        self.assertEqual(summ["title"], "Weight")
        self.assertEqual(summ["kind"], "weight overview")
        content = summ["content"]
        for token in ("Selected range", "Current weight", "average", "low", "high",
                      "Total change", "Entries logged"):
            self.assertIn(token, content)

    # -- it lands in the envelope as authoritative current-request focus -----
    def test_summary_is_current_request_focus_in_envelope(self):
        cc = get_current_context_baseline(
            self.user, page_context={"url": WEIGHT_URL, "focus_ref": WEIGHT_REF})
        focus = cc["current_screen"]["focus"]
        self.assertIsNotNone(focus)
        self.assertEqual(focus["authority"], "current_request")
        self.assertEqual(focus["source"], "canonical")
        self.assertIn("Weight overview", focus["content"])

    # -- one source of truth: the page stats == the assistant's summary ------
    def test_page_stats_and_summary_share_one_source(self):
        from apps.health.services.weight_summary import build_weight_range_summary
        facts = build_weight_range_summary(self.user, range_key="all")
        resp = self.client.get(WEIGHT_URL)
        wp = resp.context["wp"]
        # The page payload renders the SAME deterministic numbers, keyed by stat.
        by_key = {s["key"]: s["value"] for s in wp["stats"]}
        self.assertEqual(by_key["low"], facts["low_lb"])
        self.assertEqual(by_key["high"], facts["high_lb"])
        self.assertEqual(by_key["avg"], facts["avg_lb"])
        self.assertEqual(by_key["change"], facts["total_change_lb"])
        # …and the assistant narrates that identical average (default range = All Time).
        self.assertIn(f"average {facts['avg_lb']} lb",
                      resolve_current_context(self.user, ref=WEIGHT_REF)["content"])

    # -- the provider is strictly user-scoped (ownership boundary) -----------
    def test_summary_is_user_scoped(self):
        other = self._mk_user("other-wcc@example.com")
        WeightEntry.objects.create(user=other, value=150, unit="lb",
                                   recorded_at=self.now)
        content = resolve_current_context(other, ref=WEIGHT_REF)["content"]
        self.assertIn("150", content)         # other user's own entry
        self.assertNotIn("311", content)      # never self.user's data

    # -- optional selected point (deterministic lookup, Phase-2 transport) ---
    def test_selected_point_param_is_narrated(self):
        point = (self.now - timedelta(days=10)).date().isoformat()
        summ = resolve_current_context(self.user, ref=f"{WEIGHT_REF};point={point}")
        self.assertIn("Selected point", summ["content"])

    # -- empty state degrades gracefully ------------------------------------
    def test_empty_weight_summary(self):
        empty = self._mk_user("empty-wcc@example.com")
        summ = resolve_current_context(empty, ref=WEIGHT_REF)
        self.assertIsNotNone(summ)
        self.assertIn("no weight entries", summ["content"].lower())


class OverviewPagePatternTests(TestCase):
    """The pattern itself generalizes: any page can register a provider + declare a key."""

    def test_registered_provider_resolves_and_unknown_key_is_none(self):
        user = User.objects.create_user(email="pat@example.com", password="pw12345!")

        @register_page_summary("test.demo_overview")
        def _demo(u, params):
            return {"title": "Demo", "content": "Demo overview facts", "kind": "demo overview"}

        summ = resolve_current_context(user, ref="summary:test.demo_overview")
        self.assertEqual(summ["title"], "Demo")
        self.assertEqual(summ["content"], "Demo overview facts")
        # Unknown provider key resolves to None (never a crash, never a wrong object).
        self.assertIsNone(resolve_current_context(user, ref="summary:test.nope"))

    def test_mixin_emits_summary_descriptor(self):
        class _Base:
            def get_context_data(self, **kwargs):
                return {}

        class _V(PageSummaryMixin, _Base):
            page_summary_key = "test.demo_overview"
            page_summary_title = "Demo"

        desc = _V().get_context_data()["current_context_descriptor"]
        self.assertEqual(desc["ref"], "summary:test.demo_overview")
        self.assertEqual(desc["kind"], "page summary")

    def test_mixin_folds_params_into_ref(self):
        class _Base:
            def get_context_data(self, **kwargs):
                return {}

        class _V(PageSummaryMixin, _Base):
            page_summary_key = "test.demo_overview"

            def get_page_summary_params(self):
                return {"point": "2026-07-05"}

        ref = _V().get_context_data()["current_context_descriptor"]["ref"]
        self.assertEqual(ref, "summary:test.demo_overview;point=2026-07-05")
