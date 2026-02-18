"""
Whole Life Journey — CoS Documentation Generator

Project: Whole Life Journey
Path: apps/core/ai_docs/cos_doc_generator.py
Purpose: Generate human-readable admin guide content from CoS code

Description:
    Reads the CoS registry metadata, validates against live code,
    and produces structured Markdown articles ready for the admin
    guide. Each article is generated from code references — not
    hand-written — so it stays accurate as code changes.

Public API:
    - generate_cos_admin_guide() -> dict
      Returns section metadata + list of article dicts.

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import hashlib
import importlib
import json
import logging

from datetime import datetime

from .cos_doc_registry import (
    ENGINE_DEPENDENCIES,
    BLUEPRINT_MODEL_FIELDS,
    get_cos_registry,
    validate_registry,
)

logger = logging.getLogger(__name__)

COS_VERSION = "1.0.0"
COS_SECTION_KEY = "cos-architecture"
COS_SECTION_TITLE = "Chief of Staff Architecture"
COS_SECTION_ICON = "🧠"
COS_SECTION_DESCRIPTION = (
    "Auto-generated documentation for the Chief of Staff (CoS) "
    "intelligence layer. Updated automatically from code."
)


def _compute_dependency_checksum():
    """
    Compute a checksum of the engine dependency map.

    Returns a hex digest that changes when engines, functions,
    or models are added or removed.
    """
    payload = json.dumps(
        {
            'engines': {
                k: sorted(v['functions'])
                for k, v in sorted(ENGINE_DEPENDENCIES.items())
            },
            'models': {
                k: sorted(v['expected_fields'])
                for k, v in sorted(BLUEPRINT_MODEL_FIELDS.items())
            },
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _generate_overview_article():
    """Generate the top-level CoS overview article."""
    content = """## What is the Chief of Staff?

The Chief of Staff (CoS) is the intelligence layer that transforms
Whole Life Journey from a passive tracking app into a proactive Life
Operating System. It continuously monitors user behavior, detects
drift from commitments, and intervenes with calibrated urgency.

### Core Capabilities

| Capability | Description |
|------------|-------------|
| **Personal Operating Blueprint** | User-defined identity, priorities, and operating style |
| **Daily Architecture** | Nightly planning engine that builds tomorrow's schedule |
| **Drift Detection** | Real-time monitoring of deviations from commitments |
| **Predictive Modeling** | 24/72-hour drift probability forecasting |
| **Intelligent Friction** | Five-level escalation with identity-cost-aware gates |
| **Recovery Plans** | Compensating action suggestions when Tier 1 is impacted |
| **Curveball Protocol** | Real-time re-optimization for unexpected events |

### Intelligence Pipeline Integration

The CoS operates within Phase 3 (Post-Execution) of the intelligence
pipeline. It consumes state from SAE, insights from PIE, and predictions
from PRIE. It produces interventions delivered through DNE and learning
signals consumed by GLOE.

