"""Read-only Phase 0 report command — SCAFFOLD.

Two functions:
  1. Always: run the shadow classifier over the golden corpus and print
     mode-accuracy + a per-prompt table (no DB needed — proves the instrument).
  2. If the observation model exists (post-migration): aggregate real
     observations into the success metrics. Until then, prints a notice.

Never writes anything. Safe to run anytime.

    python manage.py beth_mode_report
    python manage.py beth_mode_report --golden-only
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ai.cognitive_mode import golden_corpus as gc
from apps.ai.cognitive_mode.shadow_classifier import classify


class Command(BaseCommand):
    help = "Phase 0 read-only report: golden-corpus accuracy + (future) live observation aggregates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--golden-only", action="store_true",
            help="Only run the golden-corpus accuracy check (skip live aggregates).",
        )

    def handle(self, *args, **opts):
        self._golden_report()
        if not opts.get("golden_only"):
            self._live_report()

    # -- golden corpus accuracy (no DB) --------------------------------------
    def _golden_report(self):
        total = len(gc.GOLDEN)
        correct = 0
        domain_correct = 0
        coach_correct = 0
        rows = []
        for entry in gc.GOLDEN:
            pred = classify(entry["message"])
            mode_ok = gc.mode_is_correct(entry, pred.mode)
            correct += int(mode_ok)
            dom_ok = (entry["expected_domain"] is None) or (pred.domain == entry["expected_domain"])
            domain_correct += int(dom_ok)
            coach_ok = pred.coach_tail == entry.get("coach_tail_expected", False)
            coach_correct += int(coach_ok)
            rows.append((entry["id"], pred.mode, "OK" if mode_ok else "MISS",
                         pred.domain, "ok" if dom_ok else "x", round(pred.confidence, 2)))

        acc = correct / total if total else 0.0
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== Golden Corpus — Shadow Classifier ==="))
        for rid, mode, ok, dom, dok, conf in rows:
            style = self.style.SUCCESS if ok == "OK" else self.style.ERROR
            self.stdout.write(style(f"  [{ok:4}] {rid:28} -> mode={mode:9} dom={str(dom):16} ({dok}) conf={conf}"))
        self.stdout.write("")
        self.stdout.write(f"  MODE accuracy   : {correct}/{total} = {acc:.0%}   (target >= 85%)")
        self.stdout.write(f"  DOMAIN accuracy : {domain_correct}/{total} = {domain_correct/total:.0%}   (secondary, not gated)")
        self.stdout.write(f"  COACH-tail acc  : {coach_correct}/{total} = {coach_correct/total:.0%}")
        verdict = self.style.SUCCESS("PASS") if acc >= 0.85 else self.style.ERROR("BELOW THRESHOLD")
        self.stdout.write(f"  Threshold gate  : {verdict}\n")

    # -- live aggregates (requires post-migration model) ---------------------
    def _live_report(self):
        try:
            from apps.ai.models import CognitiveModeObservation  # noqa: F401
        except Exception:
            self.stdout.write(self.style.WARNING(
                "  [live] CognitiveModeObservation model not present — Phase 0 storage "
                "not yet migrated/enabled. Skipping live aggregates.\n"))
            return
        # ---- TODO (post-migration): aggregate route_mismatch, greedy_route_flag,
        #      analyze traffic share, legacy-branch contamination, etc. ----
        self.stdout.write(self.style.WARNING(
            "  [live] Observation model present but aggregation not implemented in "
            "Phase 0 scaffold.\n"))
