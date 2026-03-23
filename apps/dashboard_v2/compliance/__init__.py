"""
Compliance Audit System — canonical event layer for tracked commitments.

Architecture:
    raw data → domain adapters → ComplianceEvent rows → rollup service → cards / detail UI

Modules:
    constants    — enums, status definitions, reason codes
    models       — ComplianceEvent model
    adapters/    — per-domain evaluation logic
    rollup       — summary aggregation from canonical events
    views        — API endpoints for drill-down UI
"""
