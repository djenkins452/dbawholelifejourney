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
    # Google Calendar
    GoogleCalendarSettingsView,
    GoogleCalendarSaveSettingsView,
    GoogleCalendarConnectView,
    GoogleCalendarCallbackView,
    GoogleCalendarDisconnectView,
    GoogleCalendarSyncView,
    GoogleCalendarPushEventView,
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
    
    # Inventory Photos
    path("inventory/<int:item_pk>/photos/new/", InventoryPhotoCreateView.as_view(), name="inventory_photo_create"),
    path("inventory/photos/<int:pk>/delete/", InventoryPhotoDeleteView.as_view(), name="inventory_photo_delete"),
    path("inventory/photos/<int:pk>/set-primary/", InventoryPhotoSetPrimaryView.as_view(), name="inventory_photo_set_primary"),
    
    # Pets
    path("pets/", PetListView.as_view(), name="pet_list"),
    path("pets/new/", PetCreateView.as_view(), name="pet_create"),
    path("pets/<int:pk>/", PetDetailView.as_view(), name="pet_detail"),
    path("pets/<int:pk>/edit/", PetUpdateView.as_view(), name="pet_update"),
    
    # Pet Records
    path("pets/<int:pet_pk>/records/new/", PetRecordCreateView.as_view(), name="pet_record_create"),
    path("pets/records/<int:pk>/edit/", PetRecordUpdateView.as_view(), name="pet_record_update"),
    path("pets/records/<int:pk>/delete/", PetRecordDeleteView.as_view(), name="pet_record_delete"),
    
    # Recipes
    path("recipes/", RecipeListView.as_view(), name="recipe_list"),
    path("recipes/new/", RecipeCreateView.as_view(), name="recipe_create"),
    path("recipes/<int:pk>/", RecipeDetailView.as_view(), name="recipe_detail"),
    path("recipes/<int:pk>/edit/", RecipeUpdateView.as_view(), name="recipe_update"),
    path("recipes/<int:pk>/delete/", RecipeDeleteView.as_view(), name="recipe_delete"),
    path("recipes/<int:pk>/favorite/", RecipeToggleFavoriteView.as_view(), name="recipe_toggle_favorite"),
    
    # Maintenance Logs
    path("maintenance/", MaintenanceLogListView.as_view(), name="maintenance_list"),
    path("maintenance/new/", MaintenanceLogCreateView.as_view(), name="maintenance_create"),
    path("maintenance/<int:pk>/", MaintenanceLogDetailView.as_view(), name="maintenance_detail"),
    path("maintenance/<int:pk>/edit/", MaintenanceLogUpdateView.as_view(), name="maintenance_update"),
    path("maintenance/<int:pk>/delete/", MaintenanceLogDeleteView.as_view(), name="maintenance_delete"),
    
    # Documents
    path("documents/", DocumentListView.as_view(), name="document_list"),
    path("documents/new/", DocumentCreateView.as_view(), name="document_create"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document_detail"),
    path("documents/<int:pk>/edit/", DocumentUpdateView.as_view(), name="document_update"),
    path("documents/<int:pk>/delete/", DocumentDeleteView.as_view(), name="document_delete"),
    path("documents/<int:pk>/download/", DocumentDownloadView.as_view(), name="document_download"),
    
    # Google Calendar
    path("calendar/google/", GoogleCalendarSettingsView.as_view(), name="google_calendar_settings"),
    path("calendar/google/settings/", GoogleCalendarSaveSettingsView.as_view(), name="google_calendar_save_settings"),
    path("calendar/google/connect/", GoogleCalendarConnectView.as_view(), name="google_calendar_connect"),
    path("calendar/google/callback/", GoogleCalendarCallbackView.as_view(), name="google_calendar_callback"),
    path("calendar/google/disconnect/", GoogleCalendarDisconnectView.as_view(), name="google_calendar_disconnect"),
    path("calendar/google/sync/", GoogleCalendarSyncView.as_view(), name="google_calendar_sync"),
    path("events/<int:pk>/push-to-google/", GoogleCalendarPushEventView.as_view(), name="google_calendar_push_event"),
]