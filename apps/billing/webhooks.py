"""
Stripe webhook handlers.

Processes incoming webhook events from Stripe.
"""

import logging

import stripe
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import PaymentAuditLog
from .services import StripeService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Handle Stripe webhook events.

    Endpoint: /billing/webhook/stripe/

    Verifies webhook signature and dispatches to appropriate handlers.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    if not webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        return HttpResponse(status=500)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        return HttpResponse(status=400)

    # Log the webhook receipt
    PaymentAuditLog.log(
        action=PaymentAuditLog.ACTION_WEBHOOK_RECEIVED,
        stripe_event_id=event.id,
        details={
            'type': event.type,
        }
    )

    # Route to appropriate handler
    event_type = event.type
    event_data = event.data.object

    try:
        if event_type == 'checkout.session.completed':
            StripeService.handle_checkout_completed(event_data)

        elif event_type == 'invoice.paid':
            StripeService.handle_invoice_paid(event_data)

        elif event_type == 'invoice.payment_failed':
            StripeService.handle_invoice_payment_failed(event_data)

        elif event_type == 'customer.subscription.updated':
            StripeService.handle_subscription_updated(event_data)

        elif event_type == 'customer.subscription.deleted':
            StripeService.handle_subscription_deleted(event_data)

        else:
            logger.info(f"Unhandled webhook event type: {event_type}")

    except Exception as e:
        logger.exception(f"Error handling webhook {event_type}: {e}")
        # Return 200 anyway to prevent Stripe retries for our errors
        # The error is logged and can be investigated

    return HttpResponse(status=200)
