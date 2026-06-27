"""
Health URLs - Physical and Cognitive wellness tracking.

URL Structure:
- /health/ - Landing page (Physical vs Cognitive)
- /health/physical/ - Physical health home and features
- /health/cognitive/ - Cognitive health (Brain Training, mounted in config/urls.py)
"""

from django.urls import path
from django.views.generic import RedirectView

from . import views
from . import views_acquisition
from . import views_body_composition
from . import views_cycle
from . import views_dashboards
from . import views_export
from . import views_insights
from . import views_sleep_api

app_name = "health"

# Legacy URL redirects (301 permanent) for backwards compatibility
# These redirect old /health/X/ URLs to new /health/physical/X/ URLs
legacy_redirects = [
    # Main features
    path("weight/", RedirectView.as_view(pattern_name="health:weight_list", permanent=True)),
    path("weight/<path:rest>", RedirectView.as_view(url="/health/physical/weight/%(rest)s", permanent=True)),
    path("fasting/", RedirectView.as_view(pattern_name="health:fasting_list", permanent=True)),
    path("fasting/<path:rest>", RedirectView.as_view(url="/health/physical/fasting/%(rest)s", permanent=True)),
    path("heart-rate/", RedirectView.as_view(pattern_name="health:heartrate_list", permanent=True)),
    path("heart-rate/<path:rest>", RedirectView.as_view(url="/health/physical/heart-rate/%(rest)s", permanent=True)),
    path("hrv/", RedirectView.as_view(url="/health/physical/hrv/dashboard/", permanent=True)),
    path("hrv/<path:rest>", RedirectView.as_view(url="/health/physical/hrv/%(rest)s", permanent=True)),
    path("vo2-max/", RedirectView.as_view(url="/health/physical/vo2-max/dashboard/", permanent=True)),
    path("vo2-max/<path:rest>", RedirectView.as_view(url="/health/physical/vo2-max/%(rest)s", permanent=True)),
    path("respiratory-rate/", RedirectView.as_view(url="/health/physical/respiratory-rate/dashboard/", permanent=True)),
    path("respiratory-rate/<path:rest>", RedirectView.as_view(url="/health/physical/respiratory-rate/%(rest)s", permanent=True)),
    path("body-temperature/", RedirectView.as_view(url="/health/physical/body-temperature/dashboard/", permanent=True)),
    path("body-temperature/<path:rest>", RedirectView.as_view(url="/health/physical/body-temperature/%(rest)s", permanent=True)),
    path("caffeine/", RedirectView.as_view(url="/health/physical/caffeine/dashboard/", permanent=True)),
    path("caffeine/<path:rest>", RedirectView.as_view(url="/health/physical/caffeine/%(rest)s", permanent=True)),
    path("mindful-minutes/", RedirectView.as_view(url="/health/physical/mindful-minutes/dashboard/", permanent=True)),
    path("mindful-minutes/<path:rest>", RedirectView.as_view(url="/health/physical/mindful-minutes/%(rest)s", permanent=True)),
    path("activity/", RedirectView.as_view(url="/health/physical/activity/dashboard/", permanent=True)),
    path("activity/<path:rest>", RedirectView.as_view(url="/health/physical/activity/%(rest)s", permanent=True)),
    path("steps/", RedirectView.as_view(pattern_name="health:steps_list", permanent=True)),
    path("steps/<path:rest>", RedirectView.as_view(url="/health/physical/steps/%(rest)s", permanent=True)),
    path("sleep/", RedirectView.as_view(pattern_name="health:sleep_list", permanent=True)),
    path("sleep/<path:rest>", RedirectView.as_view(url="/health/physical/sleep/%(rest)s", permanent=True)),
    path("water/", RedirectView.as_view(pattern_name="health:water_list", permanent=True)),
    path("water/<path:rest>", RedirectView.as_view(url="/health/physical/water/%(rest)s", permanent=True)),
    path("glucose/", RedirectView.as_view(pattern_name="health:glucose_dashboard", permanent=True)),
    path("glucose/<path:rest>", RedirectView.as_view(url="/health/physical/glucose/%(rest)s", permanent=True)),
    path("blood-pressure/", RedirectView.as_view(pattern_name="health:blood_pressure_list", permanent=True)),
    path("blood-pressure/<path:rest>", RedirectView.as_view(url="/health/physical/blood-pressure/%(rest)s", permanent=True)),
    path("blood-oxygen/", RedirectView.as_view(pattern_name="health:blood_oxygen_list", permanent=True)),
    path("blood-oxygen/<path:rest>", RedirectView.as_view(url="/health/physical/blood-oxygen/%(rest)s", permanent=True)),
    path("quick-log/", RedirectView.as_view(pattern_name="health:quick_log", permanent=True)),
    path("medicine/", RedirectView.as_view(pattern_name="health:intake_home", permanent=True)),
    path("medicine/<path:rest>", RedirectView.as_view(url="/health/physical/intake/%(rest)s", permanent=True)),
    path("fitness/", RedirectView.as_view(pattern_name="health:fitness_home", permanent=True)),
    path("fitness/<path:rest>", RedirectView.as_view(url="/health/physical/fitness/%(rest)s", permanent=True)),
    path("nutrition/", RedirectView.as_view(pattern_name="health:nutrition_home", permanent=True)),
    path("nutrition/<path:rest>", RedirectView.as_view(url="/health/physical/nutrition/%(rest)s", permanent=True)),
    path("providers/", RedirectView.as_view(pattern_name="health:provider_list", permanent=True)),
    path("providers/<path:rest>", RedirectView.as_view(url="/health/physical/providers/%(rest)s", permanent=True)),
    path("cycle/", RedirectView.as_view(pattern_name="health:cycle_dashboard", permanent=True)),
    path("cycle/<path:rest>", RedirectView.as_view(url="/health/physical/cycle/%(rest)s", permanent=True)),
    # API redirects
    path("api/sleep/", RedirectView.as_view(url="/health/physical/api/sleep/", permanent=True)),
    path("api/sleep/<path:rest>", RedirectView.as_view(url="/health/physical/api/sleep/%(rest)s", permanent=True)),
    path("api/cycle/", RedirectView.as_view(url="/health/physical/api/cycle/", permanent=True)),
    path("api/cycle/<path:rest>", RedirectView.as_view(url="/health/physical/api/cycle/%(rest)s", permanent=True)),
]

