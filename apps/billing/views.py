"""
Billing views.

Handles plan selection, checkout, success/cancel pages, and customer portal.
"""

import logging

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.core.utils import user_log_id
from .models import BillingProfile
from .services import StripeService, determine_tier_by_age, get_stripe

logger = logging.getLogger(__name__)


def get_or_create_billing_profile(user):
    """Get or create a billing profile for a user."""
    profile, created = BillingProfile.objects.get_or_create(user=user)
    if created:
        # Set the tier based on user's age
        profile.pricing_tier = determine_tier_by_age(user.date_of_birth)
        profile.save(update_fields=['pricing_tier'])
    return profile


@login_required
def select_plan(request):
    """
    Display available subscription plans.

    Shows appropriate plans based on user's age (student vs adult).
    """
    user = request.user
    profile = get_or_create_billing_profile(user)

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
        logger.exception(f"Checkout error for {user_log_id(request.user)}: {e}")
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
        'profile': get_or_create_billing_profile(request.user),
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
        logger.exception(f"Portal error for {user_log_id(request.user)}: {e}")
        messages.error(request, 'Unable to access billing portal. Please try again.')
        return redirect('billing:billing_settings')


@login_required
def billing_settings(request):
    """
    Display billing settings and subscription status.

    Shows current plan, next billing date, referral stats, and credits.
    """
    profile = get_or_create_billing_profile(request.user)

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
        logger.exception(f"Cancel error for {user_log_id(request.user)}: {e}")
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


@login_required
def submit_suggestion(request):
    """
    Submit a feature suggestion.

    Rate limited to 3 suggestions per user per month.
    """
    from .forms import FeatureSuggestionForm
    from .models import FeatureSuggestion
    from django.utils import timezone
    from datetime import timedelta

    # Check rate limit (3 per month)
    month_ago = timezone.now() - timedelta(days=30)
    recent_count = FeatureSuggestion.objects.filter(
        user=request.user,
        created_at__gte=month_ago,
    ).count()

    if request.method == 'POST':
        if recent_count >= 3:
            messages.error(
                request,
                'You can only submit 3 suggestions per month. Please wait before submitting more.'
            )
            return redirect('billing:billing_settings')

        form = FeatureSuggestionForm(request.POST)
        if form.is_valid():
            suggestion = form.save(commit=False)
            suggestion.user = request.user
            suggestion.save()
            messages.success(
                request,
                'Thank you for your suggestion! We review all ideas and will notify you if we implement yours.'
            )
            return redirect('billing:billing_settings')
    else:
        form = FeatureSuggestionForm()

    return render(request, 'billing/submit_suggestion.html', {
        'form': form,
        'suggestions_remaining': max(0, 3 - recent_count),
    })


@login_required
def payout_preferences(request):
    """
    Founding Members can set their payout preferences.
    """
    from .forms import PayoutPreferencesForm

    profile = get_or_create_billing_profile(request.user)

    # Only Founding Members can access this
    if not profile.is_founding_member:
        messages.error(request, 'Payout preferences are only available for Founding Members.')
        return redirect('billing:billing_settings')

    if request.method == 'POST':
        form = PayoutPreferencesForm(request.POST)
        if form.is_valid():
            profile.payout_method = form.cleaned_data['payout_method']
            profile.payout_email = form.cleaned_data.get('payout_email', '')
            profile.payout_phone = form.cleaned_data.get('payout_phone', '')
            profile.save(update_fields=[
                'payout_method',
                'payout_email',
                'payout_phone',
                'updated_at',
            ])
            messages.success(request, 'Payout preferences updated.')
            return redirect('billing:billing_settings')
    else:
        form = PayoutPreferencesForm(initial={
            'payout_method': profile.payout_method,
            'payout_email': profile.payout_email,
            'payout_phone': profile.payout_phone,
        })

    return render(request, 'billing/payout_preferences.html', {
        'form': form,
        'profile': profile,
    })


@login_required
def credit_history(request):
    """
    View account credit transaction history.
    """
    from .models import CreditTransaction

    transactions = CreditTransaction.objects.filter(
        user=request.user
    ).order_by('-created_at')[:50]

    return render(request, 'billing/credit_history.html', {
        'transactions': transactions,
        'profile': get_or_create_billing_profile(request.user),
    })


@login_required
def trial_expired(request):
    """
    Display trial expired page with subscription options.

    Users are redirected here when their free trial has expired
    and they don't have an active subscription.
    """
    profile = get_or_create_billing_profile(request.user)

    # If user actually has access, redirect to dashboard
    if profile.has_access:
        return redirect('dashboard:home')

    # Determine which tier the user qualifies for
    eligible_tier = determine_tier_by_age(request.user.date_of_birth)

    context = {
        'profile': profile,
        'eligible_tier': eligible_tier,
        'is_student_eligible': eligible_tier == BillingProfile.TIER_STUDENT,
        'trial_ended': profile.trial_ends_at,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    }

    return render(request, 'billing/trial_expired.html', context)


