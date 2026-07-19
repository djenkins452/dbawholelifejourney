"""
The ONE canonical configuration contract.

This is the single source of configuration truth: every monitor, startup check,
and doc derives from this file. Do NOT hard-code configuration requirements
anywhere else.

Secrecy rule: this file names variables and classifies them; it NEVER contains a
secret value. Presence is all that is ever evaluated.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── Runtime services (the canonical Railway topology) ────────────────────
# `runs_media` = this service processes/stores durable media (needs storage
# config). `celery` = a Celery process. Determined from the deployment audit.
SERVICE_WEB = "web"
SERVICE_WORKER = "worker"
SERVICE_BEAT = "beat"
SERVICE_CHATWORKER = "chatworker"
SERVICE_BUILD = "build"
SERVICE_DB_ADMIN = "db_admin"

RUNTIME_SERVICES = (SERVICE_WEB, SERVICE_WORKER, SERVICE_BEAT, SERVICE_CHATWORKER)
ALL_SERVICES = RUNTIME_SERVICES + (SERVICE_BUILD, SERVICE_DB_ADMIN)

# Human labels for customer-language/operator surfaces.
SERVICE_LABELS = {
    SERVICE_WEB: "Web App",
    SERVICE_WORKER: "Background Worker",
    SERVICE_BEAT: "Scheduler",
    SERVICE_CHATWORKER: "Chat Worker",
    SERVICE_BUILD: "Build Runner",
    SERVICE_DB_ADMIN: "Database Admin",
}

# ── Classification + severity vocabularies ───────────────────────────────
CLASS_SECRET = "secret"      # never displayed; presence-only
CLASS_CONFIG = "config"      # non-secret operational config
CLASS_PUBLIC = "public"      # safe to display

SEV_CRITICAL = "critical"    # outage / data-loss / security risk if wrong
SEV_DEGRADED = "degraded"    # feature impaired, platform still up
SEV_ADVISORY = "advisory"    # hygiene / future-risk only

SOURCE_SHARED = "shared"           # belongs in Railway Shared Variables
SOURCE_SERVICE_LOCAL = "service"   # intentionally per-service


@dataclass(frozen=True)
class VariableSpec:
    """One configuration variable's canonical contract (never a value)."""
    name: str
    classification: str            # CLASS_*
    description: str
    capability: str                # customer-facing capability affected
    required_services: tuple       # services where it is REQUIRED (prod)
    severity: str = SEV_DEGRADED   # impact if missing from a required service
    environments: tuple = ("production",)
    preferred_source: str = SOURCE_SHARED
    empty_valid: bool = False      # is an empty string a valid value?
    fail_startup: bool = False     # SHOULD a missing value fail service startup?
    remediation: str = ""
    duplicate_local_allowed: bool = True   # may a service-local copy coexist?
    consistency_required: bool = False     # must copies agree across services?
    # Optional deterministic format check on the *presence-safe* metadata only
    # (length band / prefix), never the raw value. Reserved for later phases.
    format_hint: Optional[str] = None

    def requires(self, service: str) -> bool:
        return service in self.required_services


# ── THE CONTRACT ─────────────────────────────────────────────────────────
# Populated from the as-built audit (Phase 1). Grouped by concern (Phase 3).
# `required_services` lists services where the variable is REQUIRED in
# production; a service NOT listed does not need it (no false positive).

