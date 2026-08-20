# ==============================================================================
# File: apps/ai/management/commands/llm_dev_usage.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic development-spend summary over existing LLMUsageEvent rows
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-20
# ==============================================================================
"""What has development actually cost?

    python manage.py llm_dev_usage --days 7

Reads only existing `LLMUsageEvent` rows — no provider calls, no new telemetry. It exists
so Danny never again learns about development API spend from a credit-card notification.

Two things it refuses to blur:
  * **Unknown cost is not zero.** Rows with no price-book entry are reported as UNPRICED,
    with their token counts, never folded into a dollar total.
  * **Unattributed is not production.** A call with no asserted classification is shown as
    unattributed, because a missing label is not evidence that a real user did anything.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count, Sum
from django.utils import timezone

from apps.owner_finance.models import LLMUsageEvent


class Command(BaseCommand):
    help = "Summarize recent LLM spend, separating known cost from unpriced calls."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, **opts):
        since = timezone.now() - timezone.timedelta(days=opts["days"])
        qs = LLMUsageEvent.objects.filter(created_at__gte=since)
        if not qs.exists():
            self.stdout.write(f"No LLM usage recorded in the last {opts['days']} days.")
            return

        priced = qs.filter(cost_is_known=True)
        unpriced = qs.filter(cost_is_known=False)

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nLLM usage — last {opts['days']} days ({qs.count()} calls)"))

        known = priced.aggregate(c=Sum("cost_usd"))["c"] or 0
        self.stdout.write(f"\n  Known cost:  ${float(known):.4f}  ({priced.count()} calls)")
        if unpriced.exists():
            u = unpriced.aggregate(i=Sum("input_tokens"), o=Sum("output_tokens"))
            self.stdout.write(self.style.WARNING(
                f"  UNPRICED:    cost UNKNOWN — not $0.00  ({unpriced.count()} calls, "
                f"{u['i'] or 0} in / {u['o'] or 0} out tokens)"))
            for r in (unpriced.values("model_name").annotate(n=Count("id")).order_by("-n")):
                self.stdout.write(self.style.WARNING(
                    f"      no price-book entry: {r['model_name']} ({r['n']} calls)"))

        self._table(qs, "traffic_class", "By traffic class")
        self._table(qs, "source", "By source")

        self.stdout.write(self.style.MIGRATE_HEADING("\nAuthorized development runs"))
        self._authorizations(qs)
        self.stdout.write("")

    def _table(self, qs, dim, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{title}"))
        for r in (qs.values(dim).annotate(
                n=Count("id"), cost=Sum("cost_usd"),
                i=Sum("input_tokens"), o=Sum("output_tokens")).order_by("-n")):
            key = r[dim] or "(unset)"
            unp = qs.filter(**{dim: r[dim]}, cost_is_known=False).count()
            flag = self.style.WARNING(f"  [{unp} UNPRICED]") if unp else ""
            self.stdout.write(
                f"  {key:<26} calls={r['n']:<5} in={r['i'] or 0:<9} out={r['o'] or 0:<7} "
                f"${float(r['cost'] or 0):.4f}{flag}")

    def _authorizations(self, qs):
        from apps.ai.models import RealLLMAuthorization
        rows = RealLLMAuthorization.objects.all()[:10]
        if not rows:
            self.stdout.write("  None — no paid development run has ever been authorized.")
            return
        for a in rows:
            used = qs.filter(metadata__llm_run_id=a.run_id)
            cost = used.filter(cost_is_known=True).aggregate(c=Sum("cost_usd"))["c"] or 0
            self.stdout.write(
                f"  {a.run_id:<26} budget {a.calls_used}/{a.calls_authorized} used"
                f"  recorded={used.count()} calls  ${float(cost):.4f}"
                f"  {'LIVE' if a.is_live else 'spent/expired'}\n"
                f"      reason: {a.reason[:70]}")
