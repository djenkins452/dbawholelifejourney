"""
CoS Purity Guard — Enforcement Layer for Architecture Law Compliance.

Project: Whole Life Journey
Path: apps/core/ai_orchestrator/cos_purity_guard.py

Purpose:
    Enforces the architectural law: Raw Data → Signals/State → CoS → LLM.
    Detects and classifies violations when CoS context builders or response
    generators perform raw DB queries or live computations on the request path.

Architecture:
    - HARD violation: Domain is covered by SAE — raw query must be replaced.
    - SOFT violation: Domain has no SAE builder yet — allowed temporarily,
      logged for future coverage.

Usage:
    from apps.core.ai_orchestrator.cos_purity_guard import (
        log_cos_purity_violation,
        COS_COVERED_DOMAINS,
    )

    # In a builder that still uses raw DB for an uncovered domain:
    log_cos_purity_violation(
        domain='finance',
        file=__file__,
        operation='FinancialGoal.objects.filter()',
        operation_type='query',
    )
"""

import logging
import time

logger = logging.getLogger("wlj.cos_purity")

# ── Domains with full SAE state builder coverage ──────────────────────
# If a domain is in this set, any raw DB query in the CoS context path
# is a HARD violation and should use SAE state instead.
COS_COVERED_DOMAINS = frozenset({
    "health",
    "fitness",
    "fasting",
    "medicine",
    "nutrition",
    "faith",
    "journal",
    "goals",
    "purpose",  # alias for goals
    "habits",
    "tasks",
    "meals",
    "transformation",
    "governance",
    "scan",
    "behavior",
    "life_events",
    "intervention",
    "feedback",
})

# ── Domains that lack SAE coverage — SOFT violations ──────────────────
# Raw queries are temporarily allowed but must be logged.
COS_UNCOVERED_DOMAINS = frozenset({
    "finance",
    "brain_training",
    "capture",
    "medical",
    "relationships",
    "calendar",
})


def classify_violation(domain: str) -> str:
    """Classify a violation as HARD or SOFT based on SAE coverage.

    Returns:
        'HARD' if domain has SAE coverage (raw query is avoidable),
        'SOFT' if domain lacks SAE coverage (raw query is temporarily needed).
    """
    if domain in COS_COVERED_DOMAINS:
        return "HARD"
    return "SOFT"


def log_cos_purity_violation(
    domain: str,
    file: str,
    operation: str,
    operation_type: str = "query",
    detail: str = "",
):
    """Log a structured CoS purity violation for observability.

    Called by context builders that still perform raw DB access or live
    computation on the CoS request path.

    Args:
        domain: The data domain being accessed (e.g., 'finance', 'health').
        file: The source file (__file__).
        operation: Description of the raw operation (e.g., 'Budget.objects.filter()').
        operation_type: 'query' or 'computation'.
        detail: Optional additional context.
    """
    violation_type = classify_violation(domain)

    structured_data = {
        "violation_type": violation_type,
        "domain": domain,
        "file": file.split("/apps/")[-1] if "/apps/" in file else file,
        "operation": operation,
        "operation_type": operation_type,
        "timestamp": time.time(),
    }
    if detail:
        structured_data["detail"] = detail

    if violation_type == "HARD":
        logger.warning(
            "COS_PURITY_HARD domain=%s op=%s file=%s — "
            "SAE covers this domain; raw DB access must be replaced",
            domain,
            operation,
            structured_data["file"],
            extra={"cos_purity": structured_data},
        )
    else:
        logger.info(
            "COS_PURITY_SOFT domain=%s op=%s file=%s — "
            "no SAE builder yet; raw DB allowed temporarily",
            domain,
            operation,
            structured_data["file"],
            extra={"cos_purity": structured_data},
        )
