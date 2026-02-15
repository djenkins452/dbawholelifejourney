"""
DBE — Briefing Selector.

Selects the top items from guidance, insights, and predictions
for inclusion in the daily briefing. Max 5 items total.

Priority order:
1. Critical guidance (priority 1-2)
2. High-confidence predictions (confidence >= 0.80)
3. Warning/critical insights
4. Remaining guidance (priority 3-5)
5. State changes / informational insights
"""

import logging

logger = logging.getLogger(__name__)

MAX_BRIEFING_ITEMS = 5


def select_briefing_items(guidance_items, insights, predictions):
    """
    Select top items for the daily briefing.

    Args:
        guidance_items: QuerySet/list of GuidanceItem instances.
        insights: QuerySet/list of Insight instances.
        predictions: QuerySet/list of Prediction instances.

    Returns:
        list of dicts, each with keys:
            - type: "guidance" | "insight" | "prediction"
            - title: str
            - message: str
            - priority: int (1=highest)
            - confidence: float or None
            - source_id: int (original record PK)
            - module: str
    """
    candidates = []

    # 1. Critical guidance (priority 1-2)
    for item in guidance_items:
        score = _guidance_priority_score(item)
        candidates.append({
            "type": "guidance",
            "title": item.title,
            "message": item.message,
            "priority": item.priority,
            "confidence": item.confidence_score,
            "source_id": item.id,
            "module": item.module or "",
            "_sort_score": score,
        })

    # 2. Predictions
    for pred in predictions:
        score = _prediction_priority_score(pred)
        candidates.append({
            "type": "prediction",
            "title": f"{pred.prediction_type} prediction",
            "message": pred.explanation or "",
            "priority": 2 if pred.confidence_score and pred.confidence_score >= 0.80 else 3,
            "confidence": pred.confidence_score,
            "source_id": pred.id,
            "module": pred.module or "",
            "_sort_score": score,
        })

    # 3. Insights
    for insight in insights:
        score = _insight_priority_score(insight)
        candidates.append({
            "type": "insight",
            "title": insight.title,
            "message": insight.message,
            "priority": _severity_to_priority(insight.severity),
            "confidence": insight.confidence_score,
            "source_id": insight.id,
            "module": insight.module or "",
            "_sort_score": score,
        })

    # Sort by score (lower = higher priority) and take top N
    candidates.sort(key=lambda x: x["_sort_score"])
    selected = candidates[:MAX_BRIEFING_ITEMS]

    # Remove internal sort key
    for item in selected:
        item.pop("_sort_score", None)

    return selected


def _guidance_priority_score(item):
    """Lower score = higher priority."""
    return item.priority * 10


def _prediction_priority_score(pred):
    """Predictions scored by confidence (inverted)."""
    confidence = pred.confidence_score or 0.5
    return 25 - (confidence * 20)  # High confidence → lower score


def _insight_priority_score(insight):
    """Insights scored by severity."""
    severity_map = {
        "critical": 10,
        "warning": 20,
        "positive": 35,
        "info": 40,
    }
    return severity_map.get(insight.severity, 40)


def _severity_to_priority(severity):
    """Map insight severity to numeric priority."""
    return {
        "critical": 1,
        "warning": 2,
        "positive": 3,
        "info": 4,
    }.get(severity, 4)
