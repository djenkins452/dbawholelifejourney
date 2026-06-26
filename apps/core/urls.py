"""
Whole Life Journey - Core URL Configuration

Project: Whole Life Journey
Path: apps/core/urls.py
Purpose: URL routing for core pages and API endpoints

Description:
    Defines URL patterns for the core app including the landing page,
    static content pages (terms, privacy, about), and the What's New
    release notes feature.

URL Patterns:
    - /                   : Landing page (redirects to dashboard if authenticated)
    - /terms/            : Terms of Service
    - /privacy/          : Privacy Policy
    - /about/            : About page
    - /whats-new/        : Full release notes list
    - /api/whats-new/*   : Release notes API endpoints

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.urls import include, path

from . import views

app_name = "core"

urlpatterns = [
    # Blueprint API
    path("api/blueprint/", include("apps.core.blueprint.urls")),

    path("", views.LandingPageView.as_view(), name="landing"),
    path("_health/", views.HealthCheckView.as_view(), name="health_check"),
    path("terms/", views.TermsOfServiceView.as_view(), name="terms"),
    path("privacy/", views.PrivacyPolicyView.as_view(), name="privacy"),
    path("about/", views.AboutView.as_view(), name="about"),
    path("study/flashcards/", views.StudyFlashcardsView.as_view(), name="study_flashcards"),
    path("app-review/", views.AppReviewView.as_view(), name="app_review"),
    path("app-review/login/", views.AppReviewLoginView.as_view(), name="app_review_login"),
    path("ux-design/", views.UXDesignView.as_view(), name="ux_design"),
    path("login-preview/", views.LoginPreviewView.as_view(), name="login_preview"),

    # More (mobile nav overflow)
    path("more/", views.MoreView.as_view(), name="more"),

    # Favorites hub (mobile top icon)
    path("favorites/", views.FavoritesHubView.as_view(), name="favorites_hub"),

    # What's New / Release Notes
    path("whats-new/", views.WhatsNewListView.as_view(), name="whats_new_list"),
    path("api/whats-new/check/", views.WhatsNewCheckView.as_view(), name="whats_new_check"),
    path("api/whats-new/dismiss/", views.WhatsNewDismissView.as_view(), name="whats_new_dismiss"),

    # Development Notice (early access reminder)
    path("api/development-notice/check/", views.DevelopmentNoticeCheckView.as_view(), name="dev_notice_check"),
    path("api/development-notice/dismiss/", views.DevelopmentNoticeDismissView.as_view(), name="dev_notice_dismiss"),

    # Favorites API
    path("api/favorites/toggle/", views.FavoriteToggleView.as_view(), name="favorite_toggle"),
    path("api/favorites/check/", views.FavoriteCheckView.as_view(), name="favorite_check"),
    path("api/favorites/menu/", views.FavoritesMenuDataView.as_view(), name="favorites_menu"),

    # Restore (Undo Delete) API
    path("api/restore/", views.RestoreItemView.as_view(), name="restore_item"),

    # Search History API
    path("api/search-history/", views.SearchHistoryGetView.as_view(), name="search_history_get"),
    path("api/search-history/save/", views.SearchHistorySaveView.as_view(), name="search_history_save"),
    path("api/search-history/clear/", views.SearchHistoryClearView.as_view(), name="search_history_clear"),

    # 404 Reporting API
    path("api/report-404/", views.Report404View.as_view(), name="report_404"),

    # Notification Center
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),

    # Notification API
    path("api/notifications/unread/", views.NotificationUnreadView.as_view(), name="notifications_unread"),
    path("api/notifications/<int:pk>/read/", views.NotificationMarkReadView.as_view(), name="notification_mark_read"),
    path("api/notifications/mark-all-read/", views.NotificationMarkAllReadView.as_view(), name="notifications_mark_all_read"),
    path("api/notifications/count/", views.NotificationCountView.as_view(), name="notifications_count"),

    # Notification Setup Popup API
    path("api/notification-setup/check/", views.NotificationSetupCheckView.as_view(), name="notification_setup_check"),
    path("api/notification-setup/dismiss/", views.NotificationSetupDismissView.as_view(), name="notification_setup_dismiss"),
]
