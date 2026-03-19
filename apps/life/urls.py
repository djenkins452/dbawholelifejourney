"""
Life Module URLs - Complete
"""

from django.urls import path

from .views import (
    # Home
    LifeHomeView,
    # Projects
    ProjectListView,
    ProjectDetailView,
    ProjectCreateView,
    ProjectUpdateView,
    ProjectDeleteView,
    # Tasks
    TaskListView,
    TaskCreateView,
    TaskUpdateView,
    TaskDeleteView,
    TaskToggleView,
    TaskSkipView,
    # Routines
    RoutineListView,
    RoutineCreateView,
    RoutineUpdateView,
    RoutineDeleteView,
    RoutineToggleView,
    RoutineSkipView,
    RoutineCompleteToggleView,
    RoutineMigrationView,
    # Calendar & Events
    CalendarView,
    EventCreateView,
    EventUpdateView,
    EventDeleteView,
    # Inventory
    InventoryListView,
    InventoryDetailView,
    InventoryCreateView,
    InventoryUpdateView,
    InventoryDeleteView,
    # Inventory Photos
    InventoryPhotoCreateView,
    InventoryPhotoDeleteView,
    InventoryPhotoSetPrimaryView,
    # Pets
    PetListView,
    PetDetailView,
    PetCreateView,
    PetUpdateView,
    PetDeleteView,
    # Pet Records
    PetRecordCreateView,
    PetRecordUpdateView,
    PetRecordDeleteView,
    # Recipes
    RecipeListView,
    RecipeDetailView,
    RecipeCreateView,
    RecipeUpdateView,
    RecipeDeleteView,
    RecipeToggleFavoriteView,
    RecipeScanView,
    RecipeScanProcessView,
    RecipeScanConfirmView,
    RecipeBulkUploadView,
    RecipeBulkUploadProcessView,
    RecipeBulkReviewView,
    RecipeBulkProcessOneView,
    RecipeBulkStatusView,
    RecipeBulkConfirmView,
    RecipeBulkConfirmAllView,
    # Maintenance Logs
    MaintenanceLogListView,
    MaintenanceLogDetailView,
    MaintenanceLogCreateView,
    MaintenanceLogUpdateView,
    MaintenanceLogDeleteView,
    # Documents
    DocumentListView,
    DocumentDetailView,
    DocumentCreateView,
    DocumentUpdateView,
    DocumentDeleteView,
    DocumentDownloadView,
    DocumentViewInlineView,
    # Significant Events
    SignificantEventListView,
    SignificantEventDetailView,
    SignificantEventCreateView,
    SignificantEventUpdateView,
    SignificantEventDeleteView,
    # Google Calendar
    GoogleCalendarSettingsView,
    GoogleCalendarSaveSettingsView,
    GoogleCalendarConnectView,
    GoogleCalendarCallbackView,
    GoogleCalendarDisconnectView,
    GoogleCalendarSyncView,
    GoogleCalendarPushEventView,
    # Gmail Integration
    GmailSettingsView,
    GmailConnectView,
    GmailCallbackView,
    GmailDisconnectView,
    GmailSaveSettingsView,
    GmailManualScanView,
    GmailSyncCronView,
    # Bulk Actions
    BulkDeleteTasksView,
    BulkDeleteInventoryView,
    BulkDeleteDocumentsView,
    BulkDeleteRecipesView,
    BulkDeleteMaintenanceView,
    BulkDeleteSignificantEventsView,
)

app_name = "life"

