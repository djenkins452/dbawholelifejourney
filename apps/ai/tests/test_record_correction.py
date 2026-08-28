# ==============================================================================
# File: apps/ai/tests/test_record_correction.py
# Description: Contract — M4 EXACT-IDENTITY RECORD CORRECTION.
#
#   INVARIANT: a corrective action must target an EXACT canonical record identity.
#   If the target or the replacement truth is unknown, WLJ must not guess.
#
#   Origin (production 2026-08-27): the CoS created an erroneous weight record and
#   could not reverse it (complete_execution_item with source_id=None → "unsupported"),
#   then offered to "fix" it by substituting an unrelated historical weight from nine
#   days earlier. Removal must bind to identity; replacement truth is never invented.
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services import action_interface as ai
from apps.ai.cos_services import record_correction as rc
from apps.ai.models import ActionConfirmation, ToolCallLog
from apps.health.models import WeightEntry


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="correction@test.com", password="x")
        cls.other = get_user_model().objects.create_user(
            email="correction-other@test.com", password="x")

    def setUp(self):
        cache.clear()
        WeightEntry.all_objects.all().delete()
        ActionConfirmation.objects.all().delete()
        now = timezone.now()
        self.bad = WeightEntry.objects.create(
            user=self.user, value=Decimal("534.0"), unit="lb",
            notes="unrelated payload text", recorded_at=now)
        self.good = WeightEntry.objects.create(
            user=self.user, value=Decimal("270.5"), unit="lb",
            recorded_at=now - timedelta(days=1))


class IdentityTests(_Base):
    """1, 2, 8 — identity is required, and history can never become the target."""

    def test_exact_identity_is_required(self):
        for missing in (None, "", 0):
            out = rc.describe_target(self.user, "weight", missing)
            self.assertEqual(out["status"], rc.AMBIGUOUS)
            self.assertIn("won't guess", out["message"])

    def test_ambiguous_target_removes_nothing(self):
        rc.remove_record(self.user, "weight", None)
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 2)

    def test_unknown_record_type_is_refused(self):
        out = rc.remove_record(self.user, "journal_entry", 1)
        self.assertEqual(out["status"], rc.UNSUPPORTED)
        self.assertFalse(out["removed"])

    def test_another_users_record_is_not_findable(self):
        out = rc.remove_record(self.other, "weight", self.bad.pk)
        self.assertEqual(out["status"], rc.NOT_FOUND)
        self.bad.refresh_from_db()
        self.assertEqual(self.bad.status, "active")

    def test_no_unrestricted_cross_domain_delete_exists(self):
        """10 — only explicitly registered record types are correctable."""
        self.assertEqual(set(rc.RECORD_TYPES), {"weight", "food"})
        for foreign in ("task", "journal", "goal", "user", "*", "weightentry"):
            self.assertIsNone(rc.spec_for(foreign))


class RemovalTests(_Base):
    """4, 5, 6 — exactly that record, idempotently, with nothing invented."""

    def test_removal_affects_only_the_targeted_record(self):
        rc.remove_record(self.user, "weight", self.bad.pk)
        self.bad.refresh_from_db()
        self.good.refresh_from_db()
        self.assertEqual(self.bad.status, "deleted")
        self.assertIsNotNone(self.bad.deleted_at)
        self.assertEqual(self.good.status, "active",
                         "an unrelated record was affected")

    def test_removal_is_soft_delete_not_destruction(self):
        rc.remove_record(self.user, "weight", self.bad.pk)
        self.assertFalse(WeightEntry.objects.filter(pk=self.bad.pk).exists())
        self.assertTrue(WeightEntry.all_objects.filter(pk=self.bad.pk).exists())

    def test_retry_is_idempotent(self):
        first = rc.remove_record(self.user, "weight", self.bad.pk)
        second = rc.remove_record(self.user, "weight", self.bad.pk)
        self.assertEqual(first["status"], rc.OK)
        self.assertEqual(second["status"], rc.ALREADY_REMOVED)
        self.assertFalse(second["removed"])
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 1)

    def test_no_replacement_value_is_ever_written(self):
        """6, 8 — removing a bad record must not create a 'corrected' one, and an
        unrelated historical value can never become the new truth."""
        before = set(WeightEntry.objects.filter(user=self.user)
                     .values_list("pk", flat=True))
        rc.remove_record(self.user, "weight", self.bad.pk)
        after = set(WeightEntry.objects.filter(user=self.user)
                    .values_list("pk", flat=True))
        self.assertTrue(after.issubset(before), "a replacement record was created")
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 1)

    def test_the_service_cannot_write_a_value_at_all(self):
        import inspect
        src = inspect.getsource(rc)
        self.assertNotIn("objects.create", src)
        self.assertNotIn(".value =", src)


