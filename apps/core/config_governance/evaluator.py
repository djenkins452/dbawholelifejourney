"""
Deterministic configuration evaluation: manifests × contract → findings.

Pure and deterministic — no LLM, no I/O, no clock except the ``now`` passed in.
Given the set of per-service presence manifests and the canonical contract, it
returns findings + an overall status. This is the single place "is configuration
valid?" is decided.

Honesty rule (Phase 7): WLJ cannot read Railway's variable-sharing UI, and a
service that crashed on a fatal missing variable self-reports NOTHING. So a
required service with no fresh manifest is **UNKNOWN**, never Healthy — we report
"cannot verify," we never fabricate a pass.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.config_governance import contract as _c
from apps.core.config_governance import manifest as _m

# Overall status vocabulary (worst-wins precedence).
HEALTHY, DEGRADED, CRITICAL, UNKNOWN = "healthy", "degraded", "critical", "unknown"
_STATUS_RANK = {HEALTHY: 0, DEGRADED: 1, UNKNOWN: 2, CRITICAL: 3}

# Runtime services that MUST be present to call the system verifiable. A missing
# manifest for one of these yields UNKNOWN (never Healthy). Chatworker is
# optional (only deployed when the dedicated chat queue is enabled).
_MUST_RUN = (_c.SERVICE_WEB, _c.SERVICE_WORKER, _c.SERVICE_BEAT)

_SEV_TO_STATUS = {
    _c.SEV_CRITICAL: CRITICAL,
    _c.SEV_DEGRADED: DEGRADED,
    _c.SEV_ADVISORY: DEGRADED,   # advisory findings degrade, never go critical
}


def _worse(a, b):
    return a if _STATUS_RANK[a] >= _STATUS_RANK[b] else b


def _manifest_is_fresh(manifest, now):
    ts = parse_datetime(manifest.get("published_at", "") or "")
    if ts is None:
        return False
    return (now - ts) <= timedelta(seconds=_m.FRESH_WINDOW_SECONDS)


def evaluate(manifests: dict, now=None, environment: str = "production") -> dict:
    """Evaluate all manifests against the contract. Returns a telemetry dict.

    ``manifests`` = {service: manifest} from ``manifest.read_all_manifests()``.
    """
    now = now or timezone.now()
    findings = []
    overall = HEALTHY

    # --- Which required services can we actually verify? ---------------
    fresh = {
        svc: mf for svc, mf in (manifests or {}).items()
        if isinstance(mf, dict) and _manifest_is_fresh(mf, now)
    }
    unverified = []
    for svc in _MUST_RUN:
        if svc not in fresh:
            unverified.append(svc)
            findings.append({
                "code": "service_unverified",
                "kind": "unverified",
                "severity": _c.SEV_CRITICAL,
                "status": UNKNOWN,
                "variable": None,
                "service": svc,
                "service_label": _c.SERVICE_LABELS.get(svc, svc),
                "capability": "Configuration verification for this service",
                "detail": (
                    f"{_c.SERVICE_LABELS.get(svc, svc)} has not reported a fresh "
                    "configuration manifest. It may be down, crashing on startup, "
                    "or unreachable — its configuration cannot be verified."
                ),
                "remediation": (
                    "Check the service is deployed and healthy; a crash on a "
                    "required variable prevents it from self-reporting."
                ),
            })
            overall = _worse(overall, UNKNOWN)

    # --- Per-variable, per-service presence evaluation ----------------
    for spec in _c.CONTRACT:
        if environment not in spec.environments:
            continue
        satisfied_in, missing_in = [], []
        for svc in spec.required_services:
            mf = fresh.get(svc)
            if mf is None:
                continue  # unverifiable — already surfaced as service_unverified
            presence = (mf.get("presence") or {}).get(spec.name, _m.ABSENT)
            ok = presence == _m.PRESENT or (presence == _m.EMPTY and spec.empty_valid)
            (satisfied_in if ok else missing_in).append(svc)

        if missing_in:
            status = _SEV_TO_STATUS[spec.severity]
            findings.append({
                "code": "missing_required",
                "kind": "missing",
                "severity": spec.severity,
                "status": status,
                "variable": spec.name,
                "classification": spec.classification,
                "services": [_c.SERVICE_LABELS.get(s, s) for s in missing_in],
                "service_keys": missing_in,
                "capability": spec.capability,
                "detail": (
                    f"Required for: {', '.join(_c.SERVICE_LABELS.get(s, s) for s in missing_in)}."
                ),
                "remediation": spec.remediation,
                "preferred_source": spec.preferred_source,
            })
            overall = _worse(overall, status)

            # Cross-service inconsistency: present on some required services,
            # absent on others (the exact Cloudinary incident shape).
            if spec.consistency_required and satisfied_in:
                findings.append({
                    "code": "inconsistent_across_services",
                    "kind": "inconsistent",
                    "severity": spec.severity,
                    "status": _SEV_TO_STATUS[spec.severity],
                    "variable": spec.name,
                    "services": [_c.SERVICE_LABELS.get(s, s) for s in missing_in],
                    "present_on": [_c.SERVICE_LABELS.get(s, s) for s in satisfied_in],
                    "capability": spec.capability,
                    "detail": (
                        f"Present on {', '.join(_c.SERVICE_LABELS.get(s, s) for s in satisfied_in)} "
                        f"but missing from {', '.join(_c.SERVICE_LABELS.get(s, s) for s in missing_in)}."
                    ),
                    "remediation": spec.remediation,
                })

    # --- Roll up ------------------------------------------------------
    # Never report Healthy when a required service is unverifiable (already
    # enforced above by pushing overall to UNKNOWN).
    affected_services = sorted({
        lbl
        for f in findings
        for lbl in (f.get("services") or ([f["service_label"]] if f.get("service_label") else []))
    })
    affected_caps = sorted({f["capability"] for f in findings if f.get("capability")})
    critical = [f for f in findings if f["status"] == CRITICAL]
    degraded = [f for f in findings if f["status"] == DEGRADED]
    unknowns = [f for f in findings if f["status"] == UNKNOWN]

    return {
        "status": overall,
        "findings": findings,
        "counts": {
            "critical": len(critical),
            "degraded": len(degraded),
            "unknown": len(unknowns),
            "total": len(findings),
        },
        "checked_services": sorted(fresh.keys()),
        "unverified_services": [_c.SERVICE_LABELS.get(s, s) for s in unverified],
        "affected_services": affected_services,
        "affected_capabilities": affected_caps,
        "contract_variables": len(_c.CONTRACT),
        "environment": environment,
        "verified_at": now.isoformat(),
    }
