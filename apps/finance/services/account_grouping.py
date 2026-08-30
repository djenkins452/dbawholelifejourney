# ==============================================================================
# File: apps/finance/services/account_grouping.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Accounts, gathered under the institution they actually come from.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Chase accounts under "Chase", First Horizon accounts under "First Horizon".

The institution comes from the account's **connection** — `bank_connection.
institution_name`, which the provider supplied when the connection was made. It is
never inferred from the account's own name or its free-text `institution` field: those
are labels a person can type anything into, and grouping money by a guess about a
string is how two "Chase"s and a "chase " end up as separate banks.

An account with no connection was created by hand, so it says so — "Manually added" —
rather than being filed under an institution nobody linked.

ONE function serves the dashboard card and the full Accounts page, so the two cannot
drift into disagreeing about which bank an account belongs to.
"""
from __future__ import annotations

#: Where hand-created and unlinked accounts go. Sorts last, deliberately: it is a
#: residual group, not an institution competing alphabetically with real ones.
MANUAL_GROUP = "Manually added"


def institution_name_for(account):
    """The authoritative display name of the institution behind this account."""
    connection = getattr(account, "bank_connection", None)
    if connection is None:
        return None
    name = (connection.institution_name or "").strip()
    return name or None


def group_accounts_by_institution(accounts):
    """`[{"institution": str, "is_manual": bool, "accounts": [...]}, …]`.

    Every account appears exactly once. Institutions sort by display name;
    "Manually added" sorts last however it compares alphabetically. Order WITHIN a
    group is left exactly as the caller supplied it, so the existing
    `sort_order, name` intent is preserved rather than re-decided here.
    """
    groups = {}
    for account in accounts:
        name = institution_name_for(account)
        key = name or MANUAL_GROUP
        groups.setdefault(key, []).append(account)

    ordered = sorted(
        groups.items(),
        # (is_manual, casefolded name) — manual last, everything else by display name.
        key=lambda item: (item[0] == MANUAL_GROUP, item[0].casefold()),
    )
    return [
        {"institution": name, "is_manual": name == MANUAL_GROUP, "accounts": rows}
        for name, rows in ordered
    ]
