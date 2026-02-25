"""
CDCE — Cross-Domain Correlation Engine.

Discovers multi-domain patterns that single-domain insight rules cannot
detect. Correlates sleep with mood, exercise with energy, finance with
stress, faith engagement with consistency.

CDCE is a Phase 3 post-execution engine. It runs AFTER SAE builds user
state and PIE/PRIE generate per-domain insights.

Cadence: every 6 hours (ISE-scheduled batch).
"""
