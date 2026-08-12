"""
FinanceDomainTruth — the canonical interface to Finance truth.

Second domain proving the facade is domain-agnostic: it composes `CurrentFinance`
(Current Truth, sync-freshness shape) + the SAE finance snapshot, behind the SAME
interface as Health. History is pending a `FinanceHistory` provider (one grouped
Transaction query) — when added it registers here with no interface change.
"""
from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import DomainTruth, register_domain_truth


@register_domain_truth
class FinanceDomainTruth(DomainTruth):
    domain = "finance"
    current_metrics = ("net_worth", "month_spending")
    # Monthly cash-flow trends (FinanceHistory — one grouped Transaction query). With >= 2
    # history metrics Finance now composes a whole-domain executive assessment (state +
    # trends) automatically; the model reads spending/income/net over time.
    history_metrics = ("spending", "income", "net_cashflow")
    # Record-level truth over the canonical Transaction / FinancialAccount models — the
    # deterministic evidence behind "what did I spend at Costco", "my biggest expenses this
    # month", "which transactions drove this", "list my accounts". Exposure of EXISTING truth
    # (the same rows behind FinanceHistory + the Finance pages); the model reasons over the
    # records. Only the user's OWN, non-sensitive fields are surfaced — never credentials,
    # tokens, full account numbers, or import internals (last4 is the safe partial).
    entity_types = ("transaction", "account")
    _MAX_TX = 100

    def current(self, metric):
        from apps.finance.services.current_finance import CurrentFinance
        fn = {"net_worth": CurrentFinance.net_worth,
              "month_spending": CurrentFinance.month_spending}.get(metric)
        if fn is None:
            return CurrentTruth.absent("finance", metric, reason="unsupported metric")
        return fn(self.user)

    def history(self, metric, period="this_year", start=None, end=None, **kwargs):
        from apps.finance.services.finance_history import FinanceHistory
        fn = {"spending": FinanceHistory.spending,
              "income": FinanceHistory.income,
              "net_cashflow": FinanceHistory.net_cashflow}.get(metric)
        if fn is None:
            raise KeyError(f"finance history unsupported: {metric!r} "
                           f"(have {self.history_metrics})")
        return fn(self.user, period=period, start=start, end=end)

    # -- record-level entities (transactions + accounts) ----------------------
    def describe(self, entity_type="transaction", filters=None):
        et = (entity_type or "transaction")
        if et == "account":
            return self._describe_accounts()
        if et != "transaction":
            raise KeyError(f"finance domain cannot describe {et!r} "
                           f"(have {self.entity_types})")
        from datetime import date as _date

        from django.db.models import Q

        from apps.core.truth.periods import resolve_period
        from apps.core.utils import get_user_today
        from apps.finance.models import Transaction
        f = filters or {}
        # Canonical transaction rows (exclude opening-balance rows, exactly as FinanceHistory
        # does — one authority, one definition of "a transaction").
        qs = Transaction.objects.filter(user=self.user, is_opening_balance=False)
        if f.get("on_date"):
            d = f["on_date"]
            d = _date.fromisoformat(d[:10]) if isinstance(d, str) else d
            qs = qs.filter(date=d)
        elif f.get("start") or f.get("end") or f.get("period"):
            p = resolve_period(f.get("period") or "custom", get_user_today(self.user),
                               start=f.get("start"), end=f.get("end"))
            qs = qs.filter(date__range=(p.start, p.end))
        if f.get("contains"):                       # "what did I spend at Costco"
            c = str(f["contains"]).strip()
            qs = qs.filter(Q(description__icontains=c) | Q(payee__icontains=c))
        qs = qs.select_related("account", "category").order_by("-date", "-id")
        return [self._transaction_entity(t) for t in qs[:self._MAX_TX]]

    def _describe_accounts(self):
        from apps.finance.models import FinancialAccount
        accts = (FinancialAccount.objects.filter(user=self.user, is_hidden=False)
                 .order_by("sort_order", "name"))
        return [self._account_entity(a) for a in accts]

    def describe_one(self, name):
        # A NAMED lookup resolves an ACCOUNT ("my Chase Checking"); individual transactions are
        # not uniquely named — those come through describe('transaction', filters={contains:...}).
        from apps.finance.models import FinancialAccount
        q = (name or "").strip()
        if not q:
            return None
        matches = list(FinancialAccount.objects.filter(
            user=self.user, is_hidden=False, name__icontains=q)[:2])
        return self._account_entity(matches[0]) if len(matches) == 1 else None

    def _transaction_entity(self, t):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="transaction",
            identity=(t.description or t.payee or "transaction").strip(),
            definition={"amount": float(t.amount),
                        "direction": "income" if t.amount > 0 else "expense",
                        "category": t.category.name if t.category_id else None,
                        "account": t.account.name if t.account_id else None,
                        "payee": (t.payee or "").strip() or None},
            status="cleared" if t.is_cleared else "pending",
            plan={"date": t.date.isoformat()},
            freshness=F.CURRENT,
        )

    def _account_entity(self, a):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="account",
            identity=a.name,
            definition={"account_type": a.account_type,
                        "institution": (a.institution or "").strip() or None,
                        "last4": a.account_number_last4 or None,
                        "currency": a.currency,
                        "include_in_net_worth": a.include_in_net_worth},
            status="active",
            standing={"current_balance": float(a.current_balance)},
            freshness=F.CURRENT,
        )
