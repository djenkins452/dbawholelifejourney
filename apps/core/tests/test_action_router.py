"""Universal Action Routing — contract tests.

Every actionable item must resolve to ONE of three interactions
(informational / complete_here / open_workflow), deterministically and
crash-safe, so every surface honors the same route.
"""
from django.core.cache import cache
from django.test import TestCase

from apps.core.action_router import (
    ActionType,
    resolve_route,
    route_for_finding,
)


class _RouterTestBase(TestCase):
    def setUp(self):
        # TeachingDestination.get_all_active() is cached; the DB rolls back
        # between tests but the cache does not — clear it so a destination
        # created in one test never leaks into another.
        cache.delete("teaching_destinations_all")
        self.addCleanup(lambda: cache.delete("teaching_destinations_all"))


class ResolveRouteTests(_RouterTestBase):
    def test_complete_here_takes_precedence(self):
        r = resolve_route(text="Shower", complete_url="/x/routine/5/complete/")
        self.assertEqual(r.action_type, ActionType.COMPLETE_HERE)
        self.assertEqual(r.complete_url, "/x/routine/5/complete/")
        self.assertTrue(r.is_actionable)

    def test_explicit_destination_is_open_workflow(self):
        r = resolve_route(destination_url="/journal/", destination_label="Journal")
        self.assertEqual(r.action_type, ActionType.OPEN_WORKFLOW)
        self.assertEqual(r.destination_url, "/journal/")

    def test_nothing_resolvable_is_informational(self):
        r = resolve_route(text="the weather is nice", module=None)
        self.assertEqual(r.action_type, ActionType.INFORMATIONAL)
        self.assertFalse(r.is_actionable)
        self.assertIsNone(r.destination_url)

    def test_module_home_fallback_when_subject_unknown(self):
        # No specific subject keyword, but a known module → land on its home.
        r = resolve_route(text="Overtraining risk detected", module="health")
        self.assertEqual(r.action_type, ActionType.OPEN_WORKFLOW)
        self.assertEqual(r.destination_url, "/health/physical/")

    def test_as_dict_shape(self):
        d = resolve_route(destination_url="/journal/").as_dict()
        for k in ("action_type", "destination_url", "complete_url",
                  "complete_label", "tooltip", "is_actionable"):
            self.assertIn(k, d)


class RouteForFindingTests(_RouterTestBase):
    """Deterministic subject → destination fallback (registry empty in tests)."""

    def _dest(self, title, module="health"):
        return route_for_finding({"title": title, "message": "", "module": module})

    def test_protein_routes_to_nutrition(self):
        r = self._dest("Protein intake below target — 53–80% (avg 65%) over 4 days")
        self.assertEqual(r.action_type, ActionType.OPEN_WORKFLOW)
        self.assertEqual(r.destination_url, "/health/physical/nutrition/")

    def test_calories_route_to_nutrition(self):
        self.assertEqual(
            self._dest("Calories under target — 27–35% (avg 31%)").destination_url,
            "/health/physical/nutrition/")

    def test_sleep_routes_to_sleep(self):
        self.assertEqual(self._dest("Sleep 62% of target").destination_url,
                         "/health/physical/sleep/")

    def test_weight_routes_to_weight(self):
        self.assertEqual(self._dest("Weight above last milestone").destination_url,
                         "/health/physical/weight/")

    def test_bible_routes_to_faith(self):
        self.assertEqual(
            self._dest("Bible reading streak broken", module="faith").destination_url,
            "/faith/reading-plans/")

    def test_model_like_object_supported(self):
        class _I:
            title = "Protein intake 55% of target"
            message = ""
            module = "health"
        self.assertEqual(route_for_finding(_I()).destination_url,
                         "/health/physical/nutrition/")


class RegistryWinsWhenPresentTests(_RouterTestBase):
    """When the canonical TeachingDestination registry has a match, it is the
    source of truth (richer than the hardcoded fallback)."""

    def test_registry_destination_overrides_fallback(self):
        from apps.help.models import TeachingDestination
        TeachingDestination.objects.create(
            destination_id="protein-log", name="Protein Log",
            path_description="Health → Nutrition → Protein",
            url="/health/physical/nutrition/protein/",
            keywords="protein, macros, protein intake",
            module="health", is_active=True,
        )
        from django.core.cache import cache
        cache.delete("teaching_destinations_all")
        r = route_for_finding({"title": "Protein intake 55% of target",
                               "message": "", "module": "health"})
        self.assertEqual(r.destination_url, "/health/physical/nutrition/protein/")
