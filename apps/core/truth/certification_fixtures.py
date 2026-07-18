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
               "range_start": today - timedelta(days=7), "range_end": today,
               "last_taken_date": (today - timedelta(days=1)).isoformat()}


def build_nutrition_fixture(email="cert_nutrition@example.com"):
    """Foods with KNOWN macros across the last week: today (oatmeal), yesterday
    (pizza), today-3 (chicken), today-5 (salad). One entry per day, so each day's
    total — and therefore the windowed averages — is exact and deterministic."""
    from apps.health.models import FoodEntry
    u = _mk_user(email)
    today = get_user_today(u)
    # (name, meal, day-offset, time, calories, protein_g, carbs_g, fat_g)
    rows = [
        ("Oatmeal", FoodEntry.MEAL_BREAKFAST, 0, time(8, 0), 500, 20, 80, 10),
        ("Pepperoni Pizza", FoodEntry.MEAL_DINNER, 1, time(19, 0), 600, 40, 50, 20),
        ("Grilled Chicken", FoodEntry.MEAL_DINNER, 3, time(18, 0), 800, 60, 70, 30),
        ("Caesar Salad", FoodEntry.MEAL_LUNCH, 5, time(12, 30), 400, 20, 30, 10),
    ]
    for name, meal, off, t, cal, pro, carb, fat in rows:
        FoodEntry.objects.create(
            user=u, food_name=name, quantity=Decimal("1"),
            serving_size=Decimal("1"), serving_unit="serving", meal_type=meal,
            logged_date=today - timedelta(days=off), logged_time=t, status="active",
            total_calories=Decimal(cal), total_protein_g=Decimal(pro),
            total_carbohydrates_g=Decimal(carb), total_fat_g=Decimal(fat))
    # Window [today-5, today-1] holds salad / chicken / pizza (today excluded — the
    # current day's intake is still in progress). Averages are the mean of those
    # three daily totals: cal (400+800+600)/3, protein (20+60+40)/3, etc.
    return u, {
        "pizza_date": today - timedelta(days=1),
        "week_start": today - timedelta(days=5),
        "week_end": today - timedelta(days=1),
        "calories_yesterday": 600.0,
        "avg_calories_week": 600.0,
        "avg_protein_week": 40.0,
        "avg_carbs_week": 50.0,
        "avg_fat_week": 20.0,
    }


def build_vitals_fixture(email="cert_vitals@example.com"):
    """Glucose + blood-pressure readings across the last week, one per day, so the
    per-day series and its average are exact. Window [today-5, today-1] holds three
    readings each — enough for a timeline, an average, and a latest-vs-previous
    comparison ("how has my BP changed")."""
    from apps.health.models import GlucoseEntry, BloodPressureEntry
    u = _mk_user(email)
    today = get_user_today(u)
    # (day-offset, glucose mg/dL, systolic, diastolic)
    rows = [
        (5, 100, 122, 78),
        (3, 120, 130, 85),
        (1, 110, 120, 80),
    ]
    for off, g, sys, dia in rows:
        d = _at(today - timedelta(days=off))
        GlucoseEntry.objects.create(user=u, value=Decimal(g), unit="mg/dL", recorded_at=d)
        BloodPressureEntry.objects.create(user=u, systolic=sys, diastolic=dia, recorded_at=d)
    # Averages over the three in-window days:
    #   glucose (100+120+110)/3 = 110 · systolic (122+130+120)/3 = 124 ·
    #   diastolic (78+85+80)/3 = 81. Latest (today-1) systolic 120 < previous 130.
    return u, {
        "range_start": today - timedelta(days=5),
        "range_end": today - timedelta(days=1),
        "glucose_week_avg": 110.0,
        "bp_systolic_week_avg": 124.0,
        "bp_diastolic_week_avg": 81.0,
    }


# The fixture registry — a QuestionSpec references a builder by key.
FIXTURES = {
    "weight": build_weight_fixture,
    "medication": build_medication_fixture,
    "nutrition": build_nutrition_fixture,
    "vitals": build_vitals_fixture,
}
