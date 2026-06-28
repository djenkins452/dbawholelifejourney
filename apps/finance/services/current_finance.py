"""
CurrentFinance — Finance's authoritative Current Truth provider (Layer 1).

Second consumer of the platform Current Truth capability (apps.core.truth.current),
proving it is domain-agnostic: Finance reuses the SAME `CurrentTruth` object and the
SAME Freshness module as Health, with ZERO new composition logic.

The VALUE is read from pre-computed SAE finance state (never live-computed on the
request path — AI Engineering Rules). The FRESHNESS uses `classify_sync_freshness`
over `BankConnection.last_sync_at` — the snapshot shape of freshness, vs Health's
per-day shape — both from the one platform module.
"""
import logging

from apps.core.truth.current import CurrentTruth
from apps.core.truth.freshness import CURRENT, classify_sync_freshness

logger = logging.getLogger(__name__)

_STALE_AFTER_SECONDS = 24 * 3600   # bank data older than a day reads as stale


class CurrentFinance:

    @classmethod
    def net_worth(cls, user):
        summary = cls._summary(user)
        nw = summary.get("net_worth")
        if nw is None:
            return CurrentTruth.absent("finance", "net_worth",
                                       reason="no accounts on file")
        fresh, as_of = cls._sync_freshness(user)
        return CurrentTruth.found("finance", "net_worth", nw, fresh, unit="USD",
                                  as_of=as_of, source="build_finance_state")

    @classmethod
    def month_spending(cls, user):
        summary = cls._summary(user)
        spend = summary.get("month_spending")
        if spend is None:
            return CurrentTruth.absent("finance", "month_spending",
                                       reason="no transactions this month")
        fresh, as_of = cls._sync_freshness(user)
        return CurrentTruth.found("finance", "month_spending", spend, fresh,
                                  unit="USD", as_of=as_of, source="build_finance_state")

    # -- internals ------------------------------------------------------------
    @staticmethod
    def _summary(user):
        from apps.core.ai_state.state_engine import get_module_state
        try:
            st = get_module_state(user, "finance", allow_rebuild=False) or {}
        except Exception:
            logger.warning("CurrentFinance: finance state read failed user=%s",
                           getattr(user, "id", None), exc_info=True)
            st = {}
        return (st.get("_contract") or {}).get("summary") or {}

    @staticmethod
    def _sync_freshness(user):
        """(verdict, as_of_iso). Manual-only accounts have no sync concept → the
        user-entered balance IS current. Connected accounts read from last_sync_at."""
        from django.utils import timezone
        from apps.finance.models import BankConnection
        latest = (BankConnection.objects.filter(user=user)
                  .exclude(last_sync_at=None).order_by("-last_sync_at").first())
        if latest is None:
            return CURRENT, None
        verdict = classify_sync_freshness(
            has_data=True, last_sync=latest.last_sync_at, now=timezone.now(),
            stale_after_seconds=_STALE_AFTER_SECONDS)
        return verdict, latest.last_sync_at.date().isoformat()
