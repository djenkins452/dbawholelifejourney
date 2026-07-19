"""Truth Layer by-name/identity audit — eliminate the SUBSET/MISROUTE defect class.

The Truth Validation Center's resolved mode binds a prompt to a specific object NAME, so the
CoS retrieves by name — exercising each domain's `describe_one`. A provider whose `describe_one`
covers only a SUBSET of its `entity_types` passes list retrieval but returns NOTHING by name
(the Faith class). These tests prove, per domain and per entity type, that the by-name path
returns the SAME complete, correctly-typed object as the list path, and fails honestly on a
name that matches nothing. Providers are the authority — no Validation-Center-only retrieval.
"""
from django.test import TestCase
from django.utils import timezone

from apps.core.truth.domain import get_domain_truth
from apps.core.truth.entity import CompleteEntity


def _roundtrip(test, user, domain, entity_type, *, name=None, expect_kind=None):
    """List path -> pick a record -> by-name path -> assert SAME object, complete + typed."""
    truth = get_domain_truth(user, domain)
    ents = list(truth.describe(entity_type) or [])
    test.assertTrue(ents, f"{domain}.{entity_type}: list path returned nothing")
    target = ents[0]
    lookup = name or (target.identity or "").strip()
    test.assertTrue(lookup, f"{domain}.{entity_type}: no identity to look up")
    got = truth.describe_one(lookup)
    test.assertIsNotNone(got, f"{domain}.describe_one({lookup!r}) returned nothing (SUBSET gap)")
    # type-respecting: never a different entity type with a similar name
    test.assertEqual(got.kind, expect_kind or target.kind,
                     f"{domain}.describe_one({lookup!r}) returned the wrong TYPE")
    # complete composed entity, not a reduced/partial object
    d = got.to_dict()
    test.assertTrue(any(d.get(k) for k in ("definition", "standing", "plan", "performance")),
                    f"{domain}.{entity_type}: by-name entity is empty/partial")
    # honest failure — a nonexistent name must not fall back to another record
    test.assertIsNone(truth.describe_one(f"zzz-no-such-object-{domain}-qqq"),
                      f"{domain}.describe_one(garbage) silently returned a record")
    return target, got


# ---------------------------------------------------------------------------
class ByNameFallbackMechanismTests(TestCase):
    """Unit test the reusable multi-type fallback in isolation (no DB)."""

    def _provider(self, by_type):
        from apps.core.truth.domain import DomainTruth

        class Fake(DomainTruth):
            domain = "fake"
            entity_types = tuple(by_type)

            def describe(self, entity_type=None):
                return by_type.get(entity_type, [])
        return Fake(None)

    def _e(self, kind, identity):
        return CompleteEntity(kind=kind, identity=identity, definition={"x": 1})

    def test_matches_a_non_first_type(self):
        p = self._provider({"a": [self._e("a", "Alpha")], "b": [self._e("b", "Beta")]})
        got = p._entity_by_identity("Beta", ("a", "b"))
        self.assertEqual(got.kind, "b")

    def test_exact_beats_substring_across_types(self):
        p = self._provider({"a": [self._e("a", "Squat Day")],
                            "b": [self._e("b", "Squat")]})
        got = p._entity_by_identity("Squat", ("a", "b"))
        self.assertEqual(got.identity, "Squat")   # exact 'b' beats substring 'a'

    def test_type_order_sets_precedence(self):
        p = self._provider({"a": [self._e("a", "Harold")], "b": [self._e("b", "Harold")]})
        self.assertEqual(p._entity_by_identity("Harold", ("b", "a")).kind, "b")

    def test_missing_and_empty_return_none(self):
        p = self._provider({"a": [self._e("a", "Alpha")]})
        self.assertIsNone(p._entity_by_identity("nope", ("a",)))
        self.assertIsNone(p._entity_by_identity("", ("a",)))

    def test_dict_entities_supported(self):
        p = self._provider({"a": [{"kind": "a", "identity": "DictOne", "definition": {}}]})
        self.assertIsNotNone(p._entity_by_identity("DictOne", ("a",)))


