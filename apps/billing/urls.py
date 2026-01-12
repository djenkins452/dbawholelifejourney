"""
Billing URL configuration.
"""

from django.urls import path

from . import views, webhooks

app_name = 'billing'

urlpatterns = [
    # Plan selection and checkout
    path('plans/', views.select_plan, name='select_plan'),
    path('checkout/', views.create_checkout_session, name='create_checkout'),
    path('checkout/success/', views.checkout_success, name='checkout_success'),
    path('checkout/cancel/', views.checkout_cancel, name='checkout_cancel'),

    # Customer portal and settings
    path('portal/', views.customer_portal, name='customer_portal'),
    path('settings/', views.billing_settings, name='billing_settings'),
    path('cancel/', views.cancel_subscription, name='cancel_subscription'),

    # Referral capture
    path('referral/', views.capture_referral, name='capture_referral'),

    # Feature suggestions
    path('suggest/', views.submit_suggestion, name='submit_suggestion'),

    # Founding Member payout preferences
    path('payout-preferences/', views.payout_preferences, name='payout_preferences'),

    # Credit history
    path('credits/', views.credit_history, name='credit_history'),

    # Webhooks
    path('webhook/stripe/', webhooks.stripe_webhook, name='stripe_webhook'),
]
