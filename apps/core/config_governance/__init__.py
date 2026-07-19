"""
WLJ Configuration Governance — deterministic configuration-drift detection.

WLJ owns the deterministic truth of *what configuration each runtime service
requires* and *whether each service actually has it*. This package is that
authority. It NEVER reads or transmits secret VALUES — only presence
(true/false) per variable per service. The conversational model is never
consulted about configuration validity.

Layout (single responsibility each):
  * ``contract``   — the ONE canonical configuration contract (data).
  * ``manifest``   — each service self-reports a secret-safe presence manifest.
  * ``evaluator``  — pure deterministic evaluation: manifests × contract → findings.
  * ``startup``    — publishes the local manifest + report-only startup validation.

Governing doc: ``docs/WLJ_CONFIGURATION_GOVERNANCE.md``.
"""
