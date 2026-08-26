# ==============================================================================
# File: apps/finance/services/category_taxonomy.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The globally-safe WLJ spending taxonomy + deterministic provider mapping.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""WLJ's canonical spending categories, and how provider classifications map onto them.

**Category and economic entity are separate dimensions.** "Software / Beacon / paid from
Personal" is three independent facts: what was bought, who bears the cost, and who paid.
Attribution answers the second; this module answers the first. Neither substitutes for
the other.

**Global means `user=None`.** `TransactionCategory.get_for_user` matches
`Q(user=user) | Q(is_system=True)`, so a row that is `is_system=True` AND owned by a user
leaks that user's classification into everyone else's list. Every category seeded here is
`user=None, is_system=True` — genuinely shared, owned by nobody.

**Mapping is deterministic and gated by the provider's own confidence.** No model call,
no per-transaction inference. When the provider is not confident enough, WLJ leaves the
category unset rather than guessing — an unset category is honest, a wrong one is not.
"""
from __future__ import annotations

#: Provider confidence levels WLJ will act on. Anything weaker leaves the category unset.
TRUSTED_CONFIDENCE = frozenset({"VERY_HIGH", "HIGH"})

#: (name, category_type, icon, color). Kept deliberately small: a short list a person can
#: hold in their head beats a taxonomy nobody maintains.
SYSTEM_CATEGORIES = (
    # Income
    ("Income", "income", "💰", "#10b981"),
    ("Refunds", "income", "↩️", "#6366f1"),
    # Movement between the user's own accounts — never spending.
    ("Transfer", "transfer", "🔁", "#64748b"),
    # Expense
    ("Housing", "expense", "🏠", "#ef4444"),
    ("Utilities", "expense", "💡", "#f59e0b"),
    ("Groceries", "expense", "🛒", "#22c55e"),
    ("Dining", "expense", "🍽️", "#f97316"),
    ("Transportation", "expense", "🚗", "#3b82f6"),
    ("Travel", "expense", "✈️", "#0ea5e9"),
    ("Health", "expense", "🩺", "#ec4899"),
    ("Insurance", "expense", "🛡️", "#8b5cf6"),
    ("Software", "expense", "💻", "#6366f1"),
    ("Professional Services", "expense", "🧾", "#14b8a6"),
    ("Entertainment", "expense", "🎬", "#a855f7"),
    ("Shopping", "expense", "🛍️", "#eab308"),
    ("Education", "expense", "🎓", "#0891b2"),
    ("Giving", "expense", "🎁", "#f43f5e"),
    ("Loan Payments", "expense", "🏦", "#78716c"),
    ("Fees", "expense", "💳", "#94a3b8"),
    ("Taxes", "expense", "🏛️", "#57534e"),
    ("Other", "expense", "•", "#6b7280"),
)

#: Plaid personal-finance-category PRIMARY -> WLJ category name. One-to-one, explicit,
#: reviewable. An unmapped primary leaves the category unset rather than guessing.
PROVIDER_PRIMARY_TO_WLJ = {
    "INCOME": "Income",
    "TRANSFER_IN": "Transfer",
    "TRANSFER_OUT": "Transfer",
    "LOAN_PAYMENTS": "Loan Payments",
    "BANK_FEES": "Fees",
    "ENTERTAINMENT": "Entertainment",
    "FOOD_AND_DRINK": "Dining",
    "GENERAL_MERCHANDISE": "Shopping",
    "HOME_IMPROVEMENT": "Housing",
    "MEDICAL": "Health",
    "PERSONAL_CARE": "Health",
    "GENERAL_SERVICES": "Professional Services",
    "GOVERNMENT_AND_NON_PROFIT": "Giving",
    "TRANSPORTATION": "Transportation",
    "TRAVEL": "Travel",
    "RENT_AND_UTILITIES": "Utilities",
}

#: DETAILED overrides where the primary is too coarse to be useful.
PROVIDER_DETAILED_TO_WLJ = {
    "FOOD_AND_DRINK_GROCERIES": "Groceries",
    "GENERAL_SERVICES_INSURANCE": "Insurance",
    "GENERAL_SERVICES_EDUCATION": "Education",
    "GENERAL_SERVICES_ACCOUNTING_AND_FINANCIAL_PLANNING": "Professional Services",
    "GENERAL_MERCHANDISE_ELECTRONICS": "Shopping",
    "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES": "Shopping",
    "RENT_AND_UTILITIES_RENT": "Housing",
    "GOVERNMENT_AND_NON_PROFIT_TAX_PAYMENT": "Taxes",
    "TRANSFER_OUT_ACCOUNT_TRANSFER": "Transfer",
    "TRANSFER_IN_ACCOUNT_TRANSFER": "Transfer",
    "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT": "Transfer",
    "INCOME_TAX_REFUND": "Refunds",
    # Software/SaaS lives under general services in the provider taxonomy.
    "GENERAL_SERVICES_CONSULTING_AND_LEGAL": "Professional Services",
}


def seed_system_categories():
    """Create the global taxonomy. Idempotent — safe to run any number of times.

    Returns `(created, existing)`. Never creates a user-owned row, and never edits a
    category a user has customised.
    """
    from apps.finance.models import TransactionCategory

    created, existing = 0, 0
    for index, (name, category_type, icon, color) in enumerate(SYSTEM_CATEGORIES):
        _, was_created = TransactionCategory.objects.get_or_create(
            user=None, is_system=True, name=name, category_type=category_type,
            parent=None,
            defaults={"icon": icon, "color": color, "sort_order": index,
                      "is_active": True},
        )
        created += int(was_created)
        existing += int(not was_created)
    return created, existing


def system_category(name):
    """Look up one global category by name, or None."""
    from apps.finance.models import TransactionCategory
    return TransactionCategory.objects.filter(
        user=None, is_system=True, name=name, is_active=True).first()


def system_category_map():
    """{name: category} for the global taxonomy — ONE query for a whole import batch."""
    from apps.finance.models import TransactionCategory
    return {c.name: c for c in TransactionCategory.objects.filter(
        user=None, is_system=True, is_active=True)}


def map_provider_category(primary, detailed, confidence):
    """Provider classification -> WLJ category NAME, or None. Deterministic.

    Returns None when the provider is not confident enough or the value is unmapped:
    an unset category is honest; a guessed one silently corrupts every total built on it.
    """
    if (confidence or "").upper() not in TRUSTED_CONFIDENCE:
        return None
    detailed_key = (detailed or "").upper()
    if detailed_key in PROVIDER_DETAILED_TO_WLJ:
        return PROVIDER_DETAILED_TO_WLJ[detailed_key]
    return PROVIDER_PRIMARY_TO_WLJ.get((primary or "").upper())
