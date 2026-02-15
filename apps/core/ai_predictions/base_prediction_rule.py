"""
PRIE — Base Prediction Rule contract.

All prediction rules must inherit from BasePredictionRule
and implement applies() and predict().
"""


class BasePredictionRule:
    """
    Base class for prediction rules.

    Subclasses must define:
        rule_name: unique identifier
        module: which WLJ module (health, goals, etc.)
        prediction_type: type of prediction (weight_30d, etc.)
        min_confidence_to_store: minimum confidence to persist (default 0.3)
    """

    rule_name = "base"
    module = "core"
    prediction_type = "base"
    min_confidence_to_store = 0.30

    def applies(self, user, event):
        """
        Check if this prediction rule should run for the given event.

        Args:
            user: Django User instance.
            event: Event dict (same format as PIE events).

        Returns:
            bool
        """
        return False

    def predict(self, user, event):
        """
        Generate predictions for the user.

        Returns:
            List of prediction dicts, each with:
            - prediction_type: str
            - module: str
            - predicted_value: float or None
            - predicted_date: datetime
            - confidence_score: float (0-1)
            - explanation: str (human-readable)
            - evidence: dict (auditable data)
            - dedupe_key: str
        """
        return []
