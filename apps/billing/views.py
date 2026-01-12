"""
Billing views.

Handles plan selection, checkout, success/cancel pages, and customer portal.
"""

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .models import BillingProfile
from .services import StripeService, determine_tier_by_age, get_stripe

logger = logging.getLogger(__name__)


@login_required
def select_plan(request):
    """
    Display available subscription plans.

    Shows appropriate plans based on user's age (student vs adult).
    """
    user = request.user
    profile = user.billing_profile

    # Determine which tier the user qualifies for
    eligible_tier = determine_tier_by_age(user.date_of_birth)

    # Get promo code from URL if present
    promo_code = request.GET.get('promo', '')

    # Get referral code from session or URL
    referral_code = request.session.get('referral_code') or request.GET.get('ref', '')

    context = {
        'profile': profile,
        'eligible_tier': eligible_tier,
        'is_student_eligible': eligible_tier == BillingProfile.TIER_STUDENT,
        'promo_code': promo_code,
        'referral_code': referral_code,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    }

    return render(request, 'billing/select_plan.html', context)


@login_required
@require_POST
def create_checkout_session(request):
    """
    Create a Stripe Checkout session and redirect.

    POST params:
        price_key: The plan to purchase (student_monthly, adult_annual, etc.)
        promo_code: Optional promo code
    """
    price_key = request.POST.get('price_key')
    promo_code = request.POST.get('promo_code', '')

    if not price_key:
        messages.error(request, 'Please select a plan.')
        return redirect('billing:select_plan')

    # Get referral code from session
    referral_code = request.session.get('referral_code', '')

    try:
        success_url = request.build_absolute_uri(reverse('billing:checkout_success'))
        cancel_url = request.build_absolute_uri(reverse('billing:checkout_cancel'))

        session = StripeService.create_checkout_session(
            user=request.user,
            price_key=price_key,
            success_url=success_url,
            cancel_url=cancel_url,
            promo_code=promo_code,
            referral_code=referral_code,
        )

        return redirect(session.url)

    except ValueError as e:
        messages.error(request, str(e))
        return redirect('billing:select_plan')
    except Exception as e:
        logger.exception(f"Checkout error for {request.user.email}: {e}")
        messages.error(request, 'An error occurred. Please try again.')
        return redirect('billing:select_plan')


@login_required
def checkout_success(request):
    """
    Handle successful checkout return.

    The actual subscription update happens via webhook.
    This page just confirms to the user.
    """
    session_id = request.GET.get('session_id')

    # Optionally verify the session
    if session_id:
        try:
            stripe_client = get_stripe()
            session = stripe_client.checkout.Session.retrieve(session_id)
            # Session data can be used to show confirmation details
        except Exception:
            pass

    # Clear referral code from session
    if 'referral_code' in request.session:
        del request.session['referral_code']

    messages.success(request, 'Welcome to Whole Life Journey! Your subscription is now active.')

    return render(request, 'billing/checkout_success.html', {
        'profile': request.user.billing_profile,
    })


@login_required
def checkout_cancel(request):
    """
    Handle checkout cancellation.

    User clicked back or cancelled during Stripe Checkout.
    """
    messages.info(request, 'Checkout was cancelled. You can try again when ready.')
    return redirect('billing:select_plan')


@login_required
def customer_portal(request):
    """
    Redirect to Stripe Customer Portal.

    Allows users to manage their subscription, update payment method,
    view invoices, etc.
    """
    try:
        return_url = request.build_absolute_uri(reverse('billing:billing_settings'))
        session = StripeService.create_customer_portal_session(
            user=request.user,
            return_url=return_url,
        )
        return redirect(session.url)
    except Exception as e:
        logger.exception(f"Portal error for {request.user.email}: {e}")
        messages.error(request, 'Unable to access billing portal. Please try again.')
        return redirect('billing:billing_settings')


@login_required
def billing_settings(request):
    """
    Display billing settings and subscription status.

    Shows current plan, next billing date, referral stats, and credits.
    """
    profile = request.user.billing_profile

    # Get referral stats
    referral_count = profile.user.referrals_made.count() if hasattr(profile.user, 'referrals_made') else 0
    paying_referrals = profile.user.referral_rewards_given.filter(
        first_payment_date__isnull=False
    ).count() if hasattr(profile.user, 'referral_rewards_given') else 0

    context = {
        'profile': profile,
        'referral_count': referral_count,
        'paying_referrals': paying_referrals,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    }

    return render(request, 'billing/billing_settings.html', context)


@login_required
@require_POST
def cancel_subscription(request):
    """
    Cancel the user's subscription at period end.
    """
    try:
        StripeService.cancel_subscription(request.user, at_period_end=True)
        messages.success(
            request,
            'Your subscription will be cancelled at the end of your current billing period.'
        )
    except ValueError as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.exception(f"Cancel error for {request.user.email}: {e}")
        messages.error(request, 'Unable to cancel subscription. Please try again.')

    return redirect('billing:billing_settings')


@require_GET
def capture_referral(request):
    """
    Capture referral code from URL and store in session.

    URL: /join?ref=CODE or /billing/referral/?ref=CODE
    Redirects to signup page.
    """
    referral_code = request.GET.get('ref', '')

    if referral_code:
        # Validate the referral code exists
        if BillingProfile.objects.filter(referral_code=referral_code).exists():
            request.session['referral_code'] = referral_code
            logger.info(f"Captured referral code: {referral_code}")
        else:
            logger.warning(f"Invalid referral code attempted: {referral_code}")

    # Redirect to signup
    return redirect('account_signup')
