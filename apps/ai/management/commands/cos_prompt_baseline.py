# ==============================================================================
# File: apps/ai/management/commands/cos_prompt_baseline.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic baseline of the Chief-of-Staff prompt — sizes only
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-03
# ==============================================================================
"""What does the Chief of Staff actually read before it answers?

Prints the prompt's composition — constitution (split into invariants and guidance),
per-turn context, tool schemas — plus, when a user is named, the same measurement against
that user's REAL standing context so the structured-context contribution is a fact rather
than an estimate.

Read-only, deterministic and free: it builds the prompt and measures it. NO provider call
is made and none can be — nothing here touches the model. Sizes and WLJ's own identifiers
are printed; no conversation, no personal values.

    python manage.py cos_prompt_baseline
    python manage.py cos_prompt_baseline --email someone@example.com
    python manage.py cos_prompt_baseline --turns 50      # what real turns actually did
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.ai.model_interface import constitution_map as cmap
from apps.ai.model_interface import telemetry as tel
from apps.ai.model_interface.constitution import all_tools


def _bar(part, whole, width=28):
    filled = int(round(width * (part / whole))) if whole else 0
    return "█" * filled + "·" * (width - filled)


class Command(BaseCommand):
    help = "Measure the Chief-of-Staff prompt composition (no provider calls)."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="",
                            help="Measure against this user's real standing context.")
        parser.add_argument("--blocks", action="store_true",
                            help="List every constitution block with its classification.")
        parser.add_argument("--turns", type=int, default=0,
                            help="Summarise Stage-0 telemetry from the last N recorded "
                                 "turns (read-only; no provider calls).")

    def handle(self, *args, **opts):
        w = self.stdout.write

        if opts["turns"]:
            return self._recent_turns(opts["turns"], opts["email"])

        # ---- constitution -----------------------------------------------------
        comp = cmap.composition()
        w("")
        w("CONSTITUTION")
        w(f"  {comp['total_chars']:>7,} chars in {comp['blocks']} blocks")
        w(f"  {comp['invariant_chars']:>7,} chars  {comp['invariant_blocks']:>2} blocks  "
          f"INVARIANT  {_bar(comp['invariant_chars'], comp['total_chars'])}")
        w(f"  {comp['guidance_chars']:>7,} chars  {comp['guidance_blocks']:>2} blocks  "
          f"GUIDANCE   {_bar(comp['guidance_chars'], comp['total_chars'])}"
          f"  ({comp['guidance_share'] * 100:.1f}%)")
        w(f"  of which historical patches: {comp['historical_patch_chars']:,} chars "
          f"in {comp['historical_patch_blocks']} blocks")
        w(f"  mixed blocks (both kinds in one paragraph): {comp['mixed_blocks']}")
        w(f"  boundaries defended: {', '.join(comp['protects_covered'])}")

        if opts["blocks"]:
            w("")
            w("BLOCKS")
            for b in cmap.BLOCKS:
                flag = "PATCH" if b.patch_of else ("MIXED" if b.mixed else "")
                w(f"  {b.index:>2}  {b.chars:>6,}  {b.kind:<9} {flag:<5} "
                  f"{b.protects or '':<30} {b.heading[:52]}")

        # ---- tools ------------------------------------------------------------
        tools = tel.measure_tools(all_tools(writes_enabled=True))
        w("")
        w("TOOL SCHEMAS")
        w(f"  {tools['tool_schema_chars']:>7,} chars across {tools['tools_exposed']} "
          f"exposed tools")
        for entry in tools["largest_tools"]:
            w(f"  {entry['chars']:>7,}  {entry['name']}")

        # ---- the whole prompt -------------------------------------------------
        email = opts["email"]
        if not email:
            w("")
            w(f"TOTAL (constitution + tool schemas): "
              f"{comp['total_chars'] + tools['tool_schema_chars']:,} chars")
            w("Pass --email to include the per-turn context for a real user.")
            return

        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            w(f"No user with email {email}")
            return

        from apps.ai.model_interface.service import ModelInterfaceService
        svc = ModelInterfaceService(user)
        sections = svc._prompt_sections(svc.build_standing_context())
        sizes = tel.measure_sections(sections)
        total = sizes["total"]

        w("")
        w(f"SYSTEM PROMPT for {email}")
        for name, size in sizes.items():
            if name == "total":
                continue
            w(f"  {size:>7,}  {_bar(size, total)}  {name}")
        w(f"  {total:>7,}  system prompt")
        w(f"  {total + tools['tool_schema_chars']:>7,}  including tool schemas")

        w("")
        w("DUPLICATED INSTRUCTION THEMES (mentions per section)")
        grand = 0
        for name, text in sections.items():
            counts = tel.duplicate_instruction_counts(text)
            if not counts:
                continue
            grand += sum(counts.values())
            detail = "  ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            w(f"  {name}: {detail}")
        w(f"  total mentions: {grand}")

    # -- what real turns actually did ------------------------------------------
    def _recent_turns(self, limit, email):
        """Aggregate the telemetry already riding on recorded turns.

        This is the half of Stage 0 that answers the migration's questions: how much of
        the prompt is paid for on every turn, how many of the exposed tools are ever
        reached, and whether Phase 2 changes the answer when it runs. Read-only.
        """
        from apps.ai.models import ToolCallLog

        w = self.stdout.write
        rows = ToolCallLog.objects.filter(kind="response").order_by("-id")
        if email:
            rows = rows.filter(user__email__iexact=email)

        records = []
        for row in rows[:max(limit * 3, limit)]:
            record = (row.result_digest or {}).get("telemetry")
            if record:
                records.append(record)
            if len(records) >= limit:
                break

        if not records:
            w("No telemetry recorded yet. It is written by turns served after the "
              "Stage-0 deploy; older rows predate it.")
            return

        w("")
        w(f"TELEMETRY over {len(records)} recorded turns"
          + (f" for {email}" if email else ""))

        def avg(fn):
            vals = [fn(r) for r in records]
            vals = [v for v in vals if isinstance(v, (int, float))]
            return sum(vals) / len(vals) if vals else 0

        w(f"  prompt chars (mean)     {avg(lambda r: (r.get('prompt_chars') or {}).get('total', 0)):>10,.0f}")
        w(f"    constitution          {avg(lambda r: (r.get('prompt_chars') or {}).get('constitution', 0)):>10,.0f}")
        w(f"    structured context    {avg(lambda r: (r.get('prompt_chars') or {}).get('structured_context', 0)):>10,.0f}")
        w(f"    current situation     {avg(lambda r: (r.get('prompt_chars') or {}).get('current_situation', 0)):>10,.0f}")
        w(f"  tool schema chars       {avg(lambda r: (r.get('tools') or {}).get('tool_schema_chars', 0)):>10,.0f}")
        w(f"  tools exposed (mean)    {avg(lambda r: (r.get('tools') or {}).get('tools_exposed', 0)):>10,.1f}")
        w(f"  distinct tools called   {avg(lambda r: r.get('tools_called_distinct', 0)):>10,.1f}")
        w(f"  tool-loop rounds        {avg(lambda r: (r.get('loop') or {}).get('rounds_used') or 0):>10,.1f}")

        called = {}
        for r in records:
            for name in r.get("tools_called") or []:
                called[name] = called.get(name, 0) + 1
        w("")
        w("  tools actually called:")
        for name, count in sorted(called.items(), key=lambda kv: -kv[1]):
            w(f"    {count:>4}  {name}")
        exposed = int(avg(lambda r: (r.get("tools") or {}).get("tools_exposed", 0)) or 0)
        w(f"    {len(called)} distinct of {exposed} exposed were reached at all")

        eligible = [r for r in records if (r.get("phase2") or {}).get("eligible")]
        used = [r for r in records if (r.get("phase2") or {}).get("used")]
        changed = [r for r in used if (r.get("phase2") or {}).get("materially_changed")]
        w("")
        w(f"  PHASE 2: eligible on {len(eligible)}, ran on {len(used)}, "
          f"materially changed the answer on {len(changed)}")
        if used:
            w(f"           mean word overlap with phase 1: "
              f"{avg(lambda r: (r.get('phase2') or {}).get('word_overlap') or 0):.3f}")

        lost = {}
        for r in records:
            for key in (r.get("coverage") or {}).get("silently_lost") or []:
                lost[key] = lost.get(key, 0) + 1
        if lost:
            w("")
            w(f"  context keys lost across the phase boundary: {lost}")
