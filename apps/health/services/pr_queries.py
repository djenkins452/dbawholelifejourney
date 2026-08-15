"""
PersonalRecordQueries — canonical Personal-Record entity truth (Layer 1 exposure).

Exposes the EXISTING `PersonalRecord` model (weight / reps / e1RM / time PRs, with the
canonical Brzycki `estimated_1rm`) as `CompleteEntity` records for the platform Entity +
Analysis surfaces — so the Chief of Staff can answer "what are my personal records",
"what's the most weight I've lifted", "have I set any PRs recently" from truth WLJ already
owns. Pure exposure: no new calculation, no re-derivation — the estimated 1RM is the
model's own canonical property. Soft-delete respected (status='active').
"""
from apps.core.truth.entity import CompleteEntity


def _num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_entity(pr):
    """One PersonalRecord → a CompleteEntity. `pr.exercise` is select_related by the caller."""
    ex_name = getattr(getattr(pr, "exercise", None), "name", None) or "Exercise"
    type_label = pr.get_pr_type_display() if hasattr(pr, "get_pr_type_display") else pr.pr_type
    return CompleteEntity(
        kind="personal_record",
        identity=f"{ex_name} — {type_label}",
        definition={
            "exercise": ex_name,
            "pr_type": pr.pr_type,
            "achieved_date": pr.achieved_date.isoformat() if pr.achieved_date else None,
            "previous_value": _num(pr.previous_value),
        },
        status="achieved",
        performance={
            "weight_lb": _num(pr.weight),
            "reps": pr.reps,
            "estimated_1rm_lb": _num(getattr(pr, "estimated_1rm", None)),
            "duration_seconds": pr.duration_seconds,
        },
    )


class PersonalRecordQueries:

    _DESCRIBE_LIMIT = 50

    @classmethod
    def describe(cls, user, *, start=None, end=None, limit=None):
        """The user's personal records as `CompleteEntity` objects, newest-achieved first.
        `start`/`end` optionally scope to a period ("PRs this year"); unscoped returns the
        recent bounded set. Soft-delete respected."""
        from apps.health.models import PersonalRecord
        qs = (PersonalRecord.objects.filter(user=user, status="active")
              .select_related("exercise").order_by("-achieved_date"))
        if start is not None and end is not None:
            qs = qs.filter(achieved_date__range=(start, end))
        cap = cls._DESCRIBE_LIMIT if limit is None else limit
        return [_to_entity(pr) for pr in qs[:cap]]

    @classmethod
    def describe_one(cls, user, name):
        """The most recent PR whose exercise name matches `name` (e.g. "bench press"), or
        None — so "what's my bench PR" cites the actual record."""
        from apps.health.models import PersonalRecord
        n = (name or "").strip()
        if not n:
            return None
        pr = (PersonalRecord.objects.filter(user=user, status="active",
                                            exercise__name__icontains=n)
              .select_related("exercise").order_by("-achieved_date").first())
        return _to_entity(pr) if pr else None
