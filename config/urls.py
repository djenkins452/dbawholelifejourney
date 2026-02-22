"""
Whole Life Journey - Main URL Configuration

Project: Whole Life Journey
Path: config/urls.py
Purpose: Central URL routing for all application modules

Description:
    This is the root URL configuration that dispatches requests to all
    app-specific URL patterns. It defines the main entry points for each
    module and configures Django admin, authentication, and media serving.

Key Responsibilities:
    - Route requests to appropriate app URL configurations
    - Configure Django admin at a custom secure path
    - Include django-allauth authentication URLs
    - Serve media files in both development and production
    - Define custom 404/500 error handlers

URL Namespaces:
    - core: Landing page, terms, about pages
    - users: Profile, preferences, onboarding
    - dashboard: Main dashboard and widgets
    - journal: Journal entries and prompts
    - faith: Scripture, prayer, devotionals
    - health: Fitness, nutrition, medicine tracking
    - life: Tasks, projects, inventory, events
    - purpose: Goals, vision, direction
    - help: Context-aware help system
    - scan: AI Camera scanning feature
    - finance: Financial accounts, budgets, goals, metrics

Security Notes:
    - Admin URL uses configurable path (ADMIN_URL_PATH) to reduce attack surface
    - Custom error handlers for consistent user experience

Copyright:
    (c) Whole Life Journey. All rights reserved.
    This code is proprietary and may not be copied, modified, or distributed
    without explicit permission.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import FileResponse, Http404
from django.urls import include, path
import os


def serve_media(request, path):
    """Serve media files in production (for Railway ephemeral storage)."""
    file_path = os.path.join(settings.MEDIA_ROOT, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(open(file_path, 'rb'))
    raise Http404("Media file not found")


urlpatterns = [
    # Admin - using custom path for security (H-4)
    # The path is configurable via ADMIN_URL_PATH env var, defaults to 'wlj-admin'
    path(f"{settings.ADMIN_URL_PATH}/", admin.site.urls),
    # Authentication (django-allauth)
    # Custom signup view to handle reCAPTCHA validation in form.clean()
    # This prevents low reCAPTCHA scores from triggering Django error emails
    path("accounts/signup/", __import__('apps.users.views', fromlist=['CustomSignupView']).CustomSignupView.as_view(), name="account_signup"),
    path("accounts/", include("allauth.urls")),
    # API endpoints for admin project tasks
    path("api/admin/project/", include("apps.admin_console.api_urls")),
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
    # Camera Scan
    path('scan/', include('apps.scan.urls', namespace='scan')),
    # Audio Capture & Transcription
    path('capture/', include('apps.capture.urls', namespace='capture')),
    # AI Personal Assistant (public-facing)
    path('assistant/', include('apps.ai.urls', namespace='ai')),
    # Assistant Self-Improvement Admin Views (internal admin tools)
    path('assistant-admin/', include('assistant.urls', namespace='assistant')),
    # SMS Notifications
    path('sms/', include('apps.sms.urls', namespace='sms')),
    # Finance
    path('finance/', include('apps.finance.urls', namespace='finance')),
    # Billing & Subscriptions
    path('billing/', include('apps.billing.urls', namespace='billing')),
    # Security Assessment Dashboard (CISO Review)
    path('security/', include('apps.security.urls', namespace='security')),
    # Mobile App API (iOS/Android)
    path('api/mobile/', include('apps.mobile.urls', namespace='mobile')),
    # Brain Training (Health > Cognitive Health)
    path('health/cognitive/', include('apps.brain_training.urls', namespace='brain_training')),
    # Medical Labs & Vitals
    path('medical/', include('apps.medical.urls', namespace='medical')),
    # AI Insights Inbox
    path('insights/', include('apps.core.ai_insights.urls', namespace='ai_insights')),
    # AI Guidance (PGE)
    path('guidance/', include('apps.core.ai_guidance.urls', namespace='ai_guidance')),
    # Intelligence Command Center (ICC)
    path('intelligence/', include('apps.core.urls_intelligence_center', namespace='intelligence')),
    # Weekly Intelligence Reports (WIRE)
    path('intelligence/weekly/', include('apps.core.ai_weekly_report.urls', namespace='ai_weekly_report')),
    # Evidence & Explainability (E3)
    path('intelligence/explain/', include('apps.core.ai_explain.urls', namespace='ai_explain')),
    # Delivery & Notification Engine (DNE)
    path('intelligence/delivery/', include('apps.core.ai_delivery.urls', namespace='ai_delivery')),
    # Calendar Engine — CoS Time Command Center
    path('calendar/', include('apps.calendar_engine.urls', namespace='calendar_engine')),
    # Owner Financial Command Center (superuser only)
    path('owner/finance/', include('apps.owner_finance.urls', namespace='owner_finance')),
    # Referral link redirect (short URL)
    path('join', include([
        path('', lambda r: __import__('django.shortcuts', fromlist=['redirect']).redirect('billing:capture_referral') if r.GET.get('ref') else __import__('django.shortcuts', fromlist=['redirect']).redirect('account_signup')),
    ])),
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


# Custom error handlers
handler404 = 'apps.core.views.custom_404'
handler500 = 'apps.core.views.custom_500'
