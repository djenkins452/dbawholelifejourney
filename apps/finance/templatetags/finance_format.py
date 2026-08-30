# ==============================================================================
# File: apps/finance/templatetags/finance_format.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The one way Finance renders money to a person.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Presentation only — nothing here changes a stored value, a sign, or a calculation.

Finance was rendering `${{ x|floatformat:2 }}`, which produced `$46968.05` (no
thousands separator) and, for anything negative, `$-396178.58` — a minus sign stranded
between the currency symbol and the digits, which is not how money is written anywhere.
A few places worked around it with `|slice:"1:"` to chop the sign off the string, which
is a formatting decision hidden inside a string operation.

Three filters, one rule each:

* `money`        — the value as it is:      `$46,968.05` · `-$396,178.58` · `$0.00`
* `money_signed` — always shows the sign:   `+$3,585.85` · `-$2,127.31`
* `money_abs`    — magnitude only:          `$396,178.58` (for "Over by …", or where a
                  neighbouring label or colour already carries the direction)

The minus always precedes the currency symbol. Semantic colour classes stay in the
templates: the number says how much, the class says what it means, and neither should
start deciding the other.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

#: What to show when there is genuinely nothing to show. Not "$0.00" — a missing value
#: and a zero balance are different facts, and only one of them is a number.
EMPTY = "—"


def _to_decimal(value):
    """Coerce whatever the template hands us, or return None if it is not a number."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


#: Two decimal places, rounded the way money is rounded.
CENTS = Decimal("0.01")


def _grouped(amount: Decimal) -> str:
    """Absolute value with thousands separators and exactly two decimals.

    Quantised with ROUND_HALF_UP explicitly. Python's default formatting uses
    banker's rounding, so `0.005` would render as `$0.00` — correct for statistics,
    surprising for money, and not what a person checking a figure expects. Only the
    DISPLAYED string is rounded; the stored value is untouched.
    """
    rounded = abs(amount).quantize(CENTS, rounding=ROUND_HALF_UP)
    return f"{rounded:,.2f}"


@register.filter
def money(value, empty=EMPTY):
    """`$46,968.05` · `-$396,178.58` · `$0.00`.

    The sign leads, so a negative reads as one number rather than a dollar sign
    followed by a surprise.
    """
    amount = _to_decimal(value)
    if amount is None:
        return empty
    sign = "-" if amount < 0 else ""
    return mark_safe(f"{sign}${_grouped(amount)}")


@register.filter
def money_signed(value, empty=EMPTY):
    """`+$3,585.85` · `-$2,127.31` · `$0.00`.

    For places where the direction is the point — a cash-flow line, an income vs
    expense pair — and the reader should not have to infer it from a colour alone.
    Zero takes no sign, because it has no direction.
    """
    amount = _to_decimal(value)
    if amount is None:
        return empty
    if amount > 0:
        sign = "+"
    elif amount < 0:
        sign = "-"
    else:
        sign = ""
    return mark_safe(f"{sign}${_grouped(amount)}")


@register.filter
def money_abs(value, empty=EMPTY):
    """`$396,178.58` — magnitude only, sign deliberately dropped.

    Use ONLY where the surrounding words already say the direction ("Over by …",
    "Spent"). Replaces `|floatformat:2|slice:"1:"`, which chopped the minus off the
    rendered string and silently produced "$96,178.58" for a positive number.
    """
    amount = _to_decimal(value)
    if amount is None:
        return empty
    return mark_safe(f"${_grouped(amount)}")
