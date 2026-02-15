"""
Base Rule Contract — All insight rules must implement this interface.
"""


class BaseInsightRule:
    """
    Contract for pluggable insight rules.

    Subclasses must implement applies() and evaluate().
    """

    rule_name = "base"
    module = "core"
    insight_type = "base"
    min_confidence_to_store = 0.6
    min_confidence_to_notify = 0.8

    def applies(self, user, event):
        """
        Check if this rule should run for the given event.

        Args:
            user: Django user instance.
            event: Dict with event_type, module, action, record_id, etc.

        Returns:
            True if this rule should evaluate.
        """
        return False

    def evaluate(self, user, event):
        """
        Evaluate the rule and return insight dicts.

        Returns:
            List of dicts, each with:
            - severity: "info"|"positive"|"warning"|"critical"
            - title: Short title
            - message: Full message
            - confidence_score: 0.0-1.0
            - explain_why: Why this insight was generated
            - evidence: Dict with record ids, dates, values
            - dedupe_key: Unique key for deduplication
        """
        return []
