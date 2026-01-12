"""
Generate billing documentation from BILLING_CONFIG.

This command creates markdown documentation that reflects the current
billing configuration, ensuring documentation stays in sync with code.

Usage:
    python manage.py generate_billing_docs
    python manage.py generate_billing_docs --output docs/billing_pricing.md
"""

import os
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Generate billing documentation from BILLING_CONFIG'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='docs/billing_go_live_checklist.md',
            help='Output file path (default: docs/billing_go_live_checklist.md)',
        )
        parser.add_argument(
            '--print',
            action='store_true',
            help='Print to stdout instead of writing to file',
        )

    def handle(self, *args, **options):
        config = getattr(settings, 'BILLING_CONFIG', {})

        if not config:
            self.stderr.write(self.style.ERROR('BILLING_CONFIG not found in settings'))
            return

        doc = self.generate_documentation(config)

        if options['print']:
            self.stdout.write(doc)
        else:
            output_path = options['output']
            with open(output_path, 'w') as f:
                f.write(doc)
            self.stdout.write(
                self.style.SUCCESS(f'Documentation written to {output_path}')
            )

    def generate_documentation(self, config):
        """Generate markdown documentation from config."""
        student = config.get('student', {})
        adult = config.get('adult', {})
        founding = config.get('founding', {})
        rewards = config.get('rewards', {})
        stripe_fees = config.get('stripe_fees', {})
        env_vars = config.get('env_vars', {})

        # Calculate net revenue after Stripe fees
        def net_revenue(price):
            fee_pct = stripe_fees.get('percentage', Decimal('2.9'))
            fee_flat = stripe_fees.get('flat_fee', Decimal('0.30'))
            fee = (price * fee_pct / 100) + fee_flat
            return price - fee

        doc = f"""# WLJ Billing System - Go Live Checklist (Phase 12)

**Auto-generated from BILLING_CONFIG**
**Business Entity:** {config.get('business_name', 'Beacon Innovation LLC')}
**Product:** {config.get('product_name', 'Whole Life Journey')}

---

## Pricing Configuration

### Tier Thresholds
- **Student Max Age:** {config.get('student_max_age', 22)} (age {config.get('student_max_age', 22)} and under)
- **Adult Min Age:** {config.get('adult_min_age', 23)} (age {config.get('adult_min_age', 23)} and over)

### Pricing Tiers

| Tier | Monthly | Annual | Savings | Description |
|------|---------|--------|---------|-------------|
| **{student.get('name', 'Student')}** | ${student.get('monthly_price', '4.99')} | ${student.get('annual_price', '49.00')} | {student.get('annual_savings_percent', 18)}% | {student.get('description', 'For students age 22 and under')} |
| **{adult.get('name', 'Adult')}** | ${adult.get('monthly_price', '7.99')} | ${adult.get('annual_price', '79.00')} | {adult.get('annual_savings_percent', 18)}% | {adult.get('description', 'For adults age 23 and over')} |
| **{founding.get('name', 'Founding Member')}** | - | - | Lifetime | ${founding.get('lifetime_price', '59.00')} one-time |

### Revenue After Stripe Fees ({stripe_fees.get('percentage', '2.9')}% + ${stripe_fees.get('flat_fee', '0.30')})

| Plan | Price | Stripe Fee | Net Revenue | Margin |
|------|-------|------------|-------------|--------|
| Student Monthly | ${student.get('monthly_price', '4.99')} | ${(student.get('monthly_price', Decimal('4.99')) * stripe_fees.get('percentage', Decimal('2.9')) / 100 + stripe_fees.get('flat_fee', Decimal('0.30'))):.2f} | ${net_revenue(student.get('monthly_price', Decimal('4.99'))):.2f} | {(net_revenue(student.get('monthly_price', Decimal('4.99'))) / student.get('monthly_price', Decimal('4.99')) * 100):.1f}% |
| Student Annual | ${student.get('annual_price', '49.00')} | ${(student.get('annual_price', Decimal('49.00')) * stripe_fees.get('percentage', Decimal('2.9')) / 100 + stripe_fees.get('flat_fee', Decimal('0.30'))):.2f} | ${net_revenue(student.get('annual_price', Decimal('49.00'))):.2f} | {(net_revenue(student.get('annual_price', Decimal('49.00'))) / student.get('annual_price', Decimal('49.00')) * 100):.1f}% |
| Adult Monthly | ${adult.get('monthly_price', '7.99')} | ${(adult.get('monthly_price', Decimal('7.99')) * stripe_fees.get('percentage', Decimal('2.9')) / 100 + stripe_fees.get('flat_fee', Decimal('0.30'))):.2f} | ${net_revenue(adult.get('monthly_price', Decimal('7.99'))):.2f} | {(net_revenue(adult.get('monthly_price', Decimal('7.99'))) / adult.get('monthly_price', Decimal('7.99')) * 100):.1f}% |
| Adult Annual | ${adult.get('annual_price', '79.00')} | ${(adult.get('annual_price', Decimal('79.00')) * stripe_fees.get('percentage', Decimal('2.9')) / 100 + stripe_fees.get('flat_fee', Decimal('0.30'))):.2f} | ${net_revenue(adult.get('annual_price', Decimal('79.00'))):.2f} | {(net_revenue(adult.get('annual_price', Decimal('79.00'))) / adult.get('annual_price', Decimal('79.00')) * 100):.1f}% |
| Founding Lifetime | ${founding.get('lifetime_price', '59.00')} | ${(founding.get('lifetime_price', Decimal('59.00')) * stripe_fees.get('percentage', Decimal('2.9')) / 100 + stripe_fees.get('flat_fee', Decimal('0.30'))):.2f} | ${net_revenue(founding.get('lifetime_price', Decimal('59.00'))):.2f} | {(net_revenue(founding.get('lifetime_price', Decimal('59.00'))) / founding.get('lifetime_price', Decimal('59.00')) * 100):.1f}% |

---

## Rewards Configuration

| Reward Type | Amount | Description |
|-------------|--------|-------------|
| **Referral Bonus** | ${rewards.get('referral_bonus', '5.00')} | Both referrer and referred user receive this |
| **Suggestion Reward** | ${rewards.get('suggestion_reward', '5.00')} | For implemented feature suggestions |
| **Founding Quarterly Bonus** | ${founding.get('quarterly_bonus_per_referral', '5.00')} | Per qualified referral ({rewards.get('referral_qualification_days', 90)} days) |

**Limits:**
- Suggestions per month: {rewards.get('suggestions_per_month_limit', 3)}
- Referral qualification period: {rewards.get('referral_qualification_days', 90)} days

---

## Stripe Setup

### Step 1: Create Stripe Account

1. Go to https://dashboard.stripe.com/register
2. Sign up using **{config.get('business_name', 'Beacon Innovation LLC')}** business details
3. Complete business verification (EIN, bank account)

### Step 2: Create Products in Stripe Dashboard

Go to https://dashboard.stripe.com/products and create:

#### Product 1: {student.get('name', 'Student')} Subscription
- **Monthly Price:** ${student.get('monthly_price', '4.99')}/month → copy ID to `STRIPE_PRICE_STUDENT_MONTHLY`
- **Annual Price:** ${student.get('annual_price', '49.00')}/year → copy ID to `STRIPE_PRICE_STUDENT_ANNUAL`

#### Product 2: {adult.get('name', 'Adult')} Subscription
- **Monthly Price:** ${adult.get('monthly_price', '7.99')}/month → copy ID to `STRIPE_PRICE_ADULT_MONTHLY`
- **Annual Price:** ${adult.get('annual_price', '79.00')}/year → copy ID to `STRIPE_PRICE_ADULT_ANNUAL`

#### Product 3: {founding.get('name', 'Founding Member')}
- **Lifetime Price:** ${founding.get('lifetime_price', '59.00')} one-time → copy ID to `STRIPE_PRICE_FOUNDING`

### Step 3: Configure Webhook

1. Go to https://dashboard.stripe.com/webhooks
2. Add endpoint: `https://wholelifejourney.com/billing/webhook/stripe/`
3. Select events:
   - `checkout.session.completed`
   - `invoice.paid`
   - `invoice.payment_failed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Copy signing secret to `STRIPE_WEBHOOK_SECRET`

---

## Environment Variables

Set these in Railway (or your hosting provider):

```bash
# Stripe API Keys
STRIPE_PUBLIC_KEY=pk_live_xxxxxxxxxxxxxxxxxxxx
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxx

# Price IDs (from Stripe Dashboard)
STRIPE_PRICE_STUDENT_MONTHLY=price_xxxx  # ${student.get('monthly_price', '4.99')}/month
STRIPE_PRICE_STUDENT_ANNUAL=price_xxxx   # ${student.get('annual_price', '49.00')}/year
STRIPE_PRICE_ADULT_MONTHLY=price_xxxx    # ${adult.get('monthly_price', '7.99')}/month
STRIPE_PRICE_ADULT_ANNUAL=price_xxxx     # ${adult.get('annual_price', '79.00')}/year
STRIPE_PRICE_FOUNDING=price_xxxx         # ${founding.get('lifetime_price', '59.00')} lifetime
```

### Variable Reference

| Variable | Description |
|----------|-------------|
"""
        for var_name, description in env_vars.items():
            doc += f"| `{var_name}` | {description} |\n"

        doc += f"""
---

## Key URLs

| URL | Purpose |
|-----|---------|
| `/join` | Referral capture + redirect to signup |
| `/billing/plans/` | Plan selection page |
| `/billing/settings/` | Billing settings (manage subscription) |
| `/billing/portal/` | Stripe Customer Portal |
| `/billing/webhook/stripe/` | Stripe webhook endpoint |
| `/billing/suggest/` | Feature suggestion form |
| `/billing/credits/` | Credit history |
| `/billing/payout/` | Payout preferences (Founding Members) |

---

## Post-Setup Verification

1. **Test Webhook:** Send test event from Stripe dashboard
2. **Test Checkout:** Use test card `4242 4242 4242 4242`
3. **Verify Profile:** Check BillingProfile updated in Django admin

---

## Configuration File Reference

To change pricing, edit `BILLING_CONFIG` in `config/settings.py`.
Then run: `python manage.py generate_billing_docs` to update this file.

---

*Auto-generated by `python manage.py generate_billing_docs`*
"""

        return doc
