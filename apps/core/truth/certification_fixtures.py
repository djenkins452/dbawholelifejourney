"""
Deterministic fixtures for Truth Retrieval Certification (Owner-1).

Each builder seeds a KNOWN user state at explicit USER-LOCAL dates and returns
`(user, anchors)`. No OpenAI, no wall-clock dependence beyond `get_user_today`
(the specs anchor against it explicitly, and use custom date ranges so named-period
month boundaries can never make a test flaky). The SAME fixtures back both the
deterministic Layer-1 tests and — via the shared QuestionSpec — the Customer Truth run.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.utils import get_user_today

User = get_user_model()


def _mk_user(email):
    from apps.users.models import TermsAcceptance
    u = User.objects.create_user(email=email, password="x")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _at(d):
    """A tz-aware datetime at noon on date `d` (stable within the user-local day)."""
    return timezone.make_aware(datetime.combine(d, time(12, 0)))


def build_weight_fixture(email="cert_weight@example.com"):
    """Weigh-ins at today-7 (185), today-3 (182), today-1 (180)."""
    from apps.health.models import WeightEntry
    u = _mk_user(email)
    today = get_user_today(u)
    d7, d3, d1 = (today - timedelta(days=7), today - timedelta(days=3),
                  today - timedelta(days=1))
    for d, v in [(d7, "185.0"), (d3, "182.0"), (d1, "180.0")]:
        WeightEntry.objects.create(user=u, value=Decimal(v), unit="lb", recorded_at=_at(d))
    return u, {"latest_weight": 180.0, "prior_weight": 182.0,
               "specific_date": d3, "specific_weight": 182.0,
               "range_start": d7, "range_end": today}


def build_medication_fixture(email="cert_med@example.com"):
    """Two active prescriptions (Metformin, Lisinopril), daily schedule, taken all
    of the last 7 days so adherence is non-zero and deterministic."""
    from apps.health.models import Intake, IntakeSchedule, IntakeLog
    u = _mk_user(email)
    today = get_user_today(u)
    for name in ["Metformin", "Lisinopril"]:
        m = Intake.objects.create(
            user=u, name=name, dose="10mg", frequency="daily",
            start_date=today - timedelta(days=30), intake_status="active",
            intake_type="medication", category="prescription")
        IntakeSchedule.objects.create(intake=m, scheduled_time=time(0, 1),
                                      days_of_week="0,1,2,3,4,5,6", is_active=True)
        for i in range(1, 8):
            IntakeLog.objects.create(user=u, intake=m,
                                     scheduled_date=today - timedelta(days=i),
                                     log_status="taken")
    return u, {"med_names": ["Lisinopril", "Metformin"],
               "range_start": today - timedelta(days=7), "range_end": today}


def build_nutrition_fixture(email="cert_nutrition@example.com"):
    """Foods on today (oatmeal), yesterday (pizza), and today-2 (salad)."""
    from apps.health.models import FoodEntry
    u = _mk_user(email)
    today = get_user_today(u)
    rows = [
        ("Oatmeal", FoodEntry.MEAL_BREAKFAST, today, time(8, 0)),
        ("Pepperoni Pizza", FoodEntry.MEAL_DINNER, today - timedelta(days=1), time(19, 0)),
        ("Caesar Salad", FoodEntry.MEAL_LUNCH, today - timedelta(days=2), time(12, 30)),
    ]
    for name, meal, d, t in rows:
        FoodEntry.objects.create(
            user=u, food_name=name, quantity=Decimal("1"),
            serving_size=Decimal("1"), serving_unit="serving", meal_type=meal,
            logged_date=d, logged_time=t, status="active")
    return u, {"pizza_date": today - timedelta(days=1)}


# The fixture registry — a QuestionSpec references a builder by key.
FIXTURES = {
    "weight": build_weight_fixture,
    "medication": build_medication_fixture,
    "nutrition": build_nutrition_fixture,
}
