"""
Phase 18.2 — Decision Governance Layer tests.

Verifies that validate_decision() enforces all 5 governance rules:
1. Reality Constraint — fixed items cannot be moved
2. Priority Hierarchy — higher tier overdue beats lower tier
3. No Logical Nonsense — completed items never recommended
4. Constraint inference — items get correct constraint_type
5. Tier inference — items map to correct priority tier
"""

from django.test import TestCase

from apps.ai.decision_governor import (
    GovernanceViolation,
    _infer_constraint_type,
    _infer_tier,
    validate_decision,
)


def _item(title, source_type='task', importance='foundational',
          domain='life', time_status='overdue', completed=False,
          is_protected=False, commitment_level='', scheduled_time='06:00'):
    return {
        'source_type': source_type,
        'title': title,
        'importance': importance,
        'domain': domain,
        'time_status': time_status,
        'completed_today': completed,
        'is_protected': is_protected,
        'commitment_level': commitment_level,
        'scheduled_time': scheduled_time,
        'execution_group_type': 'standalone',
        'execution_group_id': None,
    }


# ══════════════════════════════════════════════════════════════
# Rule 1: Reality Constraint — fixed items cannot be moved
# ══════════════════════════════════════════════════════════════

class RealityConstraintTests(TestCase):
    def test_cannot_move_fixed_item(self):
        """If the recommendation suggests moving a protected/fixed
        item, it must be rejected."""
        items = [
            _item("Las Vegas Trip", is_protected=True,
                  commitment_level='foundational'),
        ]
        with self.assertRaises(GovernanceViolation) as ctx:
            validate_decision(
                "Do this next: Move Las Vegas Trip to next week.\n\n"
                "Reason:\nSchedule conflict.",
                exec_items=items,
            )
        self.assertEqual(ctx.exception.rule, 'REALITY_CONSTRAINT')

    def test_cannot_delay_fixed_item(self):
        items = [
            _item("Las Vegas Trip", is_protected=True,
                  commitment_level='foundational'),
        ]
        with self.assertRaises(GovernanceViolation):
            validate_decision(
                "Do this next: Delay Las Vegas Trip.\n\nReason:\nBusy.",
                exec_items=items,
            )

    def test_can_recommend_starting_fixed_item(self):
        """Starting a fixed item is allowed — only moving/delaying
        is blocked."""
        items = [
            _item("Las Vegas Trip", is_protected=True,
                  commitment_level='foundational'),
        ]
        result = validate_decision(
            "Do this next: Start Las Vegas Trip prep.\n\n"
            "Reason:\nTrip is tomorrow.",
            exec_items=items,
        )
        self.assertIn("Las Vegas Trip", result)


# ══════════════════════════════════════════════════════════════
# Rule 2: Priority Hierarchy — faith > health > work > etc.
# ══════════════════════════════════════════════════════════════

class PriorityHierarchyTests(TestCase):
    def test_workout_overdue_blocks_shower(self):
        """Shower (tier 3, household) must not be recommended when
        Workout (tier 1, health) is overdue."""
        items = [
            _item("Workout and Drink Protein Shake",
                  domain='health', importance='foundational'),
            _item("Shower", domain='life',
                  importance='important'),
        ]
        with self.assertRaises(GovernanceViolation) as ctx:
            validate_decision(
                "Do this next: Start Shower.\n\nReason:\nOverdue.",
                exec_items=items,
            )
        self.assertEqual(ctx.exception.rule, 'PRIORITY_HIERARCHY')
        self.assertIn("Workout", ctx.exception.reason)

    def test_prayer_overdue_blocks_work(self):
        """Prayer (tier 0, faith) outranks Work on WLJ (tier 2)."""
        items = [
            _item("Prayer Time", domain='faith'),
            _item("Work on WLJ", domain='work'),
        ]
        with self.assertRaises(GovernanceViolation):
            validate_decision(
                "Do this next: Start Work on WLJ.\n\nReason:\nOverdue.",
                exec_items=items,
            )

    def test_same_tier_allowed(self):
        """Two items in the same tier — no violation."""
        items = [
            _item("Prayer Time", domain='faith'),
            _item("Bible Reading", domain='faith'),
        ]
        result = validate_decision(
            "Do this next: Start Prayer Time.\n\nReason:\nOverdue.",
            exec_items=items,
        )
        self.assertIn("Prayer Time", result)


# ══════════════════════════════════════════════════════════════
# Rule 4: No Logical Nonsense — completed items never recommended
# ══════════════════════════════════════════════════════════════

class NoNonsenseTests(TestCase):
    def test_completed_item_blocked(self):
        items = [
            _item("Wake up", completed=True),
            _item("Work on WLJ", completed=False),
        ]
        with self.assertRaises(GovernanceViolation) as ctx:
            validate_decision(
                "Do this next: Start Wake up.\n\nReason:\nOverdue.",
                exec_items=items,
            )
        self.assertEqual(ctx.exception.rule, 'NO_NONSENSE')

    def test_non_completed_item_allowed(self):
        items = [
            _item("Work on WLJ", completed=False),
        ]
        result = validate_decision(
            "Do this next: Start Work on WLJ.\n\nReason:\nOverdue.",
            exec_items=items,
        )
        self.assertIn("Work on WLJ", result)


# ══════════════════════════════════════════════════════════════
# Tier inference
# ══════════════════════════════════════════════════════════════

class TierInferenceTests(TestCase):
    def test_prayer_is_tier_0(self):
        self.assertEqual(_infer_tier(_item("Prayer Time")), 0)

    def test_bible_reading_is_tier_0(self):
        self.assertEqual(_infer_tier(_item("Bible Reading")), 0)

    def test_workout_is_tier_1(self):
        self.assertEqual(
            _infer_tier(_item("Workout and Drink Protein Shake")), 1,
        )

    def test_medication_dose_is_tier_1(self):
        self.assertEqual(
            _infer_tier(_item("Mounjaro", source_type='medication_dose')), 1,
        )

    def test_work_on_wlj_is_tier_2(self):
        self.assertEqual(
            _infer_tier(_item("Work on WLJ", domain='work')), 2,
        )

    def test_shower_is_tier_3(self):
        self.assertEqual(
            _infer_tier(_item("Shower", importance='important',
                              domain='life')),
            3,
        )

    def test_flexible_item_is_tier_4(self):
        self.assertEqual(
            _infer_tier(_item("Empty Dishwasher", importance='flexible')),
            4,
        )


# ══════════════════════════════════════════════════════════════
# Constraint inference
# ══════════════════════════════════════════════════════════════

class ConstraintInferenceTests(TestCase):
    def test_protected_item_is_fixed(self):
        self.assertEqual(
            _infer_constraint_type(_item("Trip", is_protected=True)),
            'fixed',
        )

    def test_foundational_commitment_is_fixed(self):
        self.assertEqual(
            _infer_constraint_type(
                _item("Meeting", commitment_level='foundational'),
            ),
            'fixed',
        )

    def test_scheduled_important_is_anchored(self):
        self.assertEqual(
            _infer_constraint_type(
                _item("Lunch", commitment_level='important',
                      scheduled_time='12:00'),
            ),
            'anchored',
        )

    def test_no_schedule_no_protection_is_flexible(self):
        self.assertEqual(
            _infer_constraint_type(
                _item("Something", scheduled_time=None,
                      commitment_level='flexible'),
            ),
            'flexible',
        )
