# ==============================================================================
# File: docs/wlj_finance_module_scope.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Finance Module Scope - Concepts, boundaries, and WLJ integration
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-02
# Last Updated: 2026-01-02
# ==============================================================================

# WLJ Finance Module Scope

## Overview

The Finance Module extends Whole Life Journey's holistic approach to personal wellness by adding financial awareness and intentionality. Aligned with WLJ's philosophy of calm, long-term focus rather than frantic optimization, the Finance Module helps users track their financial life with purpose and reflection.

This document defines what the Finance Module includes, how it integrates with the broader WLJ ecosystem, and what is explicitly out of scope for the initial release.

---

## 1. Supported Financial Account Types

The Finance Module supports tracking of the following account types:

### 1.1 Asset Accounts (Positive Balance)

| Account Type | Description | Examples |
|--------------|-------------|----------|
| **Checking** | Primary transactional accounts | Bank of America Checking, Chase Checking |
| **Savings** | Interest-bearing deposit accounts | Emergency Fund, Vacation Savings |
| **Cash** | Physical cash or petty cash tracking | Wallet, Home Safe |
| **Investment** | Brokerage and retirement accounts | 401(k), IRA, Taxable Brokerage |
| **Property** | Real estate and valuable assets | Primary Home, Rental Property |
| **Other Asset** | Miscellaneous assets | Cryptocurrency, Collectibles |

### 1.2 Liability Accounts (Negative Balance)

| Account Type | Description | Examples |
|--------------|-------------|----------|
| **Credit Card** | Revolving credit lines | Visa, Mastercard, Store Cards |
| **Loan** | Installment loans | Personal Loan, Car Loan |
| **Mortgage** | Real estate debt | Primary Mortgage, HELOC |
| **Student Loan** | Educational debt | Federal Student Loans, Private Loans |
| **Other Liability** | Miscellaneous debts | Medical Bills, Family Loans |

### 1.3 Account Metadata

Each account includes:
- **Name**: User-defined account name
- **Institution**: Bank/financial institution name
- **Account Type**: From types above
- **Current Balance**: Latest balance (manually entered or synced)
- **Currency**: Default USD, with support for multi-currency
- **Is Active**: Whether account appears in active views
- **Notes**: Optional user notes

---

## 2. Core Finance Concepts

### 2.1 Transactions

The atomic unit of financial activity.

| Field | Description |
|-------|-------------|
| **Date** | When the transaction occurred |
| **Amount** | Transaction value (positive = inflow, negative = outflow) |
| **Description** | Merchant name or transaction description |
| **Category** | Budget category assignment |
| **Account** | Which account this affects |
| **Payee** | Who received/sent the money |
| **Notes** | Optional user notes |
| **Is Recurring** | Flag for expected recurring transactions |
| **Cleared** | Whether transaction has cleared the account |

### 2.2 Categories

Hierarchical classification for transactions and budgets.

```
Income
├── Salary
├── Business Income
├── Investment Income
├── Gifts Received
└── Other Income

Expenses
├── Housing
│   ├── Rent/Mortgage
│   ├── Utilities
│   └── Maintenance
├── Transportation
│   ├── Fuel
│   ├── Insurance
│   └── Maintenance
├── Food
│   ├── Groceries
│   └── Dining Out
├── Health
│   ├── Insurance
│   ├── Medical
│   └── Pharmacy
├── Giving
│   ├── Tithe
│   ├── Charity
│   └── Gifts Given
├── Personal
│   ├── Clothing
│   ├── Entertainment
│   └── Subscriptions
└── Other Expenses
```

Categories are:
- **System-defined** (seeded defaults) + **User-customizable**
- **Hierarchical** (parent/child relationships)
- **Color-coded** for visual distinction in charts

### 2.3 Budgets

Monthly spending plans by category.

| Field | Description |
|-------|-------------|
| **Category** | Which category this budget applies to |
| **Month** | The budget period (YYYY-MM) |
| **Budgeted Amount** | Planned spending limit |
| **Rollover** | Whether unused budget rolls to next month |
| **Notes** | Optional planning notes |

Budget features:
- **Monthly budgets** by category
- **Budget vs. Actual** comparison
- **Visual indicators**: On-track (green), Warning (yellow), Over (red)
- **Rollover option** for flexible categories

