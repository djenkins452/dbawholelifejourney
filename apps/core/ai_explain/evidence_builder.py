"""
E3 — Evidence Builder.

Builds structured evidence lists from intelligence objects.
Uses snapshot data already stored — does NOT scan the entire DB.

Evidence format:
[
    {
        "type": "weight_entry|habit_log|goal|scripture_reading|...",
        "id": 123,
        "date": "2026-02-15",
        "summary": "Short description",
        "url": "/health/weight/123/"
    }
]
"""

import logging

logger = logging.getLogger(__name__)


def build_evidence_for_guidance(guidance_item):
    """
    Build evidence list from a PGE GuidanceItem.

    Uses the item's existing evidence JSONField plus metadata.

    Args:
        guidance_item: GuidanceItem instance.

    Returns:
        list of evidence dicts.
    """
    evidence = []

    # Pull from the GuidanceItem's evidence JSONField
    stored_evidence = guidance_item.evidence or {}
    data_points = stored_evidence.get("data_points", [])

    for dp in data_points:
        evidence.append({
            "type": dp.get("name", "data_point"),
            "id": dp.get("id"),
            "date": dp.get("date"),
            "summary": _format_data_point(dp),
            "url": dp.get("url", ""),
        })

    # Add source engine reference
    source_map = {
        "prie_prediction": ("prediction", "PRIE prediction"),
        "pie_insight": ("insight", "PIE insight"),
        "sae_state": ("state_snapshot", "SAE state observation"),
    }
    source_info = source_map.get(guidance_item.source, ("composite", "Multiple sources"))
    if not evidence:
        evidence.append({
            "type": source_info[0],
            "id": None,
            "date": guidance_item.created_at.date().isoformat() if guidance_item.created_at else None,
            "summary": f"Based on: {source_info[1]}",
            "url": "",
        })

    # Add module-specific breadcrumb
    module_urls = {
        "health": "/health/",
        "goals": "/purpose/goals/",
        "habits": "/life/habits/",
        "journal": "/journal/",
        "faith": "/faith/",
        "finance": "/finance/",
    }
    module = guidance_item.module
    if module and module in module_urls:
        evidence.append({
            "type": "module_link",
            "id": None,
            "date": None,
            "summary": f"Related module: {module.title()}",
            "url": module_urls[module],
        })

    return evidence


def build_evidence_for_briefing(daily_briefing):
    """
    Build evidence list from a DBE DailyBriefing.

    Uses the briefing's snapshot JSONFields.

    Args:
        daily_briefing: DailyBriefing instance.

    Returns:
        list of evidence dicts.
    """
    evidence = []
    briefing_date = daily_briefing.briefing_date.isoformat()

    # Guidance items included
    guidance = daily_briefing.guidance_snapshot or {}
    for item in guidance.get("items", []):
        evidence.append({
            "type": "guidance_item",
            "id": item.get("id"),
            "date": briefing_date,
            "summary": f"[{item.get('source', 'guidance')}] {item.get('title', 'Guidance')}",
            "url": "/guidance/",
        })

    # Insights included
    insights = daily_briefing.insight_snapshot or {}
    for item in insights.get("items", []):
        evidence.append({
            "type": "insight",
            "id": item.get("id"),
            "date": briefing_date,
            "summary": f"[{item.get('severity', 'info')}] {item.get('title', 'Insight')}",
            "url": "/insights/",
        })

    # Predictions included
    predictions = daily_briefing.prediction_snapshot or {}
    for item in predictions.get("items", []):
        evidence.append({
            "type": "prediction",
            "id": item.get("id"),
            "date": briefing_date,
            "summary": f"{item.get('prediction_type', 'Prediction')} "
                       f"(confidence: {item.get('confidence_score', 0):.0%})",
            "url": "",
        })

    if not evidence:
        evidence.append({
            "type": "state_snapshot",
            "id": None,
            "date": briefing_date,
            "summary": "Based on daily state snapshot",
            "url": "/dashboard/",
        })

    return evidence


def build_evidence_for_weekly_report(weekly_report):
    """
    Build evidence list from a WIRE WeeklyIntelligenceReport.

    Uses the report's snapshot JSONFields.

    Args:
        weekly_report: WeeklyIntelligenceReport instance.

    Returns:
        list of evidence dicts.
    """
    evidence = []
    week_start = weekly_report.week_start_date.isoformat()

    # State deltas
    state_deltas = weekly_report.state_delta_snapshot or {}
    for delta in state_deltas.get("deltas", []):
        evidence.append({
            "type": "state_change",
            "id": None,
            "date": week_start,
            "summary": delta.get("label", "State change"),
            "url": "",
        })

    # Insights
    insights = weekly_report.insight_snapshot or {}
    for item in insights.get("insights", [])[:5]:
        evidence.append({
            "type": "insight",
            "id": None,
            "date": item.get("created_at", week_start)[:10] if item.get("created_at") else week_start,
            "summary": f"[{item.get('severity', 'info')}] {item.get('title', 'Insight')}",
            "url": "/insights/",
        })

    # Predictions
    predictions = weekly_report.prediction_snapshot or {}
    for item in predictions.get("predictions", [])[:5]:
        evidence.append({
            "type": "prediction",
            "id": None,
            "date": item.get("created_at", week_start)[:10] if item.get("created_at") else week_start,
            "summary": item.get("title", "Prediction"),
            "url": "",
        })

    # Guidance interactions
    guidance = weekly_report.guidance_snapshot or {}
    acted_count = sum(1 for g in guidance.get("guidance", []) if g.get("acted"))
    if acted_count > 0:
        evidence.append({
            "type": "guidance_interaction",
            "id": None,
            "date": week_start,
            "summary": f"{acted_count} guidance item{'s' if acted_count > 1 else ''} acted upon",
            "url": "/guidance/",
        })

    # Learning snapshot
    learning = weekly_report.learning_snapshot or {}
    resp = learning.get("responsiveness_score")
    if resp is not None:
        evidence.append({
            "type": "learning_profile",
            "id": None,
            "date": week_start,
            "summary": f"Engagement score: {resp:.0%}",
            "url": "",
        })

    if not evidence:
        evidence.append({
            "type": "weekly_aggregation",
            "id": None,
            "date": week_start,
            "summary": "Aggregated from weekly intelligence data",
            "url": "/intelligence/weekly/",
        })

    return evidence


def _format_data_point(dp):
    """Format a data point dict into a human-readable summary."""
    name = dp.get("name", "data")
    value = dp.get("value")
    if value is True:
        return f"{name.replace('_', ' ').title()}: Yes"
    elif value is False:
        return f"{name.replace('_', ' ').title()}: No"
    elif value is not None:
        return f"{name.replace('_', ' ').title()}: {value}"
    return name.replace("_", " ").title()
