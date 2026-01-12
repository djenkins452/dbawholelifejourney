# WLJ Stripe Integration Documentation

**Last Updated:** 2026-01-12
**Status:** Active - Deployed to Production

---

## Overview

Whole Life Journey uses Stripe for subscription billing with three pricing tiers:
- **Student** ($4.99/month or $49.00/year) - Age 22 and under
- **Adult** ($7.99/month or $79.00/year) - Age 23 and over
- **Founding Member** ($59.00 one-time) - Lifetime access with referral bonuses

---

## Stripe Dashboard

- **Account:** Beacon Innovation LLC
- **Dashboard:** https://dashboard.stripe.com
- **Products:** https://dashboard.stripe.com/products
- **Webhooks:** https://dashboard.stripe.com/webhooks
- **API Keys:** https://dashboard.stripe.com/apikeys

---

## Stripe Products & Price IDs

### Student Subscription (prod_TmO5s2yxNEL74M)
| Plan | Price | Price ID |
|------|-------|----------|
| Monthly | $4.99/month | `price_1SopJCAiNkM0OuTPEnSpZ8BF` |
| Annual | $49.00/year | `price_1SopJCAiNkM0OuTPUBN7RP2f` |

### Adult Subscription (prod_TmOAp3LAnuY79o)
| Plan | Price | Price ID |
|------|-------|----------|
| Monthly | $7.99/month | `price_1SopNzAiNkM0OuTPmp0N5ygr` |
| Annual | $79.00/year | `price_1SopNzAiNkM0OuTPgu0U6gBr` |

### Founding Member Lifetime (prod_TmOBXptgM4Zaxx)
| Plan | Price | Price ID |
|------|-------|----------|
| One-time | $59.00 | `price_1SopPMAiNkM0OuTPSB4yqJtE` |

---

## Environment Variables (Railway)

```bash
# Stripe API Keys
STRIPE_PUBLIC_KEY=pk_live_...        # Publishable key
STRIPE_SECRET_KEY=sk_live_...        # Secret key
STRIPE_WEBHOOK_SECRET=whsec_...      # Webhook signing secret

# Price IDs
STRIPE_PRICE_STUDENT_MONTHLY=price_1SopJCAiNkM0OuTPEnSpZ8BF
STRIPE_PRICE_STUDENT_ANNUAL=price_1SopJCAiNkM0OuTPUBN7RP2f
STRIPE_PRICE_ADULT_MONTHLY=price_1SopNzAiNkM0OuTPmp0N5ygr
STRIPE_PRICE_ADULT_ANNUAL=price_1SopNzAiNkM0OuTPgu0U6gBr
STRIPE_PRICE_FOUNDING=price_1SopPMAiNkM0OuTPSB4yqJtE
```

---

## Webhook Configuration

**Endpoint URL:** `https://wholelifejourney.com/billing/webhook/stripe/`

**Events Listened:**
- `checkout.session.completed` - Activates subscription after payment
- `invoice.paid` - Confirms recurring payment success
- `invoice.payment_failed` - Handles failed payments
- `customer.subscription.updated` - Tracks plan changes
- `customer.subscription.deleted` - Handles cancellations

---

## Key URLs

| URL | Purpose |
|-----|---------|
| `/billing/plans/` | Plan selection page |
| `/billing/checkout/` | Creates Stripe Checkout session |
| `/billing/success/` | Post-payment success page |
| `/billing/cancel/` | Checkout cancellation page |
| `/billing/settings/` | Subscription management |
| `/billing/portal/` | Stripe Customer Portal redirect |
| `/billing/webhook/stripe/` | Webhook endpoint |
| `/join?ref=CODE` | Referral code capture |

---

## Django Admin

| URL | Purpose |
|-----|---------|
| `/admin/billing/billingconfiguration/` | Manage pricing & rewards |
| `/admin/billing/billingprofile/` | View user subscriptions |
| `/admin/billing/paymentauditlog/` | Payment audit trail |
| `/admin/billing/credittransaction/` | Credit history |
| `/admin/billing/referralreward/` | Referral tracking |

---

## Key Files

| File | Purpose |
|------|---------|
| `apps/billing/models.py` | BillingConfiguration, BillingProfile, audit models |
| `apps/billing/services.py` | StripeService class |
| `apps/billing/webhooks.py` | Webhook handler |
| `apps/billing/views.py` | Plan selection, checkout flow |
| `apps/billing/admin.py` | Django Admin interface |
| `apps/billing/signals.py` | Auto-create BillingProfile on user creation |
| `templates/billing/` | Billing templates |

---

## Billing Models

### BillingConfiguration (Singleton)
Manages all pricing via Django Admin:
- Business name, product name
- Age threshold (student_max_age = 22)
- Pricing tiers (student/adult monthly/annual, founding lifetime)
- Rewards (referral_bonus, suggestion_reward, founding_quarterly_bonus)
- Rate limits (suggestions_per_month_limit, referral_qualification_days)

### BillingProfile
Per-user billing data:
- `pricing_tier` - student/adult/founding
- `subscription_status` - none/trial/active/past_due/canceled
- `billing_cycle` - monthly/annual/lifetime
- `stripe_customer_id` - Stripe customer ID
- `stripe_subscription_id` - Stripe subscription ID
- `referral_code` - Unique code for referrals
- `account_credit` - Credit balance

---

## Testing

### Test Card Numbers
- Success: `4242 4242 4242 4242`
- Decline: `4000 0000 0000 0002`
- Requires Auth: `4000 0025 0000 3155`

### Test Flow
1. Go to `/billing/plans/`
2. Select a plan
3. Use test card `4242 4242 4242 4242`
4. Any future expiration, any CVC
5. Verify webhook received in Stripe Dashboard
6. Check BillingProfile updated in Django Admin

---

## Current Issues

### CSS Not Loading on /billing/plans/
- Template extends `base.html` correctly
- Uses Tailwind CSS classes
- Need to investigate static files or browser cache

---

## Revenue After Stripe Fees (2.9% + $0.30)

| Plan | Price | Fee | Net | Margin |
|------|-------|-----|-----|--------|
| Student Monthly | $4.99 | $0.44 | $4.55 | 91.1% |
| Student Annual | $49.00 | $1.72 | $47.28 | 96.5% |
| Adult Monthly | $7.99 | $0.53 | $7.46 | 93.3% |
| Adult Annual | $79.00 | $2.59 | $76.41 | 96.7% |
| Founding | $59.00 | $2.01 | $56.99 | 96.6% |

---

## Rewards System

| Type | Amount | Description |
|------|--------|-------------|
| Referral Bonus | $5.00 | Both referrer and referred receive |
| Suggestion Reward | $5.00 | For implemented feature suggestions |
| Founding Quarterly | $5.00 | Per qualified referral (90 days) |

---

*See also: `docs/wlj_third_party_services.md` for full service documentation*