# ---------------------------------------------------------------------------
class GoalsByNameTests(TestCase):
    def setUp(self):
        from apps.core.truth.certification_fixtures import build_goals_fixture
        self.user, _ = build_goals_fixture()

    def test_goal_by_name_still_works(self):
        _roundtrip(self, self.user, "goals", "goal", name="France 2027", expect_kind="goal")

    def test_annual_direction_by_name(self):          # was a SUBSET gap
        _roundtrip(self, self.user, "goals", "annual_direction")

    def test_milestone_by_name(self):                 # was a SUBSET gap
        got = get_domain_truth(self.user, "goals").describe_one("Save €10k")
        self.assertIsNotNone(got)
        self.assertEqual(got.kind, "milestone")


class MealsByNameTests(TestCase):
    def test_dietary_profile_by_name(self):           # was a SUBSET gap
        from apps.core.truth.certification_fixtures import build_dietary_fixture
        user, _ = build_dietary_fixture()
        _roundtrip(self, user, "meals", "dietary_profile")


class MedicalByNameTests(TestCase):
    def setUp(self):
        from apps.core.truth.certification_fixtures import build_medical_fixture
        self.user, _ = build_medical_fixture()

    def test_lab_result_by_name_still_works(self):
        _roundtrip(self, self.user, "medical", "lab_result")

    def test_lab_panel_by_name(self):                 # was a SUBSET gap
        _roundtrip(self, self.user, "medical", "lab_panel",
                   name="Basic Metabolic Panel", expect_kind="lab_panel")


class HealthByNameTests(TestCase):
    def test_weight_by_identity(self):                # was a SUBSET gap (workout-only before)
        from apps.core.truth.certification_fixtures import build_weight_fixture
        user, _ = build_weight_fixture()
        _roundtrip(self, user, "health", "weight")

    def test_workout_matches_contained_exercise(self):
        # "my last squat session" — 'squat' is an EXERCISE inside the session, not its name
        from apps.health.models import Exercise, WorkoutExercise, WorkoutSession
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(email="wq_squat@example.com", password="x")
        session = WorkoutSession.objects.create(
            user=user, date=timezone.localdate(), started_at=timezone.now(),
            completed_at=timezone.now(), name="Leg Day", session_mode="structured")
        ex = Exercise.objects.create(name="Barbell Squat", is_active=True)
        WorkoutExercise.objects.create(session=session, exercise=ex, order=0)
        got = get_domain_truth(user, "health").describe_one("squat")
        self.assertIsNotNone(got, "workout with a squat exercise not found by name")
        self.assertEqual(got.kind, "workout")


class LegacyByNameTests(TestCase):
    def setUp(self):
        from apps.core.truth.certification_fixtures import build_legacy_fixture
        self.user, _ = build_legacy_fixture()

    def test_person_by_name(self):
        got = get_domain_truth(self.user, "legacy").describe_one("Harold Keck")
        self.assertIsNotNone(got)
        self.assertEqual(got.kind, "person")

    def test_exact_place_name_not_shadowed_by_person(self):   # MISROUTE guard
        got = get_domain_truth(self.user, "legacy").describe_one("The Farmhouse")
        self.assertIsNotNone(got)
        self.assertEqual(got.kind, "place")

    def test_exact_memory_title_resolves(self):              # MISROUTE guard
        got = get_domain_truth(self.user, "legacy").describe_one("Summers at the farm")
        self.assertIsNotNone(got)
        self.assertEqual(got.kind, "memory")

    def test_garbage_name_fails_honestly(self):
        self.assertIsNone(get_domain_truth(self.user, "legacy").describe_one("zzz-nope-qqq"))


class OkProviderRegressionTests(TestCase):
    """Lock the already-OK named paths so the fixes don't regress them."""

    def test_medicine_metformin(self):
        from apps.core.truth.certification_fixtures import build_medication_fixture
        user, _ = build_medication_fixture()
        got = get_domain_truth(user, "medicine").describe_one("Metformin")
        self.assertIsNotNone(got)

    def test_relationships_person(self):
        from apps.core.truth.certification_fixtures import build_relationships_fixture
        user, _ = build_relationships_fixture()
        truth = get_domain_truth(user, "relationships")
        ents = list(truth.describe("person") or [])
        self.assertTrue(ents)
        got = truth.describe_one(ents[0].identity)
        self.assertIsNotNone(got)
        self.assertEqual(got.kind, "person")
