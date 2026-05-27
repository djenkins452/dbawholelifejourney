"""
CoS Briefing — deterministic, narrative-shaped composition of canonical state.

Both ``dashboard_v3`` and (future) Beth narration MUST read from the same
composer so the surfaces cannot disagree. No LLM, no new computation —
this layer only aggregates and reshapes data already produced by SAE,
the deterministic selectors, and the PIE/PRIE/PGE engines.
"""

from apps.core.cos_briefing.executive_summary import build_executive_summary
from apps.core.cos_briefing.rhythm import build_rhythm_sections

__all__ = ["build_executive_summary", "build_rhythm_sections"]
