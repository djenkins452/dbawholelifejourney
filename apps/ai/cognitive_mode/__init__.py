"""Beth Cognitive Mode — Phase 0 (shadow / log-only).

This package is INERT by design. Nothing here changes any response Beth gives.
It exists to *measure* whether a real Analyze reasoning lane should be built:

  - taxonomy.py          : mode/domain enums + per-(mode,domain) package requirements
  - shadow_classifier.py : pure, deterministic message -> predicted mode/domain
  - golden_corpus.py     : labeled real-failure prompts (classifier oracle + A/B set)
  - telemetry.py         : observation dataclass + record stub (NO db write yet)
  - model_ab.py          : offline model A/B scaffold (NO api execution)

Activation requires explicit feature flags (all default OFF) plus a DB migration
and a single live-path hook — neither of which is implemented in Phase 0's inert
build. See docs/BETH_PHASE0_SHADOW_CLASSIFIER_PLAN.md.
"""
