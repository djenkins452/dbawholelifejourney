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