### 2.4 Financial Goals

Purpose-driven savings and debt targets.

| Goal Type | Description | Example |
|-----------|-------------|---------|
| **Savings Goal** | Accumulate a target amount | Emergency Fund: $10,000 |
| **Debt Payoff** | Pay down a liability | Pay off Credit Card: $5,000 → $0 |
| **Giving Goal** | Charitable contribution target | Annual Tithe: $6,000 |
| **Major Purchase** | Save for a specific purchase | New Car Down Payment: $8,000 |

Goal fields:
- **Name**: User-defined goal name
- **Type**: From types above
- **Target Amount**: Dollar amount to achieve
- **Current Amount**: Progress toward target
- **Target Date**: Optional deadline
- **Linked Account**: Optional account association
- **Status**: Active, Completed, Paused, Abandoned

### 2.5 Financial Metrics

Calculated indicators of financial health.

| Metric | Calculation | Purpose |
|--------|-------------|---------|
| **Net Worth** | Total Assets - Total Liabilities | Overall wealth snapshot |
| **Cash Flow** | Income - Expenses (monthly) | Monthly surplus/deficit |
| **Savings Rate** | (Income - Expenses) / Income × 100 | Percentage of income saved |
| **Debt-to-Income** | Monthly Debt Payments / Monthly Income × 100 | Debt burden indicator |
| **Emergency Fund Ratio** | Liquid Savings / Monthly Expenses | Months of runway |

---

## 3. Integration with WLJ Ecosystem

The Finance Module is not isolated—it connects meaningfully with existing WLJ modules.

### 3.1 Purpose Module Integration

| WLJ Concept | Finance Connection |
|-------------|-------------------|
| **Life Goals** | Financial goals can be linked to LifeGoal records (e.g., "Build financial security" → Emergency Fund goal) |
| **Life Domains** | "Finances" domain for organizing goals |
| **Annual Direction** | Financial intentions tied to Word of the Year |
| **Change Intentions** | Behavior shifts like "Spend mindfully" tracked via budget adherence |

### 3.2 Life Module Integration

| WLJ Concept | Finance Connection |
|-------------|-------------------|
| **Projects** | Major purchases or financial milestones as projects (e.g., "Pay off Student Loans") |
| **Tasks** | Financial to-dos: "Review budget", "Call insurance company", "Transfer to savings" |
| **Documents** | Financial documents stored in Life module (tax returns, insurance policies, statements) |
| **Calendar** | Bill due dates as calendar events |

### 3.3 Journal Module Integration

| WLJ Concept | Finance Connection |
|-------------|-------------------|
| **Journal Entries** | Reflect on financial decisions, goals, progress |
| **Categories** | "Financial" category for finance-related entries |
| **Mood Tracking** | Correlate mood with financial stress/wins |
| **Prompts** | Finance-specific reflection prompts |

Example prompts:
- "What financial decision am I most proud of this month?"
- "What does financial peace mean to me?"
- "How do my spending habits align with my values?"

### 3.4 Faith Module Integration (Optional)

For users with Faith module enabled:
- **Giving tracking** integrated with tithe/offering goals
- **Stewardship reflections** via journal prompts
- **Scripture references** for financial wisdom

### 3.5 Dashboard Integration

- **Finance widget** on main dashboard showing:
  - Net worth trend (mini chart)
  - Budget status summary
  - Upcoming bills
  - Goal progress
- **Quick actions**: Log expense, Check budget, View accounts

### 3.6 AI Coach Integration

The AI Personal Assistant can:
- Analyze spending patterns
- Identify budget concerns
- Celebrate financial wins
- Suggest reflection topics based on financial data
- Provide gentle accountability for financial goals

---

## 4. Scope Boundaries

### 4.1 In Scope (Initial Release)

| Feature | Priority | Description |
|---------|----------|-------------|
| Manual account management | P0 | Create, edit, archive accounts |
| Manual transaction entry | P0 | Add, edit, categorize transactions |
| Category management | P0 | System defaults + user customization |
| Monthly budgets | P1 | Budget by category with tracking |
| Financial goals | P1 | Savings, debt, giving goals |
| Basic metrics dashboard | P1 | Net worth, cash flow, savings rate |
| WLJ integration hooks | P1 | Links to Goals, Tasks, Journal |
| Transaction search/filter | P2 | Find transactions by various criteria |
| Budget vs. actual reports | P2 | Monthly spending analysis |
| Goal progress visualization | P2 | Charts and progress bars |
| CSV import | P2 | Import transactions from bank exports |