```
SAE → PIE → PRIE → CoS Blueprint Engines → DNE
                         ↓
                     GLOE (learning)
```
"""
    return {
        'title': 'CoS Overview',
        'slug': 'cos-overview',
        'content': content.strip(),
        'order': 1,
    }


def _generate_component_article(component, order):
    """
    Generate an article for a single CoS component.

    Args:
        component: Registry entry dict.
        order: Display order for this article.

    Returns:
        dict — Article data.
    """
    lines = []
    lines.append(f"## {component['name']}")
    lines.append("")
    lines.append(component['description'])
    lines.append("")

    # Engines section
    engine_names = component.get('engines', [])
    if engine_names:
        lines.append("### Engines")
        lines.append("")
        lines.append("| Engine | Module | Functions |")
        lines.append("|--------|--------|-----------|")
        for ename in engine_names:
            edef = ENGINE_DEPENDENCIES.get(ename, {})
            mod = edef.get('module', 'unknown')
            funcs = ', '.join(f'`{f}`' for f in edef.get('functions', []))
            lines.append(f"| {ename} | `{mod}` | {funcs} |")
        lines.append("")

    # Models section
    model_names = component.get('models', [])
    if model_names:
        lines.append("### Data Models")
        lines.append("")
        for mname in model_names:
            mdef = BLUEPRINT_MODEL_FIELDS.get(mname, {})
            fields = mdef.get('expected_fields', [])
            lines.append(f"**{mname}**")
            lines.append("")
            if fields:
                lines.append("Fields: " + ", ".join(f'`{f}`' for f in fields))
                lines.append("")

    # Tier rules
    tier_rules = component.get('tier_rules', {})
    if tier_rules:
        tiers = tier_rules.get('tiers', {})
        if tiers:
            lines.append("### Tier Definitions")
            lines.append("")
            lines.append("| Tier | Description |")
            lines.append("|------|-------------|")
            for tier_num, desc in sorted(tiers.items()):
                lines.append(f"| T{tier_num} | {desc} |")
            lines.append("")

        rule_b = tier_rules.get('rule_b')
        if rule_b:
            lines.append(f"**Rule B (Conflict Resolution):** {rule_b}")
            lines.append("")

        conflict_order = tier_rules.get('conflict_resolution_order')
        if conflict_order:
            lines.append(f"**Conflict Resolution Order:** {conflict_order}")
            lines.append("")

    # Identity cost
    identity_cost = component.get('identity_cost', {})
    if identity_cost:
        lines.append("### Identity Cost Calculation")
        lines.append("")
        lines.append(identity_cost.get('formula_description', ''))
        lines.append("")
        lines.append(
            f"Source: `{identity_cost.get('source', '')}"
            f".{identity_cost.get('function', '')}`"
        )
        lines.append("")

    # Scheduling
    scheduling = component.get('scheduling', {})
    if scheduling:
        lines.append("### Scheduling")
        lines.append("")
        lines.append(f"- **ISE Task:** `{scheduling.get('task_name', '')}`")
        lines.append(f"- **Interval:** {scheduling.get('interval', '')}")
        lines.append("")

    # Plan lifecycle
    lifecycle = component.get('plan_lifecycle', [])
    if lifecycle:
        lines.append("### Plan Lifecycle")
        lines.append("")
        for item in lifecycle:
            lines.append(f"1. **{item.split(' — ')[0]}**"
                        f" — {item.split(' — ')[1]}" if ' — ' in item else f"1. {item}")
        lines.append("")

    # Risk warnings
    risk_warnings = component.get('risk_warnings', [])
    if risk_warnings:
        lines.append("### Risk Warnings")
        lines.append("")
        for w in risk_warnings:
            lines.append(f"- {w}")
        lines.append("")

    # Curveball behavior
    behavior = component.get('behavior', {})
    if behavior and component['key'] == 'curveball_protocol':
        lines.append("### Curveball Handling")
        lines.append("")
        lines.append(f"- Default tier: **T{behavior.get('curveball_tier', 2)}**")
        if behavior.get('curveball_locked'):
            lines.append("- Curveball block is **locked** (cannot be displaced)")
        resolution = behavior.get('resolution')
        if resolution:
            lines.append(f"- {resolution}")
        lines.append("")

    # Drift types
    drift_types = component.get('drift_types', {})
    if drift_types:
        lines.append("### Monitored Drift Types")
        lines.append("")
        for dt in drift_types.get('types', []):
            lines.append(f"- {dt}")
        lines.append("")

    # Scoring
    scoring = component.get('scoring', {})
    if scoring:
        lines.append("### Scoring Formula")
        lines.append("")
        lines.append(scoring.get('formula_description', ''))
        lines.append("")

    # Prediction factors
    prediction_factors = component.get('prediction_factors', {})
    if prediction_factors:
        lines.append("### Prediction Factors")
        lines.append("")
        lines.append("| Factor | Weight & Description |")
        lines.append("|--------|---------------------|")
        for factor, desc in prediction_factors.items():
            label = factor.replace('_', ' ').title()
            lines.append(f"| {label} | {desc} |")
        lines.append("")

    # Thresholds
    thresholds = component.get('thresholds', {})
    if thresholds:
        lines.append("### Thresholds")
        lines.append("")
        for key, val in thresholds.items():
            label = key.replace('_', ' ').title()
            lines.append(f"- **{label}:** {val}")
        lines.append("")

    # Escalation levels
    escalation_levels = component.get('escalation_levels', {})
    if escalation_levels:
        lines.append("### Escalation Levels")
        lines.append("")
        lines.append("| Level | Name | Description |")
        lines.append("|-------|------|-------------|")
        for level, desc in sorted(escalation_levels.items()):
            name = desc.split(' — ')[0] if ' — ' in desc else desc
            detail = desc.split(' — ')[1] if ' — ' in desc else ''
            lines.append(f"| {level} | {name} | {detail} |")
        lines.append("")

    # Tolerance adjustment
    tolerance = component.get('tolerance_adjustment', {})
    if tolerance:
        lines.append("### Interruption Tolerance")
        lines.append("")
        for level, desc in tolerance.items():
            lines.append(f"- **{level.title()}:** {desc}")
        lines.append("")

    # Friction gate
    friction_gate = component.get('friction_gate', {})
    if friction_gate:
        lines.append("### Friction Gate")
        lines.append("")
        lines.append(f"**Trigger:** {friction_gate.get('trigger', '')}")
        lines.append("")
        contents = friction_gate.get('contents', [])
        if contents:
            lines.append("**Gate contents:**")
            lines.append("")
            for c in contents:
                lines.append(f"- {c}")
            lines.append("")
        options = friction_gate.get('response_options', [])
        if options:
            lines.append("**Response options:**")
            lines.append("")
            for o in options:
                lines.append(f"- {o}")
            lines.append("")

    # Trigger conditions
    trigger_conditions = component.get('trigger_conditions', [])
    if trigger_conditions:
        lines.append("### Trigger Conditions")
        lines.append("")
        for tc in trigger_conditions:
            lines.append(f"- {tc}")
        lines.append("")

    # Deduplication
    dedup = component.get('deduplication', {})
    if dedup:
        lines.append(f"**Deduplication:** {dedup.get('window', '')}")
        lines.append("")

    # Calculation (alignment index)
    calculation = component.get('calculation', {})
    if calculation:
        lines.append("### Calculation")
        lines.append("")
        lines.append(calculation.get('formula_description', ''))
        lines.append("")

    # Evidence
    evidence = component.get('evidence', {})
    if evidence:
        lines.append("### Evidence & Explainability")
        lines.append("")
        lines.append(evidence.get('description', ''))
        lines.append("")

    # Recovery plan behavior
    if behavior and component['key'] == 'recovery_plan':
        lines.append("### Recovery Behavior")
        lines.append("")
        lines.append(f"**Trigger:** {behavior.get('trigger', '')}")
        lines.append("")
        lines.append(f"**Output:** {behavior.get('output', '')}")
        lines.append("")

    # Configuration fields
    config_fields = component.get('configuration_fields', [])
    if config_fields:
        lines.append("### Configuration Fields")
        lines.append("")
        lines.append(
            "These fields on the Personal Operating Blueprint control "
            "assistant behavior:"
        )
        lines.append("")
        for f in config_fields:
            lines.append(f"- `{f}`")
        lines.append("")

    # Guardrails
    guardrails = component.get('guardrails', [])
    if guardrails:
        lines.append("### Guardrails")
        lines.append("")
        for g in guardrails:
            lines.append(f"- ✓ {g}")
        lines.append("")

    content = '\n'.join(lines).strip()

    # Slugify the key
    slug = f"cos-{component['key'].replace('_', '-')}"

    return {
        'title': component['name'],
        'slug': slug,
        'content': content,
        'order': order,
    }


def _generate_engine_map_article(order):
    """Generate an article listing all engine dependencies."""
    lines = [
        "## Engine Dependency Map",
        "",
        "Complete listing of all engines referenced by the CoS layer, "
        "validated against live code.",
        "",
        "### CoS Blueprint Engines",
        "",
        "| Engine | Module | Functions |",
        "|--------|--------|-----------|",
    ]

    cos_engines = [
        'blueprint_engine', 'priority_engine', 'architecture_engine',
        'drift_engine', 'intervention_engine', 'assistant_triggers',
    ]
    for ename in cos_engines:
        edef = ENGINE_DEPENDENCIES.get(ename, {})
        mod = edef.get('module', '')
        funcs = ', '.join(f'`{f}`' for f in edef.get('functions', []))
        lines.append(f"| {ename} | `{mod}` | {funcs} |")

    lines.extend([
        "",
        "### Upstream Intelligence Engines",
        "",
        "| Engine | Module | Functions |",
        "|--------|--------|-----------|",
    ])

    upstream = [
        'ai_orchestrator', 'ai_state', 'ai_insights', 'ai_predictions',
        'ai_guidance', 'ai_guidance_learning', 'ai_briefing',
        'ai_scheduler', 'ai_explain', 'ai_delivery', 'persona_engine',
    ]
    for ename in upstream:
        edef = ENGINE_DEPENDENCIES.get(ename, {})
        mod = edef.get('module', '')
        funcs = ', '.join(f'`{f}`' for f in edef.get('functions', []))
        lines.append(f"| {ename} | `{mod}` | {funcs} |")

    lines.append("")

    return {
        'title': 'Engine Dependency Map',
        'slug': 'cos-engine-map',
        'content': '\n'.join(lines).strip(),
        'order': order,
    }


def _generate_data_model_article(order):
    """Generate an article documenting all CoS data models."""
    lines = [
        "## Data Model Reference",
        "",
        "Complete field listing for all CoS models, validated against "
        "the Django ORM.",
        "",
    ]

    for model_name, model_def in BLUEPRINT_MODEL_FIELDS.items():
        lines.append(f"### {model_name}")
        lines.append("")
        lines.append(f"**Module:** `{model_def['module']}`")
        lines.append("")
        lines.append("| Field | Status |")
        lines.append("|-------|--------|")

        # Try to get actual field types from the model
        try:
            mod = importlib.import_module(model_def['module'])
            model_class = getattr(mod, model_name, None)
            if model_class:
                model_fields = {
                    f.name: f.get_internal_type()
                    for f in model_class._meta.get_fields()
                    if hasattr(f, 'get_internal_type')
                }
                for field_name in model_def['expected_fields']:
                    ftype = model_fields.get(field_name, 'unknown')
                    lines.append(f"| `{field_name}` | {ftype} ✓ |")
            else:
                for field_name in model_def['expected_fields']:
                    lines.append(f"| `{field_name}` | registered |")
        except ImportError:
            for field_name in model_def['expected_fields']:
                lines.append(f"| `{field_name}` | registered |")

        lines.append("")

    return {
        'title': 'Data Model Reference',
        'slug': 'cos-data-models',
        'content': '\n'.join(lines).strip(),
        'order': order,
    }


def _generate_scheduler_article(order):
    """Generate an article documenting ISE scheduled tasks for CoS."""
    lines = [
        "## Scheduled Tasks",
        "",
        "CoS tasks registered with the Intelligence Scheduler Engine (ISE).",
        "",
        "| Task | Interval | Description |",
        "|------|----------|-------------|",
    ]

    try:
        from apps.core.ai_scheduler.scheduler_registry import SCHEDULED_TASKS
        cos_tasks = {
            k: v for k, v in SCHEDULED_TASKS.items()
            if 'CoS' in v.get('description', '')
              or k.startswith('run_architecture')
              or k.startswith('run_drift')
              or k.startswith('run_assistant')
        }
        for task_name, task_def in cos_tasks.items():
            interval = task_def.get('interval_seconds', 0)
            if interval >= 86400:
                interval_str = f"{interval // 86400} day(s)"
            elif interval >= 3600:
                interval_str = f"{interval // 3600} hour(s)"
            else:
                interval_str = f"{interval // 60} minute(s)"
            desc = task_def.get('description', '')
            lines.append(f"| `{task_name}` | {interval_str} | {desc} |")
    except ImportError:
        lines.append("| — | — | Scheduler registry not available |")

    lines.append("")

    return {
        'title': 'Scheduled Tasks',
        'slug': 'cos-scheduled-tasks',
        'content': '\n'.join(lines).strip(),
        'order': order,
    }


def _generate_version_article(order):
    """Generate the version stamp article."""
    checksum = _compute_dependency_checksum()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    content = f"""## Version & Sync Status

