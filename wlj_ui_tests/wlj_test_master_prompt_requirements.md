# WLJ Functional UI Testing System — Master Requirements & Governance

**Version:** 1.0.0
**Created:** 2026-02-25
**Status:** Phase 0 — Requirements & Governance (Documentation Only)
**Author:** Claude Code (Opus 4.6)

---

## Table of Contents

1. [Executive Overview](#1-executive-overview)
2. [System Goals](#2-system-goals)
3. [Architecture Diagram](#3-architecture-diagram)
4. [Directory Structure](#4-directory-structure)
5. [Phase Breakdown](#5-phase-breakdown)
6. [Guardrails](#6-guardrails)
7. [YAML Schema Specification](#7-yaml-schema-specification)
8. [Reporting Specification](#8-reporting-specification)
9. [Artifact Specification](#9-artifact-specification)
10. [Prompt Generation Specification](#10-prompt-generation-specification)
11. [Safety Specification](#11-safety-specification)
12. [Deployment Integration Specification](#12-deployment-integration-specification)
13. [Risk Analysis](#13-risk-analysis)
14. [Rollback Plan](#14-rollback-plan)
15. [Validation Checklist](#15-validation-checklist)
16. [Phase Tracking Log](#16-phase-tracking-log)

---

## 1. Executive Overview

The WLJ Functional UI Testing System is a **Playwright + Python** framework for automated functional testing of the Whole Life Journey Django application. It provides:

- **Production-safe** testing with strict guardrails preventing data corruption or business logic modification
- **Module-isolated** test suites covering all 23 WLJ application modules
- **YAML-driven** test case definitions for maintainability and readability
- **Claude-integrated** failure reporting that generates actionable fix prompts
- **Phased delivery** with explicit scope boundaries, validation gates, and rollback plans

This document is the **authoritative governance record**. No framework code may be written until this document is approved. All implementation must conform to this specification.

### What This Build Covers

This master build creates **framework infrastructure only** — the test runner, executor, selector system, reporting, artifact capture, prompt generation, schema validation, and CLI. It does **not** create full test coverage. The framework is designed so thousands of tests can be safely added later via YAML suite files.

### What This Build Does NOT Cover

- Writing individual test cases for each module
- CI/CD pipeline configuration (documented but not implemented)
- Production deployment of the test runner
- Integration with the WLJ AdminTask system

---

## 2. System Goals

| # | Goal | Success Criteria |
|---|------|-----------------|
| G1 | Production-safe execution | Zero production data modified or deleted outside cleanup prefix scope |
| G2 | Module isolation | Each module runs independently with its own suite, reports, and artifacts |
| G3 | YAML-driven cases | Non-developer stakeholders can read and understand test definitions |
| G4 | Actionable failure reports | Every failure produces a Claude-compatible fix prompt with reproduction steps |
| G5 | Incremental scalability | Adding a new module requires only a new directory + suite.yaml — no framework changes |
| G6 | Environment-aware safety | Production runs enforce rate limiting, cleanup prefix matching, and no destructive actions |
| G7 | Deterministic execution | Same suite + same app state = same results |
| G8 | Minimal codebase impact | Framework changes are isolated to `wlj_ui_tests/**`; only `data-testid` attributes added to templates |

---

## 3. Architecture Diagram

```
                    +---------------------+
                    |   CLI Runner         |
                    |   run_suite.py       |
                    +----------+----------+
                               |
                    +----------v----------+
                    |   Schema Validator   |
                    |   schema_validator   |
                    +----------+----------+
                               |
                    +----------v----------+
                    |   YAML Suite Loader  |
                    |   runner.py          |
                    +----------+----------+
                               |
              +----------------+----------------+
              |                                 |
   +----------v----------+          +-----------v---------+
   |   Action Executor    |          |   Safety Controller  |
   |   executor.py        |          |   safety.py          |
   +---------++-----------+          +-----------+---------+
             ||                                  |
   +---------v+-----------+          +-----------v---------+
   |   Selector Engine     |          |   Cleanup Engine     |
   |   selectors.py        |          |   (prefix-enforced)  |
   +---------++-----------+          +---------------------+
             ||
   +---------v+-----------+
   |   Playwright Browser  |
   |   (Chromium headless)  |
   +----------++-----------+
              ||
   +----------v+----------+     +---------------------+
   |   Reporting Engine    |---->|   Artifact Capture   |
   |   reporting.py        |     |   artifacts.py       |
   +----------++-----------+     +---------------------+
              ||
   +----------v+----------+
   |   Prompt Builder      |
   |   prompt_builder.py   |
   +----------------------+

Data Flow:
  suite.yaml --> validate --> load --> execute steps --> assert --> report
                                                    |
                                              on failure:
                                              capture screenshot + HTML
                                              generate claude_fix_prompt.md
```

### Component Responsibilities

| Component | File | Purpose |
|-----------|------|---------|
| CLI Runner | `run_suite.py` | Entry point, argument parsing, orchestration |
| Schema Validator | `framework/schema_validator.py` | Validates YAML against required schema |
| Runner | `framework/runner.py` | Loads YAML, iterates cases, delegates to executor |
| Executor | `framework/executor.py` | Translates action types to Playwright calls |
| Selectors | `framework/selectors.py` | Resolves selector strategies to Playwright locators |
| Reporting | `framework/reporting.py` | Writes pass/fail NDJSON logs + run summary |
| Artifacts | `framework/artifacts.py` | Captures screenshots + HTML dumps on failure |
| Prompt Builder | `framework/prompt_builder.py` | Generates Claude fix prompts from failures |
| Safety | `framework/safety.py` | Enforces production safety rules |

---

## 4. Directory Structure

```
wlj_ui_tests/
├── wlj_test_master_prompt_requirements.md    # THIS FILE — governance document
├── run_suite.py                               # CLI entry point
├── conftest.py                                # Playwright pytest fixtures (if needed)
├── requirements.txt                           # Playwright + dependencies
│
├── framework/                                 # Core framework code
│   ├── __init__.py
│   ├── runner.py                              # YAML loader + case orchestrator
│   ├── executor.py                            # Action execution engine
│   ├── selectors.py                           # Selector resolution
│   ├── reporting.py                           # NDJSON + summary reporting
│   ├── artifacts.py                           # Screenshot + HTML capture
│   ├── prompt_builder.py                      # Claude fix prompt generator
│   ├── schema_validator.py                    # YAML schema validation
│   └── safety.py                              # Production safety controls
│
├── modules/                                   # Module-isolated test suites
│   ├── journal/
│   │   ├── suite.yaml
│   │   ├── reports/
│   │   └── artifacts/
│   ├── faith/
│   │   ├── suite.yaml
│   │   ├── reports/
│   │   └── artifacts/
│   ├── health/
│   │   ├── suite.yaml
│   │   ├── reports/
│   │   └── artifacts/
│   ├── organize/                              # life app (tasks, projects, inventory)
│   │   ├── suite.yaml
│   │   ├── reports/
│   │   └── artifacts/
│   ├── goals/                                 # purpose app
│   │   ├── suite.yaml
│   │   ├── reports/
│   │   └── artifacts/
│   ├── capture/
│   │   ├── suite.yaml
│   │   ├── reports/
│   │   └── artifacts/
│   ├── cos/                                   # calendar_engine app
│   │   ├── suite.yaml
│   │   ├── reports/
│   │   └── artifacts/
│   ├── preferences/                           # users app (settings/prefs)
│   │   ├── suite.yaml
│   │   ├── reports/
│   │   └── artifacts/
│   └── admin/                                 # admin_console app
│       ├── suite.yaml
│       ├── reports/
│       └── artifacts/
│
├── reports/                                   # Aggregated cross-module reports
│   ├── pass.ndjson
│   ├── fail.ndjson
│   └── run_summary.json
│
└── artifacts/                                 # Aggregated artifacts (fallback)
    └── .gitkeep
```

### Module-to-App Mapping

| Test Module | Django App(s) | Notes |
|-------------|---------------|-------|
| journal | journal | Journal entries, prompts |
| faith | faith | Scripture, prayer, devotionals |
| health | health, medical | Fitness, nutrition, medicine, labs, vitals |
| organize | life | Tasks, projects, inventory, events |
| goals | purpose | Goals, vision, direction |
| capture | capture | Audio capture, transcription |
| cos | calendar_engine, cos | CoS Time Command Center |
| preferences | users | Profile, preferences, onboarding |
| admin | admin_console | Admin task management |

Additional modules may be added later for: `dashboard`, `finance`, `billing`, `ai`, `brain_training`, `scan`, `security`, `sms`, `help`.

---

## 5. Phase Breakdown

### Phase 0 — Requirements and Governance

| Attribute | Value |
|-----------|-------|
| **Purpose** | Create the authoritative requirements document |
| **Scope** | Documentation only |
| **Files to create** | `wlj_ui_tests/wlj_test_master_prompt_requirements.md` |
| **Files allowed to modify** | None |
| **Tasks** | Write full requirements, define all phases, define YAML schema, define guardrails |
| **Validation criteria** | Document covers all 15 required sections; no framework code exists |
| **Exit criteria** | User approval of this document |
| **Risk level** | None — documentation only |
| **Rollback plan** | Delete `wlj_ui_tests/` directory |

---

### Phase 1 — Framework Skeleton

| Attribute | Value |
|-----------|-------|
| **Purpose** | Create directory structure and empty module scaffolding |
| **Scope** | Directories and `__init__.py` files only |
| **Files to create** | All directories listed in Section 4; `__init__.py` for framework/; `requirements.txt`; `.gitkeep` files for empty dirs |
| **Files allowed to modify** | None outside `wlj_ui_tests/` |
| **Tasks** | 1. Create `wlj_ui_tests/framework/` with `__init__.py` 2. Create all module directories with `reports/` and `artifacts/` subdirs 3. Create `wlj_ui_tests/reports/` and `wlj_ui_tests/artifacts/` 4. Create `requirements.txt` with `playwright>=1.40.0` + `pyyaml>=6.0` + `jsonschema>=4.0` |
| **Validation criteria** | All directories exist; `requirements.txt` is valid; no Python logic files yet |
| **Exit criteria** | `find wlj_ui_tests -type d` matches expected structure |
| **Risk level** | Negligible — directory creation only |
| **Rollback plan** | `rm -rf wlj_ui_tests/` (preserving this requirements doc) |
| **Max files changed** | 10 |
| **Max lines of code** | 50 (init files + requirements.txt + gitkeeps) |

---

### Phase 2 — Core Runner Engine

| Attribute | Value |
|-----------|-------|
| **Purpose** | Build the YAML-loading, case-iterating runner |
| **Scope** | `framework/runner.py` only |
| **Files to create** | `wlj_ui_tests/framework/runner.py` |
| **Files allowed to modify** | `wlj_ui_tests/framework/__init__.py` (exports) |
| **Tasks** | 1. Implement `SuiteRunner` class 2. YAML loading with `yaml.safe_load()` 3. Case iteration with pass/fail tracking 4. Integration hooks for executor, reporting, artifacts 5. Environment-aware base URL configuration |
| **Validation criteria** | Runner loads a sample YAML and iterates cases (stub executor) |
| **Exit criteria** | Unit test: load a minimal YAML, confirm cases are enumerated |
| **Risk level** | Low — new file only, no existing code modified |
| **Rollback plan** | Delete `framework/runner.py` |
| **Max files changed** | 2 |
| **Max lines of code** | 300 |

---

### Phase 3 — Action Execution Engine

| Attribute | Value |
|-----------|-------|
| **Purpose** | Build the Playwright action executor |
| **Scope** | `framework/executor.py` only |
| **Files to create** | `wlj_ui_tests/framework/executor.py` |
| **Files allowed to modify** | `wlj_ui_tests/framework/__init__.py` |
| **Tasks** | 1. Implement `ActionExecutor` class 2. Support action types: `NAVIGATE`, `CLICK`, `TYPE`, `SELECT`, `WAIT`, `ASSERT` 3. Each action maps to Playwright page methods 4. Timeout handling per action 5. Error capture with context |
| **Validation criteria** | Each action type is callable and maps to correct Playwright method |
| **Exit criteria** | Unit test: execute a NAVIGATE + CLICK + TYPE + ASSERT sequence against a mock page |
| **Risk level** | Low — new file only |
| **Rollback plan** | Delete `framework/executor.py` |
| **Max files changed** | 2 |
| **Max lines of code** | 300 |

**Supported Action Types:**

| Action | Parameters | Playwright Mapping |
|--------|-----------|-------------------|
| `NAVIGATE` | `url` | `page.goto(url)` |
| `CLICK` | `selector` | `page.locator(selector).click()` |
| `TYPE` | `selector`, `value` | `page.locator(selector).fill(value)` |
| `SELECT` | `selector`, `value` | `page.locator(selector).select_option(value)` |
| `WAIT` | `selector` or `timeout_ms` | `page.locator(selector).wait_for()` or `page.wait_for_timeout(ms)` |
| `ASSERT` | `selector`, `expected`, `assert_type` | Various assertion methods (see Section 7) |

---

### Phase 4 — Selector System

| Attribute | Value |
|-----------|-------|
| **Purpose** | Build the selector resolution engine |
| **Scope** | `framework/selectors.py` only |
| **Files to create** | `wlj_ui_tests/framework/selectors.py` |
| **Files allowed to modify** | `wlj_ui_tests/framework/__init__.py` |
| **Tasks** | 1. Implement `SelectorResolver` class 2. Support strategies: `data-testid`, `name`, `id`, `text_contains`, `role` 3. Priority resolution: `data-testid` > `id` > `name` > `role` > `text_contains` 4. Compound selector support |
| **Validation criteria** | Each selector strategy produces correct Playwright locator string |
| **Exit criteria** | Unit test: resolve each strategy type to expected locator |
| **Risk level** | Low — new file only |
| **Rollback plan** | Delete `framework/selectors.py` |
| **Max files changed** | 2 |
| **Max lines of code** | 200 |

**Selector Strategy Priority:**

```
1. data-testid  →  [data-testid="value"]         (preferred, most stable)
2. id           →  #value                          (stable if unique)
3. name         →  [name="value"]                  (form elements)
4. role         →  role=value                      (accessibility)
5. text_contains → text=value                      (fragile, last resort)
```

**YAML Selector Syntax:**

```yaml
selector:
  strategy: data-testid      # required
  value: journal-save-btn    # required
```

---

### Phase 5 — Reporting System

| Attribute | Value |
|-----------|-------|
| **Purpose** | Build pass/fail NDJSON logging and run summary |
| **Scope** | `framework/reporting.py` only |
| **Files to create** | `wlj_ui_tests/framework/reporting.py` |
| **Files allowed to modify** | `wlj_ui_tests/framework/__init__.py` |
| **Tasks** | 1. Implement `ReportWriter` class 2. Write `pass.ndjson` (one JSON object per line per passing case) 3. Write `fail.ndjson` (one JSON object per line per failing case) 4. Write `run_summary.json` (aggregate stats) 5. Module-scoped report paths |
| **Validation criteria** | Reports are valid NDJSON; summary contains correct counts |
| **Exit criteria** | Unit test: simulate 3 passes + 2 fails, verify file contents |
| **Risk level** | Low — new file only |
| **Rollback plan** | Delete `framework/reporting.py` |
| **Max files changed** | 2 |
| **Max lines of code** | 250 |

---

### Phase 6 — Artifact Capture

| Attribute | Value |
|-----------|-------|
| **Purpose** | Build screenshot and HTML dump capture on failure |
| **Scope** | `framework/artifacts.py` only |
| **Files to create** | `wlj_ui_tests/framework/artifacts.py` |
| **Files allowed to modify** | `wlj_ui_tests/framework/__init__.py` |
| **Tasks** | 1. Implement `ArtifactCapture` class 2. Screenshot capture (PNG) on failure 3. HTML dump capture on failure 4. File naming: `{module}_{case_id}_{timestamp}.{ext}` 5. Module-scoped artifact paths |
| **Validation criteria** | Artifacts are saved to correct module directory with correct naming |
| **Exit criteria** | Unit test: trigger capture, verify files exist with correct names |
| **Risk level** | Low — new file only |
| **Rollback plan** | Delete `framework/artifacts.py` |
| **Max files changed** | 2 |
| **Max lines of code** | 150 |

---

### Phase 7 — Claude Fix Prompt Generator

| Attribute | Value |
|-----------|-------|
| **Purpose** | Generate actionable Claude Code fix prompts from failures |
| **Scope** | `framework/prompt_builder.py` only |
| **Files to create** | `wlj_ui_tests/framework/prompt_builder.py` |
| **Files allowed to modify** | `wlj_ui_tests/framework/__init__.py` |
| **Tasks** | 1. Implement `PromptBuilder` class 2. Read `fail.ndjson` entries 3. Generate `claude_fix_prompt.md` with structured fix instructions 4. Include: case_id, failure reason, selector used, artifact paths, reproduction command, required fix instructions |
| **Validation criteria** | Generated prompt contains all required fields |
| **Exit criteria** | Unit test: feed failure data, verify prompt output structure |
| **Risk level** | Low — new file only |
| **Rollback plan** | Delete `framework/prompt_builder.py` |
| **Max files changed** | 2 |
| **Max lines of code** | 200 |

---

### Phase 8 — YAML Schema Loader and Validator

| Attribute | Value |
|-----------|-------|
| **Purpose** | Validate YAML suite files against the required schema |
| **Scope** | `framework/schema_validator.py` only |
| **Files to create** | `wlj_ui_tests/framework/schema_validator.py` |
| **Files allowed to modify** | `wlj_ui_tests/framework/__init__.py` |
| **Tasks** | 1. Implement `SchemaValidator` class 2. Define JSON Schema for suite YAML structure 3. Validate: version, suite metadata, module, auth, defaults, cases, steps, asserts, cleanup 4. Clear error messages on validation failure |
| **Validation criteria** | Valid YAML passes; invalid YAML fails with descriptive errors |
| **Exit criteria** | Unit test: validate good + bad YAML files |
| **Risk level** | Low — new file only |
| **Rollback plan** | Delete `framework/schema_validator.py` |
| **Max files changed** | 2 |
| **Max lines of code** | 300 |

---

### Phase 9 — Module Isolation System

| Attribute | Value |
|-----------|-------|
| **Purpose** | Ensure each module has isolated reports, artifacts, and suite configuration |
| **Scope** | Module directory creation + runner integration |
| **Files to create** | Stub `suite.yaml` files for each of the 9 initial modules |
| **Files allowed to modify** | `framework/runner.py` (module path resolution), `framework/reporting.py` (module-scoped output) |
| **Tasks** | 1. Create stub `suite.yaml` for each module (valid but empty cases) 2. Ensure runner resolves module paths correctly 3. Ensure reporting writes to module-specific `reports/` directory 4. Ensure artifacts write to module-specific `artifacts/` directory |
| **Validation criteria** | Running a module suite writes to that module's reports/ and artifacts/ only |
| **Exit criteria** | Run stub suite for 2 modules, verify isolated output |
| **Risk level** | Low — new files + minor modifications to framework files |
| **Rollback plan** | Delete stub suite files; revert runner/reporting changes |
| **Max files changed** | 10 |
| **Max lines of code** | 200 |

---

### Phase 10 — Safety Controls

| Attribute | Value |
|-----------|-------|
| **Purpose** | Implement production safety mode, cleanup protection, prefix enforcement |
| **Scope** | `framework/safety.py` + integration into runner and executor |
| **Files to create** | `wlj_ui_tests/framework/safety.py` |
| **Files allowed to modify** | `framework/runner.py` (safety check hooks), `framework/executor.py` (cleanup prefix enforcement) |
| **Tasks** | 1. Implement `SafetyController` class 2. Detect production vs development environment from `BASE_URL` 3. Enforce cleanup prefix: `AUTOTEST\|<MODULE>\|<RUN_ID>\|` 4. Rate limiting in production mode 5. Block destructive actions in production mode 6. Validate all cleanup operations match prefix |
| **Validation criteria** | Non-prefixed cleanup is blocked; rate limiting is active in prod mode |
| **Exit criteria** | Unit test: attempt non-prefixed cleanup in prod mode — must fail |
| **Risk level** | Medium — modifies runner and executor, but adds safety not risk |
| **Rollback plan** | Delete `safety.py`; revert hooks in runner.py and executor.py |
| **Max files changed** | 3 |
| **Max lines of code** | 250 |

---

### Phase 11 — CLI Runner

| Attribute | Value |
|-----------|-------|
| **Purpose** | Build the command-line interface for running test suites |
| **Scope** | `run_suite.py` entry point |
| **Files to create** | `wlj_ui_tests/run_suite.py` |
| **Files allowed to modify** | None |
| **Tasks** | 1. Implement argument parsing: `--suite`, `--module`, `--base-url`, `--headed`, `--env` 2. Wire CLI to `SuiteRunner` 3. Exit codes: 0 = all pass, 1 = failures, 2 = error 4. Summary output to stdout |
| **Validation criteria** | CLI runs with `--help` and with a stub suite |
| **Exit criteria** | `python wlj_ui_tests/run_suite.py --suite modules/journal/suite.yaml` executes without error |
| **Risk level** | Low — new file only |
| **Rollback plan** | Delete `run_suite.py` |
| **Max files changed** | 1 |
| **Max lines of code** | 150 |

**CLI Interface:**

```bash
# Run a specific module suite
python wlj_ui_tests/run_suite.py --suite modules/journal/suite.yaml

# Run a module by name
python wlj_ui_tests/run_suite.py --module journal

# Run against specific environment
python wlj_ui_tests/run_suite.py --module journal --base-url http://localhost:8000

# Run headed (visible browser) for debugging
python wlj_ui_tests/run_suite.py --module journal --headed

# Run in production safety mode
python wlj_ui_tests/run_suite.py --module journal --env production
```

---

## 6. Guardrails

### 6.1 Allowed Modifications

| Scope | What | Constraints |
|-------|------|------------|
| `wlj_ui_tests/**` | All files | Full read/write/create/delete |
| Django templates | `data-testid` attributes only | Attribute additions only; no structural changes, no logic changes, no style changes |
| `wlj_ui_tests/framework/**` | Selector helpers | Must be minimal; must not import from `apps/` |

### 6.2 Forbidden Modifications

The following are **absolutely forbidden** and must never be modified by this testing system:

| Category | Examples |
|----------|---------|
| CoS engine code | `apps/cos/`, `apps/calendar_engine/` business logic |
| Scheduler/orchestration | APScheduler jobs, cron configurations |
| AI engine/pipeline | `apps/ai/`, intelligence engines, OpenAI integration |
| Database models | Any `models.py`, any migration file |
| Business logic | Any `views.py`, `forms.py`, `serializers.py`, `services.py` in `apps/` |
| Authentication | `apps/users/` auth logic, allauth configuration |
| Production configuration | `config/settings.py`, `config/settings_production.py` |
| Infrastructure | `Procfile`, `nixpacks.toml`, `railway.json`, Docker files |
| Deployment | CI/CD pipelines, deploy scripts |

### 6.3 Data Safety

| Rule | Enforcement |
|------|------------|
| No production data deletion | Cleanup only deletes records matching `AUTOTEST\|<MODULE>\|<RUN_ID>\|` |
| No user data access | Tests use dedicated test accounts only |
| No non-test record modification | All created records must use the autotest prefix |
| Test data isolation | Each test run gets a unique `RUN_ID` for its data prefix |

### 6.4 Change Limits Per Phase

| Constraint | Limit |
|-----------|-------|
| Files changed per phase | Maximum 10 |
| Lines of code per phase | Maximum 300 |
| Template modifications per phase | Maximum 5 (data-testid additions only) |

---

## 7. YAML Schema Specification

### 7.1 Full Schema

```yaml
# Suite metadata
version: "1.0"                          # Required. Schema version.
suite: "Journal Module Tests"           # Required. Human-readable suite name.
module: "journal"                       # Required. Module identifier (matches directory name).

# Authentication configuration
auth:
  strategy: "session"                   # Required. One of: session, token, none.
  username: "${TEST_USERNAME}"          # Env var reference for username.
  password: "${TEST_PASSWORD}"          # Env var reference for password.
  login_url: "/accounts/login/"        # URL for session-based auth.

# Suite-wide defaults
defaults:
  timeout_ms: 5000                     # Default timeout for actions.
  base_url: "${BASE_URL}"             # Base URL for NAVIGATE actions.
  screenshot_on_failure: true          # Capture screenshot on assertion failure.
  html_dump_on_failure: true           # Capture HTML on assertion failure.

# Test cases
cases:
  - id: "journal-create-entry"         # Required. Unique within suite.
    name: "Create a new journal entry" # Required. Human-readable name.
    tags: ["smoke", "crud"]            # Optional. For filtering.
    priority: "high"                   # Optional. high | medium | low.

    steps:
      - action: NAVIGATE
        url: "/journal/"

      - action: CLICK
        selector:
          strategy: data-testid
          value: journal-new-entry-btn

      - action: TYPE
        selector:
          strategy: name
          value: title
        input: "AUTOTEST|journal|${RUN_ID}|Test Entry"

      - action: TYPE
        selector:
          strategy: name
          value: content
        input: "This is an automated test entry."

      - action: CLICK
        selector:
          strategy: data-testid
          value: journal-save-btn

      - action: WAIT
        selector:
          strategy: data-testid
          value: journal-entry-detail
        timeout_ms: 3000

    asserts:
      - type: text_contains
        selector:
          strategy: data-testid
          value: journal-entry-title
        expected: "AUTOTEST|journal|${RUN_ID}|Test Entry"

      - type: url_contains
        expected: "/journal/"

      - type: element_visible
        selector:
          strategy: data-testid
          value: journal-entry-detail

    cleanup:
      - action: NAVIGATE
        url: "/journal/"
      - action: CLICK
        selector:
          strategy: data-testid
          value: journal-delete-autotest
        condition: "prefix_match"       # Only delete if title matches AUTOTEST prefix
```

### 7.2 Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | Yes | Schema version, currently `"1.0"` |
| `suite` | string | Yes | Human-readable suite name |
| `module` | string | Yes | Module identifier matching directory name |
| `auth.strategy` | enum | Yes | `session`, `token`, or `none` |
| `auth.username` | string | Conditional | Required for `session` and `token` strategies |
| `auth.password` | string | Conditional | Required for `session` and `token` strategies |
| `auth.login_url` | string | Conditional | Required for `session` strategy |
| `defaults.timeout_ms` | integer | No | Default: `5000` |
| `defaults.base_url` | string | No | Default: `${BASE_URL}` env var |
| `defaults.screenshot_on_failure` | boolean | No | Default: `true` |
| `defaults.html_dump_on_failure` | boolean | No | Default: `true` |
| `cases[].id` | string | Yes | Unique case identifier (kebab-case) |
| `cases[].name` | string | Yes | Human-readable case name |
| `cases[].tags` | list[string] | No | For filtering (e.g., `smoke`, `regression`, `crud`) |
| `cases[].priority` | enum | No | `high`, `medium`, `low` |
| `cases[].steps[].action` | enum | Yes | `NAVIGATE`, `CLICK`, `TYPE`, `SELECT`, `WAIT`, `ASSERT` |
| `cases[].steps[].selector` | object | Conditional | Required for `CLICK`, `TYPE`, `SELECT`, `WAIT`, `ASSERT` |
| `cases[].steps[].selector.strategy` | enum | Yes (in selector) | `data-testid`, `name`, `id`, `text_contains`, `role` |
| `cases[].steps[].selector.value` | string | Yes (in selector) | Selector value |
| `cases[].steps[].url` | string | Conditional | Required for `NAVIGATE` |
| `cases[].steps[].input` | string | Conditional | Required for `TYPE` |
| `cases[].steps[].value` | string | Conditional | Required for `SELECT` |
| `cases[].steps[].timeout_ms` | integer | No | Overrides default timeout |
| `cases[].asserts[].type` | enum | Yes | `text_contains`, `text_equals`, `url_contains`, `url_equals`, `element_visible`, `element_not_visible`, `element_count`, `attribute_equals` |
| `cases[].asserts[].selector` | object | Conditional | Required for element-based assertions |
| `cases[].asserts[].expected` | string/int | Yes | Expected value |
| `cases[].cleanup[]` | list[step] | No | Steps to clean up test data |
| `cases[].cleanup[].condition` | string | No | `prefix_match` — only execute if autotest prefix matches |

### 7.3 Assertion Types

| Type | Parameters | Description |
|------|-----------|-------------|
| `text_contains` | `selector`, `expected` | Element text contains expected string |
| `text_equals` | `selector`, `expected` | Element text exactly equals expected string |
| `url_contains` | `expected` | Current URL contains expected string |
| `url_equals` | `expected` | Current URL exactly equals expected string |
| `element_visible` | `selector` | Element is visible on page |
| `element_not_visible` | `selector` | Element is not visible on page |
| `element_count` | `selector`, `expected` | Number of matching elements equals expected count |
| `attribute_equals` | `selector`, `attribute`, `expected` | Element attribute equals expected value |

### 7.4 Variable Substitution

The following variables are available in YAML values:

| Variable | Source | Description |
|----------|--------|-------------|
| `${BASE_URL}` | Environment | Base URL of the application |
| `${TEST_USERNAME}` | Environment | Test account username |
| `${TEST_PASSWORD}` | Environment | Test account password |
| `${RUN_ID}` | Generated | Unique identifier for this test run (UUID4 short) |
| `${MODULE}` | Suite metadata | Current module name |
| `${TIMESTAMP}` | Generated | ISO 8601 timestamp of test execution |

---

## 8. Reporting Specification

### 8.1 Pass Log (`pass.ndjson`)

One JSON object per line, one line per passing case:

```json
{"case_id": "journal-create-entry", "suite": "Journal Module Tests", "module": "journal", "status": "pass", "duration_ms": 2340, "timestamp": "2026-02-25T10:30:00Z", "steps_executed": 6, "run_id": "a1b2c3d4"}
```

### 8.2 Fail Log (`fail.ndjson`)

One JSON object per line, one line per failing case:

```json
{"case_id": "journal-create-entry", "suite": "Journal Module Tests", "module": "journal", "status": "fail", "duration_ms": 5120, "timestamp": "2026-02-25T10:30:05Z", "failed_step": 4, "action": "CLICK", "selector": {"strategy": "data-testid", "value": "journal-save-btn"}, "error": "Timeout waiting for selector [data-testid='journal-save-btn']", "screenshot": "artifacts/journal_journal-create-entry_20260225T103005.png", "html_dump": "artifacts/journal_journal-create-entry_20260225T103005.html", "run_id": "a1b2c3d4"}
```

### 8.3 Run Summary (`run_summary.json`)

```json
{
  "run_id": "a1b2c3d4",
  "suite": "Journal Module Tests",
  "module": "journal",
  "timestamp": "2026-02-25T10:30:00Z",
  "duration_ms": 45230,
  "environment": "development",
  "base_url": "http://localhost:8000",
  "total_cases": 10,
  "passed": 8,
  "failed": 2,
  "pass_rate": 0.80,
  "failures": [
    {
      "case_id": "journal-create-entry",
      "error": "Timeout waiting for selector [data-testid='journal-save-btn']"
    },
    {
      "case_id": "journal-edit-entry",
      "error": "Assertion failed: text_contains expected 'Updated' but got 'Original'"
    }
  ]
}
```

### 8.4 Report Locations

| Scope | Path |
|-------|------|
| Module-specific | `wlj_ui_tests/modules/<module>/reports/` |
| Aggregated | `wlj_ui_tests/reports/` |

Module reports contain only that module's results. Aggregated reports combine all modules from a multi-module run.

---

## 9. Artifact Specification

### 9.1 Screenshot Capture

| Attribute | Value |
|-----------|-------|
| Format | PNG |
| Trigger | Assertion failure or step failure |
| Naming | `{module}_{case_id}_{timestamp}.png` |
| Storage | `modules/<module>/artifacts/` |
| Full page | Yes (full page screenshot, not viewport only) |

### 9.2 HTML Dump Capture

| Attribute | Value |
|-----------|-------|
| Format | HTML |
| Trigger | Assertion failure or step failure |
| Naming | `{module}_{case_id}_{timestamp}.html` |
| Storage | `modules/<module>/artifacts/` |
| Content | Full `page.content()` at time of failure |

### 9.3 Artifact Retention

Artifacts are **not** committed to git. The `artifacts/` directories should be in `.gitignore`. Artifacts are ephemeral and exist for the duration of analysis/debugging.

---

## 10. Prompt Generation Specification

### 10.1 Claude Fix Prompt Structure

The `claude_fix_prompt.md` file is generated per module after a test run with failures. It is designed to be copy-pasted directly into a Claude Code session.

```markdown
# WLJ UI Test Failure — Fix Required

## Environment
- **Module:** journal
- **Run ID:** a1b2c3d4
- **Base URL:** http://localhost:8000
- **Timestamp:** 2026-02-25T10:30:00Z

## Failure 1 of 2

### Case: journal-create-entry
**Name:** Create a new journal entry

### What Failed
- **Step:** 4 (CLICK)
- **Action:** CLICK on [data-testid="journal-save-btn"]
- **Error:** Timeout waiting for selector [data-testid='journal-save-btn']

### Selector Details
- **Strategy:** data-testid
- **Value:** journal-save-btn
- **Resolved to:** [data-testid="journal-save-btn"]

### Artifacts
- **Screenshot:** wlj_ui_tests/modules/journal/artifacts/journal_journal-create-entry_20260225T103005.png
- **HTML Dump:** wlj_ui_tests/modules/journal/artifacts/journal_journal-create-entry_20260225T103005.html

### Reproduction
```bash
python wlj_ui_tests/run_suite.py --module journal --headed
```

### Required Fix
1. Check if the element with `data-testid="journal-save-btn"` exists in the journal entry form template
2. If missing, add `data-testid="journal-save-btn"` to the save button element
3. If present, check if the element is conditionally rendered or hidden
4. Verify the page has fully loaded before the click action
5. Run the test again to confirm the fix

---

## Failure 2 of 2
[... next failure ...]
```

### 10.2 Prompt Generation Rules

| Rule | Description |
|------|-------------|
| One prompt per module | All failures for a module are in one file |
| Actionable instructions | Every failure includes specific fix steps |
| Artifact references | Always include paths to screenshots and HTML dumps |
| Reproduction command | Always include the exact CLI command to reproduce |
| No speculation | Only report what the test system observed |

---

## 11. Safety Specification

### 11.1 Production Safety Mode

Production safety mode is **automatically activated** when `BASE_URL` matches a production hostname pattern (configurable, default: contains `railway.app` or does not contain `localhost`).

| Control | Behavior |
|---------|----------|
| Cleanup prefix enforcement | All cleanup operations must match `AUTOTEST\|<MODULE>\|<RUN_ID>\|` — operations not matching are blocked |
| Rate limiting | Minimum 500ms between page navigations; minimum 200ms between actions |
| No destructive actions | `DELETE`, `DROP`, database-modifying API calls are blocked |
| Mandatory artifact capture | Screenshots and HTML dumps are captured on every failure (cannot be disabled) |
| Audit logging | All actions are logged with timestamps |

### 11.2 Cleanup Prefix Standard

All test-created data must be prefixed:

```
AUTOTEST|<MODULE>|<RUN_ID>|<description>
```

Example:
```
AUTOTEST|journal|a1b2c3d4|Test Entry
```

The cleanup engine will **only** delete records matching this exact prefix pattern. The regex for validation:

```python
CLEANUP_PREFIX_PATTERN = r'^AUTOTEST\|[a-z_]+\|[a-f0-9]+\|'
```

### 11.3 Environment Detection

```python
def is_production(base_url: str) -> bool:
    """Determine if the target is a production environment."""
    production_indicators = ['railway.app', 'wholelifejourney.com']
    development_indicators = ['localhost', '127.0.0.1', '0.0.0.0']

    for indicator in development_indicators:
        if indicator in base_url:
            return False
    for indicator in production_indicators:
        if indicator in base_url:
            return True
    # Default to production safety if unknown
    return True
```

### 11.4 Test Account Requirements

Tests must use dedicated test accounts, never real user accounts. Test accounts should be:

- Created with the `AUTOTEST` prefix in the username/email
- Have known, fixed credentials stored in environment variables
- Have permissions appropriate for the module being tested

---

## 12. Deployment Integration Specification

### 12.1 CI/CD Integration Plan (Documentation Only — Not Implemented in This Build)

The framework is designed to integrate with CI/CD pipelines in a future phase:

```
Pipeline Stage: Post-Deploy Smoke Tests
Trigger: After successful deployment to staging/production
Steps:
  1. Install Playwright browsers
  2. Set environment variables (BASE_URL, TEST_USERNAME, TEST_PASSWORD)
  3. Run smoke-tagged cases: python wlj_ui_tests/run_suite.py --tag smoke --env production
  4. Check exit code: 0 = pass, 1 = failures exist
  5. Upload artifacts on failure
  6. Generate Claude fix prompt on failure
```

### 12.2 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BASE_URL` | Yes | Target application URL |
| `TEST_USERNAME` | Yes | Test account email |
| `TEST_PASSWORD` | Yes | Test account password |
| `WLJ_TEST_ENV` | No | `development` or `production` (auto-detected if not set) |
| `WLJ_TEST_HEADED` | No | `true` to run with visible browser |
| `WLJ_TEST_TIMEOUT` | No | Default timeout in ms (default: 5000) |

### 12.3 Dependencies

```
# requirements.txt
playwright>=1.40.0
pyyaml>=6.0
jsonschema>=4.0
```

Playwright browser installation:
```bash
playwright install chromium
```

---

## 13. Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Test modifies production data | Low | Critical | Cleanup prefix enforcement, production safety mode, audit logging |
| Test creates orphaned data | Medium | Low | Cleanup runs after every case; prefix enables manual cleanup |
| Selector breaks after UI change | High | Low | `data-testid` attributes are stable; not tied to styling or structure |
| Test flakiness due to timing | Medium | Medium | Configurable timeouts, explicit WAIT steps, retry logic in executor |
| Framework code affects app performance | Low | Low | Framework is completely separate; no runtime imports from `apps/` |
| Template `data-testid` additions break UI | Negligible | Negligible | `data-testid` is invisible to users; no CSS or JS side effects |
| Test credentials leaked | Low | High | Credentials in env vars only; never in YAML or code files |
| Playwright browser consumes resources | Medium | Low | Headless by default; single browser instance per suite |

---

## 14. Rollback Plan

### Per-Phase Rollback

Each phase has a specific rollback procedure documented in its phase definition (Section 5). General principle: since each phase creates new files in `wlj_ui_tests/`, rollback is a file deletion.

### Full System Rollback

To completely remove the testing framework:

```bash
# 1. Remove the entire testing directory
rm -rf wlj_ui_tests/

# 2. Remove any data-testid attributes added to templates (if any were added)
# Search for data-testid additions in git history:
git log --all --oneline -- '*.html' | head -20
# Revert specific commits that added data-testid attributes

# 3. Remove from .gitignore (if entries were added)
# Revert .gitignore changes related to test artifacts
```

### Partial Rollback (Single Phase)

```bash
# Identify files created in the phase from the phase tracking log (Section 16)
# Delete only those files
# Verify no other files depend on the deleted files
# Run remaining tests to confirm no breakage
```

---

## 15. Validation Checklist

### Phase 0 Checklist (This Document)

- [x] Executive overview written
- [x] System goals defined with success criteria
- [x] Architecture diagram (text) created
- [x] Directory structure documented
- [x] All 12 phases defined with full attributes
- [x] Guardrails documented (allowed/forbidden modifications)
- [x] YAML schema fully specified with field definitions
- [x] Reporting specification (pass/fail NDJSON + summary JSON)
- [x] Artifact specification (screenshots + HTML dumps)
- [x] Prompt generation specification (Claude fix prompt format)
- [x] Safety specification (production mode, prefix enforcement, rate limiting)
- [x] Deployment integration documented (CI/CD plan, env vars, dependencies)
- [x] Risk analysis with likelihood, impact, and mitigations
- [x] Rollback plans (per-phase and full system)
- [x] Validation checklist (this section)
- [x] No framework code created in this phase

### Phase 1 Checklist
- [ ] All directories created per Section 4
- [ ] `framework/__init__.py` exists
- [ ] `requirements.txt` created with correct dependencies
- [ ] No Python logic files created
- [ ] File count ≤ 10

### Phase 2 Checklist
- [ ] `framework/runner.py` created
- [ ] `SuiteRunner` class implemented
- [ ] YAML loading works with `yaml.safe_load()`
- [ ] Case iteration works
- [ ] Lines of code ≤ 300

### Phase 3 Checklist
- [ ] `framework/executor.py` created
- [ ] All 6 action types supported (NAVIGATE, CLICK, TYPE, SELECT, WAIT, ASSERT)
- [ ] Each action maps to correct Playwright method
- [ ] Lines of code ≤ 300

### Phase 4 Checklist
- [ ] `framework/selectors.py` created
- [ ] All 5 selector strategies supported
- [ ] Priority resolution works correctly
- [ ] Lines of code ≤ 200

### Phase 5 Checklist
- [ ] `framework/reporting.py` created
- [ ] `pass.ndjson` output is valid NDJSON
- [ ] `fail.ndjson` output is valid NDJSON
- [ ] `run_summary.json` contains correct aggregate stats
- [ ] Lines of code ≤ 250

### Phase 6 Checklist
- [ ] `framework/artifacts.py` created
- [ ] Screenshots captured as PNG
- [ ] HTML dumps captured
- [ ] File naming follows convention
- [ ] Lines of code ≤ 150

### Phase 7 Checklist
- [ ] `framework/prompt_builder.py` created
- [ ] Generated prompt includes all required fields
- [ ] Prompt is copy-paste ready for Claude Code
- [ ] Lines of code ≤ 200

### Phase 8 Checklist
- [ ] `framework/schema_validator.py` created
- [ ] JSON Schema validates all YAML fields
- [ ] Invalid YAML produces descriptive errors
- [ ] Lines of code ≤ 300

### Phase 9 Checklist
- [ ] Stub `suite.yaml` exists for all 9 modules
- [ ] Module path resolution works in runner
- [ ] Reports write to module-specific directories
- [ ] Artifacts write to module-specific directories
- [ ] Lines of code ≤ 200

### Phase 10 Checklist
- [ ] `framework/safety.py` created
- [ ] Production safety mode activates on production URLs
- [ ] Cleanup prefix enforcement blocks non-matching deletions
- [ ] Rate limiting works in production mode
- [ ] Lines of code ≤ 250

### Phase 11 Checklist
- [ ] `run_suite.py` created
- [ ] `--suite`, `--module`, `--base-url`, `--headed`, `--env` arguments work
- [ ] Exit codes correct (0, 1, 2)
- [ ] Lines of code ≤ 150

---

## 16. Phase Tracking Log

This section is updated after each phase completion to track implementation progress across sessions.

| Phase | Status | Date Started | Date Completed | Files Created | Files Modified | Notes |
|-------|--------|-------------|----------------|---------------|----------------|-------|
| 0 | **COMPLETE** | 2026-02-25 | 2026-02-25 | 1 | 0 | This document |
| 1 | PENDING | — | — | — | — | — |
| 2 | PENDING | — | — | — | — | — |
| 3 | PENDING | — | — | — | — | — |
| 4 | PENDING | — | — | — | — | — |
| 5 | PENDING | — | — | — | — | — |
| 6 | PENDING | — | — | — | — | — |
| 7 | PENDING | — | — | — | — | — |
| 8 | PENDING | — | — | — | — | — |
| 9 | PENDING | — | — | — | — | — |
| 10 | PENDING | — | — | — | — | — |
| 11 | PENDING | — | — | — | — | — |

---

*End of Master Requirements Document*
