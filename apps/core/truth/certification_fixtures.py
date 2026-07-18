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


def build_body_measurements_fixture(email="cert_body@example.com"):
    """Waist + body-fat measurements trending DOWN across the last month, one per
    check-in date, so the series, its average, and latest-vs-previous are exact.
    Window [today-30, today-2] holds three waist readings: 36 → 35 → 34."""
    from apps.health.models import BodyCompositionEntry
    u = _mk_user(email)
    today = get_user_today(u)
    # (day-offset, waist in, body_fat_pct)
    rows = [(30, "36.0", "26.0"), (14, "35.0", "24.0"), (2, "34.0", "22.0")]
    for off, waist, bf in rows:
        d = today - timedelta(days=off)
        BodyCompositionEntry.objects.create(
            user=u, metric_name="waist", value=Decimal(waist), unit="in",
            measurement_date=d)
        BodyCompositionEntry.objects.create(
            user=u, metric_name="body_fat_pct", value=Decimal(bf), unit="%",
            measurement_date=d)
    # waist avg (36+35+34)/3 = 35; latest (today-2) 34 < previous 35.
    return u, {
        "range_start": today - timedelta(days=30),
        "range_end": today - timedelta(days=2),
        "waist_avg": 35.0,
    }


def build_journal_fixture(email="cert_journal@example.com"):
    """Journal entries with moods across the last week (mood history) + a titled
    entry yesterday (entity lookup by date)."""
    from apps.journal.models import JournalEntry
    u = _mk_user(email)
    today = get_user_today(u)
    rows = [(0, "great", "Grateful morning"), (1, "good", "Steady day"),
            (3, "okay", "A bit tired"), (5, "low", "Rough patch")]
    for off, mood, title in rows:
        JournalEntry.objects.create(
            user=u, entry_date=today - timedelta(days=off), mood=mood,
            title=title, body=f"<p>{title}.</p>")
    return u, {"range_start": today - timedelta(days=5),
              "range_end": today - timedelta(days=1),
              "yesterday": (today - timedelta(days=1)).isoformat()}


def build_faith_fixture(email="cert_faith@example.com"):
    """Prayer requests (entity) — one unanswered 'Healing for Mom', one answered."""
    from apps.faith.models import PrayerRequest
    u = _mk_user(email)
    PrayerRequest.objects.create(user=u, title="Healing for Mom", priority="urgent",
                                 is_answered=False, description="Please heal her.")
    PrayerRequest.objects.create(user=u, title="New job", priority="normal",
                                 is_answered=True, description="Thankful.")
    return u, {"prayer_name": "Healing"}


def build_relationships_fixture(email="cert_rel@example.com"):
    """relationships.Person rows — Heather (recent contact) + others."""
    from apps.relationships.models import Person
    u = _mk_user(email)
    today = get_user_today(u)
    heather_last = today - timedelta(days=3)
    Person.objects.create(owner=u, first_name="Heather", last_name="Jones",
                          relationship_type="friend", interaction_count=12,
                          last_interaction_date=heather_last, notes="College friend.")
    Person.objects.create(owner=u, first_name="Marcus", relationship_type="colleague",
                          interaction_count=4, last_interaction_date=today - timedelta(days=40))
    return u, {"heather": "Heather", "heather_last": heather_last.isoformat()}


def build_calendar_fixture(email="cert_cal@example.com"):
    """CalendarEvents: one tomorrow, one 2 days out, two in the past week."""
    from apps.calendar_engine.models import CalendarEvent
    from apps.calendar_engine.utils.idempotency import compute_idempotency_key
    u = _mk_user(email)
    today = get_user_today(u)

    def _ev(title, day_offset, hour=10):
        start = timezone.make_aware(datetime.combine(
            today + timedelta(days=day_offset), time(hour, 0)))
        end = start + timedelta(hours=1)
        CalendarEvent.objects.create(
            user=u, title=title, start_dt=start, end_dt=end, status="scheduled",
            idempotency_key=compute_idempotency_key(u.id, title, start, end))
    _ev("Dentist", 1)
    _ev("Team sync", 2)
    _ev("Past meeting A", -2)
    _ev("Past meeting B", -4)
    return u, {"range_start": today - timedelta(days=5),
              "range_end": today, "event_name": "Dentist"}


