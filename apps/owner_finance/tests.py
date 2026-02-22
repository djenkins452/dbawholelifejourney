"""Tests for owner_finance app — Phase 1 & 2."""

import base64
import secrets
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    ThirdPartyVendor, LLMPriceBook, LLMUsageEvent,
    UserSubscriptionSnapshot, VendorBillingRecord,
)
from .services.telemetry import log_llm_usage

User = get_user_model()


# ---------------------------------------------------------------------------
# Test user helpers (mirrors AdminTestMixin from admin_console tests)
# ---------------------------------------------------------------------------

def _accept_terms(user):
    from apps.users.models import TermsAcceptance
    current_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
    TermsAcceptance.objects.create(user=user, terms_version=current_version)


def _complete_onboarding(user):
    user.preferences.has_completed_onboarding = True
    user.preferences.save()


def _verify_email(user):
    from allauth.account.models import EmailAddress
    EmailAddress.objects.get_or_create(
        user=user, email=user.email,
        defaults={'verified': True, 'primary': True},
    )


def _create_mfa_credential(user):
    from apps.users.models import WebAuthnCredential
    credential_id = secrets.token_bytes(32)
    credential_id_b64 = base64.urlsafe_b64encode(credential_id).rstrip(b'=').decode()
    public_key = secrets.token_bytes(64)
    WebAuthnCredential.objects.create(
        user=user,
        credential_id=credential_id,
        credential_id_b64=credential_id_b64,
        public_key=public_key,
        device_name='Test Device',
    )


def make_ready_user(email, password, is_staff=False, is_superuser=False):
    """Create a user that passes all middleware checks."""
    user = User.objects.create_user(
        email=email, password=password,
        is_staff=is_staff, is_superuser=is_superuser,
    )
    _accept_terms(user)
    _complete_onboarding(user)
    _verify_email(user)
    if is_staff or is_superuser:
        _create_mfa_credential(user)
    return user


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class ThirdPartyVendorTest(TestCase):
    def test_create_vendor(self):
        v = ThirdPartyVendor.objects.create(name='OpenAI', category='LLM')
        self.assertEqual(str(v), 'OpenAI (LLM / AI)')


class LLMPriceBookTest(TestCase):
    def setUp(self):
        self.vendor = ThirdPartyVendor.objects.create(name='OpenAI', category='LLM')

    def test_create_price_entry(self):
        pb = LLMPriceBook.objects.create(
            vendor=self.vendor,
            model_name='gpt-4o-mini',
            effective_start=date(2024, 7, 1),
            input_cost_per_1m_tokens_usd=Decimal('0.15'),
            output_cost_per_1m_tokens_usd=Decimal('0.60'),
            is_active=True,
        )
        self.assertIn('gpt-4o-mini', str(pb))


# ---------------------------------------------------------------------------
# Telemetry service tests
# ---------------------------------------------------------------------------

class TelemetryServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com', password='testpass123',
        )
        self.vendor = ThirdPartyVendor.objects.create(name='OpenAI', category='LLM')
        self.price = LLMPriceBook.objects.create(
            vendor=self.vendor,
            model_name='gpt-4o-mini',
            effective_start=date(2024, 7, 1),
            input_cost_per_1m_tokens_usd=Decimal('0.15'),
            output_cost_per_1m_tokens_usd=Decimal('0.60'),
            is_active=True,
        )

    def test_log_llm_usage_computes_cost(self):
        log_llm_usage(
            user=self.user,
            feature='MAIN_RESPONSE',
            model_name='gpt-4o-mini',
            input_tokens=1000,
            output_tokens=500,
        )
        event = LLMUsageEvent.objects.first()
        self.assertIsNotNone(event)
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.feature, 'MAIN_RESPONSE')
        self.assertEqual(event.input_tokens, 1000)
        self.assertEqual(event.output_tokens, 500)
        # Cost: (1000 * 0.15 / 1M) + (500 * 0.60 / 1M) = 0.000150 + 0.000300 = 0.000450
        self.assertAlmostEqual(float(event.cost_usd), 0.000450, places=6)

    def test_log_llm_usage_missing_pricebook(self):
        log_llm_usage(
            user=self.user,
            feature='OTHER',
            model_name='nonexistent-model',
            input_tokens=100,
            output_tokens=50,
        )
        event = LLMUsageEvent.objects.first()
        self.assertIsNotNone(event)
        self.assertEqual(event.cost_usd, Decimal('0'))
        self.assertTrue(event.metadata.get('missing_pricebook'))

    def test_log_llm_usage_no_user(self):
        log_llm_usage(
            user=None,
            feature='INTENT',
            model_name='gpt-4o-mini',
            input_tokens=200,
            output_tokens=100,
        )
        event = LLMUsageEvent.objects.first()
        self.assertIsNotNone(event)
        self.assertIsNone(event.user)


# ---------------------------------------------------------------------------
# Security tests
# ---------------------------------------------------------------------------

class OwnerSecurityTest(TestCase):
    def setUp(self):
        self.regular_user = make_ready_user(
            'regular@example.com', 'testpass123',
        )
        self.superuser = make_ready_user(
            'admin@example.com', 'testpass123',
            is_staff=True, is_superuser=True,
        )

    def test_regular_user_gets_redirected(self):
        self.client.login(email='regular@example.com', password='testpass123')
        response = self.client.get(reverse('owner_finance:overview'))
        self.assertEqual(response.status_code, 302)

    def test_superuser_gets_200(self):
        self.client.login(email='admin@example.com', password='testpass123')
        response = self.client.get(reverse('owner_finance:overview'))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_user_gets_redirected(self):
        response = self.client.get(reverse('owner_finance:overview'))
        self.assertEqual(response.status_code, 302)

    def test_all_pages_secured(self):
        """All owner finance pages should redirect for regular users."""
        self.client.login(email='regular@example.com', password='testpass123')
        for url_name in ['overview', 'users', 'features', 'vendors']:
            response = self.client.get(reverse(f'owner_finance:{url_name}'))
            self.assertEqual(
                response.status_code, 302,
                f'{url_name} should be 302 for regular user',
            )


# ---------------------------------------------------------------------------
# View tests
# ---------------------------------------------------------------------------

class OverviewViewTest(TestCase):
    def setUp(self):
        self.superuser = make_ready_user(
            'admin@example.com', 'testpass123',
            is_staff=True, is_superuser=True,
        )
        self.vendor = ThirdPartyVendor.objects.create(name='OpenAI', category='LLM')
        LLMPriceBook.objects.create(
            vendor=self.vendor,
            model_name='gpt-4o-mini',
            effective_start=date(2024, 7, 1),
            input_cost_per_1m_tokens_usd=Decimal('0.15'),
            output_cost_per_1m_tokens_usd=Decimal('0.60'),
            is_active=True,
        )

    def _login(self):
        self.client.login(email='admin@example.com', password='testpass123')

    def test_overview_with_data(self):
        for i in range(5):
            log_llm_usage(
                user=self.superuser,
                feature='MAIN_RESPONSE',
                model_name='gpt-4o-mini',
                input_tokens=1000,
                output_tokens=500,
            )
        self._login()
        response = self.client.get(reverse('owner_finance:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('kpi', response.context)
        self.assertEqual(response.context['kpi']['total_calls'], 5)

    def test_overview_empty(self):
        self._login()
        response = self.client.get(reverse('owner_finance:overview'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['kpi']['total_calls'], 0)

    def test_date_range_filter(self):
        self._login()
        response = self.client.get(reverse('owner_finance:overview') + '?days=7')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['days'], 7)
