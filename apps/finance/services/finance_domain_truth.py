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
    history_metrics = ()        # pending FinanceHistory (one Transaction query)

    def current(self, metric):
        from apps.finance.services.current_finance import CurrentFinance
        fn = {"net_worth": CurrentFinance.net_worth,
              "month_spending": CurrentFinance.month_spending}.get(metric)
        if fn is None:
            return CurrentTruth.absent("finance", metric, reason="unsupported metric")
        return fn(self.user)

    def history(self, metric, period="last_month", **kwargs):
        raise KeyError("finance history not yet registered (FinanceHistory pending)")