class ConfirmationTests(_Base):
    """3, 9 — M1 authorization integrity holds for corrections."""

    def _propose(self, record_id=None):
        rid = self.bad.pk if record_id is None else record_id
        target = rc.describe_target(self.user, "weight", rid)
        return ai.request_confirmation_for(
            self.user, "delete_record",
            {"record_type": "weight", "record_id": rid,
             "target": target.get("description", "")}, turn_id="t")

    def test_confirmation_shows_the_exact_record_being_removed(self):
        conf = self._propose()["confirmation"]
        auth = conf["authorization"]
        self.assertIn("Delete record", auth)
        self.assertIn("534.0 lb", auth)          # the record's current stored state
        self.assertIn(str(self.bad.pk), auth)    # bound to the exact identity

    def test_confirmation_is_bound_and_executes_that_identity_once(self):
        cid = self._propose()["confirmation"]["confirmation_id"]
        rec = ActionConfirmation.objects.get(id=cid)
        self.assertEqual(rec.action, "delete_record")
        self.assertEqual(rec.params["record_id"], self.bad.pk)
        for _ in range(3):
            ai.resolve_pending_action(self.user, cid, confirm=True)
        self.bad.refresh_from_db()
        self.assertEqual(self.bad.status, "deleted")
        self.assertEqual(WeightEntry.objects.filter(user=self.user).count(), 1)

    def test_declining_removes_nothing(self):
        cid = self._propose()["confirmation"]["confirmation_id"]
        ai.resolve_pending_action(self.user, cid, confirm=False)
        self.bad.refresh_from_db()
        self.assertEqual(self.bad.status, "active")

    def test_audit_identifies_record_action_and_result(self):
        """7 — old record → action → result is reconstructable."""
        cid = self._propose()["confirmation"]["confirmation_id"]
        ai.resolve_pending_action(self.user, cid, confirm=True, turn_id="t-audit")
        row = ToolCallLog.objects.filter(user=self.user,
                                         tool_name="delete_record").latest("created_at")
        d = row.result_digest
        self.assertEqual(d.get("record_type"), "weight")
        self.assertEqual(d.get("record_id"), self.bad.pk)
        self.assertTrue(d.get("removed"))
        self.assertIn("534.0 lb", d.get("description", ""))
        self.assertEqual(d.get("confirmation_id"), cid)


class IdentityIsRetrievableTests(_Base):
    """A correction can only bind to an identity the CoS can actually obtain.

    Without a retrievable id the model can SEE a wrong entry but has no safe way to
    name it — which is exactly how the production bad weight became unremovable. This
    closes the loop: retrieve → id → delete_record(id) → bound confirmation → removal.
    """

    def test_weight_retrieval_exposes_the_record_identity(self):
        from apps.ai.cos_services.domain_entity import get_domain_entity
        env = get_domain_entity(self.user, "health", entity_type="weight")
        ids = [(e.get("definition") or {}).get("record_id")
               for e in (env.get("entities") or [])]
        self.assertIn(self.bad.pk, ids,
                      "the CoS cannot obtain the identity a correction requires")

    def test_the_retrieved_identity_is_the_one_correction_accepts(self):
        from apps.ai.cos_services.domain_entity import get_domain_entity
        env = get_domain_entity(self.user, "health", entity_type="weight")
        target = [e for e in (env.get("entities") or [])
                  if (e.get("performance") or {}).get("weight") == 534.0][0]
        rid = target["definition"]["record_id"]
        out = rc.remove_record(self.user, "weight", rid)
        self.assertEqual(out["status"], rc.OK)
        self.bad.refresh_from_db()
        self.assertEqual(self.bad.status, "deleted")


class FoodRecordCorrectionTests(TestCase):
    """The same identity-bound mechanism, a second registered type — no new machinery."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email="food-correction@test.com", password="x")

    def setUp(self):
        from apps.health.models import FoodEntry
        cache.clear()
        FoodEntry.all_objects.all().delete()
        self.meal = FoodEntry.objects.create(
            user=self.user, food_name="Sample Meal", meal_type="dinner",
            quantity=1, serving_size=1, serving_unit="serving",
            total_calories=100, logged_date=timezone.localdate())

    def test_food_record_is_removable_by_exact_identity(self):
        from apps.health.models import FoodEntry
        out = rc.remove_record(self.user, "food", self.meal.pk)
        self.assertEqual(out["status"], rc.OK)
        self.assertIn("Sample Meal", out["description"])
        self.assertFalse(FoodEntry.objects.filter(pk=self.meal.pk).exists())
        self.assertTrue(FoodEntry.all_objects.filter(pk=self.meal.pk).exists())

    def test_food_removal_is_idempotent_and_invents_nothing(self):
        from apps.health.models import FoodEntry
        rc.remove_record(self.user, "food", self.meal.pk)
        again = rc.remove_record(self.user, "food", self.meal.pk)
        self.assertEqual(again["status"], rc.ALREADY_REMOVED)
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 0)
