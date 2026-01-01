"""
Admin Console URLs
"""

from django.urls import path

from . import views

app_name = "admin_console"

urlpatterns = [
    # Dashboard
    path("", views.AdminDashboardView.as_view(), name="dashboard"),

    # Site Configuration
    path("config/", views.SiteConfigView.as_view(), name="site_config"),

    # Themes
    path("themes/", views.ThemeListView.as_view(), name="theme_list"),
    path("themes/new/", views.ThemeCreateView.as_view(), name="theme_create"),
    path("themes/<int:pk>/edit/", views.ThemeUpdateView.as_view(), name="theme_update"),
    path("themes/<int:pk>/delete/", views.ThemeDeleteView.as_view(), name="theme_delete"),
    path("themes/<int:pk>/preview/", views.ThemePreviewView.as_view(), name="theme_preview"),

    # Categories
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/new/", views.CategoryCreateView.as_view(), name="category_create"),
    path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category_update"),
    path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),

    # Users
    path("users/", views.UserListView.as_view(), name="user_list"),

    # Choice Categories
    path("choices/", views.ChoiceCategoryListView.as_view(), name="choice_category_list"),
    path("choices/new/", views.ChoiceCategoryCreateView.as_view(), name="choice_category_create"),
    path("choices/<int:pk>/edit/", views.ChoiceCategoryUpdateView.as_view(), name="choice_category_update"),
    path("choices/<int:pk>/delete/", views.ChoiceCategoryDeleteView.as_view(), name="choice_category_delete"),

    # Choice Options
    path("choices/<int:category_pk>/options/", views.ChoiceOptionListView.as_view(), name="choice_option_list"),
    path("choices/<int:category_pk>/options/new/", views.ChoiceOptionCreateView.as_view(), name="choice_option_create"),
    path("choices/options/<int:pk>/edit/", views.ChoiceOptionUpdateView.as_view(), name="choice_option_update"),
    path("choices/options/<int:pk>/delete/", views.ChoiceOptionDeleteView.as_view(), name="choice_option_delete"),

    # Test History
    path("tests/", views.TestRunListView.as_view(), name="test_run_list"),
    path("tests/run/", views.RunTestsView.as_view(), name="run_tests"),
    path("tests/<int:pk>/", views.TestRunDetailView.as_view(), name="test_run_detail"),
    path("tests/<int:pk>/delete/", views.TestRunDeleteView.as_view(), name="test_run_delete"),

    # Project Phases
    path("projects/phases/", views.ProjectPhaseListView.as_view(), name="project_phase_list"),
    path("projects/phases/new/", views.ProjectPhaseCreateView.as_view(), name="project_phase_create"),
    path("projects/phases/<int:pk>/edit/", views.ProjectPhaseUpdateView.as_view(), name="project_phase_update"),
    path("projects/phases/<int:pk>/delete/", views.ProjectPhaseDeleteView.as_view(), name="project_phase_delete"),

    # Admin Tasks
    path("projects/tasks/", views.AdminTaskListView.as_view(), name="admin_task_list"),
    path("projects/tasks/new/", views.AdminTaskCreateView.as_view(), name="admin_task_create"),
    path("projects/tasks/<int:pk>/edit/", views.AdminTaskUpdateView.as_view(), name="admin_task_update"),
    path("projects/tasks/<int:pk>/delete/", views.AdminTaskDeleteView.as_view(), name="admin_task_delete"),

    # Activity Logs
    path("projects/activity/", views.ActivityLogListView.as_view(), name="activity_log_list"),
    path("projects/activity/new/", views.ActivityLogCreateView.as_view(), name="activity_log_create"),
    path("projects/activity/<int:pk>/edit/", views.ActivityLogUpdateView.as_view(), name="activity_log_update"),
    path("projects/activity/<int:pk>/delete/", views.ActivityLogDeleteView.as_view(), name="activity_log_delete"),
]
