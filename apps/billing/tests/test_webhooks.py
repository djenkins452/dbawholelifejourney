"""
Tests for billing webhooks.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.billing.models import BillingProfile, PaymentAuditLog

User = get_user_model()

# Common test settings to avoid staticfiles manifest issues
TEST_STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(
    STRIPE_SECRET_KEY='sk_test_fake',
    STRIPE_WEBHOOK_SECRET='whsec_test_fake',
    STORAGES=TEST_STORAGES,
)
class StripeWebhookTest(TestCase):
    """Test Stripe webhook endpoint."""

    def setUp(self):
        self.client = Client()
        self.webhook_url = reverse('billing:stripe_webhook')

    @patch('apps.billing.webhooks.stripe.Webhook.construct_event')
    def test_webhook_verifies_signature(self, mock_construct):
        """Webhook should verify Stripe signature."""
        import stripe
        mock_construct.side_effect = stripe.error.SignatureVerificationError(
            'Invalid signature', sig_header='invalid'
        )

        response = self.client.post(
            self.webhook_url,
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='invalid',
        )

        self.assertEqual(response.status_code, 400)

    @patch('apps.billing.webhooks.stripe.Webhook.construct_event')
    @patch('apps.billing.webhooks.StripeService.handle_checkout_completed')
    def test_webhook_checkout_completed(self, mock_handler, mock_construct):
        """Webhook should handle checkout.session.completed event."""
        mock_event = MagicMock()
        mock_event.id = 'evt_test123'
        mock_event.type = 'checkout.session.completed'
        mock_event.data.object = MagicMock()
        mock_construct.return_value = mock_event

        response = self.client.post(
            self.webhook_url,
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='valid',
        )

        self.assertEqual(response.status_code, 200)
        mock_handler.assert_called_once()

    @patch('apps.billing.webhooks.stripe.Webhook.construct_event')
    @patch('apps.billing.webhooks.StripeService.handle_invoice_paid')
    def test_webhook_invoice_paid(self, mock_handler, mock_construct):
        """Webhook should handle invoice.paid event."""
        mock_event = MagicMock()
        mock_event.id = 'evt_test456'
        mock_event.type = 'invoice.paid'
        mock_event.data.object = MagicMock()
        mock_construct.return_value = mock_event

        response = self.client.post(
            self.webhook_url,
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='valid',
        )

        self.assertEqual(response.status_code, 200)
        mock_handler.assert_called_once()

    @patch('apps.billing.webhooks.stripe.Webhook.construct_event')
    def test_webhook_logs_receipt(self, mock_construct):
        """Webhook should log receipt in audit log."""
        mock_event = MagicMock()
        mock_event.id = 'evt_test789'
        mock_event.type = 'unhandled.event'
        mock_event.data.object = MagicMock()
        mock_construct.return_value = mock_event

        response = self.client.post(
            self.webhook_url,
            data='{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='valid',
        )

        self.assertEqual(response.status_code, 200)

        log = PaymentAuditLog.objects.filter(
            stripe_event_id='evt_test789'
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, PaymentAuditLog.ACTION_WEBHOOK_RECEIVED)


@override_settings(
    STRIPE_SECRET_KEY='sk_test_fake',
    STRIPE_WEBHOOK_SECRET='whsec_test_fake',
    STORAGES=TEST_STORAGES,
)
class WebhookHandlerTest(TestCase):
    """Test webhook handler methods."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='webhook@example.com',
            password='testpass123',
        )
        self.profile = self.user.billing_profile
        self.profile.stripe_customer_id = 'cus_test123'
        self.profile.save()

    def test_handle_checkout_completed_updates_profile(self):
        """handle_checkout_completed should update billing profile."""
        from apps.billing.services import StripeService

        mock_session = MagicMock()
        mock_session.id = 'cs_test123'
        mock_session.mode = 'subscription'
        mock_session.subscription = 'sub_test123'
        mock_session.metadata = {
            'user_id': str(self.user.id),
            'price_key': 'adult_monthly',
        }

        StripeService.handle_checkout_completed(mock_session)

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.pricing_tier, BillingProfile.TIER_ADULT)
        self.assertEqual(self.profile.billing_cycle, BillingProfile.CYCLE_MONTHLY)
        self.assertEqual(self.profile.stripe_subscription_id, 'sub_test123')

    def test_handle_invoice_payment_failed_updates_status(self):
        """handle_invoice_payment_failed should set status to past_due."""
        from apps.billing.services import StripeService

        mock_invoice = MagicMock()
        mock_invoice.id = 'inv_test123'
        mock_invoice.customer = 'cus_test123'
        mock_invoice.amount_due = 799
        mock_invoice.attempt_count = 1

        StripeService.handle_invoice_payment_failed(mock_invoice)

        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.subscription_status,
            BillingProfile.STATUS_PAST_DUE
        )

    def test_handle_subscription_deleted_cancels(self):
        """handle_subscription_deleted should cancel subscription."""
        from apps.billing.services import StripeService

        self.profile.stripe_subscription_id = 'sub_test123'
        self.profile.subscription_status = BillingProfile.STATUS_ACTIVE
        self.profile.save()

        mock_subscription = MagicMock()
        mock_subscription.id = 'sub_test123'
        mock_subscription.customer = 'cus_test123'

        StripeService.handle_subscription_deleted(mock_subscription)

        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.subscription_status,
            BillingProfile.STATUS_CANCELED
        )
        self.assertEqual(self.profile.stripe_subscription_id, '')
