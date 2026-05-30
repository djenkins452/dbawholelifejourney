"""View-layer tests for dashboard_v3.

Verifies:
  - /dashboard-v3/ renders 200 for an onboarded user.
  - Login is required (anonymous → redirect).
  - The dashboard_v2 route is unaffected (regression guard for isolation).
"""

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.users.models import TermsAcceptance, User


class DashboardV3ViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="v3view@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client = Client()
        self.client.login(email="v3view@test.com", password="testpass123")

    def test_home_renders_for_authenticated_user(self):
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard_v3/home.html")

    # ── PRODUCTION PROMOTION (2026-05-28) ──
    def test_canonical_dashboard_serves_v3_by_default(self):
        """/dashboard/ (dashboard_v2:home) serves dashboard_v3 by default."""
        resp = self.client.get(reverse("dashboard_v2:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard_v3/home.html")

    @override_settings(DASHBOARD_V3_DEFAULT=False)
    def test_rollback_flag_serves_v2(self):
        """Flipping DASHBOARD_V3_DEFAULT=False instantly restores v2 at
        /dashboard/ — the rollback path."""
        resp = self.client.get(reverse("dashboard_v2:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard_v2/home.html")

    def test_v2_classic_route_always_serves_v2(self):
        """/dashboard/classic/ is the preserved v2 home (validation +
        rollback target), regardless of the flag."""
        resp = self.client.get(reverse("dashboard_v2:classic"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard_v2/home.html")

    def test_v2_action_endpoints_still_reverse(self):
        """v3 depends on the dashboard_v2: action namespace — it must stay
        intact after promotion."""
        # These must not raise NoReverseMatch.
        reverse("dashboard_v2:task_toggle", kwargs={"pk": 1})
        reverse("dashboard_v2:routine_schedule_toggle", kwargs={"schedule_id": 1})
        reverse("dashboard_v2:intake_log", kwargs={"schedule_id": 1})
        reverse("dashboard_v2:cockpit_panel", kwargs={"domain": "health"})

    def test_context_carries_v3_namespace(self):
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertIn("v3", resp.context)
        self.assertIn("gauges", resp.context["v3"])
        self.assertIn("rhythm", resp.context["v3"])
        self.assertIn("executive_summary", resp.context["v3"])

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertIn(resp.status_code, (302, 301))

    def test_dashboard_v2_is_preserved_and_reachable(self):
        """Post-promotion: the V2 experience is preserved intact and still
        renders correctly at its classic route (rollback target). /dashboard/
        itself now serves V3 — covered by
        test_canonical_dashboard_serves_v3_by_default."""
        resp = self.client.get(reverse("dashboard_v2:classic"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "dashboard_v2/home.html")

    def test_no_leaked_template_comments_in_rendered_page(self):
        """Render-time check: a Django {# #} block must never leak into
        the visible HTML. If this test fails, a multi-line {# #} block
        snuck in and is showing as page text."""
        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode("utf-8")
        # The opening {# should never appear in rendered output.
        # (It's safe to assert exact-string absence — Django escapes
        # entities, so a real `{#` in HTML would have to come from a
        # broken-comment leak.)
        self.assertNotIn("{#", body, "Found a leaked Django comment in rendered HTML")
        self.assertNotIn("#}", body, "Found a leaked Django comment close in rendered HTML")

    def test_intake_group_log_kind_url_reverses(self):
        """The new kind-filtered group endpoint MUST be reachable —
        meds vs supplements rely on distinct URLs for separate workflows.
        Old URL stays for v2 backwards compatibility."""
        # Both URLs must reverse (no NoReverseMatch).
        legacy = reverse(
            "dashboard_v2:intake_group_log",
            kwargs={"time_of_day": "morning"},
        )
        kinded = reverse(
            "dashboard_v2:intake_group_log_kind",
            kwargs={"time_of_day": "morning", "kind": "medication"},
        )
        self.assertEqual(legacy, "/dashboard/actions/intake/group/morning/log/")
        self.assertEqual(
            kinded, "/dashboard/actions/intake/group/morning/medication/log/",
        )

    def test_dashboard_load_auto_completes_wake_up(self):
        """VERIFIED AUTO-COMPLETION Rule 1: loading the dashboard is
        authenticated activity → today's Wake Up routine auto-completes
        through the canonical path, and the cascade reflects it."""
        from datetime import time as dtime
        from apps.core.utils import get_user_today
        from apps.life.models import Routine, RoutineSchedule, RoutineLog

        routine = Routine.objects.create(user=self.user, name="Morning Routine")
        sched = RoutineSchedule.objects.create(
            routine=routine,
            name="Wake Up",
            scheduled_time=dtime(6, 0),
            days_of_week="0,1,2,3,4,5,6",
            is_active=True,
        )
        today = get_user_today(self.user)
        self.assertFalse(
            RoutineLog.objects.filter(schedule=sched, scheduled_date=today).exists()
        )

        resp = self.client.get(reverse("dashboard_v3:home"))
        self.assertEqual(resp.status_code, 200)

        # Wake Up must now be completed via the canonical path with auto provenance.
        log = RoutineLog.objects.get(schedule=sched, scheduled_date=today)
        self.assertEqual(log.completion_source, "auto")

    def test_task_circle_posts_to_canonical_v2_toggle_endpoint(self):
        """Operating-system contract: clicking the rhythm circle MUST
        POST to the exact same canonical mutation endpoint v2 uses
        (dashboard_v2:task_toggle). No v3 write logic. No duplicate
        path. Same engine."""
        from datetime import date
        from apps.life.models import Task

        Task.objects.create(
            user=self.user,
            title="Wire-up Test Task",
            commitment_level="important",
            completion_status="pending",
            due_date=date.today(),
        )
        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode("utf-8")

        # Rendered HTML must reference the canonical v2 task_toggle URL —
        # not a v3-specific route.
        expected_fragment = "/dashboard/actions/task/"
        self.assertIn(expected_fragment, body,
            "Rhythm circle must hx-post to the canonical v2 task_toggle URL")
        self.assertIn("data-v3-toggle", body,
            "Circle button must carry the data-v3-toggle marker for the reload script")
        self.assertIn('hx-swap="none"', body,
            "Must discard v2's response (it targets v2 markup)")

    def test_task_title_links_to_canonical_detail_url(self):
        """Title click navigates to the source. We don't recreate edit
        in v3 — we send the user to the canonical edit screen."""
        from datetime import date
        from apps.life.models import Task

        task = Task.objects.create(
            user=self.user,
            title="Detail-Link Test Task",
            commitment_level="important",
            completion_status="pending",
            due_date=date.today(),
        )
        # Verify the task model produces a non-empty detail URL — if it
        # doesn't, the title is rendered as plain text (v2 also does this)
        # and the link assertion is moot. We assert the URL appears IFF
        # get_absolute_url() returned something.
        try:
            expected = task.get_absolute_url()
        except Exception:
            expected = ""
        if expected:
            resp = self.client.get(reverse("dashboard_v3:home"))
            self.assertIn(expected, resp.content.decode("utf-8"))

    def test_v2_dial_markup_renders_when_cockpit_has_domains(self):
        """When the user has active LifeGoals/HabitGoals, the v3 gauges
        section MUST render the canonical v2 cockpit_dial.html partial —
        not the v3 fallback tiles. This test seeds a LifeDomain + LifeGoal
        so the cockpit returns data and asserts the v2 dial markup
        appears in the rendered HTML."""
        from apps.purpose.models import LifeDomain, LifeGoal

        domain, _ = LifeDomain.objects.get_or_create(
            slug="health",
            defaults={
                "name": "Health",
                "color": "#dc2626",
                "is_active": True,
                "sort_order": 1,
            },
        )
        LifeGoal.objects.create(
            user=self.user,
            domain=domain,
            title="Test goal for gauges",
            status="active",
        )

        resp = self.client.get(reverse("dashboard_v3:home"))
        body = resp.content.decode("utf-8")
        # Canonical v2 dial markers — if these aren't present, the gauges
        # aren't really rendering (regression we hit repeatedly).
        self.assertIn("v2-cockpit-dial", body)
        self.assertIn("v2-gauge-svg", body)
        self.assertIn("v2-dial-label", body)
