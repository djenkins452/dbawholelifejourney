"""
Deterministic fixtures for Truth Retrieval Certification (Owner-1).

Each builder seeds a KNOWN user state at explicit USER-LOCAL dates and returns
`(user, anchors)`. No OpenAI, no wall-clock dependence beyond `get_user_today`
(the specs anchor against it explicitly, and use custom date ranges so named-period
month boundaries can never make a test flaky). The SAME fixtures back both the
deterministic Layer-1 tests and — via the shared QuestionSpec — the Customer Truth run.
"""
from datetime import date, datetime, time, timedelta
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
    # (day-offset, glucose mg/dL, systolic, diastolic, pulse)
    rows = [
        (5, 100, 122, 78, 64),
        (3, 120, 130, 85, 70),
        (1, 110, 120, 80, 66),
    ]
    for off, g, sys, dia, pul in rows:
        d = _at(today - timedelta(days=off))
        GlucoseEntry.objects.create(user=u, value=Decimal(g), unit="mg/dL", recorded_at=d)
        BloodPressureEntry.objects.create(user=u, systolic=sys, diastolic=dia,
                                          pulse=pul, recorded_at=d)
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
    from apps.journal.models import Emotion, JournalEntry
    u = _mk_user(email)
    today = get_user_today(u)
    anxious, _ = Emotion.objects.get_or_create(
        slug="anxious", defaults={"name": "anxious", "emoji": "\U0001F630"})
    rows = [(0, "great", "Grateful morning"), (1, "good", "Steady day"),
            (3, "okay", "A bit tired"), (5, "low", "Rough patch")]
    for off, mood, title in rows:
        e = JournalEntry.objects.create(
            user=u, entry_date=today - timedelta(days=off), mood=mood,
            title=title, body=f"<p>{title}.</p>")
        if off in (1, 3):            # repeated concern across two entries
            e.emotions.add(anxious)
    return u, {"range_start": today - timedelta(days=5),
              "range_end": today - timedelta(days=1),
              "week_start": today - timedelta(days=6), "week_end": today,
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
    """relationships.Person rows — Heather (recent contact + interaction log) + others,
    plus an upcoming birthday (SignificantEvent)."""
    from apps.relationships.models import Person, RelationshipInteraction
    from apps.life.models import SignificantEvent
    u = _mk_user(email)
    today = get_user_today(u)
    heather_last = today - timedelta(days=3)
    heather = Person.objects.create(
        owner=u, first_name="Heather", last_name="Jones", relationship_type="friend",
        interaction_count=12, last_interaction_date=heather_last, notes="College friend.")
    Person.objects.create(owner=u, first_name="Marcus", relationship_type="colleague",
                          interaction_count=4, last_interaction_date=today - timedelta(days=40))
    from django.contrib.contenttypes.models import ContentType
    from apps.journal.models import JournalEntry
    # A journal entry that mentions Heather, linked as a journal-context interaction →
    # "what journal entries mention Heather" resolves to a real titled record.
    je = JournalEntry.objects.create(user=u, entry_date=today - timedelta(days=3),
                                     title="Coffee with Heather", body="<p>Great chat.</p>")
    RelationshipInteraction.objects.create(
        person=heather, user=u, context_type_label="journal",
        interaction_date=today - timedelta(days=3),
        content_type=ContentType.objects.get_for_model(JournalEntry), object_id=je.pk)
    for off, ctx in [(3, "manual"), (10, "meal"), (20, "task")]:
        RelationshipInteraction.objects.create(
            person=heather, user=u, context_type_label=ctx,
            interaction_date=today - timedelta(days=off))
    bday = today + timedelta(days=5)
    SignificantEvent.objects.create(
        user=u, title="Heather's Birthday", event_type="birthday",
        event_date=datetime(1985, bday.month, bday.day).date(), person_name="Heather")
    # Cross-WLJ truth about Heather: a shared memory at a place (→ trips/shared places)
    # and a goal that mentions her (→ 'goals involving Heather', text-matched).
    from apps.legacy.models import Memory as LMemory, Person as LPerson, Place as LPlace
    lp = LPerson.objects.create(user=u, display_name="Heather Jones",
                                relationship_label="friend")
    place = LPlace.objects.create(user=u, name="Lake Tahoe")
    mem = LMemory.objects.create(user=u, title="Tahoe trip with Heather",
                                 entry_type="MEMORY", entry_state="legacy")
    mem.people.add(lp)
    mem.places.add(place)
    from apps.purpose.models import LifeGoal
    LifeGoal.objects.create(user=u, title="Plan the reunion", status="active",
                            why_it_matters="Reconnect with Heather and old friends.")
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
              "range_end": today, "event_name": "Dentist",
              "past_date": (today - timedelta(days=2)).isoformat()}


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
    harold = Person.objects.get(user=u, display_name="Harold Keck")
    m = Memory.objects.create(user=u, title="Summers at the farm",
                              entry_type="MEMORY", entry_state="legacy",
                              occurred_on=date(1930, 6, 1), occurred_precision="year")
    m.people.add(harold)
    m2 = Memory.objects.create(user=u, title="Learning to fish",
                               entry_type="MEMORY", entry_state="legacy",
                               occurred_on=date(1935, 7, 1), occurred_precision="year")
    m2.people.add(harold)
    Person.objects.create(user=u, display_name="Robert Keck",
                          relationship_label="father", significance=5)
    Person.objects.create(user=u, display_name="Mary Keck",
                          relationship_label="mother", significance=5)
    Memory.objects.create(user=u, title="Grandma's 90th birthday party",
                          entry_type="event", entry_state="legacy",
                          occurred_on=date(1988, 5, 1), significance=5)
    return u, {"person": "Harold Keck", "place": "Farmhouse", "involves": "Harold",
              "grandfather": "grandfather"}


