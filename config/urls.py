"""
URL configuration for Whole Life Journey.

The main URL dispatcher that routes to all app-specific URLs.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path
from django.views.static import serve
import os


def serve_media(request, path):
    """Serve media files in production (for Railway ephemeral storage)."""
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(open(file_path, 'rb'))
    raise Http404("Media file not found")


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
    # Help System
    path('help/', include('apps.help.urls', namespace='help')),
]

# Serve media files
# In development, Django serves them via static() helper
# In production, we use a custom view since static() only works with DEBUG=True
# Note: Railway has ephemeral storage - files are lost on redeploy
# Consider S3/Cloudinary for persistent media storage in the future
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        path('media/<path:path>', serve_media, name='serve_media'),
    ]

# Custom admin site configuration
admin.site.site_header = "Whole Life Journey Admin"
admin.site.site_title = "WLJ Admin"
admin.site.index_title = "Administration"
