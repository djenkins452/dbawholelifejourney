"""
ICQG — Conflict Detection.

Detects conflicting intelligence outputs:
- PRIE predicts improvement but PIE flags worsening in the same metric window
- PGE outputs both positive and negative guidance for the same target area

Policy:
- Downgrade the lower-confidence item
- Or merge into "mixed signals" if both have similar confidence
- Never invent new facts
"""

import logging

logger = logging.getLogger(__name__)

# Confidence delta below which items are considered "similar confidence"
SIMILAR_CONFIDENCE_THRESHOLD = 0.15

# Priority penalty applied to the lower-confidence conflicting item
CONFLICT_PRIORITY_PENALTY = 1  # Move one level toward Info


def detect_guidance_conflicts(candidates):
    """
    Detect and resolve conflicts among guidance candidates.

    Groups candidates by (module, guidance_type base) and checks for
    conflicting signals (one positive, one negative) in the same domain.

    Args:
        candidates: list of guidance candidate dicts.

    Returns:
        list of candidates with conflicts resolved (downgraded or merged).
    """
    if len(candidates) <= 1:
        return candidates

    try:
        # Group by module
        by_module = {}
        for c in candidates:
            module = c.get("module", "general")
            by_module.setdefault(module, []).append(c)

        resolved = []
        for module, group in by_module.items():
            if len(group) <= 1:
                resolved.extend(group)
                continue

            # Check for conflicting pairs within the module
            processed = _resolve_module_conflicts(group)
            resolved.extend(processed)

        return resolved

    except Exception as e:
        logger.error(f"ICQG: Conflict detection failed: {e}")
        return candidates  # Fail open


def detect_briefing_conflicts(items):
    """
    Detect conflicts in briefing items (insights vs predictions in same domain).

    Looks for cases where a prediction says "improving" but an insight
    says "worsening" (or vice versa) for the same module/metric.

    Args:
        items: list of briefing item dicts.

    Returns:
        list of items with conflicts resolved.
    """
    if len(items) <= 1:
        return items

    try:
        # Separate by type
        predictions = [i for i in items if i.get("type") == "prediction"]
        insights = [i for i in items if i.get("type") == "insight"]
        others = [i for i in items if i.get("type") not in ("prediction", "insight")]

        if not predictions or not insights:
            return items  # No conflicts possible

        # Check for contradictions by module
        resolved_predictions = list(predictions)
        resolved_insights = list(insights)

        for pred in predictions:
            pred_module = pred.get("module", "")
            pred_signal = _classify_signal(pred)

            for insight in insights:
                ins_module = insight.get("module", "")
                ins_signal = _classify_signal(insight)

                # Only conflict if same module and opposite signals
                if pred_module == ins_module and pred_signal and ins_signal:
                    if pred_signal != ins_signal:
                        _resolve_prediction_insight_conflict(
                            pred, insight,
                            resolved_predictions, resolved_insights,
                        )

        return resolved_predictions + resolved_insights + others

    except Exception as e:
        logger.error(f"ICQG: Briefing conflict detection failed: {e}")
        return items  # Fail open


def _resolve_module_conflicts(group):
    """
    Resolve conflicts within a single module's guidance candidates.

    Looks for pairs with opposing signals (positive vs negative guidance_type).
    """
    if len(group) <= 1:
        return group

    # Classify signals
    positive = []
    negative = []
    neutral = []

    for c in group:
        signal = _classify_signal(c)
        if signal == "positive":
            positive.append(c)
        elif signal == "negative":
            negative.append(c)
        else:
            neutral.append(c)

    # No conflict if all same direction
    if not positive or not negative:
        return group

    # Conflict detected — resolve
    logger.info(
        f"ICQG: Conflict detected in module '{group[0].get('module', '?')}': "
        f"{len(positive)} positive vs {len(negative)} negative"
    )

    # Compare confidence levels
    best_positive = max(positive, key=lambda c: c.get("confidence_score") or 0)
    best_negative = max(negative, key=lambda c: c.get("confidence_score") or 0)

    pos_conf = best_positive.get("confidence_score") or 0.5
    neg_conf = best_negative.get("confidence_score") or 0.5

    if abs(pos_conf - neg_conf) < SIMILAR_CONFIDENCE_THRESHOLD:
        # Similar confidence — merge into mixed signals
        merged = _merge_mixed_signals(best_positive, best_negative)
        return [merged] + neutral
    elif pos_conf > neg_conf:
        # Positive stronger — downgrade negative
        for c in negative:
            c["priority"] = min(c.get("priority", 3) + CONFLICT_PRIORITY_PENALTY, 5)
            c.setdefault("metadata", {})["icqg_downgraded"] = True
            c["metadata"]["icqg_reason"] = "Conflicting higher-confidence positive signal"
        return positive + negative + neutral
    else:
        # Negative stronger — downgrade positive
        for c in positive:
            c["priority"] = min(c.get("priority", 3) + CONFLICT_PRIORITY_PENALTY, 5)
            c.setdefault("metadata", {})["icqg_downgraded"] = True
            c["metadata"]["icqg_reason"] = "Conflicting higher-confidence negative signal"
        return positive + negative + neutral