def build_nutrition_scoped_fixture(email="cert_nut_scoped@example.com"):
    """Meals across this week for scoped retrieval — every-lunch/breakfast/dinner,
    fast-food occurrences (count), and a lasagna (last-eaten). Separate from the
    macro-average fixture so those exact averages are undisturbed."""
    from apps.health.models import FoodEntry
    u = _mk_user(email)
    today = get_user_today(u)
    B, L, D = (FoodEntry.MEAL_BREAKFAST, FoodEntry.MEAL_LUNCH, FoodEntry.MEAL_DINNER)
    # (name, meal, day-offset)
    rows = [
        ("Oatmeal", B, 0), ("Eggs", B, 2), ("Toast", B, 4),          # 3 breakfasts
        ("Caesar Salad", L, 1), ("Turkey Wrap", L, 3),                # 2 lunches
        ("Grilled Salmon", D, 0), ("Lasagna", D, 2),                  # dinners
        ("McDonald's Big Mac", L, 1), ("McDonald's Fries", L, 5),     # 2 fast food
    ]
    for name, meal, off in rows:
        FoodEntry.objects.create(
            user=u, food_name=name, quantity=Decimal("1"), serving_size=Decimal("1"),
            serving_unit="serving", meal_type=meal, logged_date=today - timedelta(days=off),
            logged_time=time(12, 0), status="active", total_calories=Decimal("400"))
    return u, {"week_start": today - timedelta(days=6), "week_end": today,
              "pizza_or_last": "Lasagna", "fast_food": "McDonald", "fast_food_count": 2}


def build_sleep_fixture(email="cert_sleep@example.com"):
    """Sleep nights with full stage/efficiency detail (previously unreachable)."""
    from apps.health.models import SleepEntry
    u = _mk_user(email)
    today = get_user_today(u)
    for off in (1, 2, 3):
        night = today - timedelta(days=off)
        bedtime = timezone.make_aware(datetime.combine(
            night - timedelta(days=1), time(22, 30)))
        wake = timezone.make_aware(datetime.combine(night, time(6, 30)))
        SleepEntry.objects.create(
            user=u, sleep_date=night, bedtime=bedtime, wake_time=wake,
            total_duration_minutes=480, asleep_duration_minutes=445,
            stage_deep_minutes=80, stage_rem_minutes=110, stage_light_minutes=255,
            stage_awake_minutes=35, sleep_efficiency=Decimal("92.7"),
            quality_rating="good")
    return u, {}


def build_projects_fixture(email="cert_proj@example.com"):
    """Active + completed projects (Project had no provider at all)."""
    from apps.life.models import Project
    u = _mk_user(email)
    today = get_user_today(u)
    Project.objects.create(user=u, title="Kitchen remodel", status="active",
                           priority="now", target_date=today + timedelta(days=60),
                           purpose="Modernize the kitchen.")
    Project.objects.create(user=u, title="Garden refresh", status="active",
                           priority="soon")
    Project.all_objects.create(user=u, title="Tax filing 2025", status="completed",
                               completed_date=today - timedelta(days=20))
    return u, {"project": "Kitchen"}


def build_meals_fixture_recipes(email="cert_meals@example.com"):
    """Recipes (Meal Intelligence had no provider — a whole domain unreachable)."""
    from apps.meals.models import Recipe
    u = _mk_user(email)
    Recipe.objects.create(user=u, title="Chicken Stir Fry",
                          ingredients="chicken breast\nbroccoli\nsoy sauce\nrice",
                          instructions="Stir fry it all.", servings=4,
                          category="dinner", difficulty="easy")
    Recipe.objects.create(user=u, title="Overnight Oats",
                          ingredients="oats\nmilk\nchia seeds\nberries",
                          instructions="Combine and refrigerate.", servings=1)
    return u, {"recipe": "Stir Fry"}


# The fixture registry — a QuestionSpec references a builder by key.
FIXTURES = {
    "weight": build_weight_fixture,
    "nutrition_scoped": build_nutrition_scoped_fixture,
    "sleep": build_sleep_fixture,
    "projects": build_projects_fixture,
    "meals": build_meals_fixture_recipes,
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