@login_required
@require_POST
def select_faith_only(request):
    """
    User selects the free Faith Only plan after trial expires.

    Sets the billing profile to FAITH_ONLY tier/status and records the selection date.
    Faith Only gives permanent free access to the Faith module only.
    """
    profile = get_or_create_billing_profile(request.user)
    prefs = request.user.preferences

    # Set Faith Only status
    profile.pricing_tier = BillingProfile.TIER_FAITH_ONLY
    profile.subscription_status = BillingProfile.STATUS_FAITH_ONLY
    profile.save(update_fields=['pricing_tier', 'subscription_status', 'updated_at'])

    # Record when Faith Only was selected (for upgrade prompt scheduling)
    prefs.faith_only_selected_at = timezone.now()
    prefs.save(update_fields=['faith_only_selected_at', 'updated_at'])

    messages.success(
        request,
        "Welcome to Faith Only! You now have permanent free access to Scripture, "
        "prayers, reading plans, and Bible study tools."
    )

    return redirect("faith:home")


@login_required
def faith_only_upgrade(request):
    """
    Display upgrade page for Faith Only users trying to access restricted features.

    Shows what features they're missing and subscription options to upgrade.
    """
    profile = get_or_create_billing_profile(request.user)

    # If user has full access, redirect to dashboard
    if profile.has_access:
        return redirect('dashboard:home')

    # If not Faith Only (e.g., trial expired, no subscription), redirect to trial_expired
    if not profile.is_faith_only:
        return redirect('billing:trial_expired')

    # Determine which tier the user qualifies for
    eligible_tier = determine_tier_by_age(request.user.date_of_birth)

    context = {
        'profile': profile,
        'eligible_tier': eligible_tier,
        'is_student_eligible': eligible_tier == BillingProfile.TIER_STUDENT,
        'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
    }

    return render(request, 'billing/faith_only_upgrade.html', context)


@login_required
@require_GET
def faith_upgrade_prompt_check(request):
    """
    Check if the Faith Only upgrade prompt should be shown.

    Prompt Schedule (from faith_only_selected_at):
    - Week 1: Days 7-13 (show once)
    - Month 2: Days 30-44 (show once)
    - Month 3: Days 60-74 (show once, final)
    - After Day 75: No more prompts

    Returns JSON:
        should_show: bool
        prompt_type: 'week1' | 'month2' | 'month3' | null
        days_on_plan: int
    """
    profile = get_or_create_billing_profile(request.user)
    prefs = request.user.preferences

    # Only show prompts for Faith Only users
    if not profile.is_faith_only:
        return JsonResponse({'should_show': False})

    selected_at = prefs.faith_only_selected_at
    if not selected_at:
        return JsonResponse({'should_show': False})

    days_since_selection = (timezone.now() - selected_at).days

    # Week 1 prompt (days 7-13)
    if 7 <= days_since_selection < 14 and not prefs.faith_only_upgrade_week1_shown:
        return JsonResponse({
            'should_show': True,
            'prompt_type': 'week1',
            'days_on_plan': days_since_selection
        })

    # Month 2 prompt (days 30-44)
    if 30 <= days_since_selection < 45 and not prefs.faith_only_upgrade_month2_shown:
        return JsonResponse({
            'should_show': True,
            'prompt_type': 'month2',
            'days_on_plan': days_since_selection
        })

    # Month 3 prompt (days 60-74) - FINAL prompt
    if 60 <= days_since_selection < 75 and not prefs.faith_only_upgrade_month3_shown:
        return JsonResponse({
            'should_show': True,
            'prompt_type': 'month3',
            'days_on_plan': days_since_selection
        })

    return JsonResponse({'should_show': False})


@login_required
@require_POST
def faith_upgrade_prompt_dismiss(request):
    """
    Record that the upgrade prompt was shown/dismissed.

    POST body (JSON):
        prompt_type: 'week1' | 'month2' | 'month3'

    Updates the appropriate tracking field in UserPreferences.
    """
    prefs = request.user.preferences
    now = timezone.now()

    try:
        data = json.loads(request.body)
        prompt_type = data.get('prompt_type')
    except json.JSONDecodeError:
        prompt_type = request.POST.get('prompt_type')

    if prompt_type == 'week1':
        prefs.faith_only_upgrade_week1_shown = True
        prefs.faith_only_upgrade_week1_shown_at = now
        prefs.save(update_fields=[
            'faith_only_upgrade_week1_shown',
            'faith_only_upgrade_week1_shown_at',
            'updated_at'
        ])
    elif prompt_type == 'month2':
        prefs.faith_only_upgrade_month2_shown = True
        prefs.faith_only_upgrade_month2_shown_at = now
        prefs.save(update_fields=[
            'faith_only_upgrade_month2_shown',
            'faith_only_upgrade_month2_shown_at',
            'updated_at'
        ])
    elif prompt_type == 'month3':
        prefs.faith_only_upgrade_month3_shown = True
        prefs.faith_only_upgrade_month3_shown_at = now
        prefs.save(update_fields=[
            'faith_only_upgrade_month3_shown',
            'faith_only_upgrade_month3_shown_at',
            'updated_at'
        ])

    return JsonResponse({'success': True})
