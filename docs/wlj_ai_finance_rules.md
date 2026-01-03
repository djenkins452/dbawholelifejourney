# ==============================================================================
# File: docs/wlj_ai_finance_rules.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: AI Finance Interpretation Rules - Safe, Explainable AI Behavior
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================

# AI Finance Interpretation Rules

## Overview

This document establishes the rules and boundaries for how AI (OpenAI) may interpret and respond to financial data within the Whole Life Journey application. These rules ensure:

1. **Safety** - AI never provides financial advice or exposes sensitive data
2. **Explainability** - All AI insights clearly state what data was used
3. **Privacy** - Credentials, tokens, and account numbers are never exposed
4. **Alignment** - AI behavior aligns with WLJ's calm, supportive philosophy

---

## 1. AI Data Access Rules

### 1.1 Allowed Data Access

The AI **MAY access** the following financial data for insight generation:

| Data Type | Model Field | Purpose | Sensitivity |
|-----------|-------------|---------|-------------|
| Account Names | `FinancialAccount.name` | Context for insights | Low |
| Account Types | `FinancialAccount.account_type` | Categorization | Low |
| Current Balances | `FinancialAccount.current_balance` | Net worth, trends | Medium |
| Transaction Amounts | `Transaction.amount` | Spending patterns | Medium |
| Transaction Dates | `Transaction.date` | Time-based analysis | Low |
| Transaction Descriptions | `Transaction.description` | Category suggestions | Medium |
| Transaction Categories | `TransactionCategory.name` | Spending breakdown | Low |
| Budget Amounts | `Budget.budgeted_amount` | Budget vs. actual | Medium |
| Budget Progress | `Budget.spent_amount` (calculated) | Progress tracking | Medium |
| Goal Names | `FinancialGoal.name` | Encouragement context | Low |
| Goal Progress | `FinancialGoal.progress_percentage` | Celebration triggers | Low |
| Goal Targets | `FinancialGoal.target_amount` | Progress calculation | Medium |
| Metric Snapshots | `FinancialMetricSnapshot.*` | Trend analysis | Medium |

### 1.2 Prohibited Data Access

The AI **MUST NEVER access** or receive:

| Data Type | Reason |
|-----------|--------|
| `account_number_last4` | Partial account numbers could be combined with other data |
| Bank connection credentials | Never stored, never accessible |
| OAuth tokens | Session/API tokens for third-party services |
| Import file contents | Raw CSV/OFX files may contain sensitive data |
| Full transaction payee details | May contain personal information |
| User's full email address | PII exposure risk |
| Password hashes | Never exposed to any external service |

### 1.3 Aggregation Preference

When possible, the AI should receive **aggregated data** rather than raw records:

**Preferred:**
```python
# Send aggregated summary
context = {
    "total_income_this_month": 5250.00,
    "total_expenses_this_month": 3800.00,
    "savings_rate": 27.6,
    "top_expense_categories": ["Housing", "Food", "Transportation"]
}
```

**Avoid:**
```python
# Don't send individual transaction list
context = {
    "transactions": [
        {"description": "Paycheck from ACME Corp", "amount": 2500},
        {"description": "Payment to Dr. Smith", "amount": -150},
        # This exposes employer name, medical provider, etc.
    ]
}
```

---

## 2. Allowed AI Outputs

### 2.1 Permitted Output Types

| Output Type | Description | Example |
|-------------|-------------|---------|
| **Summaries** | High-level overviews of financial health | "Your spending this month is 15% lower than last month" |
| **Trends** | Pattern identification over time | "You've consistently saved more in the second half of each month" |
| **Progress Updates** | Goal and budget tracking | "You're 68% of the way to your Emergency Fund goal!" |
| **Gentle Nudges** | Supportive accountability | "Your dining out category is at 85% of budget with 10 days left" |
| **Celebrations** | Milestone recognition | "Congratulations! You hit your $1,000 savings goal!" |
| **Observations** | Neutral pattern notes | "Your largest expense category this month was Transportation" |
| **Questions** | Reflective prompts | "What's one spending habit you're proud of this month?" |

### 2.2 Prohibited Output Types

The AI **MUST NOT** generate:

| Prohibited Output | Reason | Alternative |
|-------------------|--------|-------------|
| Investment advice | Requires licensed professional | "Consider speaking with a financial advisor" |
| Tax guidance | Legal/regulatory risk | "A tax professional can help with this" |
| Debt strategy recommendations | Complex financial decisions | Offer encouragement, not strategy |
| Specific savings targets | Personal financial planning | "What savings goal feels right for you?" |
| Credit score predictions | Unverifiable, potentially harmful | Never mention credit scores |
| Account recommendations | Product advice liability | Never recommend specific banks/products |
| Emergency fund calculations | Varies by individual situation | "Many experts suggest 3-6 months of expenses" |
| Retirement projections | Complex actuarial calculations | Defer to professionals |

### 2.3 Language Guidelines

**DO use:**
- "You may want to consider..."
- "Some people find it helpful to..."
- "Your data shows..."
- "Based on your transactions..."
- "It looks like..."

**DO NOT use:**
- "You should..."
- "You need to..."
- "You must..."
- "The best strategy is..."
- "I recommend..."
- "You're making a mistake by..."

---

## 3. Credential and Token Protection

### 3.1 Absolute Prohibitions

The following MUST NEVER appear in any AI prompt or response:

1. **Bank Connection Tokens**
   - OAuth access tokens
   - Refresh tokens
   - API keys for financial services
   - Session identifiers

2. **Account Identifiers**
   - Full or partial account numbers
   - Routing numbers
   - IBAN/SWIFT codes
   - Card numbers (including last 4)