urlpatterns = [
    # Landing page at /health/
    path("", views.HealthLandingView.as_view(), name="landing"),

    # Health Intelligence (cross-cutting — not under physical/)
    path("intelligence/", views.HealthIntelligenceView.as_view(), name="health_intelligence"),
    path("intelligence/rebuild/", views.HealthRebuildView.as_view(), name="health_rebuild"),

    # Physical Health dashboard at /health/physical/
    path("physical/", views.HealthHomeView.as_view(), name="home"),

    # Weight
    path("physical/weight/", views.WeightListView.as_view(), name="weight_list"),
    path("physical/weight/log/", views.WeightCreateView.as_view(), name="weight_create"),
    path("physical/weight/<int:pk>/edit/", views.WeightUpdateView.as_view(), name="weight_update"),
    path("physical/weight/<int:pk>/delete/", views.WeightDeleteView.as_view(), name="weight_delete"),
    path("physical/weight/bulk/delete/", views.BulkDeleteWeightView.as_view(), name="weight_bulk_delete"),

    # Fasting
    path("physical/fasting/", views.FastingListView.as_view(), name="fasting_list"),
    path("physical/fasting/start/", views.StartFastView.as_view(), name="fasting_start"),
    path("physical/fasting/<int:pk>/end/", views.EndFastView.as_view(), name="fasting_end"),
    path("physical/fasting/<int:pk>/edit/", views.FastingUpdateView.as_view(), name="fasting_update"),
    path("physical/fasting/<int:pk>/delete/", views.FastingDeleteView.as_view(), name="fasting_delete"),
    path("physical/fasting/bulk/delete/", views.BulkDeleteFastingView.as_view(), name="fasting_bulk_delete"),

    # Heart Rate
    path("physical/heart-rate/", views.HeartRateListView.as_view(), name="heartrate_list"),
    path("physical/heart-rate/dashboard/", views_dashboards.HeartRateDashboardView.as_view(), name="heartrate_dashboard"),
    path("physical/heart-rate/log/", views.HeartRateCreateView.as_view(), name="heartrate_create"),
    path("physical/heart-rate/<int:pk>/edit/", views.HeartRateUpdateView.as_view(), name="heartrate_update"),
    path("physical/heart-rate/<int:pk>/delete/", views.HeartRateDeleteView.as_view(), name="heartrate_delete"),
    path("physical/heart-rate/bulk/delete/", views.BulkDeleteHeartRateView.as_view(), name="heartrate_bulk_delete"),

    # HRV Dashboard
    path("physical/hrv/dashboard/", views_dashboards.HRVDashboardView.as_view(), name="hrv_dashboard"),

    # VO2 Max Dashboard
    path("physical/vo2-max/dashboard/", views_dashboards.VO2MaxDashboardView.as_view(), name="vo2_max_dashboard"),

    # Respiratory Rate Dashboard
    path("physical/respiratory-rate/dashboard/", views_dashboards.RespiratoryRateDashboardView.as_view(), name="respiratory_rate_dashboard"),

    # Body Temperature Dashboard
    path("physical/body-temperature/dashboard/", views_dashboards.BodyTemperatureDashboardView.as_view(), name="body_temperature_dashboard"),

    # Caffeine Dashboard
    path("physical/caffeine/dashboard/", views_dashboards.CaffeineDashboardView.as_view(), name="caffeine_dashboard"),

    # Mindful Minutes Dashboard
    path("physical/mindful-minutes/dashboard/", views_dashboards.MindfulMinutesDashboardView.as_view(), name="mindful_minutes_dashboard"),

    # Activity Dashboard
    path("physical/activity/dashboard/", views_dashboards.ActivityDashboardView.as_view(), name="activity_dashboard"),

    # Steps
    path("physical/steps/", views.StepsListView.as_view(), name="steps_list"),
    path("physical/steps/log/", views.StepsCreateView.as_view(), name="steps_create"),
    path("physical/steps/<int:pk>/edit/", views.StepsUpdateView.as_view(), name="steps_update"),
    path("physical/steps/<int:pk>/delete/", views.StepsDeleteView.as_view(), name="steps_delete"),
    path("physical/steps/bulk/delete/", views.BulkDeleteStepsView.as_view(), name="steps_bulk_delete"),

    # Sleep
    path("physical/sleep/", views.SleepListView.as_view(), name="sleep_list"),
    path("physical/sleep/log/", views.SleepCreateView.as_view(), name="sleep_create"),
    path("physical/sleep/quick/", views.SleepQuickCreateView.as_view(), name="sleep_quick"),
    path("physical/sleep/<int:pk>/edit/", views.SleepUpdateView.as_view(), name="sleep_update"),
    path("physical/sleep/<int:pk>/delete/", views.SleepDeleteView.as_view(), name="sleep_delete"),
    path("physical/sleep/bulk/delete/", views.BulkDeleteSleepView.as_view(), name="sleep_bulk_delete"),

    # Sleep API
    path("physical/api/sleep/", views_sleep_api.SleepEntryListCreateView.as_view(), name="sleep_api_list"),
    path("physical/api/sleep/<int:entry_id>/", views_sleep_api.SleepEntryDetailView.as_view(), name="sleep_api_detail"),
    path("physical/api/sleep/stats/", views_sleep_api.SleepStatsView.as_view(), name="sleep_api_stats"),
    path("physical/api/sleep/sync-status/", views_sleep_api.SleepSyncStatusView.as_view(), name="sleep_api_sync_status"),

    # Water / Hydration
    path("physical/water/", views.WaterListView.as_view(), name="water_list"),
    path("physical/water/log/", views.WaterCreateView.as_view(), name="water_create"),
    path("physical/water/<int:pk>/edit/", views.WaterUpdateView.as_view(), name="water_update"),
    path("physical/water/<int:pk>/delete/", views.WaterDeleteView.as_view(), name="water_delete"),
    path("physical/water/quick/", views.QuickWaterLogView.as_view(), name="water_quick_log"),

    # Glucose
    path("physical/glucose/", views.GlucoseDashboardView.as_view(), name="glucose_dashboard"),
    path("physical/glucose/list/", views.GlucoseListView.as_view(), name="glucose_list"),
    path("physical/glucose/log/", views.GlucoseCreateView.as_view(), name="glucose_create"),
    path("physical/glucose/<int:pk>/edit/", views.GlucoseUpdateView.as_view(), name="glucose_update"),
    path("physical/glucose/<int:pk>/delete/", views.GlucoseDeleteView.as_view(), name="glucose_delete"),
    path("physical/glucose/bulk/delete/", views.BulkDeleteGlucoseView.as_view(), name="glucose_bulk_delete"),

    # Dexcom CGM Integration
    path("physical/glucose/dexcom/connect/", views.DexcomConnectView.as_view(), name="dexcom_connect"),
    path("physical/glucose/dexcom/callback/", views.DexcomCallbackView.as_view(), name="dexcom_callback"),
    path("physical/glucose/dexcom/sync/", views.DexcomSyncView.as_view(), name="dexcom_sync"),
    path("physical/glucose/dexcom/disconnect/", views.DexcomDisconnectView.as_view(), name="dexcom_disconnect"),

    # Blood Pressure
    path("physical/blood-pressure/", views.BloodPressureListView.as_view(), name="blood_pressure_list"),
    path("physical/blood-pressure/dashboard/", views_dashboards.BloodPressureDashboardView.as_view(), name="blood_pressure_dashboard"),
    path("physical/blood-pressure/log/", views.BloodPressureCreateView.as_view(), name="blood_pressure_create"),
    path("physical/blood-pressure/<int:pk>/edit/", views.BloodPressureUpdateView.as_view(), name="blood_pressure_update"),
    path("physical/blood-pressure/<int:pk>/delete/", views.BloodPressureDeleteView.as_view(), name="blood_pressure_delete"),
    path("physical/blood-pressure/bulk/delete/", views.BulkDeleteBloodPressureView.as_view(), name="blood_pressure_bulk_delete"),

    # Blood Oxygen
    path("physical/blood-oxygen/", views.BloodOxygenListView.as_view(), name="blood_oxygen_list"),
    path("physical/blood-oxygen/dashboard/", views_dashboards.BloodOxygenDashboardView.as_view(), name="blood_oxygen_dashboard"),
    path("physical/blood-oxygen/log/", views.BloodOxygenCreateView.as_view(), name="blood_oxygen_create"),
    path("physical/blood-oxygen/<int:pk>/edit/", views.BloodOxygenUpdateView.as_view(), name="blood_oxygen_update"),
    path("physical/blood-oxygen/<int:pk>/delete/", views.BloodOxygenDeleteView.as_view(), name="blood_oxygen_delete"),
    path("physical/blood-oxygen/bulk/delete/", views.BulkDeleteBloodOxygenView.as_view(), name="blood_oxygen_bulk_delete"),

    # Quick log (HTMX)
    path("physical/quick-log/", views.QuickLogView.as_view(), name="quick_log"),

    # Intake (medications + supplements)
    path("physical/intake/", views.IntakeHomeView.as_view(), name="intake_home"),
    path("physical/intake/list/", views.IntakeListView.as_view(), name="intake_list"),
    path("physical/intake/add/", views.IntakeCreateView.as_view(), name="intake_create"),
    # Medication Acquisition (Sprint 3J) — Acquire → Review → Confirm
    path("physical/intake/acquire/", views_acquisition.MedicationAcquireView.as_view(), name="medication_acquire"),
    path("physical/intake/acquire/<int:draft_id>/review/", views_acquisition.MedicationReviewView.as_view(), name="medication_review"),
    path("physical/intake/acquire/<int:draft_id>/confirm/", views_acquisition.MedicationConfirmView.as_view(), name="medication_confirm"),
    # Treatment Timeline (Sprint 4D) — chronological, deterministic, evidence-first
    path("physical/intake/timeline/", views_acquisition.MedicationTimelineView.as_view(), name="medication_timeline"),
    # What We've Noticed (Sprint 7G) — deterministic narration surface
    path("physical/intake/noticed/", views_acquisition.MedicationNoticedView.as_view(), name="medication_noticed"),
    path("physical/intake/<int:pk>/", views.IntakeDetailView.as_view(), name="intake_detail"),
    path("physical/intake/<int:pk>/edit/", views.IntakeUpdateView.as_view(), name="intake_update"),
    path("physical/intake/<int:pk>/delete/", views.IntakeDeleteView.as_view(), name="intake_delete"),
    path("physical/intake/<int:pk>/pause/", views.IntakePauseView.as_view(), name="intake_pause"),
    path("physical/intake/<int:pk>/resume/", views.IntakeResumeView.as_view(), name="intake_resume"),
    path("physical/intake/<int:pk>/complete/", views.IntakeCompleteView.as_view(), name="intake_complete"),
    path("physical/intake/<int:pk>/schedules/", views.IntakeSchedulesView.as_view(), name="intake_schedules"),
    path("physical/intake/<int:medicine_pk>/schedules/<int:schedule_pk>/delete/", views.IntakeScheduleDeleteView.as_view(), name="intake_schedule_delete"),
    path("physical/intake/<int:medicine_pk>/schedules/<int:schedule_pk>/activate/", views.IntakeScheduleActivateView.as_view(), name="intake_schedule_activate"),
    path("physical/intake/<int:pk>/supply/", views.IntakeUpdateSupplyView.as_view(), name="intake_update_supply"),
    path("physical/intake/<int:pk>/take/<int:schedule_pk>/", views.IntakeTakeView.as_view(), name="intake_take"),
    path("physical/intake/<int:pk>/skip/<int:schedule_pk>/", views.IntakeSkipView.as_view(), name="intake_skip"),
    path("physical/intake/<int:pk>/undo/<int:schedule_pk>/", views.IntakeUndoView.as_view(), name="intake_undo"),
    path("physical/intake/bulk-take/<str:time_of_day>/", views.IntakeBulkTakeView.as_view(), name="intake_bulk_take"),
    path("physical/intake/bulk-skip/<str:time_of_day>/", views.IntakeBulkSkipView.as_view(), name="intake_bulk_skip"),
    path("physical/intake/prn/", views.PRNLogView.as_view(), name="intake_prn_log"),
    path("physical/intake/history/", views.IntakeHistoryView.as_view(), name="intake_history"),
    path("physical/intake/<int:pk>/history-take/<int:schedule_pk>/", views.IntakeHistoryTakeView.as_view(), name="intake_history_take"),
    path("physical/intake/<int:pk>/history-skip/<int:schedule_pk>/", views.IntakeHistorySkipView.as_view(), name="intake_history_skip"),
    path("physical/intake/log/<int:pk>/edit/", views.IntakeLogEditView.as_view(), name="intake_log_edit"),
    path("physical/intake/adherence/", views.IntakeAdherenceView.as_view(), name="intake_adherence"),
    path("physical/intake/quick-look/", views.IntakeQuickLookView.as_view(), name="intake_quick_look"),
    path("physical/intake/<int:pk>/request-refill/", views.IntakeRequestRefillView.as_view(), name="intake_request_refill"),
    path("physical/intake/<int:pk>/clear-refill/", views.IntakeClearRefillView.as_view(), name="intake_clear_refill"),

    # Legacy medicine URL redirects (temporary, non-permanent)
    path("physical/medicine/<path:rest>", RedirectView.as_view(url="/health/physical/intake/%(rest)s", permanent=False)),

    # Fitness
    path("physical/fitness/", views.FitnessHomeView.as_view(), name="fitness_home"),
    path("physical/fitness/workouts/", views.WorkoutListView.as_view(), name="workout_list"),
    path("physical/fitness/workout/new/", views.WorkoutCreateView.as_view(), name="workout_create"),
    path("physical/fitness/workout/<int:pk>/", views.WorkoutDetailView.as_view(), name="workout_detail"),
    path("physical/fitness/workout/<int:pk>/edit/", views.WorkoutUpdateView.as_view(), name="workout_update"),
    path("physical/fitness/workout/<int:pk>/delete/", views.WorkoutDeleteView.as_view(), name="workout_delete"),
    path("physical/fitness/workout/<int:pk>/copy/", views.WorkoutCopyView.as_view(), name="workout_copy"),

    # Workout Templates
    path("physical/fitness/templates/", views.TemplateListView.as_view(), name="template_list"),
    path("physical/fitness/templates/new/", views.TemplateCreateView.as_view(), name="template_create"),
    path("physical/fitness/templates/<int:pk>/", views.TemplateDetailView.as_view(), name="template_detail"),
    path("physical/fitness/templates/<int:pk>/edit/", views.TemplateUpdateView.as_view(), name="template_update"),
    path("physical/fitness/templates/<int:pk>/delete/", views.TemplateDeleteView.as_view(), name="template_delete"),
    path("physical/fitness/templates/<int:pk>/use/", views.UseTemplateView.as_view(), name="template_use"),

    # Personal Records & Progress
    path("physical/fitness/prs/", views.PersonalRecordsView.as_view(), name="personal_records"),
    path("physical/fitness/pr/new/", views.PersonalRecordCreateView.as_view(), name="pr_create"),
    path("physical/fitness/pr/<int:pk>/edit/", views.PersonalRecordUpdateView.as_view(), name="pr_edit"),
    path("physical/fitness/pr/<int:pk>/delete/", views.PersonalRecordDeleteView.as_view(), name="pr_delete"),
    path("physical/fitness/progress/", views.ProgressView.as_view(), name="fitness_progress"),

    # Export
    path("physical/fitness/export/dashboard/", views_export.WorkoutDashboardExcelView.as_view(), name="workout_dashboard_export"),

    # HTMX Endpoints
    path("physical/fitness/exercises/", views.exercise_list_json, name="exercise_list_json"),
    path("physical/fitness/add-exercise/", views.add_exercise_htmx, name="add_exercise_htmx"),
    path("physical/fitness/add-set/<int:exercise_id>/", views.add_set_htmx, name="add_set_htmx"),

    # Template Preview API
    path("physical/fitness/api/template-preview/<int:template_id>/", views.template_preview_json, name="template_preview_json"),

    # Live Workout AJAX Endpoints
    path("physical/fitness/api/start-workout/", views.start_workout_ajax, name="start_workout_ajax"),
    path("physical/fitness/api/save-set/", views.save_set_ajax, name="save_set_ajax"),
    path("physical/fitness/api/save-cardio/", views.save_cardio_ajax, name="save_cardio_ajax"),
    path("physical/fitness/api/save-class/", views.save_class_ajax, name="save_class_ajax"),
    path("physical/fitness/api/complete-workout/", views.complete_workout_ajax, name="complete_workout_ajax"),
    path("physical/fitness/api/log-activity/", views.log_activity_ajax, name="log_activity_ajax"),
    path("physical/fitness/api/workout-state/<int:workout_id>/", views.get_workout_state_ajax, name="get_workout_state_ajax"),

    # Nutrition / Food Tracking
    path("physical/nutrition/", views.NutritionHomeView.as_view(), name="nutrition_home"),
    path("physical/nutrition/add/", views.FoodEntryCreateView.as_view(), name="food_entry_create"),
    path("physical/nutrition/quick-add/", views.QuickAddFoodView.as_view(), name="food_quick_add"),
    path("physical/nutrition/entry/<int:pk>/", views.FoodEntryDetailView.as_view(), name="food_entry_detail"),
    path("physical/nutrition/entry/<int:pk>/edit/", views.FoodEntryUpdateView.as_view(), name="food_entry_edit"),
    path("physical/nutrition/entry/<int:pk>/delete/", views.FoodEntryDeleteView.as_view(), name="food_entry_delete"),
    path("physical/nutrition/history/", views.FoodHistoryView.as_view(), name="food_history"),
    path("physical/nutrition/stats/", views.NutritionStatsView.as_view(), name="nutrition_stats"),
    path("physical/nutrition/goals/", views.NutritionGoalsView.as_view(), name="nutrition_goals"),
    path("physical/nutrition/foods/", views.CustomFoodListView.as_view(), name="custom_food_list"),
    path("physical/nutrition/foods/add/", views.CustomFoodCreateView.as_view(), name="custom_food_create"),
    path("physical/nutrition/foods/<int:pk>/edit/", views.CustomFoodUpdateView.as_view(), name="custom_food_edit"),
    path("physical/nutrition/foods/<int:pk>/delete/", views.CustomFoodDeleteView.as_view(), name="custom_food_delete"),

    # Nutrition API
    path("physical/nutrition/api/search/", views.FoodSearchAPIView.as_view(), name="food_search_api"),
    path("physical/nutrition/api/copy-entry/", views.CopyEntryAPIView.as_view(), name="copy_entry_api"),
    path("physical/nutrition/api/copy-meal/", views.CopyMealAPIView.as_view(), name="copy_meal_api"),
    path("physical/nutrition/api/copy-day/", views.CopyDayAPIView.as_view(), name="copy_day_api"),

    # Meal Templates
    path("physical/nutrition/templates/", views.MealTemplateListView.as_view(), name="meal_template_list"),
    path("physical/nutrition/templates/create/", views.MealTemplateCreateView.as_view(), name="meal_template_create"),
    path("physical/nutrition/templates/<int:pk>/edit/", views.MealTemplateEditView.as_view(), name="meal_template_edit"),
    path("physical/nutrition/templates/<int:pk>/delete/", views.MealTemplateDeleteView.as_view(), name="meal_template_delete"),
    path("physical/nutrition/api/templates/<int:pk>/apply/", views.MealTemplateApplyAPIView.as_view(), name="meal_template_apply_api"),
    path("physical/nutrition/api/save-meal-template/", views.SaveMealAsTemplateAPIView.as_view(), name="save_meal_template_api"),

    # Medical Providers
    path("physical/providers/", views.MedicalProviderListView.as_view(), name="provider_list"),
    path("physical/providers/add/", views.MedicalProviderCreateView.as_view(), name="provider_create"),
    path("physical/providers/<int:pk>/", views.MedicalProviderDetailView.as_view(), name="provider_detail"),
    path("physical/providers/<int:pk>/edit/", views.MedicalProviderUpdateView.as_view(), name="provider_update"),
    path("physical/providers/<int:pk>/delete/", views.MedicalProviderDeleteView.as_view(), name="provider_delete"),
    path("physical/providers/ai-lookup/", views.ProviderAILookupView.as_view(), name="provider_ai_lookup"),

    # Provider Staff
    path("physical/providers/<int:provider_pk>/staff/add/", views.ProviderStaffCreateView.as_view(), name="staff_create"),
    path("physical/providers/staff/<int:pk>/edit/", views.ProviderStaffUpdateView.as_view(), name="staff_update"),
    path("physical/providers/staff/<int:pk>/delete/", views.ProviderStaffDeleteView.as_view(), name="staff_delete"),

    # Cycle Tracking Pages
    path("physical/cycle/", views_cycle.CycleDashboardView.as_view(), name="cycle_dashboard"),
    path("physical/cycle/calendar/", views_cycle.CycleCalendarView.as_view(), name="cycle_calendar"),
    path("physical/cycle/settings/", views_cycle.CycleSettingsPageView.as_view(), name="cycle_settings_page"),
    path("physical/cycle/opt-in/", views_cycle.CycleOptInPageView.as_view(), name="cycle_opt_in_page"),

    # Cycle Tracking API
    path("physical/cycle/api/settings/", views_cycle.CycleSettingsViewSet.as_view(), name="cycle_settings_api"),
    path("physical/cycle/api/opt-in/", views_cycle.CycleOptInView.as_view(), name="cycle_opt_in"),
    path("physical/cycle/api/opt-out/", views_cycle.CycleOptOutView.as_view(), name="cycle_opt_out"),
    path("physical/cycle/api/check/", views_cycle.CycleSettingsCheckView.as_view(), name="cycle_check"),
    path("physical/cycle/api/period-toggle/", views_cycle.CyclePeriodToggleView.as_view(), name="cycle_period_toggle"),
    path("physical/cycle/api/day-modal/", views_cycle.CycleDayModalView.as_view(), name="cycle_day_modal"),
    path("physical/cycle/api/daily-logs/", views_cycle.CycleDailyLogViewSet.as_view(), name="cycle_daily_logs_list"),
    path("physical/cycle/api/daily-logs/<int:log_id>/", views_cycle.CycleDailyLogViewSet.as_view(), name="cycle_daily_logs_detail"),
    path("physical/cycle/api/cycles/", views_cycle.CycleViewSet.as_view(), name="cycle_cycles_list"),
    path("physical/cycle/api/cycles/current/", views_cycle.CycleViewSet.as_view(), {"action": "current"}, name="cycle_cycles_current"),
    path("physical/cycle/api/cycles/statistics/", views_cycle.CycleViewSet.as_view(), {"action": "statistics"}, name="cycle_cycles_statistics"),
    path("physical/cycle/api/cycles/<int:cycle_id>/", views_cycle.CycleViewSet.as_view(), name="cycle_cycles_detail"),
    path("physical/cycle/api/predictions/", views_cycle.CyclePredictionViewSet.as_view(), name="cycle_predictions_list"),
    path("physical/cycle/api/predictions/current/", views_cycle.CyclePredictionViewSet.as_view(), {"action": "current"}, name="cycle_predictions_current"),
    path("physical/cycle/api/predictions/regenerate/", views_cycle.CyclePredictionViewSet.as_view(), {"action": "regenerate"}, name="cycle_predictions_regenerate"),
    path("physical/cycle/api/predictions/<int:prediction_id>/", views_cycle.CyclePredictionViewSet.as_view(), name="cycle_predictions_detail"),
    path("physical/cycle/data/", views_cycle.CycleDataManagementView.as_view(), name="cycle_data_management"),
    path("physical/cycle/data/export/json/", views_cycle.CycleExportJSONView.as_view(), name="cycle_export_json"),
    path("physical/cycle/data/export/csv/", views_cycle.CycleExportCSVView.as_view(), name="cycle_export_csv"),
    path("physical/cycle/data/delete-all/", views_cycle.CycleDeleteAllView.as_view(), name="cycle_delete_all"),
    path("physical/api/cycle/export/", views_cycle.CycleExportAPIView.as_view(), name="cycle_export_api"),
    path("physical/api/cycle/delete-all/", views_cycle.CycleDeleteAllAPIView.as_view(), name="cycle_delete_all_api"),

    # Body Composition
    path("physical/body-composition/", views_body_composition.BodyCompositionListView.as_view(), name="body_composition_list"),
    path("physical/body-composition/log/", views_body_composition.BodyCompositionCreateView.as_view(), name="body_composition_create"),
    path("physical/body-composition/export/", views_body_composition.BodyCompositionExportView.as_view(), name="body_composition_export"),
    path("physical/body-composition/<int:pk>/edit/", views_body_composition.BodyCompositionUpdateView.as_view(), name="body_composition_update"),
    path("physical/body-composition/<int:pk>/delete/", views_body_composition.BodyCompositionDeleteView.as_view(), name="body_composition_delete"),

    # Health Profile
    path("physical/profile/", views_body_composition.HealthProfileView.as_view(), name="health_profile"),

    # Insights
    path("physical/insights/", views_insights.InsightListView.as_view(), name="insights_list"),
    path("physical/insights/refresh/", views_insights.InsightRefreshView.as_view(), name="insights_refresh"),
    path("physical/insights/<int:pk>/dismiss/", views_insights.InsightDismissView.as_view(), name="insights_dismiss"),

] + legacy_redirects