CONTRACT: tuple = (
    # 1) Platform runtime ------------------------------------------------
    VariableSpec(
        name="SECRET_KEY", classification=CLASS_SECRET,
        description="Django cryptographic signing key (sessions, CSRF, tokens).",
        capability="Login, sessions, and security integrity",
        required_services=RUNTIME_SERVICES, severity=SEV_CRITICAL,
        preferred_source=SOURCE_SHARED, fail_startup=True,
        duplicate_local_allowed=False, consistency_required=True,
        remediation="Set one shared SECRET_KEY across all runtime services; all must match.",
    ),
    # (ALLOWED_HOSTS / CSRF_TRUSTED_ORIGINS are hardcoded in settings, NOT env
    #  vars — intentionally excluded from the contract; audited 2026-07-19.)

    # 2) Data infrastructure --------------------------------------------
    VariableSpec(
        name="DATABASE_URL", classification=CLASS_SECRET,
        description="PostgreSQL connection string.",
        capability="All data — reading and saving anything",
        required_services=RUNTIME_SERVICES, severity=SEV_CRITICAL,
        preferred_source=SOURCE_SHARED, fail_startup=True,
        remediation="Attach the Postgres connection to every runtime service (shared).",
    ),
    VariableSpec(
        name="REDIS_URL", classification=CLASS_SECRET,
        description="Redis connection (Celery broker + cache).",
        capability="Background processing, reminders, and caching",
        required_services=(SERVICE_WORKER, SERVICE_BEAT, SERVICE_CHATWORKER, SERVICE_WEB),
        severity=SEV_CRITICAL, preferred_source=SOURCE_SHARED, fail_startup=False,
        remediation="Attach Redis to Web, Worker, Beat, and Chat Worker (shared).",
    ),

    # 3) Durable media / storage (the incident class) --------------------
    VariableSpec(
        name="CLOUDINARY_CLOUD_NAME", classification=CLASS_CONFIG,
        description="Cloudinary account cloud name for durable media storage.",
        capability="Durable file and media processing (uploads, photos, artifacts)",
        required_services=(SERVICE_WEB, SERVICE_WORKER, SERVICE_BEAT),
        severity=SEV_CRITICAL, preferred_source=SOURCE_SHARED, fail_startup=True,
        consistency_required=True,
        remediation="Share the Cloudinary variables with Web, Worker, and Beat.",
    ),
    VariableSpec(
        name="CLOUDINARY_API_KEY", classification=CLASS_SECRET,
        description="Cloudinary API key for durable media storage.",
        capability="Durable file and media processing (uploads, photos, artifacts)",
        required_services=(SERVICE_WEB, SERVICE_WORKER, SERVICE_BEAT),
        severity=SEV_CRITICAL, preferred_source=SOURCE_SHARED,
        consistency_required=True,
        remediation="Share the Cloudinary variables with Web, Worker, and Beat.",
    ),
    VariableSpec(
        name="CLOUDINARY_API_SECRET", classification=CLASS_SECRET,
        description="Cloudinary API secret for durable media storage.",
        capability="Durable file and media processing (uploads, photos, artifacts)",
        required_services=(SERVICE_WEB, SERVICE_WORKER, SERVICE_BEAT),
        severity=SEV_CRITICAL, preferred_source=SOURCE_SHARED,
        consistency_required=True,
        remediation="Share the Cloudinary variables with Web, Worker, and Beat.",
    ),

    # 4) AI providers ----------------------------------------------------
    VariableSpec(
        name="OPENAI_API_KEY", classification=CLASS_SECRET,
        description="OpenAI API key — powers the Chief of Staff / chat.",
        capability="AI assistant and conversational features",
        required_services=(SERVICE_WEB, SERVICE_WORKER, SERVICE_CHATWORKER),
        severity=SEV_DEGRADED, preferred_source=SOURCE_SHARED,
        remediation="Share OPENAI_API_KEY with Web, Worker, and Chat Worker.",
    ),
    VariableSpec(
        name="CLAUDE_API_KEY", classification=CLASS_SECRET,
        description="Operator/automation API key for admin task + ops-diagnostic endpoints.",
        capability="Internal operator automation (not customer-facing)",
        required_services=(SERVICE_WEB,), severity=SEV_ADVISORY,
        preferred_source=SOURCE_SERVICE_LOCAL, empty_valid=True,
        remediation="Set CLAUDE_API_KEY on Web if operator automation endpoints are used.",
    ),
)


def by_name() -> dict:
    return {v.name: v for v in CONTRACT}


def required_for(service: str) -> tuple:
    """Variables REQUIRED in production for a given service."""
    return tuple(v for v in CONTRACT if v.requires(service))


def contract_variable_names() -> tuple:
    return tuple(v.name for v in CONTRACT)