def _resolve_prediction_insight_conflict(pred, insight, preds_list, insights_list):
    """Resolve a specific prediction vs insight conflict."""
    pred_conf = pred.get("confidence") or 0.5
    ins_conf = insight.get("confidence") or 0.5

    if abs(pred_conf - ins_conf) < SIMILAR_CONFIDENCE_THRESHOLD:
        # Similar confidence — note mixed signals in both
        pred.setdefault("metadata", {})["icqg_mixed_signal"] = True
        insight.setdefault("metadata", {})["icqg_mixed_signal"] = True
    elif pred_conf > ins_conf:
        # Prediction stronger — downgrade insight priority
        insight["priority"] = min(insight.get("priority", 4) + CONFLICT_PRIORITY_PENALTY, 5)
        insight.setdefault("metadata", {})["icqg_downgraded"] = True
    else:
        # Insight stronger — downgrade prediction priority
        pred["priority"] = min(pred.get("priority", 4) + CONFLICT_PRIORITY_PENALTY, 5)
        pred.setdefault("metadata", {})["icqg_downgraded"] = True


def _merge_mixed_signals(positive, negative):
    """
    Merge two conflicting items into a single 'mixed signals' item.

    Never invents new facts — just combines the existing titles/messages.
    """
    merged = {
        "title": f"Mixed signals: {positive.get('module', 'data')}",
        "message": (
            f"Conflicting data detected:\n"
            f"• {positive.get('title', 'Positive signal')}: "
            f"{positive.get('message', '')[:100]}\n"
            f"• {negative.get('title', 'Negative signal')}: "
            f"{negative.get('message', '')[:100]}\n"
            f"Review your recent data for the full picture."
        ),
        "priority": min(
            positive.get("priority", 3),
            negative.get("priority", 3),
        ),
        "guidance_type": "mixed_signal",
        "source": "composite",
        "module": positive.get("module", ""),
        "confidence_score": max(
            positive.get("confidence_score") or 0,
            negative.get("confidence_score") or 0,
        ),
        "evidence": {
            "positive_evidence": positive.get("evidence", {}),
            "negative_evidence": negative.get("evidence", {}),
        },
        "dedupe_key": f"mixed_signal:{positive.get('module', '')}:{positive.get('dedupe_key', '')}",
        "metadata": {
            "icqg_merged": True,
            "positive_title": positive.get("title", ""),
            "negative_title": negative.get("title", ""),
        },
    }
    return merged


def _classify_signal(item):
    """
    Classify whether an item represents a positive or negative signal.

    Uses guidance_type, severity, title, and message keywords.
    Returns: 'positive', 'negative', or None (neutral/unknown).
    """
    # Check severity (for insights)
    severity = item.get("severity", "")
    if severity == "positive":
        return "positive"
    if severity in ("warning", "critical"):
        return "negative"

    # Check guidance_type keywords
    gtype = (item.get("guidance_type", "") or "").lower()
    title = (item.get("title", "") or "").lower()
    text = gtype + " " + title

    positive_keywords = [
        "improvement", "progress", "achieved", "on_track", "positive",
        "completed", "streak", "success", "milestone",
    ]
    negative_keywords = [
        "risk", "decline", "warning", "missed", "negative",
        "stagnation", "drop", "concern", "overdue", "behind",
    ]

    pos_match = any(kw in text for kw in positive_keywords)
    neg_match = any(kw in text for kw in negative_keywords)

    if pos_match and not neg_match:
        return "positive"
    if neg_match and not pos_match:
        return "negative"

    return None
