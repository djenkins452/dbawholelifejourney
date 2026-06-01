"""Phase 4 — hydration partial refresh POC.

Phase 3 proved the dashboard server render is fast (~60 ms). The
remaining ~4 s of perceived latency is the full `window.location.
reload()` after every tap: 258 KB HTML payload + browser teardown +
script re-execution + paint.

Phase 4 eliminates that for THREE buttons only (water / coffee /
electrolytes). The buttons now carry `data-v3-partial="utilities"`
instead of `data-v3-toggle`. The home.html JS detects the marker,
skips the reload, and dispatches a custom event that triggers the
utilities <section> to self-refresh via HTMX `hx-get` to a small
partial endpoint.

Trust contract preserved:
  - Button label number = stored WaterEntry.amount (Phase 1)
  - Hydration coefficient (effective_oz) unchanged — still display only
  - Partial endpoint reads canonical state via composer._build_utilities
  - No optimistic JS-side mutation; server is authority
  - No SAE rebuild on the partial path (Phase 3 contract held)

Blast radius: 3 buttons. Every other action (med/supp/routine/task/
Bible/wake-up) still uses the existing full-reload path. If this POC
feels instant in prod, the same pattern extends to other actions in a
follow-up.
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.health.models import WaterEntry
from apps.users.models import TermsAcceptance


User = get_user_model()


def _make_user(email="phase4@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    ) if False else TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class PartialEndpointBasicsTests(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.client = Client()
        self.client.force_login(self.user)

    def test_section_utilities_url_reverses(self):
        url = reverse("dashboard_v3:section_utilities")
        self.assertEqual(url, "/dashboard-v3/section/utilities/")

    def test_section_utilities_returns_200_with_section_id(self):
        # Seed a water entry so the utilities section renders (the
        # template gates on {% if utilities.water %}).
        from apps.core.utils import get_user_today
        WaterEntry.objects.create(
            user=self.user, amount=Decimal("8"), unit="oz",
            drink_type="water", logged_date=get_user_today(self.user),
        )
        resp = self.client.get(reverse("dashboard_v3:section_utilities"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # The HTMX swap target id must be present so subsequent
        # outerHTML swaps replace the entire section.
        self.assertIn('id="v3-utilities"', body)
        # Self-refresh wiring intact on the re-rendered section.
        self.assertIn('hx-trigger="dashboard:water-changed from:body"', body)
        self.assertIn('hx-swap="outerHTML"', body)


class PartialReflectsCanonicalStateTests(TestCase):
    """The partial reads the SAME canonical state as the full
    dashboard (composer._build_utilities) — no optimistic mutation,
    no JS-side fake values. Trust contract."""

    def setUp(self):
        self.user = _make_user("canonical@test.com")
        self.client = Client()
        self.client.force_login(self.user)

    def test_partial_reflects_new_water_entry(self):
        """Write a WaterEntry; partial total reflects it immediately
        with hydration coefficient applied."""
        from apps.core.utils import get_user_today
        # Electrolyte: 16 oz × 1.05 coefficient = 16.8 effective oz.
        WaterEntry.objects.create(
            user=self.user, amount=Decimal("16"), unit="oz",
            drink_type="electrolyte", logged_date=get_user_today(self.user),
        )
        resp = self.client.get(reverse("dashboard_v3:section_utilities"))
        body = resp.content.decode()
        # Total displayed must include the just-written entry.
        self.assertIn("16.8", body)


class PartialEndpointEfficiencyTests(TestCase):
    """The whole point of the partial is to be CHEAP — must not balloon
    queries or trigger SAE rebuild."""

    def setUp(self):
        self.user = _make_user("eff@test.com")
        self.client = Client()
        self.client.force_login(self.user)

    def test_partial_query_count_capped(self):
        """Assert the partial stays small. Full dashboard was ~127
        queries (Phase 3); the partial should be a tiny fraction."""
        from apps.core.utils import get_user_today
        WaterEntry.objects.create(
            user=self.user, amount=Decimal("8"), unit="oz",
            drink_type="water", logged_date=get_user_today(self.user),
        )
        # The partial does: WaterEntry today read + auth/session/help/
        # billing/announcements/notifications middleware. ~37-43 queries
        # observed locally (vs ~127 for full dashboard — ~3× reduction).
        # Upper bound catches a regression that adds composer/SAE work;
        # generous to avoid middleware-drift flake.
        from django.db import connection, reset_queries
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("dashboard_v3:section_utilities"))
        self.assertLessEqual(
            len(ctx.captured_queries), 60,
            f"partial fired {len(ctx.captured_queries)} queries — "
            f"Phase 4 expects ≤60 (was ~127 for full dashboard). "
            f"A jump suggests composer/SAE work crept in.",
        )

    def test_partial_does_not_trigger_sae_rebuild(self):
        """Phase 3 contract preserved on the partial path."""
        from unittest.mock import patch
        with patch(
            "apps.core.ai_state.state_engine.rebuild_user_state"
        ) as mock_rebuild:
            resp = self.client.get(reverse("dashboard_v3:section_utilities"))
        self.assertEqual(resp.status_code, 200)
        mock_rebuild.assert_not_called()


class HydrationButtonMarkupTests(TestCase):
    """The full dashboard render must serve buttons that use the new
    partial marker, NOT the full-reload marker."""

    def setUp(self):
        self.user = _make_user("markup@test.com")
        self.client = Client()
        self.client.force_login(self.user)

    def test_hydration_buttons_use_partial_marker(self):
        """All 3 hydration buttons carry data-v3-partial='utilities'
        (and explicitly DO NOT carry the legacy data-v3-toggle that
        triggers a full dashboard reload)."""
        from apps.core.utils import get_user_today
        WaterEntry.objects.create(
            user=self.user, amount=Decimal("8"), unit="oz",
            drink_type="water", logged_date=get_user_today(self.user),
        )
        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode()
        # The partial marker appears on all 3 hydration buttons.
        self.assertEqual(
            body.count('data-v3-partial="utilities"'), 3,
            "Phase 4: expected exactly 3 hydration buttons with the "
            "partial marker (water/coffee/electrolytes).",
        )

    def test_hydration_buttons_do_not_carry_legacy_toggle_marker(self):
        """Trust check — the 3 hydration buttons must NOT have BOTH
        markers (would cause a double-handler in home.html)."""
        from apps.core.utils import get_user_today
        WaterEntry.objects.create(
            user=self.user, amount=Decimal("8"), unit="oz",
            drink_type="water", logged_date=get_user_today(self.user),
        )
        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode()
        # Extract just the quick-log button row to avoid matching
        # data-v3-toggle on OTHER buttons (rhythm, focus, etc.).
        import re
        m = re.search(
            r'<div class="v3-quick-log-row"[^>]*>(.*?)</div>',
            body, re.DOTALL,
        )
        self.assertIsNotNone(m, "v3-quick-log-row not found in dashboard body")
        quick_log_block = m.group(1)
        self.assertNotIn(
            "data-v3-toggle", quick_log_block,
            "Phase 4: hydration buttons must NOT carry data-v3-toggle — "
            "would trigger both partial refresh AND full reload.",
        )


class FullDashboardGetTimingTests(TestCase):
    """The new dashboard_v3_get timing log line must emit on every
    full dashboard GET — production observability."""

    def setUp(self):
        self.user = _make_user("timing@test.com")
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_get_emits_timing_log(self):
        with self.assertLogs("dashboard.action.timing", level="INFO") as cm:
            self.client.get(reverse("dashboard_v3:home"))
        records = [r for r in cm.output if "[DASHBOARD_ACTION_TIMING]" in r]
        self.assertGreaterEqual(len(records), 1, "no timing log emitted")
        # Must identify itself as dashboard_v3_get + carry total_ms.
        joined = "\n".join(records)
        self.assertIn("action=dashboard_v3_get", joined)
        self.assertIn("total_ms=", joined)
        self.assertIn(f"user={self.user.pk}", joined)

    def test_partial_section_emits_separate_timing_log(self):
        """The partial endpoint logs its own action name so prod can
        distinguish full GET vs partial swap latency."""
        with self.assertLogs("dashboard.action.timing", level="INFO") as cm:
            self.client.get(reverse("dashboard_v3:section_utilities"))
        records = [r for r in cm.output if "[DASHBOARD_ACTION_TIMING]" in r]
        joined = "\n".join(records)
        self.assertIn("action=dashboard_v3_section_utilities", joined)
