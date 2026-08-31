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
    # `connection` exposes HOW and WHEN money data actually arrives. Without it the model
    # had no WLJ truth about synchronization at all and answered "how do my accounts update
    # through Plaid?" from generic provider knowledge — suggesting a manual refresh that
    # WLJ does not perform. The state existed on BankConnection the whole time; it was
    # simply never surfaced (a Layer-1 ACCESSIBILITY gap, not a missing capability).
    # Finance 2.0 packets (P1-P9). These are NOT new re-derivations — each is the
    # output of a named deterministic service (measures, payoff, opportunities), handed
    # over with its calculation version, assumptions, exclusions and missing inputs.
    # The model explains them; it never recomputes them. Redaction is enforced by
    # `apps/finance/tests/test_cos_evidence.py`, which walks every packet.
    entity_types = ("transaction", "account", "recurring", "budget", "goal", "entity",
                    "connection", "measures", "debt", "payoff", "payoff_comparison",
                    "obligations", "controllable_costs", "savings_opportunities",
                    "financial_snapshot", "data_health", "forecast", "affordability",
                    "net_worth", "net_worth_history", "plan_results",
                    "data_health_detail", "money_bridge", "monthly_views")
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
        if et == "connection":
            return self._describe_connections()
        packet = self._describe_packet(et, filters or {})
        if packet is not None:
            return packet
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
        qs = qs.select_related("account", "category")
        # ORDERING MUST MATCH THE QUESTION. The default is reverse-chronological, which
        # is right for "what did I spend at Costco" but WRONG for a ranking: with the
        # `_MAX_TX` cap, a busy month would return the 100 most RECENT rows and the
        # largest spend could fall outside them — a silently wrong "largest". A ranked
        # caller declares `order_by="spend_desc"`, so the cap keeps the top spends
        # instead of the newest rows. Outflows only (`amount < 0`); most negative first.
        if f.get("order_by") == "spend_desc":
            qs = qs.filter(amount__lt=0).order_by("amount", "-date", "-id")
        else:
            qs = qs.order_by("-date", "-id")
        qs = self._with_attribution(qs)
        return [self._transaction_entity(t) for t in qs[:self._MAX_TX]]

    def _describe_packet(self, entity_type, filters):
        """The Finance 2.0 evidence packets. Returns None for anything else.

        Every branch delegates to `cos_evidence`, which is the only module allowed to
        decide what leaves Finance for the model.
        """
        from decimal import Decimal

        from apps.finance.services.finance_calc import cos_evidence as E

        def _decimal(key, default="0"):
            try:
                return Decimal(str(filters.get(key) or default))
            except Exception:
                return Decimal(default)

        if entity_type == "measures":
            return [E.measures_packet(self.user, filters.get("start"),
                                      filters.get("end"))]
        if entity_type == "debt":
            if filters.get("name"):
                return [E.single_debt_priority_packet(self.user, filters["name"])]
            return [E.debt_packet(self.user)]
        if entity_type == "payoff":
            return [E.payoff_packet(
                self.user, strategy=filters.get("strategy") or "avalanche",
                extra_monthly=_decimal("extra_monthly"),
                lump_sum=_decimal("lump_sum"))]
        if entity_type == "payoff_comparison":
            return [E.payoff_comparison_packet(
                self.user, extra_monthly=_decimal("extra_monthly"),
                lump_sum=_decimal("lump_sum"))]
        if entity_type == "obligations":
            return [E.obligations_packet(self.user)]
        if entity_type == "controllable_costs":
            return [E.controllable_packet(self.user)]
        if entity_type == "savings_opportunities":
            if filters.get("target"):
                return [E.find_amount_packet(self.user, _decimal("target"))]
            return [E.opportunities_packet(self.user)]
        if entity_type == "financial_snapshot":
            return [E.snapshot_packet(self.user)]
        if entity_type == "data_health":
            return [E.coverage_packet(self.user)]
        if entity_type == "forecast":
            return [E.forecast_packet(
                self.user, horizon_days=int(filters.get("horizon_days") or 30))]
        if entity_type == "affordability":
            return [E.affordability_packet(
                self.user, _decimal("monthly_amount"),
                horizon_days=int(filters.get("horizon_days") or 90))]
        if entity_type == "net_worth":
            return [E.net_worth_packet(self.user)]
        if entity_type == "net_worth_history":
            return [E.net_worth_history_packet(
                self.user, days=int(filters.get("days") or 365))]
        if entity_type == "plan_results":
            return [E.plan_results_packet(self.user)]
        if entity_type == "data_health_detail":
            return [E.data_health_packet(self.user)]
        if entity_type == "money_bridge":
            return [E.money_bridge_packet(
                self.user, filters.get("start"), filters.get("end"))]
        if entity_type == "monthly_views":
            return [E.monthly_views_packet(
                self.user, filters.get("start"), filters.get("end"))]
        return None

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

    # ── HOW WLJ ACTUALLY SYNCS ────────────────────────────────────────────────
    # Invariant product behaviour, carried on the same surface as the per-connection
    # state so the two can never drift apart or be answered from generic knowledge.
    SYNC_MECHANICS = {
        "institution_checks": (
            "Plaid checks each institution on its own schedule — typically one to four "
            "times a day, varying by institution. WLJ does not control that cadence."),
        "primary_trigger": (
            "Plaid webhooks are WLJ's primary, low-latency ingestion trigger: when Plaid "
            "has new data it calls WLJ and WLJ pulls it straight away."),
        "safety_net": (
            "WLJ also runs a scheduled reconciliation. That is a missed-webhook safety "
            "net, not the main path."),
        "manual_sync_now": (
            "The Sync Now action calls Plaid's cursor-based /transactions/sync and "
            "retrieves changes Plaid ALREADY has. It does NOT ask Plaid to contact the "
            "bank, so it cannot make an institution produce newer data."),
        "refresh_endpoint": (
            "WLJ does not use Plaid's separate /transactions/refresh endpoint. Nothing in "
            "WLJ forces an on-demand bank refresh."),
        "expectation": (
            "Finance data is automatic but not guaranteed to be real-time. A transaction "
            "can be missing simply because the institution has not published it yet."),
        "when_action_is_needed": (
            "Reauthentication is required only when the connection is in an actionable "
            "state such as login required or consent renewal — never merely because a "
            "recent transaction is not visible yet."),
    }

    def _describe_connections(self):
        """Per-connection sync truth: what Plaid/WLJ last did, and whether the user must act.

        Facts only — timestamps, lifecycle booleans and a status the model interprets. No
        verdict about whether data is "stale", and never a token, cursor value or credential.
        """
        from apps.finance.models import BankConnection
        conns = (BankConnection.objects.filter(user=self.user)
                 .order_by("institution_name", "id")[:self._MAX_ROWS])
        if not conns:
            # "How does syncing work?" is answerable with no banks linked — and someone
            # who has not linked one is MORE likely to ask. Returning an empty list here
            # would drop the mechanics and send the model back to general knowledge of the
            # provider, which is the exact failure this entity exists to prevent.
            return [self._no_connections_entity()]
        return [self._connection_entity(c) for c in conns]

    def _no_connections_entity(self):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="connection",
            identity="no bank connections linked",
            definition={"how_it_updates": self.SYNC_MECHANICS},
            status="none",
            standing={"connections_linked": 0,
                      "user_action_required": False},
            freshness=F.CURRENT,
        )

    def _connection_entity(self, c):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="connection",
            identity=(c.institution_name or "").strip() or f"connection {c.id}",
            definition={
                # HOW it updates — identical for every connection, stated with the state
                # so the model never has to guess the mechanics.
                "how_it_updates": self.SYNC_MECHANICS,
            },
            status=c.connection_status,
            standing={
                # WLJ's OWN last successful synchronization — distinct from whatever Plaid
                # last managed to collect from the institution.
                "wlj_last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
                "transactions_synced_total": c.transactions_synced,
                "initial_window_complete": c.initial_update_complete,
                "historical_backfill_complete": c.historical_update_complete,
                # TRUE only for a genuinely actionable state (login/consent). A missing
                # recent transaction is NOT this.
                "user_action_required": c.needs_attention,
                "error_code": c.error_code or None,
                "error_message": (c.error_message or "").strip() or None,
                # A refused delivery is a WLJ-side fault worth distinguishing from an
                # institution being quiet.
                "last_webhook_rejected_at": (
                    c.last_webhook_rejected_at.isoformat()
                    if c.last_webhook_rejected_at else None),
            },
            freshness=F.CURRENT,
        )

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
        # `spend_amount` is the OUTFLOW MAGNITUDE — the already-canonical convention
        # (`amount < 0` is money out; FinanceHistory reports spending as a positive
        # magnitude) expressed as a rankable value. It is deliberately None for an
        # inflow (income, and a refund, which is an inflow): the ranked-entity
        # capability EXCLUDES a missing measure rather than coercing it to 0, so
        # "largest spend" can never rank income or a refund by construction. Transfers
        # never reach here at all — `financial_activity` excludes known AND ambiguous
        # ones. No new accounting rule is introduced; this exposes the existing one.
        definition = {"amount": float(t.amount),
                      "spend_amount": (abs(float(t.amount)) if t.amount < 0 else None),
                      # Also in `definition` so a ranked result carries WHEN it happened
                      # (the ranked path reads occurrence from `definition`).
                      "date": t.date.isoformat(),
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
            standing={"current_amount": float(g.current_value),
                      "remaining_amount": float(g.remaining_amount),
                      "meeting_target": g.is_completed,
                      # Where the number came from, so the model can say so rather
                      # than implying the user typed it.
                      "balance_source": g.balance_source_name,
                      "balance_as_of": (g.balance_as_of.isoformat()
                                        if g.balance_as_of else None)},
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
