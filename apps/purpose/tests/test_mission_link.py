"""Mission Link — deterministic relationship truth (a join + a rank, never an engine).

Covers: signal-type resolution, multi-mission, Primary-first then weight ranking, ownership
isolation, active-goal contract, no-fabrication for unmapped entities, facts-once + action
references, cache invalidation, and the no-judgment-vocabulary boundary."""
import json
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.purpose.mission_link import (
    classify_signal_type,
    enrich_action,
    get_mission_map,
    resolve_mission_link,
)
from apps.purpose.models import GoalSignalSource, LifeGoal

User = get_user_model()


def _goal(user, title, *, primary=False, status="active", why="", weight_health=None):
    g = LifeGoal.objects.create(
        user=user, title=title, status=status,
        why_it_matters=why, success_looks_like="Success.",
        target_date=date.today() + timedelta(days=200),
        is_primary_mission=primary,
    )
    # Goals auto-populate default GoalSignalSource rows (goal_signal_config). Clear them so
    # each test controls the exact signal relationship it asserts.
    g.signal_sources.all().delete()
    if weight_health is not None:
        GoalSignalSource.objects.create(goal=g, signal_type="health_activity",
                                        weight=weight_health)
    return g


class MissionLinkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="ml@example.com", password="x")
        self.other = User.objects.create_user(email="ml2@example.com", password="x")

    # 1 — Workout resolves to France 2027 through health_activity.
    def test_workout_resolves_to_primary_mission_via_health_activity(self):
        france = _goal(self.user, "France 2027", primary=True,
                       why="Run the 18K with my family.", weight_health=0.35)
        link = resolve_mission_link(self.user, item={"title": "Workout",
                                                     "source_type": "routine_item"})
        self.assertIsNotNone(link)
        self.assertEqual(link["signal_type"], "health_activity")
        self.assertEqual(link["mission_id"], france.id)
        self.assertTrue(link["is_primary"])
        self.assertEqual(link["weight"], 0.35)

    # 3 & 4 — Primary ranks ahead of a HIGHER-weight non-primary; then weight order.
    def test_primary_ranks_before_higher_weight_nonprimary(self):
        weight_goal = _goal(self.user, "Lose 30 lbs", weight_health=0.90)   # higher weight
        france = _goal(self.user, "France 2027", primary=True, weight_health=0.35)
        also = _goal(self.user, "Half marathon", weight_health=0.50)
        link = resolve_mission_link(self.user, signal_type="health_activity")
        # Primary first despite lower weight; then weight descending among non-primary.
        self.assertEqual(link["mission_id"], france.id)
        self.assertEqual(link["contributes_to"],
                         [france.id, weight_goal.id, also.id])

    # 2 — Multiple missions consume the same signal type.
    def test_multiple_missions_same_signal(self):
        a = _goal(self.user, "Goal A", weight_health=0.4)
        b = _goal(self.user, "Goal B", weight_health=0.6)
        link = resolve_mission_link(self.user, signal_type="health_activity")
        self.assertEqual(set(link["contributes_to"]), {a.id, b.id})

    # 5 — Ownership isolation: another user's goals never resolve.
    def test_user_ownership_isolation(self):
        _goal(self.other, "Their mission", primary=True, weight_health=0.35)
        self.assertIsNone(resolve_mission_link(self.user, signal_type="health_activity"))

    # 6 — Non-active goals excluded (paused/completed/released), per the active contract.
    def test_inactive_goals_excluded(self):
        for st in ("paused", "completed", "released"):
            _goal(self.user, f"{st} goal", status=st, weight_health=0.35)
        self.assertIsNone(resolve_mission_link(self.user, signal_type="health_activity"))
        # And an active one DOES resolve.
        active = _goal(self.user, "Active goal", weight_health=0.35)
        self.assertEqual(
            resolve_mission_link(self.user, signal_type="health_activity")["mission_id"],
            active.id,
        )

    # 7 — Unknown / unmapped entity → no fabricated relationship.
    def test_unmapped_entity_returns_none(self):
        _goal(self.user, "France 2027", primary=True, weight_health=0.35)
        self.assertIsNone(classify_signal_type({"title": "Buy stamps", "domain": "misc"}))
        self.assertIsNone(resolve_mission_link(self.user, item={"title": "Buy stamps",
                                                                "domain": "misc"}))
        # Mapped signal but NO goal consuming it → also None (real absence).
        self.assertIsNone(resolve_mission_link(self.user, signal_type="financial_health"))

    # 8 & 9 — Facts live once; actions carry REFERENCES, not duplicated mission prose.
    def test_facts_once_and_actions_carry_references(self):
        france = _goal(self.user, "France 2027", primary=True,
                       why="Run the 18K with my family.", weight_health=0.35)
        mm = get_mission_map(self.user)
        # Full mission facts exist exactly once, keyed by id.
        self.assertIn(france.id, mm["missions"])
        self.assertEqual(mm["missions"][france.id]["why_it_matters"],
                         "Run the 18K with my family.")
        # The enriched action carries a reference (mission_id), NOT the prose.
        action = enrich_action(self.user, {"title": "Workout",
                                           "source_type": "routine_item"}, mm)
        self.assertEqual(action["signal_type"], "health_activity")
        self.assertEqual(action["mission_link"]["mission_id"], france.id)
        self.assertNotIn("why_it_matters", json.dumps(action["mission_link"]))

    # deterministic mission facts present (id/title/primary/why/success/target/progress).
    def test_mission_facts_are_deterministic_values(self):
        g = _goal(self.user, "France 2027", primary=True,
                  why="Run the 18K with my family.", weight_health=0.35)
        facts = get_mission_map(self.user)["missions"][g.id]
        self.assertEqual(facts["title"], "France 2027")
        self.assertTrue(facts["is_primary"])
        self.assertEqual(facts["why_it_matters"], "Run the 18K with my family.")
        self.assertEqual(facts["success_looks_like"], "Success.")
        self.assertIsNotNone(facts["target_date"])
        self.assertIsInstance(facts["days_to_target"], int)
        self.assertIn("milestone_percent", facts["progress"])
        self.assertIn("momentum_score", facts["progress"])

    # 10 — No judgment / coaching / motivational / pace-label vocabulary anywhere.
    def test_no_judgment_vocabulary(self):
        _goal(self.user, "France 2027", primary=True,
              why="Run the 18K with my family.", weight_health=0.35)
        blob = json.dumps(get_mission_map(self.user)).lower()
        blob += json.dumps(resolve_mission_link(self.user,
                                                signal_type="health_activity")).lower()
        for judgment in ("on track", "at risk", "behind", "important", "recover",
                         "act now", "serious risk", "slipping", "urgent", "keep going",
                         "great job", "you should", "you need to"):
            self.assertNotIn(judgment, blob)

    # 11 — Cache invalidation: a GoalSignalSource change drops the cached map.
    def test_cache_invalidation_on_signal_change(self):
        g = _goal(self.user, "France 2027", primary=True, weight_health=0.35)
        # Prime the cache; faith_practice has no consumer yet.
        self.assertIsNone(resolve_mission_link(self.user, signal_type="faith_practice"))
        # Add a new signal source → invalidation signal fires → map rebuilds.
        GoalSignalSource.objects.create(goal=g, signal_type="faith_practice", weight=0.2)
        link = resolve_mission_link(self.user, signal_type="faith_practice")
        self.assertIsNotNone(link)
        self.assertEqual(link["mission_id"], g.id)

    def test_cache_invalidation_on_primary_change(self):
        a = _goal(self.user, "Goal A", weight_health=0.4)
        b = _goal(self.user, "Goal B", weight_health=0.6)
        # b wins by weight (neither primary).
        self.assertEqual(resolve_mission_link(self.user,
                                              signal_type="health_activity")["mission_id"], b.id)
        # Make A the Primary Mission → invalidation → A now ranks first.
        a.is_primary_mission = True
        a.save()
        self.assertEqual(resolve_mission_link(self.user,
                                              signal_type="health_activity")["mission_id"], a.id)