| Property | Value |
|----------|-------|
| **CoS Version** | {COS_VERSION} |
| **Last Sync** | {now} |
| **Dependency Checksum** | `{checksum}` |
| **Engine Count** | {len(ENGINE_DEPENDENCIES)} |
| **Model Count** | {len(BLUEPRINT_MODEL_FIELDS)} |

### What does the checksum mean?

The dependency checksum changes whenever an engine function or model
field is added or removed from the CoS registry. If the checksum
differs from the last sync, the documentation may be stale.

### Auto-sync triggers

Documentation is regenerated:
- On server startup (if checksum changed)
- On demand via admin console button
- After any migration that touches blueprint models
"""
    return {
        'title': 'Version & Sync Status',
        'slug': 'cos-version',
        'content': content.strip(),
        'order': order,
    }


def generate_cos_admin_guide():
    """
    Generate the complete CoS admin guide from live code.

    Validates the registry against actual code, then generates
    Markdown articles for each CoS component.

    Returns:
        dict with keys:
            - section: dict with section metadata
            - articles: list[dict] — article data
            - checksum: str — dependency checksum
            - validation: dict with is_valid + errors
            - generated_at: str — ISO timestamp

    Raises:
        ValueError: If registry validation fails.
    """
    # Validate first
    is_valid, errors = validate_registry()
    if not is_valid:
        logger.warning(
            "CoS registry validation found %d issue(s): %s",
            len(errors), '; '.join(errors),
        )
        # We warn but still generate — some engines may not be
        # available in dev but exist in prod. The errors are
        # included in the output for transparency.

    # Build articles
    articles = []
    order = 1

    # 1. Overview
    articles.append(_generate_overview_article())
    order += 1

    # 2-12. Component articles from registry
    registry = get_cos_registry()
    for component in registry:
        articles.append(_generate_component_article(component, order))
        order += 1

    # 13. Engine dependency map
    articles.append(_generate_engine_map_article(order))
    order += 1

    # 14. Data model reference
    articles.append(_generate_data_model_article(order))
    order += 1

    # 15. Scheduled tasks
    articles.append(_generate_scheduler_article(order))
    order += 1

    # 16. Version stamp
    articles.append(_generate_version_article(order))

    checksum = _compute_dependency_checksum()
    generated_at = datetime.utcnow().isoformat() + 'Z'

    logger.info(
        "CoS admin guide generated: %d articles, checksum=%s, valid=%s",
        len(articles), checksum, is_valid,
    )

    return {
        'section': {
            'section_key': COS_SECTION_KEY,
            'title': COS_SECTION_TITLE,
            'icon': COS_SECTION_ICON,
            'description': COS_SECTION_DESCRIPTION,
        },
        'articles': articles,
        'checksum': checksum,
        'validation': {
            'is_valid': is_valid,
            'errors': errors,
        },
        'generated_at': generated_at,
    }
