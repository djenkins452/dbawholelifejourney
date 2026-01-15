"""
Tests for VIP promo code feature.

Tests the VIPPromoCode and VIPPromoCodeUsage models, service functions,
and onboarding integration.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import (
    BillingProfile,
    VIPPromoCode,
    VIPPromoCodeUsage,
)
from apps.billing.services import (
    validate_vip_code,
    redeem_vip_code,
    has_vip_access,
)

User = get_user_model()


class VIPPromoCodeModelTest(TestCase):
    """Test VIPPromoCode model."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123',
        )
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
            first_name='Test',
        )

    def test_create_vip_code(self):
        """Can create a VIP promo code."""
        code = VIPPromoCode.objects.create(
            code='BETATESTER',
            description='Beta tester reward',
            max_uses=10,
            created_by=self.admin_user,
        )
        self.assertEqual(code.code, 'BETATESTER')
        self.assertEqual(code.max_uses, 10)
        self.assertEqual(code.current_uses, 0)
        self.assertTrue(code.is_active)

    def test_code_uppercase_normalization(self):
        """Code is normalized to uppercase on save."""
        code = VIPPromoCode.objects.create(
            code='lowercase',
            description='Test code',
        )
        self.assertEqual(code.code, 'LOWERCASE')

    def test_code_strip_whitespace(self):
        """Code whitespace is stripped on save."""
        code = VIPPromoCode.objects.create(
            code='  SPACES  ',
            description='Test code',
        )
        self.assertEqual(code.code, 'SPACES')

    def test_is_valid_active_code(self):
        """Active code with uses remaining should be valid."""
        code = VIPPromoCode.objects.create(
            code='VALID',
            description='Test',
            max_uses=10,
            is_active=True,
        )
        self.assertTrue(code.is_valid)

    def test_is_valid_expired_code(self):
        """Expired code should be invalid."""
        code = VIPPromoCode.objects.create(
            code='EXPIRED',
            description='Test',
            expires_at=timezone.now() - timedelta(days=1),
        )
        self.assertFalse(code.is_valid)

    def test_is_valid_future_expiry(self):
        """Code with future expiry should be valid."""
        code = VIPPromoCode.objects.create(
            code='FUTURE',
            description='Test',
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.assertTrue(code.is_valid)

    def test_is_valid_used_up_code(self):
        """Code with no uses remaining should be invalid."""
        code = VIPPromoCode.objects.create(
            code='USEDDUP',
            description='Test',
            max_uses=1,
            current_uses=1,
        )
        self.assertFalse(code.is_valid)

    def test_is_valid_deactivated_code(self):
        """Deactivated code should be invalid."""
        code = VIPPromoCode.objects.create(
            code='INACTIVE',
            description='Test',
            is_active=False,
        )
        self.assertFalse(code.is_valid)

    def test_is_valid_unlimited_uses(self):
        """Code with max_uses=0 should never hit limit."""
        code = VIPPromoCode.objects.create(
            code='UNLIMITED',
            description='Test',
            max_uses=0,
            current_uses=100,  # Many uses
        )
        self.assertTrue(code.is_valid)

    def test_redeem_success(self):
        """Successful redemption should update user and code."""
        code = VIPPromoCode.objects.create(
            code='REDEEM',
            description='Test',
            max_uses=10,
        )
        result = code.redeem(self.user)
        self.assertTrue(result)

        # Refresh from DB
        code.refresh_from_db()
        self.user.billing_profile.refresh_from_db()

        # Check code was incremented
        self.assertEqual(code.current_uses, 1)

        # Check user got lifetime access
        self.assertEqual(
            self.user.billing_profile.subscription_status,
            BillingProfile.STATUS_LIFETIME
        )
        self.assertEqual(
            self.user.billing_profile.pricing_tier,
            BillingProfile.TIER_FOUNDING
        )

        # Check usage record was created
        usage = VIPPromoCodeUsage.objects.get(user=self.user, vip_code=code)
        self.assertIsNotNone(usage)

    def test_redeem_already_lifetime(self):
        """User with lifetime access cannot redeem."""
        code = VIPPromoCode.objects.create(
            code='EXTRA',
            description='Test',
        )
        # Set user to lifetime first
        self.user.billing_profile.subscription_status = BillingProfile.STATUS_LIFETIME
        self.user.billing_profile.save()

        with self.assertRaises(ValueError) as context:
            code.redeem(self.user)
        self.assertIn('lifetime access', str(context.exception))

    def test_redeem_already_used_vip(self):
        """User who already used a VIP code cannot redeem again."""
        code1 = VIPPromoCode.objects.create(
            code='FIRST',
            description='Test',
        )
        code2 = VIPPromoCode.objects.create(
            code='SECOND',
            description='Test',
        )

        # Redeem first code
        code1.redeem(self.user)

        # Reset user status for testing (normally wouldn't happen)
        self.user.billing_profile.subscription_status = BillingProfile.STATUS_NONE
        self.user.billing_profile.save()

        # Try to redeem second code
        with self.assertRaises(ValueError) as context:
            code2.redeem(self.user)
        self.assertIn('already redeemed', str(context.exception))

    def test_redeem_invalid_code(self):
        """Invalid code should raise ValueError."""
        code = VIPPromoCode.objects.create(
            code='INVALID',
            description='Test',
            is_active=False,
        )
        with self.assertRaises(ValueError) as context:
            code.redeem(self.user)
        self.assertIn('no longer valid', str(context.exception))

    def test_str_method(self):
        """Test string representation."""
        code = VIPPromoCode.objects.create(
            code='TEST',
            description='Test',
            max_uses=5,
            current_uses=2,
        )
        self.assertEqual(str(code), 'TEST (2/5)')

    def test_str_method_unlimited(self):
        """Test string representation for unlimited code."""
        code = VIPPromoCode.objects.create(
            code='UNLIMITED',
            description='Test',
            max_uses=0,
            current_uses=10,
        )
        self.assertEqual(str(code), 'UNLIMITED (10/unlimited)')


class VIPPromoCodeUsageModelTest(TestCase):
    """Test VIPPromoCodeUsage model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        self.vip_code = VIPPromoCode.objects.create(
            code='USAGE',
            description='Test',
        )

    def test_usage_created_on_redeem(self):
        """Usage record created when code is redeemed."""
        self.vip_code.redeem(self.user)
        usage = VIPPromoCodeUsage.objects.get(user=self.user)
        self.assertEqual(usage.vip_code, self.vip_code)
        self.assertIsNotNone(usage.redeemed_at)

    def test_usage_str_method(self):
        """Test string representation."""
        usage = VIPPromoCodeUsage.objects.create(
            user=self.user,
            vip_code=self.vip_code,
        )
        self.assertEqual(str(usage), 'test@example.com used USAGE')

    def test_unique_together_constraint(self):
        """User can only use each code once."""
        VIPPromoCodeUsage.objects.create(
            user=self.user,
            vip_code=self.vip_code,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            VIPPromoCodeUsage.objects.create(
                user=self.user,
                vip_code=self.vip_code,
            )


class VIPPromoCodeServiceTest(TestCase):
    """Test VIP code service functions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        self.valid_code = VIPPromoCode.objects.create(
            code='VALIDCODE',
            description='Test',
        )
        self.invalid_code = VIPPromoCode.objects.create(
            code='INVALIDCODE',
            description='Test',
            is_active=False,
        )

    def test_validate_vip_code_valid(self):
        """validate_vip_code returns code for valid input."""
        result = validate_vip_code('VALIDCODE')
        self.assertEqual(result, self.valid_code)

    def test_validate_vip_code_invalid(self):
        """validate_vip_code returns None for invalid input."""
        result = validate_vip_code('INVALIDCODE')
        self.assertIsNone(result)

    def test_validate_vip_code_empty(self):
        """validate_vip_code returns None for empty input."""
        result = validate_vip_code('')
        self.assertIsNone(result)
        result = validate_vip_code(None)
        self.assertIsNone(result)

    def test_validate_vip_code_nonexistent(self):
        """validate_vip_code returns None for nonexistent code."""
        result = validate_vip_code('DOESNOTEXIST')
        self.assertIsNone(result)

    def test_validate_vip_code_case_insensitive(self):
        """Code validation should be case-insensitive."""
        result = validate_vip_code('validcode')  # lowercase
        self.assertEqual(result, self.valid_code)
        result = validate_vip_code('ValidCode')  # mixed case
        self.assertEqual(result, self.valid_code)

    def test_redeem_vip_code_success(self):
        """redeem_vip_code returns success tuple."""
        success, message = redeem_vip_code(self.user, 'VALIDCODE')
        self.assertTrue(success)
        self.assertIn('lifetime access', message)

    def test_redeem_vip_code_failure_invalid(self):
        """redeem_vip_code returns failure tuple for invalid code."""
        success, message = redeem_vip_code(self.user, 'INVALIDCODE')
        self.assertFalse(success)
        self.assertIn('no longer valid', message)

    def test_redeem_vip_code_failure_nonexistent(self):
        """redeem_vip_code returns failure for nonexistent code."""
        success, message = redeem_vip_code(self.user, 'DOESNOTEXIST')
        self.assertFalse(success)
        self.assertIn('Invalid', message)

    def test_redeem_vip_code_failure_empty(self):
        """redeem_vip_code returns failure for empty code."""
        success, message = redeem_vip_code(self.user, '')
        self.assertFalse(success)
        self.assertIn('No VIP code', message)

    def test_redeem_vip_code_with_ip(self):
        """redeem_vip_code saves IP address."""
        ip = '192.168.1.1'
        success, _ = redeem_vip_code(self.user, 'VALIDCODE', ip_address=ip)
        self.assertTrue(success)
        usage = VIPPromoCodeUsage.objects.get(user=self.user)
        self.assertEqual(usage.ip_address, ip)

    def test_has_vip_access_true(self):
        """has_vip_access returns True for lifetime users."""
        self.user.billing_profile.subscription_status = BillingProfile.STATUS_LIFETIME
        self.user.billing_profile.save()
        self.assertTrue(has_vip_access(self.user))

    def test_has_vip_access_false_active(self):
        """has_vip_access returns False for active (non-lifetime) users."""
        self.user.billing_profile.subscription_status = BillingProfile.STATUS_ACTIVE
        self.user.billing_profile.save()
        self.assertFalse(has_vip_access(self.user))

    def test_has_vip_access_false_none(self):
        """has_vip_access returns False for non-subscribed users."""
        self.user.billing_profile.subscription_status = BillingProfile.STATUS_NONE
        self.user.billing_profile.save()
        self.assertFalse(has_vip_access(self.user))


class VIPPromoCodeOnboardingIntegrationTest(TestCase):
    """
    Integration tests for VIP code in onboarding.

    These tests verify the view logic works correctly with mocked responses.
    Full end-to-end template tests require complex setup due to middleware.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )
        self.vip_code = VIPPromoCode.objects.create(
            code='ONBOARD',
            description='Test',
        )

    def test_redeem_vip_code_in_onboarding_view_logic(self):
        """Test the VIP code redemption logic that would be called from onboarding."""
        # Simulate what the onboarding view does when a VIP code is submitted
        from apps.billing.services import redeem_vip_code

        success, message = redeem_vip_code(
            user=self.user,
            code='ONBOARD',
            ip_address='127.0.0.1',
        )

        self.assertTrue(success)
        self.assertIn('lifetime access', message)

        # Verify user got lifetime access
        self.user.billing_profile.refresh_from_db()
        self.assertEqual(
            self.user.billing_profile.subscription_status,
            BillingProfile.STATUS_LIFETIME
        )

    def test_invalid_code_returns_error_message(self):
        """Test invalid code returns appropriate error."""
        from apps.billing.services import redeem_vip_code

        success, message = redeem_vip_code(
            user=self.user,
            code='INVALIDCODE',
            ip_address='127.0.0.1',
        )

        self.assertFalse(success)
        self.assertIn('Invalid', message)

    def test_has_vip_access_context(self):
        """Test has_vip_access function used in template context."""
        from apps.billing.services import has_vip_access

        # Initially no VIP access
        self.assertFalse(has_vip_access(self.user))

        # After redemption
        self.vip_code.redeem(self.user)
        self.assertTrue(has_vip_access(self.user))

    def test_empty_code_does_not_grant_access(self):
        """Empty VIP code should not grant access."""
        from apps.billing.services import redeem_vip_code

        success, message = redeem_vip_code(
            user=self.user,
            code='',
            ip_address='127.0.0.1',
        )

        self.assertFalse(success)

        # User should NOT have lifetime access
        self.user.billing_profile.refresh_from_db()
        self.assertNotEqual(
            self.user.billing_profile.subscription_status,
            BillingProfile.STATUS_LIFETIME
        )


class VIPPromoCodeAdminTest(TestCase):
    """Test VIP code admin registration and basic functionality."""

    def test_vip_promo_code_registered_in_admin(self):
        """VIPPromoCode should be registered in Django admin."""
        from django.contrib import admin
        from apps.billing.models import VIPPromoCode
        self.assertIn(VIPPromoCode, admin.site._registry)

    def test_vip_promo_code_usage_registered_in_admin(self):
        """VIPPromoCodeUsage should be registered in Django admin."""
        from django.contrib import admin
        from apps.billing.models import VIPPromoCodeUsage
        self.assertIn(VIPPromoCodeUsage, admin.site._registry)

    def test_vip_code_admin_save_sets_created_by(self):
        """Admin save_model should set created_by on new codes."""
        from django.contrib.admin.sites import AdminSite
        from apps.billing.admin import VIPPromoCodeAdmin
        from apps.billing.models import VIPPromoCode
        from unittest.mock import Mock

        admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123',
        )

        site = AdminSite()
        admin = VIPPromoCodeAdmin(VIPPromoCode, site)

        # Create a mock request with the admin user
        request = Mock()
        request.user = admin_user

        # Create a new code (not saved yet)
        code = VIPPromoCode(
            code='TESTCODE',
            description='Test',
        )

        # Call save_model (change=False for new object)
        admin.save_model(request, code, None, change=False)

        # Verify created_by was set and code was uppercased
        self.assertEqual(code.created_by, admin_user)
        self.assertEqual(code.code, 'TESTCODE')

    def test_vip_code_usage_admin_readonly(self):
        """VIPPromoCodeUsage admin should not allow add or change."""
        from django.contrib.admin.sites import AdminSite
        from apps.billing.admin import VIPPromoCodeUsageAdmin
        from apps.billing.models import VIPPromoCodeUsage
        from unittest.mock import Mock

        site = AdminSite()
        admin = VIPPromoCodeUsageAdmin(VIPPromoCodeUsage, site)
        request = Mock()

        self.assertFalse(admin.has_add_permission(request))
        self.assertFalse(admin.has_change_permission(request))
