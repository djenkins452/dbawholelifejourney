"""
TransformationProtocol model tests.

Tests CRUD, properties, and soft delete.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.health.models import TransformationProtocol
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="tp_test@example.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class TestTransformationProtocolCRUD(TestCase):
    def setUp(self):
        self.user = _create_test_user()

    def test_create_protocol(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="12-Week Cut",
            protocol_type="cut",
            start_date=date.today(),
            target_end_date=date.today() + timedelta(weeks=12),
            goal_weight=Decimal("180.00"),
            goal_body_fat=Decimal("12.00"),
        )
        self.assertEqual(protocol.name, "12-Week Cut")
        self.assertEqual(protocol.protocol_type, "cut")
        self.assertTrue(protocol.is_active)
        self.assertFalse(protocol.is_complete)

    def test_str_representation(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Summer Bulk",
            protocol_type="bulk",
            start_date=date.today(),
        )
        self.assertIn("Summer Bulk", str(protocol))
        self.assertIn("Bulk", str(protocol))

    def test_protocol_type_choices(self):
        for ptype in ["cut", "bulk", "recomp", "maintenance", "custom"]:
            protocol = TransformationProtocol.objects.create(
                user=self.user,
                name=f"Test {ptype}",
                protocol_type=ptype,
                start_date=date.today(),
            )
            self.assertEqual(protocol.protocol_type, ptype)

    def test_optional_fields(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Minimal",
            protocol_type="custom",
            start_date=date.today(),
        )
        self.assertIsNone(protocol.target_end_date)
        self.assertIsNone(protocol.goal_weight)
        self.assertIsNone(protocol.goal_body_fat)
        self.assertIsNone(protocol.life_goal)
        self.assertEqual(protocol.notes, "")


class TestTransformationProtocolProperties(TestCase):
    def setUp(self):
        self.user = _create_test_user("tp_props@example.com")

    def test_is_complete_false_by_default(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Test",
            start_date=date.today(),
        )
        self.assertFalse(protocol.is_complete)

    def test_is_complete_true_when_completed(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Test",
            start_date=date.today(),
            completed_at=timezone.now(),
        )
        self.assertTrue(protocol.is_complete)

    def test_duration_days(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Test",
            start_date=date.today(),
            target_end_date=date.today() + timedelta(days=84),
        )
        self.assertEqual(protocol.duration_days, 84)

    def test_duration_days_none_without_target(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Test",
            start_date=date.today(),
        )
        self.assertIsNone(protocol.duration_days)

    def test_days_remaining(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Test",
            start_date=date.today(),
            target_end_date=date.today() + timedelta(days=30),
        )
        remaining = protocol.days_remaining
        self.assertIsNotNone(remaining)
        self.assertGreaterEqual(remaining, 0)
        self.assertLessEqual(remaining, 30)

    def test_days_remaining_none_without_target(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Test",
            start_date=date.today(),
        )
        self.assertIsNone(protocol.days_remaining)

    def test_progress_percent(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Test",
            start_date=date.today() - timedelta(days=42),
            target_end_date=date.today() + timedelta(days=42),
        )
        progress = protocol.progress_percent
        self.assertIsNotNone(progress)
        self.assertGreaterEqual(progress, 0)
        self.assertLessEqual(progress, 100)

    def test_progress_percent_none_without_target(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="Test",
            start_date=date.today(),
        )
        self.assertIsNone(protocol.progress_percent)


class TestTransformationProtocolSoftDelete(TestCase):
    def setUp(self):
        self.user = _create_test_user("tp_delete@example.com")

    def test_soft_delete(self):
        protocol = TransformationProtocol.objects.create(
            user=self.user,
            name="To Delete",
            start_date=date.today(),
        )
        protocol.soft_delete()

        # Should not appear in default queryset
        self.assertEqual(
            TransformationProtocol.objects.filter(user=self.user).count(), 0
        )
        # Should still exist in all_objects
        self.assertEqual(
            TransformationProtocol.all_objects.filter(user=self.user).count(), 1
        )
