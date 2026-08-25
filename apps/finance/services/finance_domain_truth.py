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
    # Recurring commitments, budgets, and savings/debt goals are the SAME canonical rows
    # the Finance pages render — exposed (never re-derived) so the model can answer "what
    # subscriptions am I paying for", "am I over on groceries", "how is my vacation fund
    # doing" from records instead of a summary. Facts only: amounts, dates, and lifecycle
    # state. Never a verdict (`Budget.health_status` is deliberately NOT surfaced — the
    # model interprets), never credentials, account numbers, or free-text notes.
    entity_types = ("transaction", "account", "recurring", "budget", "goal", "entity")
    _MAX_TX = 100
    # Budgets/goals/recurring are small per-user sets; the cap bounds the read and keeps
    # `Budget.spent_amount` (one aggregate per budget) predictable.
    _MAX_ROWS = 24

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
        if et == "recurring":
            return self._describe_recurring()
        if et == "budget":
            return self._describe_budgets(filters)
        if et == "goal":
            return self._describe_goals()
        if et == "entity":
            return self._describe_entities()
        if et != "transaction":
            raise KeyError(f"finance domain cannot describe {et!r} "
                           f"(have {self.entity_types})")
        from datetime import date as _date

        from django.db.models import Q

        from apps.core.truth.periods import resolve_period
        from apps.core.utils import get_user_today
        from apps.finance.services.attribution_population import financial_activity
        f = filters or {}
        # ONE population authority (F4): the same definition Budget, FinanceHistory, the
        # metric snapshots, and the dashboard use. No surface re-derives "what counts".
        qs = financial_activity(self.user)
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
        qs = self._with_attribution(qs)
        return [self._transaction_entity(t) for t in qs[:self._MAX_TX]]

    @staticmethod
    def _with_attribution(qs):
        """Prefetch the active attribution so attribution facts cost ONE extra query.

        `to_attr` is used deliberately: calling `.filter()` on a prefetched relation
        bypasses the prefetch cache and reintroduces the N+1.
        """
        from django.db.models import Prefetch

        from apps.finance.models import TransactionAttribution
        active = (TransactionAttribution.objects
                  .filter(attribution_status=TransactionAttribution.STATUS_ACTIVE,
                          share_basis=TransactionAttribution.SHARE_FULL)
                  .select_related("attributed_entity", "paid_by_entity"))
        return qs.prefetch_related(
            Prefetch("attributions", queryset=active, to_attr="_active_attribution"))

    def _describe_recurring(self):
        """Recurring commitments (subscriptions, bills, transfers) — the canonical rows."""
        from apps.finance.models import RecurringTransaction
        rows = (RecurringTransaction.objects.filter(user=self.user)
                .select_related("account", "category")
                .order_by("next_due_date", "name"))
        return [self._recurring_entity(r) for r in rows[:self._MAX_ROWS]]

    def _describe_budgets(self, filters=None):
        """Budgets. Defaults to the CURRENT month — the question is almost always
        'am I over this month'; a period filter widens it deliberately."""
        from apps.core.truth.periods import resolve_period
        from apps.core.utils import get_user_today
        from apps.finance.models import Budget
        f = filters or {}
        qs = Budget.objects.filter(user=self.user).select_related("category")
        today = get_user_today(self.user)
        if f.get("period") or f.get("start") or f.get("end"):
            p = resolve_period(f.get("period") or "custom", today,
                               start=f.get("start"), end=f.get("end"))
            qs = qs.filter(month__range=(p.start, p.end))
        else:
            qs = qs.filter(month__year=today.year, month__month=today.month)
        qs = qs.order_by("-month", "category__name")
        return [self._budget_entity(b) for b in qs[:self._MAX_ROWS]]

    def _describe_goals(self):
        """Savings / debt-payoff / giving goals."""
        from apps.finance.models import FinancialGoal
        rows = (FinancialGoal.objects.filter(user=self.user)
                .select_related("life_goal")
                .order_by("goal_status", "target_date", "name"))
        return [self._goal_entity(g) for g in rows[:self._MAX_ROWS]]

    def _describe_entities(self):
        """Financial entities — who this user's money can belong to (F0 truth)."""
        from apps.finance.models import FinancialEntity
        rows = (FinancialEntity.objects.filter(user=self.user, is_active=True)
                .order_by("sort_order", "name"))
        return [self._entity_entity(e) for e in rows[:self._MAX_ROWS]]

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
        # Attribution facts (F0). `attributed_to` = who SHOULD bear it; `paid_by` = who
        # DID, snapshotted when the attribution was made. FACTS ONLY — WLJ never says
        # "this is on the wrong card"; the model interprets.
        rows = getattr(t, "_active_attribution", None)
        attribution = rows[0] if rows else None
        definition = {"amount": float(t.amount),
                      "direction": "income" if t.amount > 0 else "expense",
                      "category": t.category.name if t.category_id else None,
                      "account": t.account.name if t.account_id else None,
                      "payee": (t.payee or "").strip() or None}
        if attribution is not None:
            definition["attributed_to"] = attribution.attributed_entity.name
            definition["paid_by"] = attribution.paid_by_entity.name
            definition["attribution_confirmed"] = attribution.user_confirmed
        return CompleteEntity(
            kind="transaction",
            identity=(t.description or t.payee or "transaction").strip(),
            definition=definition,
            status="cleared" if t.is_cleared else "pending",
            plan={"date": t.date.isoformat()},
            freshness=F.CURRENT,
        )

    def _entity_entity(self, e):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="entity",
            identity=e.name,
            definition={"entity_type": e.entity_type,
                        "is_default_personal": e.is_default_personal},
            status="active",
            freshness=F.CURRENT,
        )

    def _recurring_entity(self, r):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="recurring",
            identity=(r.name or r.payee or "recurring commitment").strip(),
            definition={"amount": float(r.amount),
                        "direction": "income" if r.amount > 0 else "expense",
                        "frequency": r.frequency,
                        "category": r.category.name if r.category_id else None,
                        "account": r.account.name if r.account_id else None,
                        "payee": (r.payee or "").strip() or None,
                        "auto_post": r.is_auto_post},
            status="active" if r.is_active else "paused",
            plan={"next_due_date": r.next_due_date.isoformat() if r.next_due_date else None,
                  "start_date": r.start_date.isoformat() if r.start_date else None,
                  "end_date": r.end_date.isoformat() if r.end_date else None},
            performance={"occurrences_generated": r.total_generated,
                         "last_generated_date": (r.last_generated_date.isoformat()
                                                 if r.last_generated_date else None)},
            freshness=F.CURRENT,
        )

    def _budget_entity(self, b):
        # `spent_amount` / `remaining_amount` are the EXISTING Budget authority — read them,
        # never re-derive the arithmetic here (Article III.1 / IV.3). `health_status` is a
        # VERDICT and is deliberately not exposed; the model interprets the numbers.
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="budget",
            identity=(b.category.name if b.category_id else "budget"),
            definition={"budgeted_amount": float(b.total_budget),
                        "category": b.category.name if b.category_id else None},
            status="active",
            plan={"month": b.month.isoformat() if b.month else None},
            standing={"spent_amount": float(b.spent_amount),
                      "remaining_amount": float(b.remaining_amount)},
            freshness=F.CURRENT,
        )

    def _goal_entity(self, g):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="goal",
            identity=g.name,
            definition={"goal_type": g.goal_type,
                        "target_amount": float(g.target_amount),
                        "linked_life_goal": (g.life_goal.title
                                             if g.life_goal_id else None)},
            status=g.goal_status,
            plan={"target_date": g.target_date.isoformat() if g.target_date else None},
            standing={"current_amount": float(g.current_amount),
                      "remaining_amount": float(g.remaining_amount)},
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
