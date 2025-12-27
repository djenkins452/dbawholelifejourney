"""
Health URLs - Physical wellness tracking.
"""

from django.urls import path

from . import views

app_name = "health"

urlpatterns = [
    # Health dashboard
    path("", views.HealthHomeView.as_view(), name="home"),

    # Weight
    path("weight/", views.WeightListView.as_view(), name="weight_list"),
    path("weight/log/", views.WeightCreateView.as_view(), name="weight_create"),
    path("weight/<int:pk>/edit/", views.WeightUpdateView.as_view(), name="weight_update"),
    path("weight/<int:pk>/delete/", views.WeightDeleteView.as_view(), name="weight_delete"),

    # Fasting
    path("fasting/", views.FastingListView.as_view(), name="fasting_list"),
    path("fasting/start/", views.StartFastView.as_view(), name="fasting_start"),
    path("fasting/<int:pk>/end/", views.EndFastView.as_view(), name="fasting_end"),
    path("fasting/<int:pk>/edit/", views.FastingUpdateView.as_view(), name="fasting_update"),
    path("fasting/<int:pk>/delete/", views.FastingDeleteView.as_view(), name="fasting_delete"),

    # Heart Rate
    path("heart-rate/", views.HeartRateListView.as_view(), name="heartrate_list"),
    path("heart-rate/log/", views.HeartRateCreateView.as_view(), name="heartrate_create"),
    path("heart-rate/<int:pk>/edit/", views.HeartRateUpdateView.as_view(), name="heartrate_update"),
    path("heart-rate/<int:pk>/delete/", views.HeartRateDeleteView.as_view(), name="heartrate_delete"),

    # Glucose
    path("glucose/", views.GlucoseListView.as_view(), name="glucose_list"),
    path("glucose/log/", views.GlucoseCreateView.as_view(), name="glucose_create"),
    path("glucose/<int:pk>/edit/", views.GlucoseUpdateView.as_view(), name="glucose_update"),
    path("glucose/<int:pk>/delete/", views.GlucoseDeleteView.as_view(), name="glucose_delete"),

    # Quick log (HTMX)
    path("quick-log/", views.QuickLogView.as_view(), name="quick_log"),

    # Fitness
    path("fitness/", views.FitnessHomeView.as_view(), name="fitness_home"),
    path("fitness/workouts/", views.WorkoutListView.as_view(), name="workout_list"),
    path("fitness/workout/new/", views.WorkoutCreateView.as_view(), name="workout_create"),
    path("fitness/workout/<int:pk>/", views.WorkoutDetailView.as_view(), name="workout_detail"),
    path("fitness/workout/<int:pk>/edit/", views.WorkoutUpdateView.as_view(), name="workout_update"),
    path("fitness/workout/<int:pk>/delete/", views.WorkoutDeleteView.as_view(), name="workout_delete"),
    path("fitness/workout/<int:pk>/copy/", views.WorkoutCopyView.as_view(), name="workout_copy"),

    # Workout Templates
    path("fitness/templates/", views.TemplateListView.as_view(), name="template_list"),
    path("fitness/templates/new/", views.TemplateCreateView.as_view(), name="template_create"),
    path("fitness/templates/<int:pk>/", views.TemplateDetailView.as_view(), name="template_detail"),
    path("fitness/templates/<int:pk>/edit/", views.TemplateUpdateView.as_view(), name="template_update"),
    path("fitness/templates/<int:pk>/delete/", views.TemplateDeleteView.as_view(), name="template_delete"),
    path("fitness/templates/<int:pk>/use/", views.UseTemplateView.as_view(), name="template_use"),

    # Personal Records & Progress
    path("fitness/prs/", views.PersonalRecordsView.as_view(), name="personal_records"),
    path("fitness/progress/", views.ProgressView.as_view(), name="fitness_progress"),

    # HTMX Endpoints
    path("fitness/exercises/", views.exercise_list_json, name="exercise_list_json"),
    path("fitness/add-exercise/", views.add_exercise_htmx, name="add_exercise_htmx"),
    path("fitness/add-set/<int:exercise_id>/", views.add_set_htmx, name="add_set_htmx"),
]
