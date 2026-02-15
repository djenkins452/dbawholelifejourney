"""
WIRE — Report Selector.

Selects the most important items from the week's intelligence
for inclusion in the weekly report.
"""

import logging

logger = logging.getLogger(__name__)

MAX_REPORT_ITEMS = 10


def select_report_items(insights, predictions, guidance_items, state_deltas):
    """
    Select top items for the weekly report.

    Priority order:
    1. Critical predictions (confidence >= 0.8)
    2. Critical/warning insights
    3. Important state changes (meaningful deltas)
    4. Guidance engagement patterns (acted items)
    5. Remaining items

    Args:
        insights: List of insight dicts from PIE.
        predictions: List of prediction dicts from PRIE.
        guidance_items: List of guidance dicts from PGE.
        state_deltas: List of state change dicts from SAE.

    Returns:
        List of selected items (max MAX_REPORT_ITEMS).
    """
    selected = []

    # 1. Critical predictions
    for pred in predictions:
        confidence = pred.get("confidence_score", 0)
        if confidence >= 0.8:
            selected.append({
                "type": "prediction",
                "title": pred.get("title", "Prediction"),
                "detail": pred.get("description", ""),
                "priority": 1,
                "confidence": confidence,
            })

    # 2. Critical/warning insights
    for insight in insights:
        severity = insight.get("severity", "info")
        if severity in ("critical", "warning"):
            selected.append({
                "type": "insight",
                "title": insight.get("title", "Insight"),
                "detail": insight.get("description", ""),
                "priority": 2 if severity == "critical" else 3,
                "severity": severity,
            })

    # 3. Important state changes
    for delta in state_deltas:
        if delta.get("significant", False):
            selected.append({
                "type": "state_change",
                "title": delta.get("label", "State Change"),
                "detail": delta.get("description", ""),
                "priority": 3,
                "module": delta.get("module", ""),
            })

    # 4. Guidance acted items
    for item in guidance_items:
        if item.get("acted", False):
            selected.append({
                "type": "guidance_acted",
                "title": item.get("title", "Guidance"),
                "detail": item.get("message", ""),
                "priority": 4,
            })

    # 5. Fill remaining with other predictions and insights
    if len(selected) < MAX_REPORT_ITEMS:
        for pred in predictions:
            if len(selected) >= MAX_REPORT_ITEMS:
                break
            confidence = pred.get("confidence_score", 0)
            if confidence < 0.8:  # Not already added
                selected.append({
                    "type": "prediction",
                    "title": pred.get("title", "Prediction"),
                    "detail": pred.get("description", ""),
                    "priority": 5,
                    "confidence": confidence,
                })

    if len(selected) < MAX_REPORT_ITEMS:
        for insight in insights:
            if len(selected) >= MAX_REPORT_ITEMS:
                break
            severity = insight.get("severity", "info")
            if severity not in ("critical", "warning"):
                selected.append({
                    "type": "insight",
                    "title": insight.get("title", "Insight"),
                    "detail": insight.get("description", ""),
                    "priority": 5,
                    "severity": severity,
                })

    return selected[:MAX_REPORT_ITEMS]
