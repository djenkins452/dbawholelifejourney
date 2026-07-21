"""
Contract: ONE canonical module/workspace-home authority (Phase A consolidation).

Governing investigation: docs/WLJ_COS_PLATFORM_EVOLUTION_INVESTIGATION.md (Part III).
Constitution: Article III.1 (one deterministic authority per truth domain).

The canonical module/workspace-home authority is ``ModuleDefinition.route_name``
(apps/users/models.py). Every other module-home mapping that still exists for
zero-query / defensive reasons is an ADAPTER that MUST agree with it — it may
never silently return a *different* final destination.

This test locks two things so drift cannot silently return:

1. The deliberately-resolved Health inconsistency. The canonical Health
   workspace home is ``health:landing`` (``/health/``) — NOT ``health:home``
   (``/health/physical/``, a sub-page). (Resolved 2026-07-21; evidence in the
   investigation doc Part III / Appendix III.)
2. Cross-map agreement: where the CoS-facing home maps
   (``action_router._MODULE_HOME`` and ``url_resolver.MODULE_URL_MAP``) name the
   same module, they must resolve to the same URL — no forbidden duplicate
   home map can silently diverge.
"""

from django.test import SimpleTestCase
from django.urls import reverse, NoReverseMatch


class ModuleHomeAuthorityContract(SimpleTestCase):
    """Locks the canonical module-home destinations (no DB required)."""

    HEALTH_HOME_URL = "/health/"          # canonical workspace home (health:landing)
    HEALTH_SUBPAGE_URL = "/health/physical/"  # the drifted sub-page (health:home)

    def test_canonical_health_home_is_landing(self):
        """health:landing is the canonical Health workspace home at /health/."""
        self.assertEqual(reverse("health:landing"), self.HEALTH_HOME_URL)
        # The sub-page still exists but is NOT the workspace home.
        self.assertEqual(reverse("health:home"), self.HEALTH_SUBPAGE_URL)

    def test_action_router_module_home_health_is_canonical(self):
        """action_router._MODULE_HOME['health'] must be the canonical landing.

        Regression lock for the 2026-07-21 drift correction: it previously
        pointed at 'health:home' (/health/physical/).
        """
        from apps.core.action_router import _MODULE_HOME

        route_name, _label = _MODULE_HOME["health"]
        self.assertEqual(route_name, "health:landing")
        self.assertEqual(reverse(route_name), self.HEALTH_HOME_URL)

    def test_no_module_home_points_at_a_sub_page(self):
        """No module-home entry may resolve to the /health/physical/ sub-page."""
        from apps.core.action_router import _MODULE_HOME

        for slug, (route_name, _label) in _MODULE_HOME.items():
            try:
                url = reverse(route_name)
            except NoReverseMatch:  # pragma: no cover - caught by the next test
                continue
            self.assertNotEqual(
                url,
                self.HEALTH_SUBPAGE_URL,
                msg=f"module-home for '{slug}' resolves to a sub-page ({url}); "
                f"a workspace home must be the module landing.",
            )

    def test_all_action_router_module_homes_reverse(self):
        """Every module-home route name must reverse (never a broken link)."""
        from apps.core.action_router import _MODULE_HOME

        for slug, (route_name, _label) in _MODULE_HOME.items():
            try:
                reverse(route_name)
            except NoReverseMatch:
                self.fail(f"module-home route '{route_name}' for '{slug}' does not reverse")

    def test_cos_facing_home_maps_agree(self):
        """Where two CoS-facing home maps name the same module, they must agree.

        Guards against a duplicate module-home map silently returning a
        different final URL than the canonical authority.
        """
        from apps.core.action_router import _MODULE_HOME
        from apps.core.ai_orchestrator.url_resolver import MODULE_URL_MAP

        for slug, (route_name, _label) in _MODULE_HOME.items():
            if slug not in MODULE_URL_MAP:
                continue
            try:
                router_url = reverse(route_name)
            except NoReverseMatch:
                self.fail(f"_MODULE_HOME['{slug}'] route '{route_name}' does not reverse")
            map_url = MODULE_URL_MAP[slug]["url"]
            self.assertEqual(
                router_url,
                map_url,
                msg=f"module-home disagreement for '{slug}': "
                f"action_router={router_url} vs MODULE_URL_MAP={map_url}",
            )
