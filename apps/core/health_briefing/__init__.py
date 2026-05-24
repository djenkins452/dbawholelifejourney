"""
HealthBriefing — deterministic metabolic intelligence briefing for Beth.

This module composes a single, snapshot-able, pre-ranked, evidence-tagged
object that Beth (CoS) narrates over for health-related conversation.

Distinct from ``apps.core.ai_briefing`` (the Daily Briefing Engine, DBE),
which produces user-facing daily summaries from cross-domain intelligence.
HealthBriefing is consumed by Beth for narration, not by the user directly.

Architectural commitments (locked Phase 0, 2026-05-24):

* Beth consumes one composed object, not many atomic signals.
* Ranking is deterministic; Beth must not re-rank.
* The alerts-feed (UnifiedSignal renderer) is a separate channel and is
  unchanged.
* The composer runs in the background; the request path is read-only.
* Beth never receives raw domain rows (GlucoseEntry, LabResult, etc.).
"""