3. **Authentication Data**
   - Passwords or password hints
   - Security questions/answers
   - MFA codes or backup codes
   - Biometric data references

4. **Third-Party Integration Data**
   - Plaid tokens (if implemented)
   - Bank API credentials
   - Import file paths
   - Raw file contents

### 3.2 Implementation Safeguards

```python
# Example: Data sanitization before AI processing
def prepare_finance_data_for_ai(user):
    """
    Prepare financial data for AI consumption.
    Sanitizes sensitive fields and aggregates where possible.
    """
    accounts = FinancialAccount.objects.filter(
        user=user, status='active'
    ).values(
        'name',           # OK - user-defined name
        'account_type',   # OK - enum value
        'current_balance' # OK - aggregated metric
        # EXCLUDED: account_number_last4, institution details
    )

    # Return aggregated summary, not raw records
    return {
        'total_assets': sum(a['current_balance'] for a in accounts if is_asset(a)),
        'total_liabilities': sum(a['current_balance'] for a in accounts if is_liability(a)),
        'account_count': len(accounts),
        # Don't include: raw account list, institution names
    }
```

### 3.3 Logging Requirements

When financial data is sent to AI:

1. **Log the event** (without the data itself)
2. **Record which aggregations** were sent
3. **Never log** actual balances or amounts in plain text
4. **Track consent** verification occurred

---

## 4. Explainability Requirements

### 4.1 Insight Attribution

Every AI-generated financial insight MUST include:

1. **Data Source Statement**: What data was used
2. **Timeframe**: What period the insight covers
3. **Confidence Qualifier**: When dealing with patterns/predictions

**Example Format:**
```
"Based on your transactions from November 1-30, your dining expenses
were $420, which is $80 under your $500 budget for that category."
```

### 4.2 Required Transparency Elements

| Element | Description | Example |
|---------|-------------|---------|
| **Data Source** | What data was analyzed | "Based on your November transactions..." |
| **Calculation Method** | How conclusions were reached | "Adding up all 'Food' category expenses..." |
| **Timeframe** | Period covered | "Over the past 30 days..." |
| **Limitations** | What the insight doesn't know | "This doesn't include cash transactions..." |

### 4.3 Uncertainty Handling

When AI cannot provide a clear insight:

**DO:**
- "I don't have enough data to identify clear patterns yet"
- "With only 2 weeks of data, trends may change"
- "This is based on the transactions you've logged"

**DON'T:**
- Make up patterns that don't exist
- Extrapolate from insufficient data
- Provide false precision ("You spend exactly $127.33 on coffee monthly")

---

## 5. User Consent Requirements

### 5.1 Consent Verification

Before any financial data is sent to AI, the system MUST verify:

```python
def check_finance_ai_consent(user) -> bool:
    """
    Check if user has consented to AI processing of financial data.

    Consent is implied by:
    1. General AI consent toggle is ON
    2. Finance module is enabled
    3. User has not explicitly opted out of Finance AI features
    """
    prefs = user.preferences

    return (
        prefs.ai_insights_enabled and      # General AI consent
        prefs.finance_enabled and          # Finance module active
        not prefs.finance_ai_disabled      # Not explicitly opted out
    )
```

### 5.2 Consent UI Requirements

The Finance module settings should include:

- [ ] Clear explanation of what AI features use financial data
- [ ] Toggle to disable AI features while keeping manual features
- [ ] Link to privacy policy section about AI data processing
- [ ] Display of what data AI can access (summary, not exhaustive)

---

## 6. Implementation Checklist

When implementing AI features for Finance module:

### 6.1 Before Sending Data to AI

- [ ] User consent verified via `check_finance_ai_consent()`
- [ ] Data aggregated (not raw transaction list)
- [ ] Sensitive fields removed (account numbers, institution details)
- [ ] No credentials or tokens in payload
- [ ] Logging event recorded (without sensitive data)

### 6.2 Response Processing

- [ ] Response does not contain financial advice
- [ ] No specific investment/debt/tax recommendations
- [ ] Language uses "observation" tone, not "advice" tone
- [ ] Response includes data source attribution
- [ ] Uncertainty is acknowledged where appropriate

### 6.3 Display to User

- [ ] Insight clearly labeled as AI-generated
- [ ] Disclaimer present for financial topics
- [ ] Option to dismiss or hide insight
- [ ] Feedback mechanism available

---

## 7. Standard Disclaimer Text

Include this disclaimer when displaying AI financial insights:

```html
<p class="ai-disclaimer">
    This insight is generated by AI based on the transactions you've logged.
    It is not financial advice. For investment, tax, or debt decisions,
    please consult a qualified financial professional.
</p>
```

---

## 8. Failure Modes and Fallbacks

### 8.1 When AI Cannot Generate Insight

- Return a graceful empty state, not an error
- Suggest adding more data for better insights
- Never fabricate insights

### 8.2 When AI Returns Inappropriate Content

- Log the incident for review
- Display generic fallback message
- Do not display the inappropriate content

### 8.3 API Failure

- Cache recent insights for fallback
- Show "unable to generate insight" message
- Retry with exponential backoff

---

## Appendix A: Related Documents

- `docs/wlj_security_review.md` - Security findings including AI consent (C-3)
- `docs/wlj_ai_assessment.md` - AI optimization and caching strategy
- `docs/wlj_claude_features.md` - Dashboard AI and Personal Assistant features
- `apps/ai/services.py` - Core AI service implementation
- `apps/finance/models.py` - Finance data models

---

## Appendix B: Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-03 | 1.0 | Initial document creation |

---

*This document is part of the WLJ Executable Work Orchestration System - Phase 6: Finance Module*