urlpatterns = [
    # Home
    path("", LifeHomeView.as_view(), name="home"),
    
    # Projects
    path("projects/", ProjectListView.as_view(), name="project_list"),
    path("projects/new/", ProjectCreateView.as_view(), name="project_create"),
    path("projects/<int:pk>/", ProjectDetailView.as_view(), name="project_detail"),
    path("projects/<int:pk>/edit/", ProjectUpdateView.as_view(), name="project_update"),
    path("projects/<int:pk>/delete/", ProjectDeleteView.as_view(), name="project_delete"),
    
    # Tasks
    path("tasks/", TaskListView.as_view(), name="task_list"),
    path("tasks/new/", TaskCreateView.as_view(), name="task_create"),
    path("tasks/<int:pk>/edit/", TaskUpdateView.as_view(), name="task_update"),
    path("tasks/<int:pk>/delete/", TaskDeleteView.as_view(), name="task_delete"),
    path("tasks/<int:pk>/toggle/", TaskToggleView.as_view(), name="task_toggle"),
    path("tasks/<int:pk>/skip/", TaskSkipView.as_view(), name="task_skip"),
    path("tasks/bulk/delete/", BulkDeleteTasksView.as_view(), name="task_bulk_delete"),

    # Routines
    path("routines/", RoutineListView.as_view(), name="routine_list"),
    path("routines/new/", RoutineCreateView.as_view(), name="routine_create"),
    path("routines/<int:pk>/edit/", RoutineUpdateView.as_view(), name="routine_update"),
    path("routines/<int:pk>/delete/", RoutineDeleteView.as_view(), name="routine_delete"),
    path("routines/toggle/", RoutineToggleView.as_view(), name="routine_toggle"),
    path("routines/skip/", RoutineSkipView.as_view(), name="routine_skip"),
    path("routines/<int:routine_id>/toggle-complete/", RoutineCompleteToggleView.as_view(), name="routine_complete_toggle"),
    path("routines/migrate/", RoutineMigrationView.as_view(), name="routine_migration"),

    # Calendar & Events
    path("calendar/", CalendarView.as_view(), name="calendar"),
    path("events/new/", EventCreateView.as_view(), name="event_create"),
    path("events/<int:pk>/edit/", EventUpdateView.as_view(), name="event_update"),
    path("events/<int:pk>/delete/", EventDeleteView.as_view(), name="event_delete"),
    
    # Inventory
    path("inventory/", InventoryListView.as_view(), name="inventory_list"),
    path("inventory/new/", InventoryCreateView.as_view(), name="inventory_create"),
    path("inventory/<int:pk>/", InventoryDetailView.as_view(), name="inventory_detail"),
    path("inventory/<int:pk>/edit/", InventoryUpdateView.as_view(), name="inventory_update"),
    path("inventory/<int:pk>/delete/", InventoryDeleteView.as_view(), name="inventory_delete"),
    path("inventory/bulk/delete/", BulkDeleteInventoryView.as_view(), name="inventory_bulk_delete"),
    
    # Inventory Photos
    path("inventory/<int:item_pk>/photos/new/", InventoryPhotoCreateView.as_view(), name="inventory_photo_create"),
    path("inventory/photos/<int:pk>/delete/", InventoryPhotoDeleteView.as_view(), name="inventory_photo_delete"),
    path("inventory/photos/<int:pk>/set-primary/", InventoryPhotoSetPrimaryView.as_view(), name="inventory_photo_set_primary"),
    
    # Pets
    path("pets/", PetListView.as_view(), name="pet_list"),
    path("pets/new/", PetCreateView.as_view(), name="pet_create"),
    path("pets/<int:pk>/", PetDetailView.as_view(), name="pet_detail"),
    path("pets/<int:pk>/edit/", PetUpdateView.as_view(), name="pet_update"),
    path("pets/<int:pk>/delete/", PetDeleteView.as_view(), name="pet_delete"),

    # Pet Records
    path("pets/<int:pet_pk>/records/new/", PetRecordCreateView.as_view(), name="pet_record_create"),
    path("pets/records/<int:pk>/edit/", PetRecordUpdateView.as_view(), name="pet_record_update"),
    path("pets/records/<int:pk>/delete/", PetRecordDeleteView.as_view(), name="pet_record_delete"),
    
    # Recipes
    path("recipes/", RecipeListView.as_view(), name="recipe_list"),
    path("recipes/new/", RecipeCreateView.as_view(), name="recipe_create"),
    path("recipes/scan/", RecipeScanView.as_view(), name="recipe_scan"),
    path("recipes/scan/process/", RecipeScanProcessView.as_view(), name="recipe_scan_process"),
    path("recipes/scan/confirm/", RecipeScanConfirmView.as_view(), name="recipe_scan_confirm"),
    path("recipes/bulk/", RecipeBulkUploadView.as_view(), name="recipe_bulk_upload"),
    path("recipes/bulk/process/", RecipeBulkUploadProcessView.as_view(), name="recipe_bulk_upload_process"),
    path("recipes/bulk/<int:session_id>/", RecipeBulkReviewView.as_view(), name="recipe_bulk_review"),
    path("recipes/bulk/<int:session_id>/process/<int:photo_id>/", RecipeBulkProcessOneView.as_view(), name="recipe_bulk_process_one"),
    path("recipes/bulk/<int:session_id>/status/", RecipeBulkStatusView.as_view(), name="recipe_bulk_status"),
    path("recipes/bulk/<int:session_id>/confirm/", RecipeBulkConfirmView.as_view(), name="recipe_bulk_confirm"),
    path("recipes/bulk/<int:session_id>/confirm-all/", RecipeBulkConfirmAllView.as_view(), name="recipe_bulk_confirm_all"),
    path("recipes/<int:pk>/", RecipeDetailView.as_view(), name="recipe_detail"),
    path("recipes/<int:pk>/edit/", RecipeUpdateView.as_view(), name="recipe_update"),
    path("recipes/<int:pk>/delete/", RecipeDeleteView.as_view(), name="recipe_delete"),
    path("recipes/<int:pk>/favorite/", RecipeToggleFavoriteView.as_view(), name="recipe_toggle_favorite"),
    path("recipes/bulk/delete/", BulkDeleteRecipesView.as_view(), name="recipe_bulk_delete"),
    
    # Maintenance Logs
    path("maintenance/", MaintenanceLogListView.as_view(), name="maintenance_list"),
    path("maintenance/new/", MaintenanceLogCreateView.as_view(), name="maintenance_create"),
    path("maintenance/<int:pk>/", MaintenanceLogDetailView.as_view(), name="maintenance_detail"),
    path("maintenance/<int:pk>/edit/", MaintenanceLogUpdateView.as_view(), name="maintenance_update"),
    path("maintenance/<int:pk>/delete/", MaintenanceLogDeleteView.as_view(), name="maintenance_delete"),
    path("maintenance/bulk/delete/", BulkDeleteMaintenanceView.as_view(), name="maintenance_bulk_delete"),
    
    # Documents
    path("documents/", DocumentListView.as_view(), name="document_list"),
    path("documents/new/", DocumentCreateView.as_view(), name="document_create"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document_detail"),
    path("documents/<int:pk>/edit/", DocumentUpdateView.as_view(), name="document_update"),
    path("documents/<int:pk>/delete/", DocumentDeleteView.as_view(), name="document_delete"),
    path("documents/<int:pk>/download/", DocumentDownloadView.as_view(), name="document_download"),
    path("documents/<int:pk>/view/", DocumentViewInlineView.as_view(), name="document_view_inline"),
    path("documents/bulk/delete/", BulkDeleteDocumentsView.as_view(), name="document_bulk_delete"),

    # Significant Events (Birthdays, Anniversaries, etc.)
    path("significant-events/", SignificantEventListView.as_view(), name="significant_event_list"),
    path("significant-events/new/", SignificantEventCreateView.as_view(), name="significant_event_create"),
    path("significant-events/<int:pk>/", SignificantEventDetailView.as_view(), name="significant_event_detail"),
    path("significant-events/<int:pk>/edit/", SignificantEventUpdateView.as_view(), name="significant_event_update"),
    path("significant-events/<int:pk>/delete/", SignificantEventDeleteView.as_view(), name="significant_event_delete"),
    path("significant-events/bulk/delete/", BulkDeleteSignificantEventsView.as_view(), name="significant_event_bulk_delete"),

    # Google Calendar
    path("calendar/google/", GoogleCalendarSettingsView.as_view(), name="google_calendar_settings"),
    path("calendar/google/settings/", GoogleCalendarSaveSettingsView.as_view(), name="google_calendar_save_settings"),
    path("calendar/google/connect/", GoogleCalendarConnectView.as_view(), name="google_calendar_connect"),
    path("calendar/google/callback/", GoogleCalendarCallbackView.as_view(), name="google_calendar_callback"),
    path("calendar/google/disconnect/", GoogleCalendarDisconnectView.as_view(), name="google_calendar_disconnect"),
    path("calendar/google/sync/", GoogleCalendarSyncView.as_view(), name="google_calendar_sync"),
    path("events/<int:pk>/push-to-google/", GoogleCalendarPushEventView.as_view(), name="google_calendar_push_event"),

    # Gmail Integration
    path("gmail/", GmailSettingsView.as_view(), name="gmail_settings"),
    path("gmail/connect/", GmailConnectView.as_view(), name="gmail_connect"),
    path("gmail/callback/", GmailCallbackView.as_view(), name="gmail_callback"),
    path("gmail/disconnect/", GmailDisconnectView.as_view(), name="gmail_disconnect"),
    path("gmail/settings/", GmailSaveSettingsView.as_view(), name="gmail_save_settings"),
    path("gmail/scan/", GmailManualScanView.as_view(), name="gmail_manual_scan"),
    path("api/gmail/cron-sync/", GmailSyncCronView.as_view(), name="gmail_cron_sync"),
]