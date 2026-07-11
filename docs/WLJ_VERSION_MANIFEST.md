# WLJ Version Manifest — Chief of Staff Architecture Milestone

**Status:** CURRENT · Recovery-point manifest
**Milestone:** WLJ Chief of Staff Architecture Milestone
**Date:** 2026-07-11

---

## Recovery point

| Field | Value |
|---|---|
| **Annotated tag** | `milestone-cos-architecture-v1` |
| **Milestone commit SHA** | `c22dd336bbab44182dddcae50577fbc007dac4e8` |
| **Recovery-point commit (tag target)** | the SHA-stamp commit immediately following the milestone commit (run `git rev-parse milestone-cos-architecture-v1`) |
| **Branch** | `main` |
| **Deploy remote** | `git@ssh.github.com:djenkins452/dbawholelifejourney.git` (port 443) |
| **Constitution Version** | 1.0 (`docs/WLJ_CONSTITUTION.md`) |

## Runtime

| Component | Version |
|---|---|
| Django | 4.2.27 (note: CLAUDE.md says "5.x"; runtime is 4.2 — see `WLJ_KNOWN_LIMITATIONS.md`) |
| Python (local dev) | 3.9.6 (`/usr/bin/python3`) |
| Database | PostgreSQL (prod) / SQLite (dev) |
| Broker/cache | Redis |
| Workers | Celery worker + beat (+ optional chatworker `-Q chat`) |
| WSGI | Gunicorn |
| Deploy | Railway (Nixpacks) |
| Reasoning provider | OpenAI (behind Model Interface seam; provider-agnostic) |

## Migrations

| Field | Value |
|---|---|
| Applied migrations (dev DB) | 731 |
| Pending migrations | **None** (`makemigrations --check` → "No changes detected") |
| Migration policy | Forward-only in prod; one-off prod changes via `RunPython` migration only (no CLI/SSH) |

## Milestone documents (all CURRENT)

- `WLJ_CONSTITUTION.md` — the locked architecture + Constitutional Review process
- `WLJ_ACCEPTANCE_BASELINE.md` — permanent regression suite map
- `WLJ_DOCUMENTATION_INVENTORY.md` — 186-doc classification
- `WLJ_OPS_WALL_COVERAGE.md` — production observability coverage + backlog
- `WLJ_CURRENT_CONTEXT_HELP_COVERAGE.md` — page-coverage audit + backlog
- `WLJ_RELEASE_POLICY.md` — three publication levels
- `WLJ_PRODUCTION_RUNBOOKS.md` — incident/rollback/recovery
- `WLJ_SECURITY_PRIVACY_RETENTION.md` — retention (72h images), audit, provenance
- `WLJ_KNOWN_LIMITATIONS.md` — honest limitations
- `WLJ_MILESTONE_COS_ARCHITECTURE.md` — the final milestone report
- `WLJ_VERSION_MANIFEST.md` — this file

## New/changed enforcement at this milestone

- **Added:** `apps/core/tests/test_constitution_contract.py` (9 tests) — makes the Constitution executable.
- **Restored:** `apps/core/ai_state/test_health_contract_glucose_extensions.py` (renamed from `tests_…`; 26 dormant tests re-enter CI).
- **Hygiene:** deprecated `django.utils.timezone.utc` retired across billing/render/cleanup command.

## Verification at cut

- Constitutional contract suite: **53 tests, all passing** (`test_constitution_contract`, `test_request_path_safety_contract`, `test_execution_decision_authority_contract`, `test_completion_single_source_contract`, `test_visual_truth_contract`, `test_conductor_contract`, `cos.tests.test_contracts`).
- `manage.py check`: passes (2 pre-existing djstripe config infos only).
- `makemigrations --check`: clean.
