# WLJ Billing System - Go Live Checklist (Phase 12)

**Created:** 2026-01-12
**Status:** Ready for implementation
**Phases 1-11:** Complete (all code deployed, 59 tests passing)

---

## Overview

The billing system code is 100% complete and deployed. This document covers the remaining configuration steps to enable live payments.

**Business Entity:** Beacon Innovation LLC (has EIN and bank account)

---

## Step 1: Create Stripe Account

1. Go to https://dashboard.stripe.com/register
2. Sign up using Beacon Innovation LLC business details
3. Complete business verification (EIN, bank account for payouts)
4. Note your API keys from https://dashboard.stripe.com/apikeys:
   - Publishable key: `pk_live_...`
   - Secret key: `sk_live_...`

---

## Step 2: Create Products and Prices in Stripe

Go to https://dashboard.stripe.com/products and create:

### Product 1: Student Subscription
- Name: "WLJ Student"
- Description: "Whole Life Journey subscription for students (age 22 and under)"
- **Price 1 (Monthly):** $3.99/month, recurring
  - Copy Price ID → `STRIPE_PRICE_STUDENT_MONTHLY`
- **Price 2 (Annual):** $39.00/year, recurring
  - Copy Price ID → `STRIPE_PRICE_STUDENT_ANNUAL`

### Product 2: Adult Subscription
- Name: "WLJ Adult"
- Description: "Whole Life Journey subscription for adults (age 23+)"
- **Price 1 (Monthly):** $7.99/month, recurring
  - Copy Price ID → `STRIPE_PRICE_ADULT_MONTHLY`
- **Price 2 (Annual):** $79.00/year, recurring
  - Copy Price ID → `STRIPE_PRICE_ADULT_ANNUAL`

### Product 3: Founding Member
- Name: "WLJ Founding Member"
- Description: "Lifetime access with quarterly referral bonuses"
- **Price:** $59.00 one-time
  - Copy Price ID → `STRIPE_PRICE_FOUNDING`

---

## Step 3: Create Promo Codes (Optional)

Go to https://dashboard.stripe.com/coupons

### Launch Discount (20% off)
1. Click "Create coupon"
2. Type: Percentage discount
3. Percentage off: 20%
4. Duration: Once (first payment only)
5. Create a promo code: `LAUNCH20`

### Founding Member Discount
1. Create another coupon if desired for early bird pricing

---

## Step 4: Configure Webhook

Go to https://dashboard.stripe.com/webhooks

1. Click "Add endpoint"
2. Endpoint URL: `https://wholelifejourney.com/billing/webhook/stripe/`
3. Select events to listen for:
   - `checkout.session.completed`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Click "Add endpoint"
5. Copy the **Signing secret** → `STRIPE_WEBHOOK_SECRET`

---

## Step 5: Set Environment Variables in Railway

Go to Railway dashboard → WLJ project → Variables

Add these environment variables:

```
STRIPE_PUBLIC_KEY=pk_live_xxxxxxxxxxxxxxxxxxxx
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxx
STRIPE_PRICE_STUDENT_MONTHLY=price_xxxxxxxxxxxxxxxxxxxx
STRIPE_PRICE_STUDENT_ANNUAL=price_xxxxxxxxxxxxxxxxxxxx
STRIPE_PRICE_ADULT_MONTHLY=price_xxxxxxxxxxxxxxxxxxxx
STRIPE_PRICE_ADULT_ANNUAL=price_xxxxxxxxxxxxxxxxxxxx
STRIPE_PRICE_FOUNDING=price_xxxxxxxxxxxxxxxxxxxx
```

---

## Step 6: Run Database Migration (if not auto-run)

Railway should auto-run migrations on deploy. If needed manually:

```bash
# In Railway console or via railway run
python manage.py migrate
```

The billing migration creates:
- BillingProfile (linked to each user)
- ReferralReward
- ReferralQualification
- FoundingMemberPayout
- FeatureSuggestion
- CreditTransaction
- PromoCodeUsage
- PaymentAuditLog

---

## Step 7: Start Billing Scheduler

The billing scheduler handles automated tasks. Add to your Railway start command or run separately:

```bash
# Option A: Add to Procfile (if using)
scheduler: python manage.py run_billing_scheduler

# Option B: Run as separate Railway service
python manage.py run_billing_scheduler
```

**Scheduled Tasks:**
- Daily 3am: Birthday processing (age recalculation, student→adult graduation)
- Monthly 1st: Referral qualification checks (90-day tracking)
- Quarterly (Jan/Apr/Jul/Oct 1st): Founding Member bonus payouts

---

## Step 8: Verify Setup

### Test Webhook
1. Go to Stripe webhook dashboard
2. Click "Send test webhook"
3. Select `checkout.session.completed`
4. Verify 200 response in webhook logs

### Test Checkout Flow
1. Log in to WLJ as test user
2. Go to /billing/plans/
3. Click a plan
4. Use Stripe test card: `4242 4242 4242 4242`
5. Complete checkout
6. Verify BillingProfile updated in Django admin

---

## Step 9: Invite Founding Members

Send email invitations with:
- Direct signup link: `https://wholelifejourney.com/join`
- Or with promo code: `https://wholelifejourney.com/billing/plans/?promo=LAUNCH20`

---

## Key URLs

| URL | Purpose |
|-----|---------|
| `/join` | Referral capture + redirect to signup |
| `/billing/plans/` | Plan selection page |
| `/billing/settings/` | Billing settings (manage subscription) |
| `/billing/portal/` | Stripe Customer Portal redirect |
| `/billing/webhook/stripe/` | Stripe webhook endpoint |
| `/billing/suggest/` | Feature suggestion form |
| `/billing/credits/` | Credit history |
| `/billing/payout/` | Payout preferences (Founding Members) |

---

## Admin Features

Access at `/admin/billing/`:

- **BillingProfile**: View/edit user subscriptions, credits, tiers
- **ReferralReward**: Track referral signups and rewards
- **FeatureSuggestion**: Review suggestions, mark implemented (awards $5)
- **FoundingMemberPayout**: Quarterly payout records
- **PaymentAuditLog**: Immutable payment activity log

---

## Pricing Summary

| Tier | Monthly | Annual | One-time |
|------|---------|--------|----------|
| Student (≤22) | $3.99 | $39 | - |
| Adult (≥23) | $7.99 | $79 | - |
| Founding | - | - | $59 lifetime |

---

## Rewards System

| Action | Reward |
|--------|--------|
| Referral (both parties) | $5 credit each |
| Feature suggestion implemented | $5 credit |
| Founding Member quarterly bonus | $5 per qualified referral |

Credits apply automatically to next invoice.

---

## Troubleshooting

### Webhook 400 errors
- Check STRIPE_WEBHOOK_SECRET matches Stripe dashboard
- Verify endpoint URL is exactly `/billing/webhook/stripe/`

### Users not getting correct tier
- Check date_of_birth is set on User model
- Run: `python manage.py shell` then check `user.billing_profile.pricing_tier`

### Scheduler not running
- Check Railway logs for scheduler process
- Verify django-apscheduler tables exist

### Missing BillingProfile
- Signal should auto-create on user creation
- Manual fix: `BillingProfile.objects.get_or_create(user=user)`

---

## Files Reference

**Core Files:**
- `apps/billing/models.py` - All billing models
- `apps/billing/services.py` - StripeService class
- `apps/billing/webhooks.py` - Webhook handler
- `apps/billing/views.py` - UI views
- `apps/billing/admin.py` - Admin interface
- `apps/billing/email_service.py` - Email notifications

**Management Commands:**
- `python manage.py run_billing_scheduler` - Start scheduler
- `python manage.py process_birthdays` - Manual birthday processing
- `python manage.py process_quarterly_bonuses` - Manual bonus processing

**Templates:**
- `templates/billing/*.html` - UI templates (6 files)
- `templates/billing/email/*.html` - Email templates (13 files)

---

## Support

For issues, check:
1. Railway logs for errors
2. Stripe webhook logs for delivery failures
3. Django admin PaymentAuditLog for payment history
4. `docs/wlj_claude_changelog.md` for implementation details