def build_tasks_fixture(email="cert_tasks@example.com"):
    """Tasks: overdue pending, due today, and two completed in the last few days."""
    from apps.life.models import Task
    u = _mk_user(email)
    today = get_user_today(u)
    Task.objects.create(user=u, title="File taxes", completion_status="pending",
                        due_date=today - timedelta(days=3))
    Task.objects.create(user=u, title="Call plumber", completion_status="pending",
                        due_date=today)
    for off in (1, 2):
        Task.objects.create(user=u, title=f"Done task {off}",
                            completion_status="completed",
                            completed_at=_at(today - timedelta(days=off)),
                            due_date=today - timedelta(days=off))
    return u, {"range_start": today - timedelta(days=5),
              "range_end": today, "task_name": "File taxes"}


def build_goals_fixture(email="cert_goals@example.com"):
    """A primary-mission LifeGoal ('France 2027') with milestones (some completed,
    one overdue) + momentum snapshots (progress history)."""
    from apps.purpose.models import LifeGoal, GoalMilestone
    from apps.dashboard_v2.models import GoalMomentumSnapshot
    u = _mk_user(email)
    today = get_user_today(u)
    g = LifeGoal.objects.create(user=u, title="Move to France 2027", status="active",
                                is_primary_mission=True, is_foundational=True,
                                target_date=today + timedelta(days=400),
                                why_it_matters="A lifelong dream.",
                                success_looks_like="Living in Lyon.")
    GoalMilestone.objects.create(goal=g, title="Learn A2 French", completed=True,
                                 completed_date=today - timedelta(days=10),
                                 target_date=today - timedelta(days=15), sort_order=1)
    GoalMilestone.objects.create(goal=g, title="Save €10k", completed=False,
                                 target_date=today - timedelta(days=2), sort_order=2)
    GoalMilestone.objects.create(goal=g, title="Visa research", completed=False,
                                 target_date=today + timedelta(days=30), sort_order=3)
    for off, prog, mom in [(6, 30, 40), (3, 45, 55), (1, 55, 60)]:
        GoalMomentumSnapshot.objects.create(
            user=u, goal=g, snapshot_date=today - timedelta(days=off),
            progress_score=prog, momentum_score=mom)
    return u, {"mission": "France 2027", "range_start": today - timedelta(days=6),
              "range_end": today}


def build_legacy_fixture(email="cert_legacy@example.com"):
    """Legacy Person (Harold Keck), a Place, and a Memory."""
    from apps.legacy.models import Memory, Person, Place
    u = _mk_user(email)
    Person.objects.create(user=u, display_name="Harold Keck",
                          relationship_label="grandfather", birth_year=1921,
                          death_year=1998, significance=5)
    Person.objects.create(user=u, display_name="Edith Keck",
                          relationship_label="grandmother", significance=4)
    Place.objects.create(user=u, name="The Farmhouse",
                         location_text="Iowa", significance=5)
    Memory.objects.create(user=u, title="Summers at the farm",
                          entry_type="MEMORY", entry_state="legacy")
    return u, {"person": "Harold Keck", "place": "Farmhouse"}


# The fixture registry — a QuestionSpec references a builder by key.
FIXTURES = {
    "weight": build_weight_fixture,
    "medication": build_medication_fixture,
    "nutrition": build_nutrition_fixture,
    "vitals": build_vitals_fixture,
    "body": build_body_measurements_fixture,
    "journal": build_journal_fixture,
    "faith": build_faith_fixture,
    "relationships": build_relationships_fixture,
    "calendar": build_calendar_fixture,
    "tasks": build_tasks_fixture,
    "goals": build_goals_fixture,
    "legacy": build_legacy_fixture,
}
