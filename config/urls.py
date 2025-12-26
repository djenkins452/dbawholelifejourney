"""
URL configuration for Whole Life Journey.

The main URL dispatcher that routes to all app-specific URLs.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # Authentication (django-allauth)
    path("accounts/", include("allauth.urls")),
    # Core pages (landing, terms, about)
    path("", include("apps.core.urls", namespace="core")),
    # User management (profile, preferences)
    path("user/", include("apps.users.urls", namespace="users")),
    # Dashboard
    path("dashboard/", include("apps.dashboard.urls", namespace="dashboard")),
    # Journal
    path("journal/", include("apps.journal.urls", namespace="journal")),
    # Faith
    path("faith/", include("apps.faith.urls", namespace="faith")),
    # Health
    path("health/", include("apps.health.urls", namespace="health")),
    # Admin Console
    path("admin-console/", include("apps.admin_console.urls")),    
    # Life
    path("life/", include("apps.life.urls")),
    # Purpose
    path('purpose/', include('apps.purpose.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Custom admin site configuration
admin.site.site_header = "Whole Life Journey Admin"
admin.site.site_title = "WLJ Admin"
admin.site.index_title = "Administration"
