"""
PRIE — Predictive Intelligence Engine.

Trajectory projection system that forecasts likely future outcomes
based on historical patterns. Uses deterministic math-based projections
(linear regression), never hallucination.

Public API:
    from apps.core.ai_predictions import generate_predictions
"""

from apps.core.ai_predictions.prediction_engine import generate_predictions

__all__ = ["generate_predictions"]