### 4.2 Explicitly Out of Scope (Initial Release)

| Feature | Reason | Future Consideration |
|---------|--------|---------------------|
| **Bank sync (Plaid/MX)** | Security complexity, cost, regulatory | Phase 2+ |
| **Bill pay integration** | External system complexity | Not planned |
| **Investment tracking** | Specialized complexity (lots, cost basis) | Phase 3+ |
| **Tax preparation** | Specialized domain, liability concerns | Not planned |
| **Multi-user/household** | Architectural complexity | Phase 2+ |
| **Credit score tracking** | Third-party API dependency | Phase 3+ |
| **Receipt scanning** | OCR complexity, camera integration | Phase 2+ |
| **Cryptocurrency real-time** | API complexity, volatility | Phase 3+ |
| **Paycheck splitting rules** | Automation complexity | Phase 2+ |
| **Recurring transaction automation** | Scheduling complexity | Phase 2+ |

### 4.3 Design Principles

1. **Manual-First**: Start with manual entry. Automation comes later.
2. **Simplicity over Features**: A simple tool used consistently beats a complex tool ignored.
3. **Privacy-Focused**: No third-party data sharing until explicitly enabled.
4. **Reflection-Oriented**: Encourage thoughtful engagement with finances, not just tracking.
5. **Calm Design**: No gamification, no anxiety-inducing alerts, no "streak" pressure.

---

## 5. Data Model Summary

```
FinancialAccount
├── user (FK → User)
├── name, institution
├── account_type (choices)
├── current_balance
├── currency, is_active
└── created_at, updated_at

Transaction
├── user (FK → User)
├── account (FK → FinancialAccount)
├── date, amount, description
├── category (FK → TransactionCategory)
├── payee, notes
├── is_recurring, cleared
└── created_at, updated_at

TransactionCategory
├── name, parent (self-FK)
├── is_system, is_active
├── color, icon
└── sort_order

Budget
├── user (FK → User)
├── category (FK → TransactionCategory)
├── month (YYYY-MM)
├── budgeted_amount
├── rollover_enabled
└── notes

FinancialGoal
├── user (FK → User)
├── name, goal_type (choices)
├── target_amount, current_amount
├── target_date
├── linked_account (FK → FinancialAccount, optional)
├── life_goal (FK → LifeGoal, optional)
├── status
└── created_at, updated_at

FinancialMetricSnapshot
├── user (FK → User)
├── date
├── net_worth
├── total_assets, total_liabilities
├── monthly_income, monthly_expenses
├── savings_rate
└── created_at
```

---

## 6. Security Considerations

| Concern | Mitigation |
|---------|------------|
| **Sensitive Data** | Account balances encrypted at rest |
| **Access Control** | Strict user ownership (UserOwnedModel pattern) |
| **Audit Trail** | All changes logged with timestamps |
| **Soft Delete** | Financial records never hard-deleted |
| **No External Sync** | Initial release is offline/manual only |
| **Session Security** | Standard WLJ session management |

---

## 7. Success Criteria

The Finance Module is successful when users can:

1. ✅ Add and manage financial accounts (all supported types)
2. ✅ Log transactions and categorize them consistently
3. ✅ Create and track monthly budgets with visual feedback
4. ✅ Set financial goals and see progress over time
5. ✅ View net worth and key financial metrics
6. ✅ Connect financial goals to life goals and journal reflections
7. ✅ Use the finance dashboard for quick insights

---

## 8. Related Documentation

- `CLAUDE.md` - Main project context
- `docs/wlj_claude_features.md` - Feature documentation
- `apps/purpose/models.py` - LifeGoal, HabitGoal models
- `apps/life/models.py` - Task, Project, Document models
- `apps/journal/models.py` - JournalEntry model

---

*Document Status: APPROVED*
*Created: 2026-01-02*
*Author: Claude Code (automated task execution)*
