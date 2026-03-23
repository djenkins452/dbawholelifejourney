"""
Domain adapters — evaluate raw domain data into canonical ComplianceEvent rows.

Each adapter:
1. Identifies what was expected for a user on a date range
2. Identifies what actually happened
3. Creates ComplianceEvent rows with proper status + reason codes

Usage:
    from apps.dashboard_v2.compliance.adapters import evaluate_all_domains
    events = evaluate_all_domains(user, start_date, end_date)
"""

from apps.dashboard_v2.compliance.adapters.medication import evaluate_medication
from apps.dashboard_v2.compliance.adapters.workout import evaluate_workout
from apps.dashboard_v2.compliance.adapters.routine import evaluate_routine
from apps.dashboard_v2.compliance.adapters.task import evaluate_task
from apps.dashboard_v2.compliance.adapters.journal import evaluate_journal
from apps.dashboard_v2.compliance.adapters.faith import evaluate_faith

# Registry of domain adapters — new domains plug in here
DOMAIN_ADAPTERS = [
    evaluate_medication,
    evaluate_workout,
    evaluate_routine,
    evaluate_task,
    evaluate_journal,
    evaluate_faith,
]


def evaluate_all_domains(user, start_date, end_date):
    """
    Run all domain adapters and return flat list of ComplianceEvent dicts.

    Each dict is ready for ComplianceEvent.objects.create(**dict).
    Does NOT write to DB — caller decides when to persist.
    """
    events = []
    for adapter in DOMAIN_ADAPTERS:
        events.extend(adapter(user, start_date, end_date))
    return events
