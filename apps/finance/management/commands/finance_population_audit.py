# ==============================================================================
# File: apps/finance/management/commands/finance_population_audit.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Measure what the F4 population convergence changes, per user.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Report the financial impact of the converged population definition. READ-ONLY.

F4 routed Budget, FinanceHistory, the metric snapshots, the dashboard, and
`FinanceDomainTruth` onto ONE definition of real economic activity. Four surfaces
previously disagreed, so a total *could* move. This command measures by how much —
without changing anything — so the impact is reported rather than assumed.

    python manage.py finance_population_audit            # every user with transactions
    python manage.py finance_population_audit --email x  # one user

The two divergence classes it isolates:
  * paired-but-not-categorised — structurally near-impossible, because the transfer form
    (`forms.py:496–529`) stamps BOTH signals; only hand-editing produces it;
  * categorised-but-unpaired — real: a user (or an import) marks something Transfer
    without a counterpart. Previously counted by the metrics/dashboard, ignored by history.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db.models import Q, Sum

from apps.finance.models import Transaction


class Command(BaseCommand):
    help = "Measure the impact of the converged transaction-population definition."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="Audit a single user.")

    def handle(self, *args, **options):
        User = get_user_model()
        users = User.objects.filter(email=options["email"]) if options.get("email") \
            else User.objects.filter(id__in=Transaction.objects.values_list(
                "user_id", flat=True).distinct())

        grand = {"users": 0, "opening": 0, "paired_only": 0, "categorised_only": 0,
                 "both": 0, "delta": Decimal("0.00")}

        for user in users.iterator():
            base = Transaction.objects.filter(user=user)
            if not base.exists():
                continue
            opening = base.filter(is_opening_balance=True)
            paired_only = base.filter(transfer_pair__isnull=False).exclude(
                category__category_type="transfer")
            categorised_only = base.filter(
                category__category_type="transfer", transfer_pair__isnull=True)
            both = base.filter(transfer_pair__isnull=False,
                               category__category_type="transfer")

            old_metrics = self._sum(base.filter(is_opening_balance=False)
                                    .exclude(transfer_pair__isnull=False))
            converged = self._sum(base.filter(is_opening_balance=False).exclude(
                Q(transfer_pair__isnull=False) | Q(category__category_type="transfer")))
            delta = converged - old_metrics

            grand["users"] += 1
            grand["opening"] += opening.count()
            grand["paired_only"] += paired_only.count()
            grand["categorised_only"] += categorised_only.count()
            grand["both"] += both.count()
            grand["delta"] += delta

            if delta or paired_only.exists() or categorised_only.exists():
                self.stdout.write(
                    f"{user.email}: transactions={base.count()} "
                    f"opening={opening.count()} paired_only={paired_only.count()} "
                    f"categorised_only={categorised_only.count()} "
                    f"both={both.count()} metric_delta={delta:+.2f}"
                )

        self.stdout.write(self.style.SUCCESS(
            f"AUDIT: users={grand['users']} opening={grand['opening']} "
            f"paired_only={grand['paired_only']} "
            f"categorised_only={grand['categorised_only']} both={grand['both']} "
            f"total_metric_delta={grand['delta']:+.2f}"
        ))
        if grand["delta"] == 0:
            self.stdout.write("No reported total changes under the converged definition.")

    @staticmethod
    def _sum(qs):
        return qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
