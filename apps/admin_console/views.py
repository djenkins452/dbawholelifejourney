# ==============================================================================
# File: apps/admin_console/views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console views for site management and project task intake
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-01
# Last Updated: 2026-01-06
# ==============================================================================
"""
Admin Views - Custom admin interface for site management.

These views provide a user-friendly admin interface that matches
the app's design, rather than using Django's default admin.
"""

from django.contrib import messages
from django.contrib.auth.mixins import UserPassesTestMixin
from django.db import models
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from apps.core.models import Category, SiteConfiguration, Theme
from apps.core.models import ChoiceCategory, ChoiceOption
from .models import AdminGuideSection, AdminGuideArticle
from apps.core.rate_limiting import APIRateLimitMixin
from apps.core.utils import user_log_id
from apps.help.mixins import HelpContextMixin

import logging

logger = logging.getLogger(__name__)


def validate_image_file(uploaded_file, max_size_mb=5):
    """
    Validate that an uploaded file is a legitimate image.

    Security (CISO Review 2026-01-12):
    - File extension is an allowed image type
    - Content-Type header matches allowed types
    - Magic bytes verification for file type
    - File content is actually a valid image (PIL verification)
    - File size is within limits

    Args:
        uploaded_file: Django UploadedFile object
        max_size_mb: Maximum file size in megabytes

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    import os

    ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp', '.svg'}
    ALLOWED_CONTENT_TYPES = {
        'image/png', 'image/jpeg', 'image/gif', 'image/x-icon',
        'image/vnd.microsoft.icon', 'image/webp', 'image/svg+xml'
    }

    # Magic bytes for file type verification (CISO Review 2026-01-12)
    MAGIC_BYTES = {
        b'\xff\xd8\xff': 'jpeg',           # JPEG
        b'\x89PNG\r\n\x1a\n': 'png',       # PNG
        b'GIF87a': 'gif',                  # GIF87a
        b'GIF89a': 'gif',                  # GIF89a
        b'\x00\x00\x01\x00': 'ico',        # ICO
        b'RIFF': 'webp',                   # WebP (RIFF....WEBP)
    }

    # Check file extension
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"

    # Check file size
    max_bytes = max_size_mb * 1024 * 1024
    if uploaded_file.size > max_bytes:
        return False, f"File too large. Maximum size: {max_size_mb}MB"

    # Check content type header
    content_type = uploaded_file.content_type
    if content_type not in ALLOWED_CONTENT_TYPES:
        return False, f"Invalid content type '{content_type}'"

    # For non-SVG images, verify magic bytes and actual image content
    if ext != '.svg':
        try:
            # Read first bytes for magic byte check
            uploaded_file.seek(0)
            header = uploaded_file.read(16)
            uploaded_file.seek(0)

            # Verify magic bytes
            detected_format = None
            for magic, fmt in MAGIC_BYTES.items():
                if header[:len(magic)] == magic:
                    detected_format = fmt
                    break

            # Special check for WebP (RIFF....WEBP)
            if not detected_format and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
                detected_format = 'webp'

            if not detected_format:
                logger.warning(f"Magic byte validation failed for {uploaded_file.name}")
                return False, "File content does not match a valid image format"

            # Verify actual image content using PIL
            from PIL import Image
            uploaded_file.seek(0)
            img = Image.open(uploaded_file)
            img.verify()  # Verify it's a valid image
            uploaded_file.seek(0)  # Reset for later use

        except Exception as e:
            logger.warning(f"Image validation failed for {uploaded_file.name}: {e}")
            return False, "File is not a valid image"

    return True, None


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin to ensure user is staff/admin."""

    def test_func(self):
        return self.request.user.is_staff

    def handle_no_permission(self):
        messages.error(self.request, "You don't have permission to access the admin area.")
        return redirect('dashboard:home')


class AdminOverrideConfirmationMixin:
    """
    Mixin for admin override operations requiring password confirmation.

    CISO Review 2026-01-12: Sensitive admin operations require re-authentication.

    This mixin provides an extra layer of security for destructive admin operations
    by requiring the admin to re-enter their password if they haven't recently
    confirmed their identity.

    IMPORTANT: This does NOT block normal admin console viewing - only specific
    destructive operations (reset phase, unblock task, etc.).

    Configuration:
        - Timeout period: settings.WLJ_SETTINGS.get('ADMIN_OVERRIDE_TIMEOUT_MINUTES', 30)
        - Session key: 'admin_override_confirmed_at'
        - Can be disabled: settings.WLJ_SETTINGS.get('ADMIN_OVERRIDE_REQUIRE_CONFIRMATION', True)

    Safety Features:
        - Superusers can disable confirmation via settings
        - Normal admin viewing is NOT affected
        - Django's built-in /admin/ always works
        - If locked out: Use manage.py shell to clear session or disable setting

    Usage for API views:
        Call self._require_admin_confirmation(request) at the start of POST/DELETE methods.
        Returns (proceed: bool, response: JsonResponse or None)

        Example:
            proceed, error_response = self._require_admin_confirmation(request)
            if not proceed:
                return error_response
    """

    # Override in subclass to describe the operation
    admin_operation_name = 'admin_override'

    def _require_admin_confirmation(self, request):
        """
        Check if admin has confirmed their password recently.

        For API endpoints, returns a JSON response if confirmation is needed.

        Returns:
            tuple: (can_proceed: bool, error_response: JsonResponse or None)

        If can_proceed is False, return the error_response to the client.
        """
        from django.conf import settings
        from django.utils import timezone

        # Check if confirmation is disabled in settings
        wlj_settings = getattr(settings, 'WLJ_SETTINGS', {})
        require_confirmation = wlj_settings.get('ADMIN_OVERRIDE_REQUIRE_CONFIRMATION', True)

        if not require_confirmation:
            # Confirmation disabled - allow all operations
            return True, None

        # Check if user recently confirmed their password
        timeout_minutes = wlj_settings.get('ADMIN_OVERRIDE_TIMEOUT_MINUTES', 30)
        last_confirmed = request.session.get('admin_override_confirmed_at')

        if last_confirmed:
            from datetime import datetime
            try:
                last_confirmed_dt = datetime.fromisoformat(last_confirmed)
                elapsed = (timezone.now() - timezone.make_aware(last_confirmed_dt)).total_seconds() / 60

                if elapsed < timeout_minutes:
                    # Recently confirmed - allow operation
                    return True, None
            except (ValueError, TypeError):
                pass

        # Need confirmation - return appropriate response
        logger.info(
            f"Admin override confirmation required for {self.admin_operation_name} "
            f"by {user_log_id(request.user)}"
        )

        return False, JsonResponse({
            'error': 'Password confirmation required',
            'confirmation_required': True,
            'message': (
                'For security, please confirm your password to perform this admin override. '
                'Visit /user/confirm-password/ and then retry this operation.'
            ),
            'confirm_url': '/user/confirm-password/',
        }, status=403)

    def _mark_admin_confirmed(self, request):
        """Mark the session as having confirmed admin identity."""
        from django.utils import timezone
        request.session['admin_override_confirmed_at'] = timezone.now().isoformat()
        # Also update finance confirmation since they share the same password
        request.session['finance_last_activity'] = timezone.now().isoformat()


class AdminDashboardView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """
    Main admin dashboard - overview of site management options.
    """
    template_name = "admin_console/dashboard.html"
    help_context_id = "ADMIN_CONSOLE_HOME"

    def get_context_data(self, **kwargs):
        try:
            context = super().get_context_data(**kwargs)
            from django.conf import settings
            from apps.users.models import User
            from apps.journal.models import JournalEntry

            # Stats
            context['total_users'] = User.objects.count()
            context['total_entries'] = JournalEntry.objects.count()
            context['total_themes'] = Theme.objects.filter(is_active=True).count()
            context['total_categories'] = Category.objects.count()
            context['total_choice_categories'] = ChoiceCategory.objects.count()

            # Recent activity
            context['recent_users'] = User.objects.order_by('-date_joined')[:5]

            # Admin URL path for Django Admin link
            context['admin_url_path'] = settings.ADMIN_URL_PATH

            return context
        except Exception as e:
            logger.exception(f"AdminDashboardView.get_context_data failed: {e}")
            raise


# ============================================================
# Site Configuration Views
# ============================================================

class SiteConfigView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """
    Edit site configuration (singleton).
    """
    template_name = "admin_console/site_config.html"
    help_context_id = "ADMIN_CONSOLE_SITE_CONFIG"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['config'] = SiteConfiguration.get_solo()
        context['themes'] = Theme.objects.filter(is_active=True)
        return context
    
    def post(self, request):
        config = SiteConfiguration.get_solo()
        
        # Update fields
        config.site_name = request.POST.get('site_name', config.site_name)
        config.tagline = request.POST.get('tagline', config.tagline)
        config.default_theme = request.POST.get('default_theme', config.default_theme)
        config.footer_text = request.POST.get('footer_text', config.footer_text)
        config.privacy_policy_url = request.POST.get('privacy_policy_url', '')
        config.terms_url = request.POST.get('terms_url', '')
        
        # Booleans
        config.allow_registration = request.POST.get('allow_registration') == 'on'
        config.require_email_verification = request.POST.get('require_email_verification') == 'on'
        config.faith_enabled_by_default = request.POST.get('faith_enabled_by_default') == 'on'
        
        # Handle logo upload with validation
        if 'logo' in request.FILES:
            logo_file = request.FILES['logo']
            is_valid, error = validate_image_file(logo_file)
            if is_valid:
                config.logo = logo_file
            else:
                messages.error(request, f"Logo upload failed: {error}")
                return redirect('admin_console:site_config')
        elif request.POST.get('clear_logo') == 'on':
            config.logo = None

        # Handle favicon upload with validation
        if 'favicon' in request.FILES:
            favicon_file = request.FILES['favicon']
            is_valid, error = validate_image_file(favicon_file, max_size_mb=1)
            if is_valid:
                config.favicon = favicon_file
            else:
                messages.error(request, f"Favicon upload failed: {error}")
                return redirect('admin_console:site_config')
        elif request.POST.get('clear_favicon') == 'on':
            config.favicon = None

        config.save()
        messages.success(request, "Site configuration updated successfully.")
        return redirect('admin_console:site_config')


# ============================================================
# Theme Management Views
# ============================================================

class ThemeListView(HelpContextMixin, AdminRequiredMixin, ListView):
    """List all themes."""
    model = Theme
    template_name = "admin_console/theme_list.html"
    context_object_name = "themes"
    help_context_id = "ADMIN_CONSOLE_THEMES"
    
    def get_queryset(self):
        return Theme.objects.all().order_by('sort_order', 'name')


class ThemeCreateView(AdminRequiredMixin, CreateView):
    """Create a new theme."""
    model = Theme
    template_name = "admin_console/theme_form.html"
    fields = [
        'slug', 'name', 'description', 'sort_order', 'is_active', 'is_default',
        'color_primary', 'color_secondary', 'color_accent', 'color_text',
        'color_text_muted', 'color_background', 'color_surface', 'color_border',
        'dark_color_primary', 'dark_color_secondary', 'dark_color_accent', 
        'dark_color_text', 'dark_color_text_muted', 'dark_color_background',
        'dark_color_surface', 'dark_color_border',
    ]
    success_url = reverse_lazy('admin_console:theme_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"Theme '{form.instance.name}' created successfully.")
        return super().form_valid(form)


class ThemeUpdateView(AdminRequiredMixin, UpdateView):
    """Edit an existing theme."""
    model = Theme
    template_name = "admin_console/theme_form.html"
    fields = [
        'slug', 'name', 'description', 'sort_order', 'is_active', 'is_default',
        'color_primary', 'color_secondary', 'color_accent', 'color_text',
        'color_text_muted', 'color_background', 'color_surface', 'color_border',
        'dark_color_primary', 'dark_color_secondary', 'dark_color_accent', 
        'dark_color_text', 'dark_color_text_muted', 'dark_color_background',
        'dark_color_surface', 'dark_color_border',
    ]
    success_url = reverse_lazy('admin_console:theme_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"Theme '{form.instance.name}' updated successfully.")
        return super().form_valid(form)


class ThemeDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a theme."""
    model = Theme
    template_name = "admin_console/theme_confirm_delete.html"
    success_url = reverse_lazy('admin_console:theme_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"Theme '{self.object.name}' deleted.")
        return super().form_valid(form)


class ThemePreviewView(AdminRequiredMixin, View):
    """AJAX endpoint to preview theme colors."""
    
    def get(self, request, pk):
        theme = Theme.objects.get(pk=pk)
        return render(request, 'admin_console/partials/theme_preview.html', {
            'theme': theme
        })


# ============================================================
# Category Management Views
# ============================================================

class CategoryListView(AdminRequiredMixin, ListView):
    """List all categories."""
    model = Category
    template_name = "admin_console/category_list.html"
    context_object_name = "categories"
    
    def get_queryset(self):
        return Category.objects.all().order_by('name')


class CategoryCreateView(AdminRequiredMixin, CreateView):
    """Create a new category."""
    model = Category
    template_name = "admin_console/category_form.html"
    fields = ['name', 'slug', 'description', 'icon', 'order']
    success_url = reverse_lazy('admin_console:category_list')

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.name}' created successfully.")
        return super().form_valid(form)


class CategoryUpdateView(AdminRequiredMixin, UpdateView):
    """Edit a category."""
    model = Category
    template_name = "admin_console/category_form.html"
    fields = ['name', 'slug', 'description', 'icon', 'order']
    success_url = reverse_lazy('admin_console:category_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.name}' updated successfully.")
        return super().form_valid(form)


class CategoryDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a category."""
    model = Category
    template_name = "admin_console/category_confirm_delete.html"
    success_url = reverse_lazy('admin_console:category_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"Category '{self.object.name}' deleted.")
        return super().form_valid(form)


# ============================================================
# User Management Views (Basic)
# ============================================================

class UserListView(HelpContextMixin, AdminRequiredMixin, ListView):
    """List all users."""
    template_name = "admin_console/user_list.html"
    context_object_name = "users"
    paginate_by = 50
    help_context_id = "ADMIN_CONSOLE_USERS"
    
    def get_queryset(self):
        from apps.users.models import User
        return User.objects.all().order_by('-date_joined')


# ============================================================
# Choice Category & Option Views (Phase 3)
# ============================================================

class ChoiceCategoryListView(AdminRequiredMixin, ListView):
    """List all choice categories."""
    model = ChoiceCategory
    template_name = "admin_console/choice_category_list.html"
    context_object_name = "categories"
    
    def get_queryset(self):
        return ChoiceCategory.objects.all().prefetch_related('options')


class ChoiceCategoryCreateView(AdminRequiredMixin, CreateView):
    """Create a new choice category."""
    model = ChoiceCategory
    template_name = "admin_console/choice_category_form.html"
    fields = ['slug', 'name', 'description', 'app_label', 'is_system']
    success_url = reverse_lazy('admin_console:choice_category_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.name}' created.")
        return super().form_valid(form)


class ChoiceCategoryUpdateView(AdminRequiredMixin, UpdateView):
    """Edit a choice category."""
    model = ChoiceCategory
    template_name = "admin_console/choice_category_form.html"
    fields = ['slug', 'name', 'description', 'app_label', 'is_system']
    success_url = reverse_lazy('admin_console:choice_category_list')
    
    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.name}' updated.")
        return super().form_valid(form)


class ChoiceCategoryDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a choice category."""
    model = ChoiceCategory
    template_name = "admin_console/choice_category_confirm_delete.html"
    success_url = reverse_lazy('admin_console:choice_category_list')
    
    def form_valid(self, form):
        if self.object.is_system:
            messages.error(self.request, "Cannot delete system categories.")
            return redirect('admin_console:choice_category_list')
        messages.success(self.request, f"Category '{self.object.name}' deleted.")
        return super().form_valid(form)


class ChoiceOptionListView(AdminRequiredMixin, ListView):
    """List options for a specific category."""
    model = ChoiceOption
    template_name = "admin_console/choice_option_list.html"
    context_object_name = "options"
    
    def get_queryset(self):
        self.category = ChoiceCategory.objects.get(pk=self.kwargs['category_pk'])
        return ChoiceOption.objects.filter(category=self.category).order_by('sort_order')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        return context


class ChoiceOptionCreateView(AdminRequiredMixin, CreateView):
    """Create a new choice option."""
    model = ChoiceOption
    template_name = "admin_console/choice_option_form.html"
    fields = ['value', 'label', 'icon', 'color', 'sort_order', 'is_active', 'is_default']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = ChoiceCategory.objects.get(pk=self.kwargs['category_pk'])
        return context
    
    def form_valid(self, form):
        form.instance.category = ChoiceCategory.objects.get(pk=self.kwargs['category_pk'])
        messages.success(self.request, f"Option '{form.instance.label}' created.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('admin_console:choice_option_list', kwargs={'category_pk': self.kwargs['category_pk']})


class ChoiceOptionUpdateView(AdminRequiredMixin, UpdateView):
    """Edit a choice option."""
    model = ChoiceOption
    template_name = "admin_console/choice_option_form.html"
    fields = ['value', 'label', 'icon', 'color', 'sort_order', 'is_active', 'is_default']
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.object.category
        return context
    
    def form_valid(self, form):
        messages.success(self.request, f"Option '{form.instance.label}' updated.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('admin_console:choice_option_list', kwargs={'category_pk': self.object.category.pk})


class ChoiceOptionDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a choice option."""
    model = ChoiceOption
    template_name = "admin_console/choice_option_confirm_delete.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.object.category
        return context
    
    def form_valid(self, form):
        messages.success(self.request, f"Option '{self.object.label}' deleted.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('admin_console:choice_option_list', kwargs={'category_pk': self.object.category.pk})

# ============================================================
# Test History Views
# ============================================================

class TestRunListView(AdminRequiredMixin, ListView):
    """List all test runs with summary information."""
    template_name = "admin_console/test_run_list.html"
    context_object_name = "test_runs"
    paginate_by = 25
    
    def get_queryset(self):
        from apps.core.models import TestRun
        return TestRun.objects.all().order_by('-run_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.conf import settings
        from apps.core.models import TestRun

        # Get stats
        runs = TestRun.objects.all()
        context['total_runs'] = runs.count()
        context['passed_runs'] = runs.filter(status='passed').count()
        context['failed_runs'] = runs.filter(status__in=['failed', 'error']).count()

        # Latest run
        context['latest_run'] = runs.first()

        # Pass debug flag for conditional display
        context['debug'] = settings.DEBUG

        return context


class TestRunDetailView(AdminRequiredMixin, TemplateView):
    """View details of a specific test run."""
    template_name = "admin_console/test_run_detail.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.models import TestRun
        import json
        
        test_run = TestRun.objects.get(pk=self.kwargs['pk'])
        context['test_run'] = test_run
        context['details'] = test_run.details.all().order_by('app_name')
        
        # Parse failed/error tests from JSON
        for detail in context['details']:
            try:
                detail.failed_tests_list = json.loads(detail.failed_tests) if detail.failed_tests else []
            except (json.JSONDecodeError, TypeError):
                detail.failed_tests_list = []
            try:
                detail.error_tests_list = json.loads(detail.error_tests) if detail.error_tests else []
            except (json.JSONDecodeError, TypeError):
                detail.error_tests_list = []
        
        return context


class TestRunDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a test run and its details."""
    template_name = "admin_console/test_run_confirm_delete.html"
    success_url = reverse_lazy('admin_console:test_run_list')

    def get_queryset(self):
        from apps.core.models import TestRun
        return TestRun.objects.all()

    def form_valid(self, form):
        messages.success(self.request, f"Test run from {self.object.run_at.strftime('%Y-%m-%d %H:%M')} deleted.")
        return super().form_valid(form)


class RunTestsView(AdminRequiredMixin, View):
    """Run tests and redirect to results (dev only)."""

    def get(self, request):
        from django.conf import settings
        import subprocess
        import sys

        # Only allow in DEBUG mode
        if not settings.DEBUG:
            messages.error(request, "Test execution is only available in development mode.")
            return redirect('admin_console:test_run_list')

        try:
            # Run the test script
            result = subprocess.run(
                [sys.executable, 'run_tests.py'],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                cwd=settings.BASE_DIR
            )

            if result.returncode == 0:
                messages.success(request, "Tests completed successfully! Results have been recorded.")
            else:
                messages.warning(request, "Tests completed with failures. Check the results below.")

        except subprocess.TimeoutExpired:
            messages.error(request, "Test execution timed out after 5 minutes.")
        except FileNotFoundError:
            messages.error(request, "Could not find run_tests.py script.")
        except Exception as e:
            messages.error(request, f"Error running tests: {str(e)}")

        return redirect('admin_console:test_run_list')


# ============================================================
# UI Test Runner Views
# ============================================================

class UITestModulesView(AdminRequiredMixin, TemplateView):
    """Display available UI test modules with checkboxes for selection."""
    template_name = "admin_console/ui_test_modules.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.conf import settings
        from apps.admin_console.models import UITestRun

        try:
            from apps.admin_console.services.test_module_registry import discover_modules
            context['modules'] = discover_modules()
        except Exception:
            logger.exception("Failed to discover UI test modules")
            context['modules'] = []

        context['debug'] = settings.DEBUG

        # Recent UI test runs for history section
        context['recent_runs'] = UITestRun.objects.all()[:10]

        return context


class RunUITestsView(AdminRequiredMixin, View):
    """Execute UI tests for selected modules (dev only)."""

    def post(self, request):
        from django.conf import settings
        import json
        import subprocess
        import sys
        import time

        # Only allow in DEBUG mode
        if not settings.DEBUG:
            messages.error(request, "UI test execution is only available in development mode.")
            return redirect('admin_console:ui_test_modules')

        # Get selected modules from form
        selected_modules = request.POST.getlist('modules')
        headed = request.POST.get('headed') == '1'
        if not selected_modules:
            messages.warning(request, "No modules selected. Please select at least one module.")
            return redirect('admin_console:ui_test_modules')

        # Create UITestRun record
        from apps.admin_console.models import UITestRun
        ui_run = UITestRun.objects.create(
            status='running',
            modules=selected_modules,
        )

        # Run each module via subprocess
        total_cases = 0
        total_passed = 0
        total_failed = 0
        combined_output = []
        all_case_results = {"passed": [], "failed": []}
        overall_status = 'passed'
        start_time = time.time()

        ui_tests_dir = settings.BASE_DIR / 'wlj_ui_tests'

        for module_name in selected_modules:
            combined_output.append(f"\n{'=' * 60}")
            combined_output.append(f"  Module: {module_name}")
            combined_output.append(f"{'=' * 60}\n")

            try:
                cmd = [
                    sys.executable,
                    str(ui_tests_dir / 'run_suite.py'),
                    '--module', module_name,
                    '--provision-test-user',
                ]
                if headed:
                    cmd.append('--headed')
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout per module
                    cwd=str(settings.BASE_DIR),
                )

                combined_output.append(result.stdout)
                if result.stderr:
                    combined_output.append(result.stderr)

                # Parse JSON summary from stderr
                summary = _parse_ui_test_summary(result.stderr)
                if summary:
                    total_cases += summary.get('total_cases', 0)
                    total_passed += summary.get('passed', 0)
                    total_failed += summary.get('failed', 0)
                    if summary.get('failed', 0) > 0:
                        overall_status = 'failed'
                    run_id = summary.get('run_id', '')
                    if run_id and not ui_run.run_id:
                        ui_run.run_id = run_id
                    # Collect per-case results
                    results = summary.get('results', {})
                    all_case_results["passed"].extend(results.get("passed", []))
                    all_case_results["failed"].extend(results.get("failed", []))

                if result.returncode != 0 and overall_status != 'failed':
                    overall_status = 'failed'

            except subprocess.TimeoutExpired:
                combined_output.append(f"ERROR: Module {module_name} timed out after 5 minutes.")
                overall_status = 'error'
            except FileNotFoundError:
                combined_output.append(f"ERROR: Could not find run_suite.py for module {module_name}.")
                overall_status = 'error'
            except Exception as e:
                combined_output.append(f"ERROR: {module_name}: {str(e)}")
                overall_status = 'error'

        duration = time.time() - start_time
        pass_rate = (total_passed / total_cases * 100) if total_cases > 0 else 0

        # Update UITestRun record
        import socket
        ui_run.status = overall_status
        ui_run.total_cases = total_cases
        ui_run.passed = total_passed
        ui_run.failed = total_failed
        ui_run.pass_rate = pass_rate
        ui_run.duration_seconds = duration
        ui_run.output = "\n".join(combined_output)
        ui_run.environment = 'local'
        ui_run.source_host = socket.gethostname()
        ui_run.source_user = request.user.email if request.user.is_authenticated else 'admin'
        ui_run.case_results = all_case_results
        ui_run.save()

        # Sync to production (non-blocking)
        _sync_ui_test_run(ui_run)

        if overall_status == 'passed':
            messages.success(request, f"UI tests passed! {total_passed}/{total_cases} cases passed.")
        elif overall_status == 'failed':
            messages.warning(request, f"UI tests completed with failures: {total_failed}/{total_cases} failed.")
        else:
            messages.error(request, "UI test execution encountered errors.")

        return redirect('admin_console:ui_test_detail', pk=ui_run.pk)


class RunFullSuiteView(AdminRequiredMixin, View):
    """Run all modules with test cases as a full suite (dev only)."""

    def post(self, request):
        from django.conf import settings
        import subprocess
        import sys
        import time

        if not settings.DEBUG:
            messages.error(request, "UI test execution is only available in development mode.")
            return redirect('admin_console:ui_test_modules')

        # Discover modules with actual test cases
        try:
            from apps.admin_console.services.test_module_registry import discover_modules
            all_modules = discover_modules()
            runnable = [m['name'] for m in all_modules if m.get('case_count', 0) > 0]
        except Exception:
            runnable = []

        if not runnable:
            messages.warning(request, "No modules with test cases found.")
            return redirect('admin_console:ui_test_modules')

        headed = request.POST.get('headed') == '1'
        from apps.admin_console.models import UITestRun

        # Create parent full-suite record
        parent_run = UITestRun.objects.create(
            status='running',
            modules=['full_suite'],
        )

        total_cases = 0
        total_passed = 0
        total_failed = 0
        overall_status = 'passed'
        start_time = time.time()
        ui_tests_dir = settings.BASE_DIR / 'wlj_ui_tests'

        for module_name in runnable:
            module_start = time.time()
            child = UITestRun.objects.create(
                status='running',
                modules=[module_name],
                parent_run=parent_run,
            )

            try:
                cmd = [
                    sys.executable,
                    str(ui_tests_dir / 'run_suite.py'),
                    '--module', module_name,
                    '--provision-test-user',
                ]
                if headed:
                    cmd.append('--headed')
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(settings.BASE_DIR),
                )

                output = result.stdout
                if result.stderr:
                    output += "\n" + result.stderr

                summary = _parse_ui_test_summary(result.stderr)
                mod_cases = summary.get('total_cases', 0) if summary else 0
                mod_passed = summary.get('passed', 0) if summary else 0
                mod_failed = summary.get('failed', 0) if summary else 0
                mod_status = 'passed'

                if summary and mod_failed > 0:
                    mod_status = 'failed'
                if result.returncode != 0 and mod_status != 'failed':
                    mod_status = 'failed'

                child.status = mod_status
                child.total_cases = mod_cases
                child.passed = mod_passed
                child.failed = mod_failed
                child.pass_rate = (mod_passed / mod_cases * 100) if mod_cases > 0 else 0
                child.duration_seconds = time.time() - module_start
                child.run_id = summary.get('run_id', '') if summary else ''
                child.output = output
                child.case_results = summary.get('results', {}) if summary else {}
                child.save()

                total_cases += mod_cases
                total_passed += mod_passed
                total_failed += mod_failed
                if mod_status != 'passed':
                    overall_status = 'failed'

            except subprocess.TimeoutExpired:
                child.status = 'error'
                child.output = f"ERROR: Module {module_name} timed out after 5 minutes."
                child.duration_seconds = time.time() - module_start
                child.save()
                overall_status = 'error'
            except Exception as e:
                child.status = 'error'
                child.output = f"ERROR: {module_name}: {str(e)}"
                child.duration_seconds = time.time() - module_start
                child.save()
                overall_status = 'error'

        # Update parent record
        import socket
        parent_run.status = overall_status
        parent_run.total_cases = total_cases
        parent_run.passed = total_passed
        parent_run.failed = total_failed
        parent_run.pass_rate = (total_passed / total_cases * 100) if total_cases > 0 else 0
        parent_run.duration_seconds = time.time() - start_time
        parent_run.environment = 'local'
        parent_run.source_host = socket.gethostname()
        parent_run.source_user = request.user.email if request.user.is_authenticated else 'admin'
        parent_run.save()

        # Sync to production (non-blocking, includes children)
        child_runs = list(parent_run.child_runs.all())
        _sync_ui_test_run(parent_run, children=child_runs)

        if overall_status == 'passed':
            messages.success(request, f"Full suite passed! {total_passed}/{total_cases} cases across {len(runnable)} modules.")
        elif overall_status == 'failed':
            messages.warning(request, f"Full suite completed with failures: {total_failed}/{total_cases} failed.")
        else:
            messages.error(request, "Full suite encountered errors.")

        return redirect('admin_console:ui_test_detail', pk=parent_run.pk)


class UITestRunDetailView(AdminRequiredMixin, TemplateView):
    """View details of a specific UI test run."""
    template_name = "admin_console/ui_test_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.admin_console.models import UITestRun

        ui_run = get_object_or_404(UITestRun, pk=self.kwargs['pk'])
        context['ui_run'] = ui_run
        # Include child runs for full-suite views
        if ui_run.is_full_suite:
            context['child_runs'] = ui_run.child_runs.all().order_by('run_at')
        return context


def _parse_ui_test_summary(stderr_output):
    """Parse JSON summary from run_suite.py stderr output.

    The orchestrator emits a JSON summary to stderr. Find and parse it.

    Args:
        stderr_output: Combined stderr string from subprocess.

    Returns:
        Dict with summary data, or None if not found.
    """
    import json

    if not stderr_output:
        return None

    # The JSON summary is the last JSON object in stderr
    # Try parsing from the end of stderr
    lines = stderr_output.strip().split('\n')

    # Look for the JSON block (starts with { and ends with })
    json_lines = []
    in_json = False
    brace_depth = 0

    for line in reversed(lines):
        stripped = line.strip()
        if not in_json and stripped.endswith('}'):
            in_json = True

        if in_json:
            json_lines.insert(0, line)
            brace_depth += stripped.count('{') - stripped.count('}')
            if brace_depth >= 0 and stripped.startswith('{'):
                break

    if json_lines:
        try:
            return json.loads('\n'.join(json_lines))
        except json.JSONDecodeError:
            pass

    return None


def _sync_ui_test_run(ui_run, children=None):
    """Sync a UITestRun to production (non-blocking, fail-silent).

    Runs the sync in a daemon thread so it doesn't delay the HTTP response.
    """
    import threading

    def _do_sync():
        try:
            from wlj_ui_tests.framework.result_sync import sync_result

            payload = {
                "run_id": ui_run.run_id,
                "modules": ui_run.modules,
                "status": ui_run.status,
                "total_cases": ui_run.total_cases,
                "passed": ui_run.passed,
                "failed": ui_run.failed,
                "pass_rate": float(ui_run.pass_rate),
                "duration_seconds": ui_run.duration_seconds,
                "results": ui_run.case_results,
                "environment": ui_run.environment,
                "source_host": ui_run.source_host,
                "source_user": ui_run.source_user,
            }
            if children:
                payload["children"] = [
                    {
                        "run_id": c.run_id,
                        "modules": c.modules,
                        "status": c.status,
                        "total_cases": c.total_cases,
                        "passed": c.passed,
                        "failed": c.failed,
                        "pass_rate": float(c.pass_rate),
                        "duration_seconds": c.duration_seconds,
                        "results": c.case_results,
                    }
                    for c in children
                ]
            sync_result(payload, ui_run_output=ui_run.output[:10240])
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Failed to sync UITestRun %s to production", ui_run.pk
            )

    thread = threading.Thread(target=_do_sync, daemon=True)
    thread.start()


# ============================================================
# Project Phase Views
# ============================================================

class ProjectPhaseListView(HelpContextMixin, AdminRequiredMixin, ListView):
    """List all project phases."""
    template_name = "admin_console/project_phase_list.html"
    context_object_name = "phases"
    help_context_id = "ADMIN_CONSOLE_PROJECT_PHASES"

    def get_queryset(self):
        from apps.admin_console.models import AdminProjectPhase
        return AdminProjectPhase.objects.all().order_by('phase_number')


class ProjectPhaseCreateView(AdminRequiredMixin, CreateView):
    """Create a new project phase."""
    template_name = "admin_console/project_phase_form.html"
    success_url = reverse_lazy('admin_console:project_phase_list')
    fields = ['phase_number', 'name', 'objective', 'status']

    def get_queryset(self):
        from apps.admin_console.models import AdminProjectPhase
        return AdminProjectPhase.objects.all()

    def get_form_class(self):
        from django import forms
        from apps.admin_console.models import AdminProjectPhase

        class ProjectPhaseForm(forms.ModelForm):
            class Meta:
                model = AdminProjectPhase
                fields = ['phase_number', 'name', 'objective', 'status']

        return ProjectPhaseForm

    def form_valid(self, form):
        messages.success(self.request, f"Phase '{form.instance.name}' created.")
        return super().form_valid(form)


class ProjectPhaseUpdateView(AdminRequiredMixin, UpdateView):
    """Edit a project phase."""
    template_name = "admin_console/project_phase_form.html"
    success_url = reverse_lazy('admin_console:project_phase_list')
    fields = ['phase_number', 'name', 'objective', 'status']

    def get_queryset(self):
        from apps.admin_console.models import AdminProjectPhase
        return AdminProjectPhase.objects.all()

    def form_valid(self, form):
        messages.success(self.request, f"Phase '{form.instance.name}' updated.")
        return super().form_valid(form)


class ProjectPhaseDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a project phase."""
    template_name = "admin_console/project_phase_confirm_delete.html"
    success_url = reverse_lazy('admin_console:project_phase_list')

    def get_queryset(self):
        from apps.admin_console.models import AdminProjectPhase
        return AdminProjectPhase.objects.all()

    def form_valid(self, form):
        from apps.admin_console.models import DeletionProtectedError
        try:
            phase_name = self.object.name
            self.object.delete()
            messages.success(self.request, f"Phase '{phase_name}' deleted.")
            return redirect(self.success_url)
        except DeletionProtectedError as e:
            messages.error(self.request, str(e))
            return redirect('admin_console:project_phase_list')


# ============================================================
# Admin Task Views
# ============================================================

class AdminTaskListView(HelpContextMixin, AdminRequiredMixin, ListView):
    """
    List all admin tasks with filtering.

    Phase 12 requirements:
    - Display: title, phase number, status, priority, created_by, created_at
    - Order by: priority ASC, created_at ASC
    - Filterable by: phase, status, project (optional)
    - Read-only list (no inline editing required)
    - Includes Mark Ready control for backlog tasks
    """
    template_name = "admin_console/admin_task_list.html"
    context_object_name = "tasks"
    help_context_id = "ADMIN_CONSOLE_TASKS"

    def get_queryset(self):
        from apps.admin_console.models import AdminTask
        from django.db.models import Q

        queryset = AdminTask.objects.select_related('phase', 'project').all()

        # Search across text fields if query provided
        # Note: description is a JSONField with objective, inputs, actions, output
        # We search title, category, and the JSON description fields
        search_query = self.request.GET.get('q', '').strip()
        if search_query:
            # For JSONField, use key lookups for text fields
            # For arrays (inputs, actions), convert to string representation
            from django.db.models.functions import Cast
            from django.db.models import TextField

            queryset = queryset.annotate(
                description_text=Cast('description', TextField())
            ).filter(
                Q(title__icontains=search_query) |
                Q(category__icontains=search_query) |
                Q(description_text__icontains=search_query)
            )

        # Filter by phase if provided (supports multiple values)
        # When checkboxes are used, no selection means show nothing
        phase_filters = self.request.GET.getlist('phase')
        if phase_filters:
            # Convert to integers, ignore invalid values
            phase_ids = []
            for p in phase_filters:
                try:
                    phase_ids.append(int(p))
                except (ValueError, TypeError):
                    pass
            if phase_ids:
                queryset = queryset.filter(phase_id__in=phase_ids)
        elif 'phase' in self.request.GET:
            # Phase parameter was in URL but empty = show nothing
            queryset = queryset.none()

        # Filter by status if provided (supports multiple values)
        # When checkboxes are used, no selection means show nothing
        status_filters = self.request.GET.getlist('status')
        if status_filters:
            queryset = queryset.filter(status__in=status_filters)
        elif 'status' in self.request.GET:
            # Status parameter was in URL but empty = show nothing
            queryset = queryset.none()

        # Filter by project if provided (supports multiple values)
        # When checkboxes are used, no selection means show nothing
        project_filters = self.request.GET.getlist('project')
        if project_filters:
            # Convert to integers, ignore invalid values
            project_ids = []
            for p in project_filters:
                try:
                    project_ids.append(int(p))
                except (ValueError, TypeError):
                    pass
            if project_ids:
                queryset = queryset.filter(project_id__in=project_ids)
        elif 'project' in self.request.GET:
            # Project parameter was in URL but empty = show nothing
            queryset = queryset.none()

        # Handle sorting - default to priority ASC, created_at ASC
        sort_field = self.request.GET.get('sort', 'priority')
        sort_dir = self.request.GET.get('dir', 'asc')

        # Map frontend column names to model fields
        sort_field_map = {
            'id': 'pk',
            'title': 'title',
            'phase': 'phase__phase_number',
            'status': 'status',
            'priority': 'priority',
            'created_by': 'created_by',
            'created_at': 'created_at',
            'project': 'project__name',
        }

        # Get the actual field to sort by, default to priority
        actual_field = sort_field_map.get(sort_field, 'priority')

        # Apply sort direction
        if sort_dir == 'desc':
            actual_field = '-' + actual_field

        return queryset.order_by(actual_field)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.admin_console.models import AdminProjectPhase, AdminProject, AdminTask

        context['phases'] = AdminProjectPhase.objects.all().order_by('phase_number')
        context['projects'] = AdminProject.objects.all().order_by('name')
        context['status_choices'] = AdminTask.STATUS_CHOICES

        # Preserve filter values
        context['current_search_query'] = self.request.GET.get('q', '')
        context['current_phase_filters'] = self.request.GET.getlist('phase')
        context['current_status_filters'] = self.request.GET.getlist('status')
        context['current_project_filters'] = self.request.GET.getlist('project')

        # Sort state for sortable headers
        context['current_sort'] = self.request.GET.get('sort', 'priority')
        context['current_dir'] = self.request.GET.get('dir', 'asc')

        # Ready tasks warning (soft guardrail)
        ready_count = AdminTask.objects.filter(status='ready').count()
        context['ready_count'] = ready_count
        context['show_ready_warning'] = ready_count >= READY_TASKS_WARNING_THRESHOLD
        context['ready_warning_threshold'] = READY_TASKS_WARNING_THRESHOLD

        return context


class AdminTaskCreateView(AdminRequiredMixin, CreateView):
    """Create a new admin task with executable description."""
    template_name = "admin_console/admin_task_form.html"
    success_url = reverse_lazy('admin_console:admin_task_list')
    fields = ['title', 'category', 'priority', 'status', 'effort', 'phase', 'project', 'created_by', 'attachment']

    def get_queryset(self):
        from apps.admin_console.models import AdminTask
        return AdminTask.objects.all()

    def get_form_class(self):
        from django import forms
        from apps.admin_console.models import AdminTask

        class AdminTaskForm(forms.ModelForm):
            class Meta:
                model = AdminTask
                fields = ['title', 'category', 'priority', 'status', 'effort', 'phase', 'project', 'created_by', 'attachment']

        return AdminTaskForm

    def form_valid(self, form):
        from apps.admin_console.models import ExecutableTaskValidationError

        # Extract executable task description fields from POST
        objective = self.request.POST.get('objective', '').strip()
        inputs_raw = self.request.POST.get('inputs', '').strip()
        actions_raw = self.request.POST.get('actions', '').strip()
        output = self.request.POST.get('output', '').strip()

        # Parse inputs and actions from newline-separated text
        inputs = [line.strip() for line in inputs_raw.split('\n') if line.strip()] if inputs_raw else []
        actions = [line.strip() for line in actions_raw.split('\n') if line.strip()] if actions_raw else []

        # Build executable task description
        form.instance.description = {
            'objective': objective,
            'inputs': inputs,
            'actions': actions,
            'output': output
        }

        try:
            response = super().form_valid(form)
            messages.success(self.request, f"Task '{form.instance.title}' created.")
            return response
        except ExecutableTaskValidationError as e:
            for error in e.messages:
                messages.error(self.request, error)
            return self.form_invalid(form)


class AdminTaskUpdateView(AdminRequiredMixin, UpdateView):
    """Edit an admin task with executable description."""
    template_name = "admin_console/admin_task_form.html"
    success_url = reverse_lazy('admin_console:admin_task_list')
    fields = ['title', 'category', 'priority', 'status', 'effort', 'phase', 'project', 'created_by', 'attachment', 'resolution_notes']

    def get_queryset(self):
        from apps.admin_console.models import AdminTask
        return AdminTask.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.admin_console.models import (
            AdminProject, AdminProjectPhase,
            AdminTaskStatusConfig, AdminTaskPriorityConfig,
            AdminTaskCategoryConfig, AdminTaskEffortConfig
        )

        # Get phases for dropdown
        context['phases'] = AdminProjectPhase.objects.all().order_by('phase_number')

        # Get projects for dropdown
        context['projects'] = AdminProject.objects.all().order_by('name')

        # Get active config options for dropdowns (same as TaskIntakeView)
        context['status_configs'] = AdminTaskStatusConfig.objects.filter(active=True).order_by('order')
        context['priority_configs'] = AdminTaskPriorityConfig.objects.filter(active=True).order_by('order')
        context['category_configs'] = AdminTaskCategoryConfig.objects.filter(active=True).order_by('order')
        context['effort_configs'] = AdminTaskEffortConfig.objects.filter(active=True).order_by('order')

        return context

    def form_valid(self, form):
        from apps.admin_console.models import ExecutableTaskValidationError

        # Extract executable task description fields from POST
        objective = self.request.POST.get('objective', '').strip()
        inputs_raw = self.request.POST.get('inputs', '').strip()
        actions_raw = self.request.POST.get('actions', '').strip()
        output = self.request.POST.get('output', '').strip()

        # Parse inputs and actions from newline-separated text
        inputs = [line.strip() for line in inputs_raw.split('\n') if line.strip()] if inputs_raw else []
        actions = [line.strip() for line in actions_raw.split('\n') if line.strip()] if actions_raw else []

        # Build executable task description
        form.instance.description = {
            'objective': objective,
            'inputs': inputs,
            'actions': actions,
            'output': output
        }

        try:
            response = super().form_valid(form)
            messages.success(self.request, f"Task '{form.instance.title}' updated.")
            return response
        except ExecutableTaskValidationError as e:
            for error in e.messages:
                messages.error(self.request, error)
            return self.form_invalid(form)


class AdminTaskDeleteView(AdminRequiredMixin, DeleteView):
    """Delete an admin task."""
    template_name = "admin_console/admin_task_confirm_delete.html"
    success_url = reverse_lazy('admin_console:admin_task_list')

    def get_queryset(self):
        from apps.admin_console.models import AdminTask
        return AdminTask.objects.all()

    def form_valid(self, form):
        from apps.admin_console.models import DeletionProtectedError
        try:
            task_title = self.object.title
            self.object.delete()
            messages.success(self.request, f"Task '{task_title}' deleted.")
            return redirect(self.success_url)
        except DeletionProtectedError as e:
            messages.error(self.request, str(e))
            return redirect('admin_console:admin_task_list')


# ============================================================
# Phase 12: Task Intake & Controls
# ============================================================

# Guardrail threshold for ready tasks warning
READY_TASKS_WARNING_THRESHOLD = 5


class TaskIntakeView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """
    Task Intake page for admin to create new tasks.

    GET: Display the task intake form
    POST: Create a new AdminTask

    Safety rules:
    - created_by is always set to 'human'
    - Status defaults to 'backlog', not auto-set to 'ready'
    - Validates required fields
    - Requires a phase to be selected
    - Phase 17: Uses config tables for dropdowns, only shows active configs
    """
    template_name = "admin_console/task_intake.html"
    help_context_id = "ADMIN_CONSOLE_TASK_INTAKE"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.admin_console.models import (
            AdminProject, AdminProjectPhase, AdminTask,
            AdminTaskStatusConfig, AdminTaskPriorityConfig,
            AdminTaskCategoryConfig, AdminTaskEffortConfig
        )
        from .services import get_active_phase, get_or_create_default_project

        # Get phases for dropdown
        context['phases'] = AdminProjectPhase.objects.all().order_by('phase_number')

        # Get projects for dropdown
        context['projects'] = AdminProject.objects.all().order_by('name')

        # Get default project
        default_project = get_or_create_default_project()
        context['default_project'] = default_project

        # Get active phase as default
        active_phase = get_active_phase()
        context['active_phase'] = active_phase

        # Phase 17: Get active config options for dropdowns
        context['status_configs'] = AdminTaskStatusConfig.objects.filter(active=True).order_by('order')
        context['priority_configs'] = AdminTaskPriorityConfig.objects.filter(active=True).order_by('order')
        context['category_configs'] = AdminTaskCategoryConfig.objects.filter(active=True).order_by('order')
        context['effort_configs'] = AdminTaskEffortConfig.objects.filter(active=True).order_by('order')

        # Legacy choices (kept for backward compatibility)
        context['category_choices'] = AdminTask.CATEGORY_CHOICES
        context['effort_choices'] = AdminTask.EFFORT_CHOICES

        # Check if there's a warning about ready tasks count
        ready_count = AdminTask.objects.filter(status='ready').count()
        context['ready_count'] = ready_count
        context['show_ready_warning'] = ready_count >= READY_TASKS_WARNING_THRESHOLD
        context['ready_warning_threshold'] = READY_TASKS_WARNING_THRESHOLD

        return context

    def post(self, request):
        from apps.admin_console.models import (
            AdminProject, AdminProjectPhase, AdminTask,
            AdminTaskStatusConfig, AdminTaskPriorityConfig,
            AdminTaskCategoryConfig, AdminTaskEffortConfig
        )
        from .services import get_or_create_default_project

        # Extract form data
        title = request.POST.get('title', '').strip()
        phase_id = request.POST.get('phase')
        project_id = request.POST.get('project')
        priority_config_id = request.POST.get('priority_config')
        status_config_id = request.POST.get('status_config')
        category_config_id = request.POST.get('category_config')
        effort_config_id = request.POST.get('effort_config')

        # Extract Executable Task Description fields
        objective = request.POST.get('objective', '').strip()
        inputs_raw = request.POST.get('inputs', '').strip()
        actions_raw = request.POST.get('actions', '').strip()
        output = request.POST.get('output', '').strip()

        # Parse inputs and actions from newline-separated text
        inputs = [line.strip() for line in inputs_raw.split('\n') if line.strip()] if inputs_raw else []
        actions = [line.strip() for line in actions_raw.split('\n') if line.strip()] if actions_raw else []

        # Build executable task description
        description = {
            'objective': objective,
            'inputs': inputs,
            'actions': actions,
            'output': output
        }

        # Validate required fields
        errors = []
        if not title:
            errors.append("Title is required.")

        # Validate executable task description (mandatory fields per WLJ Executable Task Standard)
        if not objective:
            errors.append("Objective is required. Describe what the task should accomplish.")
        if not actions:
            errors.append("At least one action is required. Provide step-by-step instructions for execution.")
        if not output:
            errors.append("Output is required. Specify the expected deliverable or result.")

        if not phase_id:
            errors.append("Phase is required. Cannot create a task without a phase.")

        # Validate phase exists
        phase = None
        if phase_id:
            try:
                phase = AdminProjectPhase.objects.get(pk=phase_id)
            except AdminProjectPhase.DoesNotExist:
                errors.append(f"Phase with ID {phase_id} does not exist.")

        # Validate project exists or use default
        project = None
        if project_id:
            try:
                project = AdminProject.objects.get(pk=project_id)
            except AdminProject.DoesNotExist:
                errors.append(f"Project with ID {project_id} does not exist.")
        else:
            # Use default project if none specified
            project = get_or_create_default_project()

        # Validate config selections
        status_config = None
        if status_config_id:
            try:
                status_config = AdminTaskStatusConfig.objects.get(pk=status_config_id, active=True)
            except AdminTaskStatusConfig.DoesNotExist:
                errors.append("Invalid status selection.")
        else:
            # Default to backlog status
            status_config = AdminTaskStatusConfig.objects.filter(name='backlog', active=True).first()
            if not status_config:
                errors.append("No active backlog status found in configuration.")

        priority_config = None
        if priority_config_id:
            try:
                priority_config = AdminTaskPriorityConfig.objects.get(pk=priority_config_id, active=True)
            except AdminTaskPriorityConfig.DoesNotExist:
                errors.append("Invalid priority selection.")
        else:
            # Default to Normal priority (value 3)
            priority_config = AdminTaskPriorityConfig.objects.filter(value=3, active=True).first()
            if not priority_config:
                errors.append("No active Normal priority found in configuration.")

        category_config = None
        if category_config_id:
            try:
                category_config = AdminTaskCategoryConfig.objects.get(pk=category_config_id, active=True)
            except AdminTaskCategoryConfig.DoesNotExist:
                errors.append("Invalid category selection.")
        else:
            # Default to Feature category
            category_config = AdminTaskCategoryConfig.objects.filter(name='feature', active=True).first()
            if not category_config:
                errors.append("No active Feature category found in configuration.")

        effort_config = None
        if effort_config_id:
            try:
                effort_config = AdminTaskEffortConfig.objects.get(pk=effort_config_id, active=True)
            except AdminTaskEffortConfig.DoesNotExist:
                errors.append("Invalid effort selection.")
        else:
            # Default to Medium effort
            effort_config = AdminTaskEffortConfig.objects.filter(value='M', active=True).first()
            if not effort_config:
                errors.append("No active Medium effort found in configuration.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('admin_console:task_intake')

        # Get optional attachment
        attachment = request.FILES.get('attachment')

        # Create the task with config references
        task = AdminTask.objects.create(
            title=title,
            description=description,
            phase=phase,
            project=project,
            # Config ForeignKey fields
            status_config=status_config,
            priority_config=priority_config,
            category_config=category_config,
            effort_config=effort_config,
            # Legacy fields (kept in sync for backward compatibility)
            status=status_config.name if status_config else 'backlog',
            priority=priority_config.value if priority_config else 3,
            category=category_config.name if category_config else 'feature',
            effort=effort_config.value if effort_config else 'M',
            attachment=attachment,
            created_by='human'  # Always human for intake
        )

        messages.success(request, f"Task '{task.title}' created successfully.")
        return redirect('admin_console:admin_task_list')


class MarkReadyAPIView(View):
    """
    API endpoint to toggle a task from backlog to ready.

    POST /api/projects/tasks/<id>/mark-ready/

    This is a human control that:
    - Requires explicit click/action
    - Only works for tasks with status='backlog'
    - Changes status to 'ready'

    Returns:
    - 200: Success with task info
    - 400: Task is not in backlog status
    - 403: Permission denied (not admin)
    - 404: Task not found
    """

    def post(self, request, pk):
        from apps.admin_console.models import AdminTask, AdminActivityLog

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Get the task
        try:
            task = AdminTask.objects.select_related('phase').get(pk=pk)
        except AdminTask.DoesNotExist:
            return JsonResponse(
                {'error': 'Task not found'},
                status=404
            )

        # Validate current status
        if task.status != 'backlog':
            return JsonResponse(
                {'error': f"Cannot mark as ready. Task is '{task.status}', not 'backlog'."},
                status=400
            )

        # Update status
        old_status = task.status
        task.status = 'ready'
        task.save()

        # Log the change
        AdminActivityLog.objects.create(
            task=task,
            action=f"Status changed from '{old_status}' to 'ready' via Mark Ready control.",
            created_by='human'
        )

        # Get current count of ready tasks for warning
        ready_count = AdminTask.objects.filter(status='ready').count()

        return JsonResponse({
            'success': True,
            'task': {
                'id': task.id,
                'title': task.title,
                'status': task.status,
                'phase_number': task.phase.phase_number
            },
            'ready_count': ready_count,
            'show_warning': ready_count >= READY_TASKS_WARNING_THRESHOLD
        })


# ============================================================
# Activity Log Views
# ============================================================

class ActivityLogListView(AdminRequiredMixin, ListView):
    """List all activity logs."""
    template_name = "admin_console/activity_log_list.html"
    context_object_name = "logs"
    paginate_by = 50

    def get_queryset(self):
        from apps.admin_console.models import AdminActivityLog
        return AdminActivityLog.objects.select_related('task').all().order_by('-created_at')


class ActivityLogCreateView(AdminRequiredMixin, CreateView):
    """Create a new activity log."""
    template_name = "admin_console/activity_log_form.html"
    success_url = reverse_lazy('admin_console:activity_log_list')
    fields = ['task', 'action', 'created_by']

    def get_queryset(self):
        from apps.admin_console.models import AdminActivityLog
        return AdminActivityLog.objects.all()

    def get_form_class(self):
        from django import forms
        from apps.admin_console.models import AdminActivityLog

        class ActivityLogForm(forms.ModelForm):
            class Meta:
                model = AdminActivityLog
                fields = ['task', 'action', 'created_by']

        return ActivityLogForm

    def form_valid(self, form):
        messages.success(self.request, "Activity log created.")
        return super().form_valid(form)


class ActivityLogUpdateView(AdminRequiredMixin, UpdateView):
    """Edit an activity log."""
    template_name = "admin_console/activity_log_form.html"
    success_url = reverse_lazy('admin_console:activity_log_list')
    fields = ['task', 'action', 'created_by']

    def get_queryset(self):
        from apps.admin_console.models import AdminActivityLog
        return AdminActivityLog.objects.all()

    def form_valid(self, form):
        messages.success(self.request, "Activity log updated.")
        return super().form_valid(form)


class ActivityLogDeleteView(AdminRequiredMixin, DeleteView):
    """Delete an activity log."""
    template_name = "admin_console/activity_log_confirm_delete.html"
    success_url = reverse_lazy('admin_console:activity_log_list')

    def get_queryset(self):
        from apps.admin_console.models import AdminActivityLog
        return AdminActivityLog.objects.all()

    def form_valid(self, form):
        messages.success(self.request, "Activity log deleted.")
        return super().form_valid(form)


# ============================================================
# Project Task API Views
# ============================================================

class NextTasksAPIView(APIRateLimitMixin, View):
    """
    API endpoint to get next tasks from the active phase.

    GET /api/admin/project/next-tasks/
    Query params:
        - limit (optional, default 5): Maximum tasks to return

    Returns JSON array of task objects.
    Returns 403 if user is not admin.

    Rate Limiting (CISO Review 2026-01-12):
        - 60 requests per minute
        - 500 requests per hour
    """

    rate_limit_requests_per_minute = 60
    rate_limit_requests_per_hour = 500
    rate_limit_key_prefix = 'admin_api'

    def get(self, request):
        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Get limit from query params
        try:
            limit = int(request.GET.get('limit', 5))
            if limit < 1:
                limit = 5
            elif limit > 100:
                limit = 100
        except (ValueError, TypeError):
            limit = 5

        # Get next tasks using service function
        from .services import get_next_tasks
        tasks = get_next_tasks(limit=limit)

        # Build response
        result = [
            {
                'id': task.id,
                'title': task.title,
                'priority': task.priority,
                'status': task.status,
                'phase_number': task.phase.phase_number
            }
            for task in tasks
        ]

        return JsonResponse(result, safe=False)


class ActivePhaseAPIView(View):
    """
    API endpoint to get the active project phase.

    GET /api/admin/project/active-phase/

    Returns JSON object with active phase info.
    Returns 403 if user is not admin.
    """

    def get(self, request):
        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Get active phase using service function
        from .services import get_active_phase
        phase = get_active_phase()

        if not phase:
            return JsonResponse({'phase': None})

        return JsonResponse({
            'phase': {
                'id': phase.id,
                'phase_number': phase.phase_number,
                'name': phase.name,
                'objective': phase.objective,
                'status': phase.status
            }
        })


class TaskStatusUpdateAPIView(View):
    """
    API endpoint to update a task's status.

    PATCH /api/admin/project/tasks/<id>/status/

    Request body:
    {
        "status": "in_progress",
        "reason": "optional, required only for blocked"
    }

    Returns:
    - 200: Updated task JSON
    - 400: Validation error (invalid transition, missing reason, etc.)
    - 403: Permission denied (not admin)
    - 404: Task not found
    """

    def patch(self, request, pk):
        import json
        from .models import AdminTask, TaskStatusTransitionError

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Get the task
        try:
            task = AdminTask.objects.select_related('phase').get(pk=pk)
        except AdminTask.DoesNotExist:
            return JsonResponse(
                {'error': 'Task not found'},
                status=404
            )

        # Parse request body
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {'error': 'Invalid JSON body'},
                status=400
            )

        # Get status from body
        new_status = body.get('status')
        if not new_status:
            return JsonResponse(
                {'error': 'Missing required field: status'},
                status=400
            )

        # Validate status is a valid choice
        valid_statuses = [choice[0] for choice in AdminTask.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return JsonResponse(
                {'error': f"Invalid status '{new_status}'. Valid statuses: {valid_statuses}"},
                status=400
            )

        # Get optional reason
        reason = body.get('reason')

        # Attempt the status transition
        try:
            log = task.transition_status(
                new_status=new_status,
                reason=reason,
                created_by='human'  # API calls are from humans
            )
        except TaskStatusTransitionError as e:
            return JsonResponse(
                {'error': str(e)},
                status=400
            )

        # Build response
        result = {
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'category': task.category,
            'priority': task.priority,
            'status': task.status,
            'effort': task.effort,
            'blocked_reason': task.blocked_reason,
            'phase': {
                'id': task.phase.id,
                'phase_number': task.phase.phase_number,
                'name': task.phase.name,
                'status': task.phase.status
            },
            'created_by': task.created_by,
            'created_at': task.created_at.isoformat(),
            'updated_at': task.updated_at.isoformat()
        }

        # Include log info if status changed
        if log:
            result['activity_log'] = {
                'id': log.id,
                'action': log.action,
                'created_by': log.created_by,
                'created_at': log.created_at.isoformat()
            }

        return JsonResponse(result)


class ProjectMetricsAPIView(APIRateLimitMixin, View):
    """
    API endpoint to get project status metrics.

    GET /api/admin/project/metrics/

    Returns JSON object with:
    - active_phase: The currently active phase number (or None)
    - global: Metrics across all phases (total, completed, remaining, blocked)
    - active_phase_metrics: Metrics for the active phase only
    - tasks_created_by_claude: Count of tasks created by Claude
    - high_priority_remaining_tasks: High priority tasks not done

    Returns 403 if user is not admin.

    Rate Limiting (CISO Review 2026-01-12):
        - 60 requests per minute
        - 500 requests per hour
    """

    rate_limit_requests_per_minute = 60
    rate_limit_requests_per_hour = 500
    rate_limit_key_prefix = 'admin_api'

    def get(self, request):
        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Get metrics using service function
        from .services import get_project_metrics
        metrics = get_project_metrics()

        return JsonResponse(metrics)


class SystemStateAPIView(APIRateLimitMixin, View):
    """
    API endpoint to get system state snapshot for session bootstrapping.

    GET /api/admin/project/system-state/

    Returns JSON object with:
    - active_phase: {number, name, status} or null
    - objective: Active phase objective or null
    - open_tasks: Count of open (backlog/ready/in_progress) tasks in active phase
    - blocked_tasks: Count of blocked tasks in active phase
    - last_updated: ISO timestamp when snapshot was built

    Returns 403 if user is not admin.

    This endpoint is read-only and does not:
    - Trigger phase completion
    - Trigger task updates
    - Modify any data

    Rate Limiting (CISO Review 2026-01-12):
        - 60 requests per minute
        - 500 requests per hour
    """

    rate_limit_requests_per_minute = 60
    rate_limit_requests_per_hour = 500
    rate_limit_key_prefix = 'admin_api'

    def get(self, request):
        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Get snapshot using request-scope caching
        from .services import get_system_state_snapshot
        snapshot = get_system_state_snapshot(request)

        # Build response with null-safe values
        if snapshot.active_phase_number is not None:
            active_phase = {
                'number': snapshot.active_phase_number,
                'name': snapshot.active_phase_name,
                'status': snapshot.active_phase_status
            }
        else:
            active_phase = None

        return JsonResponse({
            'active_phase': active_phase,
            'objective': snapshot.active_phase_objective,
            'open_tasks': snapshot.open_tasks_count,
            'blocked_tasks': snapshot.blocked_tasks_count,
            'last_updated': snapshot.last_updated.isoformat()
        })


# ============================================================
# Project Status Page View (Phase 7)
# ============================================================

class ProjectStatusView(AdminRequiredMixin, TemplateView):
    """
    Admin-only page displaying project metrics and status.

    GET /admin/projects/status/

    Displays:
    - Active Phase info (number, name, status, objective)
    - Global Metrics (total, completed, remaining, blocked tasks)
    - Active Phase Metrics (same breakdown for active phase)
    - Risk Snapshot (high-priority remaining, Claude-created tasks)
    """
    template_name = "admin_console/project_status.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get metrics using existing service function
        from .services import get_project_metrics, get_active_phase
        metrics = get_project_metrics()
        active_phase = get_active_phase()

        # Active Phase info
        context['active_phase'] = active_phase

        # Global metrics
        context['global_metrics'] = metrics['global']

        # Active phase metrics
        context['active_phase_metrics'] = metrics['active_phase_metrics']

        # Risk snapshot
        context['high_priority_remaining'] = metrics['high_priority_remaining_tasks']
        context['tasks_created_by_claude'] = metrics['tasks_created_by_claude']

        return context


class CodebaseMetricsView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """
    Admin page displaying comprehensive codebase and project metrics.

    GET /admin/codebase-metrics/

    Displays:
    - Project Overview (age, size, apps)
    - File Statistics (counts, lines of code)
    - Code Architecture (models, views, routes, classes, functions)
    - Git Activity (commits, insertions, deletions)
    - Today's Progress
    - Commit Breakdown by Type
    - Most Productive Days
    - Coding Schedule Patterns
    """
    template_name = "admin_console/codebase_metrics.html"
    help_context_id = "ADMIN_CONSOLE_CODEBASE_METRICS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get user's timezone for proper date/time display
        user_timezone = None
        if self.request.user.is_authenticated:
            try:
                user_timezone = self.request.user.preferences.timezone
            except AttributeError:
                pass

        from .metrics_service import get_project_metrics
        metrics = get_project_metrics(user_timezone=user_timezone)

        context['metrics'] = metrics
        context['file_metrics'] = metrics.file_metrics
        context['code_metrics'] = metrics.code_metrics
        context['git_metrics'] = metrics.git_metrics
        context['generated_at'] = metrics.generated_at

        return context


# ============================================================
# Phase 10 - Hardening & Fail-Safes API Views
# ============================================================

class SystemIssuesAPIView(APIRateLimitMixin, View):
    """
    API endpoint to detect system issues.

    GET /api/admin/project/system-issues/

    Returns JSON object with:
    - issues: Array of detected issues, each with:
      - issue_type: Type of issue
      - severity: 'critical' or 'warning'
      - description: Human-readable description
      - affected_ids: List of affected resource IDs

    Returns 403 if user is not admin.

    This endpoint is read-only and does NOT mutate data.

    Rate Limiting (CISO Review 2026-01-12):
        - 60 requests per minute
        - 500 requests per hour
    """

    rate_limit_requests_per_minute = 60
    rate_limit_requests_per_hour = 500
    rate_limit_key_prefix = 'admin_api'

    def get(self, request):
        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        from .services import detect_system_issues
        issues = detect_system_issues()

        result = {
            'issues': [
                {
                    'issue_type': issue.issue_type,
                    'severity': issue.severity,
                    'description': issue.description,
                    'affected_ids': issue.affected_ids
                }
                for issue in issues
            ]
        }

        return JsonResponse(result)


class ResetPhaseOverrideAPIView(AdminOverrideConfirmationMixin, APIRateLimitMixin, View):
    """
    API endpoint to reset the active phase (admin override).

    POST /api/admin/project/override/reset-phase/

    Request body:
    {
        "phase_id": 123
    }

    Returns:
    - 200: Success with phase info
    - 400: Validation error
    - 403: Permission denied (or password confirmation required)
    - 404: Phase not found

    Rate Limiting (CISO Review 2026-01-12):
        - 30 requests per minute
        - 200 requests per hour

    Security (CISO Review 2026-01-12):
        - Requires password confirmation within timeout period
        - Disable via WLJ_SETTINGS['ADMIN_OVERRIDE_REQUIRE_CONFIRMATION'] = False
    """

    rate_limit_requests_per_minute = 30
    rate_limit_requests_per_hour = 200
    rate_limit_key_prefix = 'admin_api_override'
    admin_operation_name = 'reset_phase'

    def post(self, request):
        import json
        from .models import AdminProjectPhase
        from .services import reset_active_phase
        from apps.core.security_logging import log_admin_override

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # CISO Review 2026-01-12: Require password confirmation for override
        proceed, error_response = self._require_admin_confirmation(request)
        if not proceed:
            return error_response

        # Parse request body
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {'error': 'Invalid JSON body'},
                status=400
            )

        phase_id = body.get('phase_id')
        if not phase_id:
            return JsonResponse(
                {'error': 'Missing required field: phase_id'},
                status=400
            )

        try:
            phase = reset_active_phase(phase_id, created_by='human')
        except AdminProjectPhase.DoesNotExist:
            return JsonResponse(
                {'error': f'Phase with ID {phase_id} not found'},
                status=404
            )

        # CISO Review 2026-01-12: Audit log all override actions
        log_admin_override(
            action='reset_phase',
            request=request,
            target_type='phase',
            target_id=phase_id,
            details={
                'new_phase_number': phase.phase_number,
                'new_phase_name': phase.name,
                'new_status': phase.status,
            }
        )

        return JsonResponse({
            'success': True,
            'phase': {
                'id': phase.id,
                'phase_number': phase.phase_number,
                'name': phase.name,
                'status': phase.status
            },
            'message': f'Active phase reset to Phase {phase.phase_number} ("{phase.name}").'
        })


class UnblockTaskOverrideAPIView(AdminOverrideConfirmationMixin, APIRateLimitMixin, View):
    """
    API endpoint to force-unblock a task (admin override).

    POST /api/admin/project/override/unblock-task/

    Request body:
    {
        "task_id": 123,
        "reason": "Required explanation for the override"
    }

    Returns:
    - 200: Success with task info
    - 400: Validation error (missing reason, task not blocked)
    - 403: Permission denied (or password confirmation required)
    - 404: Task not found

    Rate Limiting (CISO Review 2026-01-12):
        - 30 requests per minute
        - 200 requests per hour

    Security (CISO Review 2026-01-12):
        - Requires password confirmation within timeout period
        - Disable via WLJ_SETTINGS['ADMIN_OVERRIDE_REQUIRE_CONFIRMATION'] = False
    """

    rate_limit_requests_per_minute = 30
    rate_limit_requests_per_hour = 200
    rate_limit_key_prefix = 'admin_api_override'
    admin_operation_name = 'unblock_task'

    def post(self, request):
        import json
        from .models import AdminTask
        from .services import force_unblock_task
        from apps.core.security_logging import log_admin_override

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # CISO Review 2026-01-12: Require password confirmation for override
        proceed, error_response = self._require_admin_confirmation(request)
        if not proceed:
            return error_response

        # Parse request body
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {'error': 'Invalid JSON body'},
                status=400
            )

        task_id = body.get('task_id')
        if not task_id:
            return JsonResponse(
                {'error': 'Missing required field: task_id'},
                status=400
            )

        reason = body.get('reason')
        if not reason or not reason.strip():
            return JsonResponse(
                {'error': 'Missing required field: reason. A reason is required for this override.'},
                status=400
            )

        try:
            task = force_unblock_task(task_id, reason, created_by='human')

            # CISO Review 2026-01-12: Audit log all override actions
            log_admin_override(
                action='unblock_task',
                request=request,
                target_type='task',
                target_id=task_id,
                details={
                    'task_title': task.title,
                    'new_status': task.status,
                    'reason': reason,
                }
            )
        except AdminTask.DoesNotExist:
            return JsonResponse(
                {'error': f'Task with ID {task_id} not found'},
                status=404
            )
        except ValueError as e:
            return JsonResponse(
                {'error': str(e)},
                status=400
            )

        return JsonResponse({
            'success': True,
            'task': {
                'id': task.id,
                'title': task.title,
                'status': task.status,
                'blocked_reason': task.blocked_reason,
                'phase': {
                    'id': task.phase.id,
                    'phase_number': task.phase.phase_number,
                    'name': task.phase.name
                }
            },
            'message': f'Task "{task.title}" has been force-unblocked.'
        })


class RecheckPhaseOverrideAPIView(AdminOverrideConfirmationMixin, APIRateLimitMixin, View):
    """
    API endpoint to re-run phase completion check (admin override).

    POST /api/admin/project/override/recheck-phase/

    Request body:
    {
        "phase_id": 123
    }

    Returns:
    - 200: Success with completion status
    - 400: Validation error
    - 403: Permission denied (or password confirmation required)
    - 404: Phase not found

    Rate Limiting (CISO Review 2026-01-12):
        - 30 requests per minute
        - 200 requests per hour

    Security (CISO Review 2026-01-12):
        - Requires password confirmation within timeout period
        - Disable via WLJ_SETTINGS['ADMIN_OVERRIDE_REQUIRE_CONFIRMATION'] = False
    """

    rate_limit_requests_per_minute = 30
    rate_limit_requests_per_hour = 200
    rate_limit_key_prefix = 'admin_api_override'
    admin_operation_name = 'recheck_phase'

    def post(self, request):
        import json
        from .models import AdminProjectPhase
        from .services import recheck_phase_completion
        from apps.core.security_logging import log_admin_override

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # CISO Review 2026-01-12: Require password confirmation for override
        proceed, error_response = self._require_admin_confirmation(request)
        if not proceed:
            return error_response

        # Parse request body
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {'error': 'Invalid JSON body'},
                status=400
            )

        phase_id = body.get('phase_id')
        if not phase_id:
            return JsonResponse(
                {'error': 'Missing required field: phase_id'},
                status=400
            )

        try:
            was_completed, unlocked_phase = recheck_phase_completion(phase_id, created_by='human')
        except AdminProjectPhase.DoesNotExist:
            return JsonResponse(
                {'error': f'Phase with ID {phase_id} not found'},
                status=404
            )

        # Build response
        phase = AdminProjectPhase.objects.get(pk=phase_id)

        # CISO Review 2026-01-12: Audit log all override actions
        log_admin_override(
            action='recheck_phase',
            request=request,
            target_type='phase',
            target_id=phase_id,
            details={
                'phase_number': phase.phase_number,
                'phase_name': phase.name,
                'was_completed': was_completed,
                'unlocked_phase_id': unlocked_phase.id if unlocked_phase else None,
            }
        )

        result = {
            'success': True,
            'phase': {
                'id': phase.id,
                'phase_number': phase.phase_number,
                'name': phase.name,
                'status': phase.status
            },
            'was_completed': was_completed,
            'unlocked_phase': None
        }

        if unlocked_phase:
            result['unlocked_phase'] = {
                'id': unlocked_phase.id,
                'phase_number': unlocked_phase.phase_number,
                'name': unlocked_phase.name,
                'status': unlocked_phase.status
            }
            result['message'] = (
                f'Phase {phase.phase_number} completed. '
                f'Phase {unlocked_phase.phase_number} ("{unlocked_phase.name}") unlocked.'
            )
        elif was_completed:
            result['message'] = f'Phase {phase.phase_number} ("{phase.name}") marked as complete.'
        else:
            result['message'] = f'Phase {phase.phase_number} ("{phase.name}") is not yet complete.'

        return JsonResponse(result)


# ============================================================
# Phase 11.1 - Preflight Guard API Views
# ============================================================

class PreflightCheckAPIView(APIRateLimitMixin, View):
    """
    API endpoint to run preflight execution check.

    GET /api/admin/project/preflight/

    This is the mandatory preflight guard for Phase 11 execution.
    Must be called and pass before any task execution begins.

    Returns JSON object with:
    - success: bool - True if all preflight checks pass
    - errors: Array of error messages (empty if success=True)

    If preflight fails:
    - Execution must stop immediately
    - No task status changes should occur
    - No files should be modified

    Returns 403 if user is not admin.

    This endpoint is read-only and does NOT mutate data.

    Rate Limiting (CISO Review 2026-01-12):
        - 60 requests per minute
        - 500 requests per hour
    """

    rate_limit_requests_per_minute = 60
    rate_limit_requests_per_hour = 500
    rate_limit_key_prefix = 'admin_api'

    def get(self, request):
        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        from .services import preflight_execution_check
        result = preflight_execution_check()

        return JsonResponse({
            'success': result.success,
            'errors': result.errors
        })


class SeedPhasesAPIView(APIRateLimitMixin, View):
    """
    API endpoint to seed AdminProjectPhase data.

    POST /api/admin/project/seed-phases/

    Seeds phases 1-11 if the table is empty.
    This is idempotent and safe for production.

    Returns JSON object with:
    - seeded: bool - True if phases were created
    - phase_count: int - Number of phases now in database
    - message: str - Description of what happened

    Returns 403 if user is not admin.

    Rate Limiting (CISO Review 2026-01-12):
        - 10 requests per minute
        - 50 requests per hour
    """

    rate_limit_requests_per_minute = 10
    rate_limit_requests_per_hour = 50
    rate_limit_key_prefix = 'admin_api_seed'

    def post(self, request):
        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        from .services import seed_admin_project_phases
        result = seed_admin_project_phases(created_by='human')

        return JsonResponse(result)


# ============================================================
# Phase 13 - Inline Editing & Priority API Views
# ============================================================

class InlineStatusUpdateAPIView(View):
    """
    API endpoint for inline status updates.

    PATCH /api/admin/project/tasks/<id>/inline-status/

    This endpoint allows changing task status directly from the task list.
    All status values are allowed: backlog, ready, in_progress, blocked, done.

    Request body:
    {
        "status": "backlog" | "ready" | "in_progress" | "blocked" | "done",
        "reason": "optional reason (required for blocked status)"
    }

    Returns:
    - 200: Success with updated task info
    - 400: Invalid status or missing reason for blocked
    - 403: Permission denied (not admin)
    - 404: Task not found
    """

    # All status values are allowed
    ALLOWED_INLINE_STATUSES = ['backlog', 'ready', 'in_progress', 'blocked', 'done']

    def patch(self, request, pk):
        import json
        import logging
        from .models import AdminTask, AdminActivityLog

        logger = logging.getLogger(__name__)

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Get the task
        try:
            task = AdminTask.objects.select_related('phase').get(pk=pk)
        except AdminTask.DoesNotExist:
            return JsonResponse(
                {'error': 'Task not found'},
                status=404
            )

        # Parse request body
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {'error': 'Invalid JSON body'},
                status=400
            )

        # Get status from body
        new_status = body.get('status')
        if not new_status:
            return JsonResponse(
                {'error': 'Missing required field: status'},
                status=400
            )

        # Validate status is a valid choice
        if new_status not in self.ALLOWED_INLINE_STATUSES:
            return JsonResponse(
                {'error': f"Invalid status: {new_status}. "
                          f"Allowed values: {self.ALLOWED_INLINE_STATUSES}"},
                status=400
            )

        # Check for blocked status requiring a reason
        reason = body.get('reason', '')
        if new_status == 'blocked' and not reason:
            return JsonResponse(
                {'error': "Reason is required when setting status to 'blocked'."},
                status=400
            )

        try:
            # No change needed
            if task.status == new_status:
                return JsonResponse({
                    'success': True,
                    'task': {
                        'id': task.id,
                        'title': task.title,
                        'status': task.status,
                        'phase_number': task.phase.phase_number if task.phase else None
                    },
                    'changed': False
                })

            # Update the task
            old_status = task.status
            task.status = new_status

            # Handle blocked reason
            if new_status == 'blocked':
                task.blocked_reason = reason
            elif old_status == 'blocked':
                # Clear blocked reason when leaving blocked status
                task.blocked_reason = ''

            task.save()

            # Log the change
            log_action = f"Status changed from '{old_status}' to '{new_status}' via inline edit."
            if new_status == 'blocked' and reason:
                log_action += f" Reason: {reason}"
            AdminActivityLog.objects.create(
                task=task,
                action=log_action,
                created_by='human'
            )

            # Get ready count for warning
            ready_count = AdminTask.objects.filter(status='ready').count()

            return JsonResponse({
                'success': True,
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'status': task.status,
                    'phase_number': task.phase.phase_number if task.phase else None
                },
                'changed': True,
                'ready_count': ready_count,
                'show_warning': ready_count >= READY_TASKS_WARNING_THRESHOLD
            })
        except Exception as e:
            logger.exception(f"Error updating task {pk} status to {new_status}")
            return JsonResponse(
                {'error': f'Server error: {str(e)}'},
                status=500
            )


class InlinePriorityUpdateAPIView(View):
    """
    API endpoint for inline priority updates.

    PATCH /api/admin/project/tasks/<id>/inline-priority/

    Request body:
    {
        "priority": 1-5
    }

    Returns:
    - 200: Success with updated task info
    - 400: Invalid priority value
    - 403: Permission denied (not admin)
    - 404: Task not found
    """

    def patch(self, request, pk):
        import json
        from .models import AdminTask, AdminActivityLog

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

        # Get the task
        try:
            task = AdminTask.objects.select_related('phase').get(pk=pk)
        except AdminTask.DoesNotExist:
            return JsonResponse(
                {'error': 'Task not found'},
                status=404
            )

        # Parse request body
        try:
            body = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse(
                {'error': 'Invalid JSON body'},
                status=400
            )

        # Get priority from body
        new_priority = body.get('priority')
        if new_priority is None:
            return JsonResponse(
                {'error': 'Missing required field: priority'},
                status=400
            )

        # Validate priority is an integer 1-5
        try:
            new_priority = int(new_priority)
        except (ValueError, TypeError):
            return JsonResponse(
                {'error': 'Priority must be an integer'},
                status=400
            )

        if new_priority < 1 or new_priority > 5:
            return JsonResponse(
                {'error': 'Priority must be between 1 and 5'},
                status=400
            )

        # No change needed
        if task.priority == new_priority:
            return JsonResponse({
                'success': True,
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'priority': task.priority,
                    'phase_number': task.phase.phase_number
                },
                'changed': False
            })

        # Update the task
        old_priority = task.priority
        task.priority = new_priority
        task.save()

        # Log the change
        AdminActivityLog.objects.create(
            task=task,
            action=f"Priority changed from {old_priority} to {new_priority} via inline edit.",
            created_by='human'
        )

        return JsonResponse({
            'success': True,
            'task': {
                'id': task.id,
                'title': task.title,
                'priority': task.priority,
                'phase_number': task.phase.phase_number
            },
            'changed': True
        })


# ============================================================
# Phase 15: Projects Operator Runbook
# ============================================================

class ProjectsRunbookView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """
    Read-only Operator Runbook page for Projects.

    GET /admin-console/projects/help/

    This view displays a static runbook with:
    - What the Projects System Is
    - Daily Operating Workflow
    - Task Status Meanings
    - When Execution Stops
    - Golden Rules

    Safety rules:
    - Admin-only access (via AdminRequiredMixin)
    - Read-only content (no forms, no data modification)
    - Does not log activity
    - Does not auto-open
    """
    template_name = "admin_console/projects_runbook.html"
    help_context_id = "ADMIN_CONSOLE_PROJECTS_RUNBOOK"


# ============================================================
# Phase 16: Admin Project Views
# ============================================================

class AdminProjectListView(HelpContextMixin, AdminRequiredMixin, ListView):
    """
    List all admin projects with task counts.

    GET /admin-console/projects/

    Displays:
    - Project name
    - Status (open/complete)
    - Total tasks count
    - Completed tasks count
    """
    template_name = "admin_console/admin_project_list.html"
    context_object_name = "projects"
    help_context_id = "ADMIN_CONSOLE_PROJECTS"

    def get_queryset(self):
        from apps.admin_console.models import AdminProject
        from django.db.models import Count, Q

        return AdminProject.objects.annotate(
            total_tasks=Count('tasks'),
            completed_tasks=Count('tasks', filter=Q(tasks__status='done'))
        ).order_by('priority', 'name')


class AdminProjectDetailView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """
    Project detail page showing tasks grouped by phase.

    GET /admin-console/projects/<id>/

    Displays:
    - Project information (name, description, status)
    - Tasks grouped by phase number
    """
    template_name = "admin_console/admin_project_detail.html"
    help_context_id = "ADMIN_CONSOLE_PROJECT_DETAIL"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.admin_console.models import AdminProject, AdminTask
        from django.db.models import Count, Q
        from collections import defaultdict

        project_id = self.kwargs.get('pk')
        project = AdminProject.objects.annotate(
            total_tasks=Count('tasks'),
            completed_tasks=Count('tasks', filter=Q(tasks__status='done'))
        ).get(pk=project_id)

        context['project'] = project

        # Get all tasks for this project, grouped by phase
        tasks = AdminTask.objects.filter(project=project).select_related('phase').order_by(
            'phase__phase_number', 'priority', 'created_at'
        )

        # Group tasks by phase
        tasks_by_phase = defaultdict(list)
        for task in tasks:
            tasks_by_phase[task.phase].append(task)

        # Convert to list of tuples for template, sorted by phase number
        context['tasks_by_phase'] = sorted(
            tasks_by_phase.items(),
            key=lambda x: x[0].phase_number
        )

        return context


class AdminProjectCreateView(AdminRequiredMixin, CreateView):
    """
    Create a new admin project.

    GET /admin-console/projects/new/
    POST /admin-console/projects/new/

    Supports popup mode (?popup=1) for creating projects from Task Intake form.
    """
    template_name = "admin_console/admin_project_form.html"
    popup_template_name = "admin_console/admin_project_form_popup.html"
    success_url = reverse_lazy('admin_console:admin_project_list')

    def get_template_names(self):
        if self.request.GET.get('popup') == '1':
            return [self.popup_template_name]
        return [self.template_name]

    def get_form_class(self):
        from django import forms
        from apps.admin_console.models import AdminProject

        class AdminProjectForm(forms.ModelForm):
            class Meta:
                model = AdminProject
                fields = ['name', 'description', 'priority']
                widgets = {
                    'name': forms.TextInput(attrs={
                        'class': 'form-input',
                        'placeholder': 'e.g., Q1 Feature Development'
                    }),
                    'description': forms.Textarea(attrs={
                        'class': 'form-textarea',
                        'rows': 3,
                        'placeholder': 'Optional description of this project...'
                    }),
                    'priority': forms.Select(attrs={
                        'class': 'form-input'
                    }),
                }

        return AdminProjectForm

    def get_queryset(self):
        from apps.admin_console.models import AdminProject
        return AdminProject.objects.all()

    def form_valid(self, form):
        import logging
        logger = logging.getLogger(__name__)
        try:
            logger.info(f"AdminProjectCreateView.form_valid: Creating project with name='{form.cleaned_data.get('name')}'")
            # Save the form manually to get the object
            self.object = form.save()
            logger.info(f"AdminProjectCreateView.form_valid: Project created with pk={self.object.pk}")

            # For popup mode, we'll re-render the template with the created project
            # so it can notify the opener window
            if self.request.GET.get('popup') == '1':
                logger.info("AdminProjectCreateView.form_valid: Rendering popup response")
                return render(self.request, self.popup_template_name, {
                    'form': self.get_form_class()(),
                    'created_project': self.object
                })

            messages.success(self.request, f"Project '{self.object.name}' created.")
            return HttpResponseRedirect(self.get_success_url())
        except Exception as e:
            logger.exception(f"AdminProjectCreateView.form_valid: Error creating project: {e}")
            raise

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Check if we came from task intake
        context['from_intake'] = self.request.GET.get('from') == 'intake'
        # Check if this is a popup window
        context['is_popup'] = self.request.GET.get('popup') == '1'
        return context

    def get_success_url(self):
        # If popup mode, this won't be used (we render the template with JS to close)
        if self.request.GET.get('popup') == '1':
            return reverse_lazy('admin_console:admin_project_create') + '?popup=1'
        # If we came from task intake, go back there
        if self.request.GET.get('from') == 'intake':
            return reverse_lazy('admin_console:task_intake')
        return reverse_lazy('admin_console:admin_project_list')


class AdminProjectUpdateView(AdminRequiredMixin, UpdateView):
    """
    Edit an existing admin project.

    GET /admin-console/projects/<id>/edit/
    POST /admin-console/projects/<id>/edit/
    """
    template_name = "admin_console/admin_project_form.html"
    success_url = reverse_lazy('admin_console:admin_project_list')

    def get_form_class(self):
        from django import forms
        from apps.admin_console.models import AdminProject

        class AdminProjectForm(forms.ModelForm):
            class Meta:
                model = AdminProject
                fields = ['name', 'description', 'status', 'priority']
                widgets = {
                    'name': forms.TextInput(attrs={
                        'class': 'form-input',
                        'placeholder': 'e.g., Q1 Feature Development'
                    }),
                    'description': forms.Textarea(attrs={
                        'class': 'form-textarea',
                        'rows': 3,
                        'placeholder': 'Optional description of this project...'
                    }),
                    'status': forms.Select(attrs={
                        'class': 'form-input'
                    }),
                    'priority': forms.Select(attrs={
                        'class': 'form-input'
                    }),
                }

        return AdminProjectForm

    def get_queryset(self):
        from apps.admin_console.models import AdminProject
        return AdminProject.objects.all()

    def form_valid(self, form):
        messages.success(self.request, f"Project '{form.instance.name}' updated.")
        return super().form_valid(form)


class AdminProjectDeleteView(AdminRequiredMixin, DeleteView):
    """
    Delete an admin project.

    GET /admin-console/projects/<id>/delete/ - confirmation page
    POST /admin-console/projects/<id>/delete/ - actual deletion

    Safety: Projects with tasks cannot be deleted (enforced by model).
    """
    template_name = "admin_console/admin_project_confirm_delete.html"
    success_url = reverse_lazy('admin_console:admin_project_list')
    context_object_name = "project"

    def get_queryset(self):
        from apps.admin_console.models import AdminProject
        return AdminProject.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get task count for the confirmation message
        context['task_count'] = self.object.tasks.count()
        return context

    def form_valid(self, form):
        from apps.admin_console.models import DeletionProtectedError
        try:
            project_name = self.object.name
            response = super().form_valid(form)
            messages.success(self.request, f"Project '{project_name}' deleted.")
            return response
        except DeletionProtectedError as e:
            messages.error(self.request, str(e))
            return redirect('admin_console:admin_project_list')


# ============================================================
# Phase 17: Task Configuration Management Views
# ============================================================

class TaskConfigDashboardView(AdminRequiredMixin, TemplateView):
    """
    Dashboard for managing task field configurations.

    GET /admin-console/projects/config/

    Displays links to manage:
    - Status configurations
    - Priority configurations
    - Category configurations
    - Effort configurations
    """
    template_name = "admin_console/config/config_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import (
            AdminTaskStatusConfig, AdminTaskPriorityConfig,
            AdminTaskCategoryConfig, AdminTaskEffortConfig
        )

        context['status_count'] = AdminTaskStatusConfig.objects.count()
        context['priority_count'] = AdminTaskPriorityConfig.objects.count()
        context['category_count'] = AdminTaskCategoryConfig.objects.count()
        context['effort_count'] = AdminTaskEffortConfig.objects.count()

        return context


# ---- Status Config Views ----

class StatusConfigListView(AdminRequiredMixin, ListView):
    """List all status configurations."""
    template_name = "admin_console/config/status_list.html"
    context_object_name = "configs"

    def get_queryset(self):
        from .models import AdminTaskStatusConfig
        return AdminTaskStatusConfig.objects.all().order_by('order', 'name')


class StatusConfigCreateView(AdminRequiredMixin, CreateView):
    """Create a new status configuration."""
    template_name = "admin_console/config/status_form.html"
    fields = ['name', 'display_name', 'execution_allowed', 'terminal', 'order', 'active']
    success_url = reverse_lazy('admin_console:config_status_list')

    def get_queryset(self):
        from .models import AdminTaskStatusConfig
        return AdminTaskStatusConfig.objects.all()

    def get_form_class(self):
        from django import forms
        from .models import AdminTaskStatusConfig

        class StatusConfigForm(forms.ModelForm):
            class Meta:
                model = AdminTaskStatusConfig
                fields = ['name', 'display_name', 'execution_allowed', 'terminal', 'order', 'active']

        return StatusConfigForm

    def form_valid(self, form):
        messages.success(self.request, f"Status '{form.instance.display_name}' created.")
        return super().form_valid(form)


class StatusConfigUpdateView(AdminRequiredMixin, UpdateView):
    """Edit a status configuration."""
    template_name = "admin_console/config/status_form.html"
    fields = ['name', 'display_name', 'execution_allowed', 'terminal', 'order', 'active']
    success_url = reverse_lazy('admin_console:config_status_list')

    def get_queryset(self):
        from .models import AdminTaskStatusConfig
        return AdminTaskStatusConfig.objects.all()

    def form_valid(self, form):
        messages.success(self.request, f"Status '{form.instance.display_name}' updated.")
        return super().form_valid(form)


class StatusConfigDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a status configuration."""
    template_name = "admin_console/config/status_confirm_delete.html"
    success_url = reverse_lazy('admin_console:config_status_list')

    def get_queryset(self):
        from .models import AdminTaskStatusConfig
        return AdminTaskStatusConfig.objects.all()

    def form_valid(self, form):
        from .models import DeletionProtectedError
        try:
            config_name = self.object.display_name
            self.object.delete()
            messages.success(self.request, f"Status '{config_name}' deleted.")
            return redirect(self.success_url)
        except DeletionProtectedError as e:
            messages.error(self.request, str(e))
            return redirect('admin_console:config_status_list')


# ---- Priority Config Views ----

class PriorityConfigListView(AdminRequiredMixin, ListView):
    """List all priority configurations."""
    template_name = "admin_console/config/priority_list.html"
    context_object_name = "configs"

    def get_queryset(self):
        from .models import AdminTaskPriorityConfig
        return AdminTaskPriorityConfig.objects.all().order_by('order', 'value')


class PriorityConfigCreateView(AdminRequiredMixin, CreateView):
    """Create a new priority configuration."""
    template_name = "admin_console/config/priority_form.html"
    fields = ['value', 'label', 'order', 'active']
    success_url = reverse_lazy('admin_console:config_priority_list')

    def get_queryset(self):
        from .models import AdminTaskPriorityConfig
        return AdminTaskPriorityConfig.objects.all()

    def get_form_class(self):
        from django import forms
        from .models import AdminTaskPriorityConfig

        class PriorityConfigForm(forms.ModelForm):
            class Meta:
                model = AdminTaskPriorityConfig
                fields = ['value', 'label', 'order', 'active']

        return PriorityConfigForm

    def form_valid(self, form):
        messages.success(self.request, f"Priority '{form.instance.label}' created.")
        return super().form_valid(form)


class PriorityConfigUpdateView(AdminRequiredMixin, UpdateView):
    """Edit a priority configuration."""
    template_name = "admin_console/config/priority_form.html"
    fields = ['value', 'label', 'order', 'active']
    success_url = reverse_lazy('admin_console:config_priority_list')

    def get_queryset(self):
        from .models import AdminTaskPriorityConfig
        return AdminTaskPriorityConfig.objects.all()

    def form_valid(self, form):
        messages.success(self.request, f"Priority '{form.instance.label}' updated.")
        return super().form_valid(form)


class PriorityConfigDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a priority configuration."""
    template_name = "admin_console/config/priority_confirm_delete.html"
    success_url = reverse_lazy('admin_console:config_priority_list')

    def get_queryset(self):
        from .models import AdminTaskPriorityConfig
        return AdminTaskPriorityConfig.objects.all()

    def form_valid(self, form):
        from .models import DeletionProtectedError
        try:
            config_name = self.object.label
            self.object.delete()
            messages.success(self.request, f"Priority '{config_name}' deleted.")
            return redirect(self.success_url)
        except DeletionProtectedError as e:
            messages.error(self.request, str(e))
            return redirect('admin_console:config_priority_list')


# ---- Category Config Views ----

class CategoryConfigListView(AdminRequiredMixin, ListView):
    """List all category configurations."""
    template_name = "admin_console/config/category_list.html"
    context_object_name = "configs"

    def get_queryset(self):
        from .models import AdminTaskCategoryConfig
        return AdminTaskCategoryConfig.objects.all().order_by('order', 'name')


class CategoryConfigCreateView(AdminRequiredMixin, CreateView):
    """Create a new category configuration."""
    template_name = "admin_console/config/category_form.html"
    fields = ['name', 'display_name', 'order', 'active']
    success_url = reverse_lazy('admin_console:config_category_list')

    def get_queryset(self):
        from .models import AdminTaskCategoryConfig
        return AdminTaskCategoryConfig.objects.all()

    def get_form_class(self):
        from django import forms
        from .models import AdminTaskCategoryConfig

        class CategoryConfigForm(forms.ModelForm):
            class Meta:
                model = AdminTaskCategoryConfig
                fields = ['name', 'display_name', 'order', 'active']

        return CategoryConfigForm

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.display_name}' created.")
        return super().form_valid(form)


class CategoryConfigUpdateView(AdminRequiredMixin, UpdateView):
    """Edit a category configuration."""
    template_name = "admin_console/config/category_form.html"
    fields = ['name', 'display_name', 'order', 'active']
    success_url = reverse_lazy('admin_console:config_category_list')

    def get_queryset(self):
        from .models import AdminTaskCategoryConfig
        return AdminTaskCategoryConfig.objects.all()

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.instance.display_name}' updated.")
        return super().form_valid(form)


class CategoryConfigDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a category configuration."""
    template_name = "admin_console/config/category_confirm_delete.html"
    success_url = reverse_lazy('admin_console:config_category_list')

    def get_queryset(self):
        from .models import AdminTaskCategoryConfig
        return AdminTaskCategoryConfig.objects.all()

    def form_valid(self, form):
        from .models import DeletionProtectedError
        try:
            config_name = self.object.display_name
            self.object.delete()
            messages.success(self.request, f"Category '{config_name}' deleted.")
            return redirect(self.success_url)
        except DeletionProtectedError as e:
            messages.error(self.request, str(e))
            return redirect('admin_console:config_category_list')


# ---- Effort Config Views ----

class EffortConfigListView(AdminRequiredMixin, ListView):
    """List all effort configurations."""
    template_name = "admin_console/config/effort_list.html"
    context_object_name = "configs"

    def get_queryset(self):
        from .models import AdminTaskEffortConfig
        return AdminTaskEffortConfig.objects.all().order_by('order', 'value')


class EffortConfigCreateView(AdminRequiredMixin, CreateView):
    """Create a new effort configuration."""
    template_name = "admin_console/config/effort_form.html"
    fields = ['value', 'label', 'order', 'active']
    success_url = reverse_lazy('admin_console:config_effort_list')

    def get_queryset(self):
        from .models import AdminTaskEffortConfig
        return AdminTaskEffortConfig.objects.all()

    def get_form_class(self):
        from django import forms
        from .models import AdminTaskEffortConfig

        class EffortConfigForm(forms.ModelForm):
            class Meta:
                model = AdminTaskEffortConfig
                fields = ['value', 'label', 'order', 'active']

        return EffortConfigForm

    def form_valid(self, form):
        messages.success(self.request, f"Effort '{form.instance.label}' created.")
        return super().form_valid(form)


class EffortConfigUpdateView(AdminRequiredMixin, UpdateView):
    """Edit an effort configuration."""
    template_name = "admin_console/config/effort_form.html"
    fields = ['value', 'label', 'order', 'active']
    success_url = reverse_lazy('admin_console:config_effort_list')

    def get_queryset(self):
        from .models import AdminTaskEffortConfig
        return AdminTaskEffortConfig.objects.all()

    def form_valid(self, form):
        messages.success(self.request, f"Effort '{form.instance.label}' updated.")
        return super().form_valid(form)


class EffortConfigDeleteView(AdminRequiredMixin, DeleteView):
    """Delete an effort configuration."""
    template_name = "admin_console/config/effort_confirm_delete.html"
    success_url = reverse_lazy('admin_console:config_effort_list')

    def get_queryset(self):
        from .models import AdminTaskEffortConfig
        return AdminTaskEffortConfig.objects.all()

    def form_valid(self, form):
        from .models import DeletionProtectedError
        try:
            config_name = self.object.label
            self.object.delete()
            messages.success(self.request, f"Effort '{config_name}' deleted.")
            return redirect(self.success_url)
        except DeletionProtectedError as e:
            messages.error(self.request, str(e))
            return redirect('admin_console:config_effort_list')


# ==============================================================================
# Claude Code API - Ready Tasks Endpoint
# ==============================================================================

class ReadyTasksAPIView(APIRateLimitMixin, View):
    """
    API endpoint for Claude Code to fetch tasks with 'ready' status.

    This endpoint is used by Claude Code's "What's Next?" protocol to
    automatically discover and execute ready tasks.

    Authentication:
        Requires CLAUDE_API_KEY header matching settings.CLAUDE_API_KEY

    Rate Limiting (CISO Review 2026-01-12):
        - 60 requests per minute
        - 500 requests per hour

    GET /admin-console/api/claude/ready-tasks/
    Query params:
        - limit (optional, default 10): Maximum tasks to return
        - auto_start (optional): If 'true', automatically marks top phase+priority tasks as 'in_progress'
        - include_in_progress (optional): If 'true', also returns tasks with 'in_progress' status

    Returns:
        JSON object with:
        - count: Number of ready tasks
        - tasks: Array of task objects with full executable description

    Example response:
        {
            "count": 1,
            "tasks": [{
                "id": 123,
                "title": "Update CLAUDE.md with Executable Task Standard",
                "phase": "Phase 1",
                "priority": 1,
                "project": "WLJ Executable Work Orchestration System",
                "description": {
                    "objective": "Define a permanent system-level standard...",
                    "inputs": ["CLAUDE.md file in the project root"],
                    "actions": ["Open the CLAUDE.md file", "Add a section..."],
                    "output": "CLAUDE.md contains a clearly documented..."
                },
                "attachment_url": "https://wholelifejourney.com/media/admin_tasks/attachments/screenshot.png"
            }]
        }

    Note: attachment_url will be null if no attachment is present.
    """

    # Rate limiting configuration (CISO Review 2026-01-12)
    rate_limit_requests_per_minute = 60
    rate_limit_requests_per_hour = 500
    rate_limit_key_prefix = 'admin_api_claude'

    def get(self, request):
        from django.conf import settings
        from .models import AdminTask
        from apps.core.rate_limiting import secure_compare_api_key

        # Authenticate via API key (CISO Review 2026-01-12: use constant-time comparison)
        api_key = request.headers.get('X-Claude-API-Key', '')

        # Check if API key is configured
        if not settings.CLAUDE_API_KEY:
            return JsonResponse(
                {'error': 'CLAUDE_API_KEY not configured on server'},
                status=500
            )

        # Validate API key using constant-time comparison to prevent timing attacks
        if not secure_compare_api_key(api_key, settings.CLAUDE_API_KEY):
            return JsonResponse(
                {'error': 'Invalid or missing API key. Include X-Claude-API-Key header.'},
                status=401
            )

        # Get limit from query params
        try:
            limit = int(request.GET.get('limit', 10))
            if limit < 1:
                limit = 10
            elif limit > 50:
                limit = 50
        except (ValueError, TypeError):
            limit = 10

        # Check for auto_start parameter
        auto_start = request.GET.get('auto_start', '').lower() == 'true'

        # Check for include_in_progress parameter (for /run-task to find started tasks)
        include_in_progress = request.GET.get('include_in_progress', '').lower() == 'true'

        # Determine which statuses to include
        statuses = ['ready']
        if include_in_progress:
            statuses.append('in_progress')

        # Fetch ready tasks using project priority rules:
        # 1. Project Priority (1 = highest, 10 = lowest)
        # 2. Phase (ascending by phase_number)
        # 3. Task Priority (highest first = lowest number)
        # 4. Create Date (oldest first)
        # 5. Task ID (tie-breaker)
        # Note: No project status filter - task status is what matters
        tasks = list(AdminTask.objects.filter(
            status__in=statuses,
        ).select_related(
            'phase', 'project'
        ).order_by(
            'project__priority',  # Project priority first
            'phase__phase_number',  # Then phase
            'priority',  # Then task priority
            'created_at',  # Then oldest first
            'id'  # Tie-breaker
        )[:limit])

        # If auto_start is true and we have tasks, mark ALL tasks at the top
        # phase+priority level as in_progress (enables parallel execution)
        started_task_ids = []
        if auto_start and tasks:
            # Get the phase and priority of the first (highest priority) task
            top_phase = tasks[0].phase_id
            top_priority = tasks[0].priority

            # Mark all tasks at this phase+priority as in_progress
            for task in tasks:
                if task.phase_id == top_phase and task.priority == top_priority:
                    task.status = 'in_progress'
                    task.save(update_fields=['status'])
                    started_task_ids.append(task.id)
                else:
                    # Tasks are ordered, so once we hit a different phase/priority, stop
                    break

        # Build response with full executable task structure
        result = {
            'count': len(tasks),
            'auto_started': started_task_ids if started_task_ids else None,
            'tasks': [
                {
                    'id': task.id,
                    'title': task.title,
                    'phase': str(task.phase),
                    'priority': task.priority,
                    'project': task.project.name,
                    'description': task.description,
                    'created_at': task.created_at.isoformat(),
                    'status': task.status,
                    'attachment_url': request.build_absolute_uri(task.attachment.url) if task.attachment else None,
                }
                for task in tasks
            ]
        }

        return JsonResponse(result)


from django.views.decorators.csrf import csrf_exempt


@method_decorator(csrf_exempt, name='dispatch')
class UpdateTaskStatusAPIView(APIRateLimitMixin, View):
    """
    API endpoint for Claude Code to update task status.

    This endpoint allows Claude Code to mark tasks as done or change status
    after completing work on them.

    Authentication:
        Requires CLAUDE_API_KEY header matching settings.CLAUDE_API_KEY

    Rate Limiting (CISO Review 2026-01-12):
        - 60 requests per minute
        - 500 requests per hour

    POST /admin-console/api/claude/tasks/<id>/status/
    Body (JSON):
        - status: New status value (e.g., 'done', 'in_progress', 'blocked')
        - reason: Optional reason (required for 'blocked' status)
        - notes: Optional resolution notes documenting what was done (for 'done' status)

    Returns:
        JSON object with success status and updated task info
    """

    # Rate limiting configuration (CISO Review 2026-01-12)
    rate_limit_requests_per_minute = 60
    rate_limit_requests_per_hour = 500
    rate_limit_key_prefix = 'admin_api_claude'

    def post(self, request, pk):
        import json
        from django.conf import settings
        from .models import AdminTask, TaskStatusTransitionError
        from apps.core.rate_limiting import secure_compare_api_key

        # Authenticate via API key (CISO Review 2026-01-12: use constant-time comparison)
        api_key = request.headers.get('X-Claude-API-Key', '')

        # Check if API key is configured
        if not settings.CLAUDE_API_KEY:
            return JsonResponse(
                {'error': 'CLAUDE_API_KEY not configured on server'},
                status=500
            )

        # Validate API key using constant-time comparison to prevent timing attacks
        if not secure_compare_api_key(api_key, settings.CLAUDE_API_KEY):
            return JsonResponse(
                {'error': 'Invalid or missing API key. Include X-Claude-API-Key header.'},
                status=401
            )

        # Get the task
        try:
            task = AdminTask.objects.get(pk=pk)
        except AdminTask.DoesNotExist:
            return JsonResponse(
                {'error': f'Task with id {pk} not found'},
                status=404
            )

        # Parse request body
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse(
                {'error': 'Invalid JSON in request body'},
                status=400
            )

        new_status = data.get('status')
        reason = data.get('reason', '')
        resolution_notes = data.get('notes', '')  # What was done to complete the task

        if not new_status:
            return JsonResponse(
                {'error': 'Missing required field: status'},
                status=400
            )

        # Validate status value
        valid_statuses = [s[0] for s in AdminTask.STATUS_CHOICES]
        if new_status not in valid_statuses:
            return JsonResponse(
                {'error': f'Invalid status: {new_status}. Valid values: {valid_statuses}'},
                status=400
            )

        # Attempt the status transition
        try:
            old_status = task.status
            task.transition_status(
                new_status,
                reason=reason,
                created_by='claude',
                resolution_notes=resolution_notes if new_status == 'done' else None
            )

            return JsonResponse({
                'success': True,
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'old_status': old_status,
                    'new_status': task.status,
                    'resolution_notes': task.resolution_notes if new_status == 'done' else None,
                }
            })

        except TaskStatusTransitionError as e:
            return JsonResponse(
                {'error': str(e)},
                status=400
            )


# ==============================================================================
# Data Load Configuration Management
# ==============================================================================

class DataLoadConfigListView(AdminRequiredMixin, ListView):
    """List all data loaders and their status."""
    template_name = "admin_console/dataload/list.html"
    context_object_name = "loaders"

    def get_queryset(self):
        from .models import DataLoadConfig
        return DataLoadConfig.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import DataLoadConfig
        context['loaded_count'] = DataLoadConfig.objects.filter(is_loaded=True).count()
        context['total_count'] = DataLoadConfig.objects.count()
        context['dataload_output'] = self.request.session.pop('dataload_output', None)
        return context


class DataLoadConfigResetView(AdminRequiredMixin, View):
    """Reset a specific data loader so it runs again on next deploy."""

    def post(self, request, pk):
        from .models import DataLoadConfig

        try:
            config = DataLoadConfig.objects.get(pk=pk)
            loader_name = config.display_name
            config.reset()
            messages.success(request, f"Reset '{loader_name}'. It will reload on next deploy.")
        except DataLoadConfig.DoesNotExist:
            messages.error(request, "Data loader not found.")

        return redirect('admin_console:dataload_list')


class DataLoadConfigResetAllView(AdminRequiredMixin, View):
    """Reset all data loaders."""

    def post(self, request):
        from .models import DataLoadConfig

        count = DataLoadConfig.objects.filter(is_loaded=True).update(
            is_loaded=False,
            loaded_at=None,
            loaded_by='',
            records_created=0,
            records_updated=0,
        )
        messages.success(request, f"Reset {count} data loaders. They will reload on next deploy.")
        return redirect('admin_console:dataload_list')


class DataLoadConfigForceRunView(AdminRequiredMixin, View):
    """Force run load_initial_data command from admin console."""

    def post(self, request):
        from django.core.management import call_command
        from io import StringIO

        output = StringIO()
        try:
            force = request.POST.get('force') == 'true'
            if force:
                call_command('load_initial_data', '--force', stdout=output)
            else:
                call_command('load_initial_data', stdout=output)

            messages.success(request, "Data load completed successfully.")
            # Store output in session for display
            request.session['dataload_output'] = output.getvalue()
        except Exception as e:
            messages.error(request, f"Data load failed: {e}")
            request.session['dataload_output'] = f"Error: {e}\n{output.getvalue()}"

        return redirect('admin_console:dataload_list')


class ClarityImportView(AdminRequiredMixin, View):
    """
    Import Dexcom Clarity CSV export into GlucoseEntry records.

    Provides a web UI for uploading Clarity CSV files and importing
    glucose readings for a specified user.
    """
    template_name = "admin_console/clarity_import.html"

    def get(self, request):
        from apps.users.models import User
        users = User.objects.filter(is_active=True).order_by('email')
        return render(request, self.template_name, {'users': users})

    def post(self, request):
        import csv
        from datetime import datetime
        from decimal import Decimal, InvalidOperation
        from io import StringIO
        from django.utils import timezone
        from apps.users.models import User
        from apps.health.models import GlucoseEntry

        # Get form data
        user_id = request.POST.get('user_id')
        csv_file = request.FILES.get('csv_file')
        dry_run = request.POST.get('dry_run') == 'on'

        users = User.objects.filter(is_active=True).order_by('email')
        context = {'users': users}

        # Validate inputs
        if not user_id:
            messages.error(request, "Please select a user.")
            return render(request, self.template_name, context)

        if not csv_file:
            messages.error(request, "Please upload a CSV file.")
            return render(request, self.template_name, context)

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            messages.error(request, "Selected user not found.")
            return render(request, self.template_name, context)

        # Read and parse CSV
        try:
            # Handle BOM and decode file
            content = csv_file.read().decode('utf-8-sig')
            reader = csv.DictReader(StringIO(content))
            rows = list(reader)
        except Exception as e:
            messages.error(request, f"Error reading CSV file: {e}")
            return render(request, self.template_name, context)

        # Filter to EGV (Estimated Glucose Value) rows only
        egv_rows = [
            row for row in rows
            if row.get('Event Type') == 'EGV' and row.get('Glucose Value (mg/dL)')
        ]

        if not egv_rows:
            messages.warning(request, f"No glucose (EGV) readings found in the CSV file. Total rows: {len(rows)}")
            return render(request, self.template_name, context)

        # Get existing timestamps to avoid duplicates
        existing_timestamps = set(
            GlucoseEntry.objects.filter(
                user=user,
                source='imported'
            ).values_list('recorded_at', flat=True)
        )

        # Parse and prepare entries
        entries_to_create = []
        skipped_duplicates = 0
        skipped_invalid = 0

        for row in egv_rows:
            try:
                # Parse timestamp (format: YYYY-MM-DDThh:mm:ss)
                timestamp_str = row.get('Timestamp (YYYY-MM-DDThh:mm:ss)', '')
                if not timestamp_str:
                    skipped_invalid += 1
                    continue

                # Parse the timestamp and make it timezone-aware
                dt = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S')
                recorded_at = timezone.make_aware(dt, timezone.get_current_timezone())

                # Check for duplicate
                if recorded_at in existing_timestamps:
                    skipped_duplicates += 1
                    continue

                # Parse glucose value
                glucose_str = row.get('Glucose Value (mg/dL)', '')
                if not glucose_str:
                    skipped_invalid += 1
                    continue

                glucose_value = Decimal(glucose_str)

                # Create entry object (don't save yet)
                entry = GlucoseEntry(
                    user=user,
                    value=glucose_value,
                    unit='mg/dL',
                    context='cgm',
                    recorded_at=recorded_at,
                    source='imported',
                    notes='Imported from Dexcom Clarity CSV'
                )
                entries_to_create.append(entry)
                existing_timestamps.add(recorded_at)  # Track to avoid duplicates within file

            except (ValueError, KeyError, InvalidOperation):
                skipped_invalid += 1
                continue

        # Build summary
        summary = {
            'total_rows': len(rows),
            'egv_rows': len(egv_rows),
            'to_import': len(entries_to_create),
            'duplicates': skipped_duplicates,
            'invalid': skipped_invalid,
            'dry_run': dry_run,
        }

        if entries_to_create:
            min_date = min(e.recorded_at for e in entries_to_create)
            max_date = max(e.recorded_at for e in entries_to_create)
            values = [float(e.value) for e in entries_to_create]
            summary['date_range'] = f"{min_date.date()} to {max_date.date()}"
            summary['avg_glucose'] = f"{sum(values) / len(values):.1f}"
            summary['min_glucose'] = f"{min(values):.0f}"
            summary['max_glucose'] = f"{max(values):.0f}"

        context['summary'] = summary
        context['selected_user'] = user

        if dry_run:
            messages.info(request, f"DRY RUN: Would import {len(entries_to_create)} glucose entries for {user.email}")
        elif entries_to_create:
            # Bulk create entries
            from django.db import transaction
            with transaction.atomic():
                GlucoseEntry.objects.bulk_create(entries_to_create, batch_size=1000)
            # Invalidate cache since bulk_create bypasses Django signals
            from assistant.data_service import invalidate_user_data_cache
            invalidate_user_data_cache(user.id, 'glucose')
            messages.success(request, f"Successfully imported {len(entries_to_create)} glucose entries for {user.email}")
        else:
            messages.warning(request, "No new entries to import (all were duplicates or invalid)")

        return render(request, self.template_name, context)


class ProjectImportView(AdminRequiredMixin, View):
    """
    Import Project Management JSON export into AdminProject, AdminProjectPhase, and AdminTask records.

    Provides a web UI for uploading JSON files that define projects with phases and tasks
    following the WLJ Executable Task Standard.
    """
    template_name = "admin_console/project_import.html"

    def get(self, request):
        from .models import AdminProject
        projects = AdminProject.objects.filter(status='open').order_by('name')
        return render(request, self.template_name, {'existing_projects': projects})

    def post(self, request):
        import json
        from django.db import transaction
        from .models import AdminProject, AdminProjectPhase, AdminTask

        # Get form data
        json_file = request.FILES.get('json_file')
        dry_run = request.POST.get('dry_run') == 'on'

        projects = AdminProject.objects.filter(status='open').order_by('name')
        context = {'existing_projects': projects}

        # Validate inputs
        if not json_file:
            messages.error(request, "Please upload a JSON file.")
            return render(request, self.template_name, context)

        # Read and parse JSON
        try:
            content = json_file.read().decode('utf-8')
            data = json.loads(content)
        except json.JSONDecodeError as e:
            messages.error(request, f"Invalid JSON file: {e}")
            return render(request, self.template_name, context)
        except Exception as e:
            messages.error(request, f"Error reading file: {e}")
            return render(request, self.template_name, context)

        # Validate JSON structure
        if 'project' not in data:
            messages.error(request, "JSON must contain a 'project' object with 'name' and 'description'.")
            return render(request, self.template_name, context)

        if 'tasks' not in data:
            messages.error(request, "JSON must contain a 'tasks' array.")
            return render(request, self.template_name, context)

        project_data = data['project']
        tasks_data = data['tasks']

        if not project_data.get('name'):
            messages.error(request, "Project must have a 'name'.")
            return render(request, self.template_name, context)

        # Check for duplicate project name
        if AdminProject.objects.filter(name=project_data['name']).exists():
            messages.error(request, f"A project with name '{project_data['name']}' already exists.")
            return render(request, self.template_name, context)

        # Parse tasks and collect phase information
        phases_needed = set()
        valid_tasks = []
        invalid_tasks = []

        for idx, task in enumerate(tasks_data, 1):
            # Validate required task fields
            errors = []

            if not task.get('name'):
                errors.append("missing 'name'")

            if not task.get('phase'):
                errors.append("missing 'phase'")

            if not task.get('description'):
                errors.append("missing 'description'")
            else:
                desc = task['description']
                if not isinstance(desc, dict):
                    errors.append("'description' must be an object")
                else:
                    if not desc.get('objective'):
                        errors.append("description missing 'objective'")
                    if 'inputs' not in desc:
                        errors.append("description missing 'inputs'")
                    if not desc.get('actions') or not isinstance(desc.get('actions'), list):
                        errors.append("description must have 'actions' array with at least one item")
                    if not desc.get('output'):
                        errors.append("description missing 'output'")

            if errors:
                invalid_tasks.append({
                    'index': idx,
                    'name': task.get('name', f'Task {idx}'),
                    'errors': errors
                })
            else:
                phases_needed.add(task['phase'])
                valid_tasks.append(task)

        # Build summary
        summary = {
            'project_name': project_data['name'],
            'project_description': project_data.get('description', ''),
            'total_tasks': len(tasks_data),
            'valid_tasks': len(valid_tasks),
            'invalid_tasks': len(invalid_tasks),
            'phases': sorted(phases_needed),
            'dry_run': dry_run,
            'invalid_task_details': invalid_tasks[:10],  # Show first 10 invalid
        }

        # Group tasks by phase for display
        tasks_by_phase = {}
        for task in valid_tasks:
            phase = task['phase']
            if phase not in tasks_by_phase:
                tasks_by_phase[phase] = []
            tasks_by_phase[phase].append(task['name'])
        summary['tasks_by_phase'] = dict(sorted(tasks_by_phase.items()))

        context['summary'] = summary

        if invalid_tasks and not dry_run:
            messages.error(request, f"Cannot import: {len(invalid_tasks)} task(s) have validation errors.")
            return render(request, self.template_name, context)

        if dry_run:
            messages.info(request, f"DRY RUN: Would create project '{project_data['name']}' with {len(valid_tasks)} tasks in {len(phases_needed)} phase(s)")
            return render(request, self.template_name, context)

        # Actually create the records
        if not valid_tasks:
            messages.warning(request, "No valid tasks to import.")
            return render(request, self.template_name, context)

        try:
            with transaction.atomic():
                # Create the project
                project = AdminProject.objects.create(
                    name=project_data['name'],
                    description=project_data.get('description', ''),
                    status='open',
                    priority=5
                )

                # Create or get phases
                phase_objects = {}
                for phase_name in phases_needed:
                    # Extract phase number from name like "Phase 1" or "Phase 2"
                    phase_num = None
                    if phase_name.lower().startswith('phase '):
                        try:
                            phase_num = int(phase_name.split()[1])
                        except (ValueError, IndexError):
                            pass

                    if phase_num is None:
                        # Generate next phase number
                        max_phase = AdminProjectPhase.objects.aggregate(
                            max_num=models.Max('phase_number')
                        )['max_num'] or 0
                        phase_num = max_phase + 1

                    # Check if phase exists
                    phase, created = AdminProjectPhase.objects.get_or_create(
                        phase_number=phase_num,
                        defaults={
                            'name': phase_name,
                            'objective': f'Tasks from imported project: {project_data["name"]}',
                            'status': 'not_started'
                        }
                    )
                    phase_objects[phase_name] = phase

                # Create tasks
                tasks_created = 0
                for task in valid_tasks:
                    # Map status
                    status_map = {
                        'New': 'backlog',
                        'Backlog': 'backlog',
                        'Ready': 'ready',
                        'In Progress': 'in_progress',
                        'Blocked': 'blocked',
                        'Done': 'done',
                    }
                    status = status_map.get(task.get('status', 'New'), 'backlog')

                    # Map effort
                    effort_map = {
                        'Low': 'S',
                        'Small': 'S',
                        'Medium': 'M',
                        'High': 'L',
                        'Large': 'L',
                    }
                    effort = effort_map.get(task.get('effort', 'Medium'), 'M')

                    # Map priority
                    priority_map = {
                        'High': 1,
                        'Medium': 2,
                        'Low': 3,
                    }
                    priority = priority_map.get(task.get('priority', 'Medium'), 2)

                    AdminTask.objects.create(
                        title=task['name'],
                        description=task['description'],
                        category='feature',
                        priority=priority,
                        status=status,
                        effort=effort,
                        phase=phase_objects[task['phase']],
                        project=project,
                        created_by='human'
                    )
                    tasks_created += 1

                messages.success(
                    request,
                    f"Successfully imported project '{project_data['name']}' with {tasks_created} tasks in {len(phases_needed)} phase(s)"
                )

        except Exception as e:
            messages.error(request, f"Error creating records: {e}")
            return render(request, self.template_name, context)

        return render(request, self.template_name, context)


# ==============================================================================
# Email Intake API (for Claude Code /process-emails command)
# ==============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class ProcessEmailsAPIView(APIRateLimitMixin, View):
    """
    API endpoint for Claude Code to trigger email intake processing.

    This endpoint allows Claude Code to poll the Automate folder for new emails
    and create AdminTasks from them, without needing Railway console access.

    Authentication:
        Requires CLAUDE_API_KEY header matching settings.CLAUDE_API_KEY

    Rate Limiting:
        - 10 requests per minute (email processing is expensive)
        - 60 requests per hour

    POST /admin-console/api/claude/process-emails/
    Query params:
        - dry_run (optional): If 'true', don't create tasks or move emails

    Returns:
        JSON object with:
        - success: Boolean indicating success
        - processed: Number of emails processed
        - tasks_created: Array of created task info
        - errors: Array of error messages if any
    """

    rate_limit_requests_per_minute = 10
    rate_limit_requests_per_hour = 60
    rate_limit_key_prefix = 'admin_api_email_intake'

    def post(self, request):
        from django.conf import settings
        from apps.core.rate_limiting import secure_compare_api_key
        from .email_intake import process_email_intake, EmailIntakeError

        # Authenticate via API key
        api_key = request.headers.get('X-Claude-API-Key', '')

        if not settings.CLAUDE_API_KEY:
            return JsonResponse(
                {'error': 'CLAUDE_API_KEY not configured on server'},
                status=500
            )

        if not secure_compare_api_key(api_key, settings.CLAUDE_API_KEY):
            return JsonResponse(
                {'error': 'Invalid or missing API key. Include X-Claude-API-Key header.'},
                status=401
            )

        # Check parameters
        dry_run = request.GET.get('dry_run', '').lower() == 'true'
        diagnose = request.GET.get('diagnose', '').lower() == 'true'

        # max_emails: batch size to avoid Cloudflare 524 timeouts (default 10)
        try:
            max_emails = int(request.GET.get('max_emails', '10'))
            max_emails = max(0, min(max_emails, 50))  # Clamp 0-50
        except (ValueError, TypeError):
            max_emails = 10

        # Diagnose mode: check settings and IMAP connectivity without processing
        if diagnose:
            return self._diagnose()

        try:
            results = process_email_intake(dry_run=dry_run, max_emails=max_emails)

            return JsonResponse({
                'success': True,
                'dry_run': dry_run,
                'processed': results['processed'],
                'errors_count': results['errors'],
                'tasks_created': results['tasks_created'],
                'error_messages': results['error_messages'],
                'total_found': results.get('total_found', results['processed']),
                'remaining': results.get('remaining', 0),
            })

        except EmailIntakeError as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
            }, status=500)
        except Exception as e:
            logger.exception("Unexpected error in email intake API")
            return JsonResponse({
                'success': False,
                'error': f'Unexpected error: {str(e)}',
            }, status=500)

    def _diagnose(self):
        """Run diagnostics on email intake configuration and IMAP connectivity."""
        from .email_intake import (
            get_email_settings, connect_imap, list_imap_folders,
            EmailIntakeError, EmailConnectionError,
        )

        diag = {
            'settings_ok': False,
            'settings_detail': {},
            'connection_ok': False,
            'connection_detail': '',
            'folders': [],
            'automate_folder_exists': False,
            'automate_email_count': 0,
        }

        # Check settings
        try:
            config = get_email_settings()
            diag['settings_ok'] = True
            diag['settings_detail'] = {
                'host': config['host'],
                'port': config['port'],
                'user': config['user'],
                'password_set': bool(config['password']),
            }
        except EmailIntakeError as e:
            diag['settings_detail'] = {'error': str(e)}
            return JsonResponse({'success': True, 'diagnose': diag})

        # Check connection
        imap = None
        try:
            imap = connect_imap()
            diag['connection_ok'] = True
            diag['connection_detail'] = 'Connected and authenticated'

            # List folders
            folders = list_imap_folders(imap)
            diag['folders'] = folders

            # Check for Automate folder specifically
            automate_variants = ['INBOX/Automate', 'INBOX.Automate', 'Automate']
            for variant in automate_variants:
                try:
                    status, data = imap.select(f'"{variant}"')
                    if status == 'OK':
                        diag['automate_folder_exists'] = True
                        diag['automate_folder_name'] = variant
                        # Count emails
                        s, d = imap.uid('search', None, 'ALL')
                        if s == 'OK' and d[0]:
                            diag['automate_email_count'] = len(d[0].split())
                        break
                except Exception:
                    continue

        except EmailConnectionError as e:
            diag['connection_detail'] = str(e)
        except Exception as e:
            diag['connection_detail'] = f'Unexpected: {str(e)}'
        finally:
            if imap:
                try:
                    imap.close()
                    imap.logout()
                except Exception:
                    pass

        return JsonResponse({'success': True, 'diagnose': diag})


# =============================================================================
# System Announcements
# =============================================================================

class SystemAnnouncementListView(HelpContextMixin, AdminRequiredMixin, ListView):
    """List all system announcements."""
    template_name = "admin_console/system_announcement_list.html"
    context_object_name = "announcements"
    help_context_id = "ADMIN_CONSOLE_ANNOUNCEMENTS"

    def get_queryset(self):
        from .models import SystemAnnouncement
        return SystemAnnouncement.objects.all().order_by('-starts_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.utils import timezone
        context['now'] = timezone.now()
        return context


class SystemAnnouncementCreateView(AdminRequiredMixin, CreateView):
    """Create a new system announcement."""
    template_name = "admin_console/system_announcement_form.html"
    success_url = reverse_lazy('admin_console:system_announcement_list')

    def get_form_class(self):
        from django import forms
        from .models import SystemAnnouncement

        class SystemAnnouncementForm(forms.ModelForm):
            class Meta:
                model = SystemAnnouncement
                fields = ['title', 'message', 'severity', 'starts_at', 'ends_at', 'is_published']
                widgets = {
                    'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Announcement title'}),
                    'message': forms.Textarea(attrs={'class': 'form-input', 'rows': 5, 'placeholder': 'Enter your message...'}),
                    'severity': forms.Select(attrs={'class': 'form-input'}),
                    'starts_at': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
                    'ends_at': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
                    'is_published': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
                }

        return SystemAnnouncementForm

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Announcement created successfully.")
        return super().form_valid(form)


class SystemAnnouncementUpdateView(AdminRequiredMixin, UpdateView):
    """Edit an existing system announcement."""
    template_name = "admin_console/system_announcement_form.html"
    success_url = reverse_lazy('admin_console:system_announcement_list')
    context_object_name = 'announcement'

    def get_queryset(self):
        from .models import SystemAnnouncement
        return SystemAnnouncement.objects.all()

    def get_form_class(self):
        from django import forms
        from .models import SystemAnnouncement

        class SystemAnnouncementForm(forms.ModelForm):
            class Meta:
                model = SystemAnnouncement
                fields = ['title', 'message', 'severity', 'starts_at', 'ends_at', 'is_published']
                widgets = {
                    'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Announcement title'}),
                    'message': forms.Textarea(attrs={'class': 'form-input', 'rows': 5, 'placeholder': 'Enter your message...'}),
                    'severity': forms.Select(attrs={'class': 'form-input'}),
                    'starts_at': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
                    'ends_at': forms.DateTimeInput(attrs={'class': 'form-input', 'type': 'datetime-local'}),
                    'is_published': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
                }

        return SystemAnnouncementForm

    def form_valid(self, form):
        messages.success(self.request, "Announcement updated successfully.")
        return super().form_valid(form)


class SystemAnnouncementDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a system announcement."""
    template_name = "admin_console/system_announcement_confirm_delete.html"
    success_url = reverse_lazy('admin_console:system_announcement_list')
    context_object_name = 'announcement'

    def get_queryset(self):
        from .models import SystemAnnouncement
        return SystemAnnouncement.objects.all()

    def form_valid(self, form):
        messages.success(self.request, "Announcement deleted.")
        return super().form_valid(form)


class SystemAnnouncementDismissAPIView(APIRateLimitMixin, View):
    """
    API endpoint for users to dismiss an announcement.

    POST /api/announcements/<id>/dismiss/
    """
    rate_limit_action = "announcement_dismiss"

    def post(self, request, pk):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        from .models import SystemAnnouncement, SystemAnnouncementDismissal

        try:
            announcement = SystemAnnouncement.objects.get(pk=pk)
        except SystemAnnouncement.DoesNotExist:
            return JsonResponse({'error': 'Announcement not found'}, status=404)

        # Create dismissal record (ignore if already exists)
        SystemAnnouncementDismissal.objects.get_or_create(
            user=request.user,
            announcement=announcement
        )

        return JsonResponse({'success': True})


# ==============================================================================
# Test Plan Views
# ==============================================================================


class TestCycleListView(HelpContextMixin, AdminRequiredMixin, ListView):
    """List all test cycles."""
    template_name = "admin_console/test_plans/cycle_list.html"
    context_object_name = 'cycles'
    help_context_id = "ADMIN_CONSOLE_TEST_PLANS"

    def get_queryset(self):
        from .models import TestCycle
        return TestCycle.objects.all().order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import TestCycle
        # Add summary stats
        cycles = self.get_queryset()
        context['total_cycles'] = cycles.count()
        context['active_cycles'] = cycles.filter(status=TestCycle.STATUS_IN_PROGRESS).count()
        context['completed_cycles'] = cycles.filter(status=TestCycle.STATUS_COMPLETED).count()
        return context


class TestCycleCreateView(AdminRequiredMixin, CreateView):
    """Create a new test cycle (optionally from template)."""
    template_name = "admin_console/test_plans/cycle_form.html"
    success_url = reverse_lazy('admin_console:test_cycle_list')

    def get_form_class(self):
        from django import forms
        from .models import TestCycle

        class TestCycleForm(forms.ModelForm):
            from_template = forms.BooleanField(
                required=False,
                initial=True,
                help_text="Populate with comprehensive WLJ test items"
            )

            class Meta:
                model = TestCycle
                fields = ['name', 'version', 'description']

        return TestCycleForm

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)

        # If from_template, populate with test items
        if form.cleaned_data.get('from_template', True):
            from .services import populate_test_cycle_from_template
            count = populate_test_cycle_from_template(self.object)
            messages.success(
                self.request,
                f"Test cycle '{self.object.name}' created with {count} test items."
            )
        else:
            messages.success(
                self.request,
                f"Test cycle '{self.object.name}' created."
            )

        return response


class TestCycleDetailView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """View and manage a test cycle with all phases and items."""
    template_name = "admin_console/test_plans/cycle_detail.html"
    help_context_id = "ADMIN_CONSOLE_TEST_PLANS"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import TestCycle, TestItem

        cycle_id = self.kwargs.get('pk')
        cycle = TestCycle.objects.prefetch_related(
            'phases__items'
        ).get(pk=cycle_id)

        context['cycle'] = cycle
        context['phases'] = cycle.phases.all().order_by('order')
        context['stats'] = cycle.stats
        context['status_choices'] = TestItem.STATUS_CHOICES
        context['priority_choices'] = TestItem.PRIORITY_CHOICES

        return context


class TestCycleDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a test cycle."""
    template_name = "admin_console/test_plans/cycle_confirm_delete.html"
    success_url = reverse_lazy('admin_console:test_cycle_list')
    context_object_name = 'cycle'

    def get_queryset(self):
        from .models import TestCycle
        return TestCycle.objects.all()

    def form_valid(self, form):
        cycle_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f"Test cycle '{cycle_name}' deleted.")
        return response


class TestCycleStartView(AdminRequiredMixin, View):
    """Start a test cycle (change status to in_progress)."""

    def post(self, request, pk):
        from .models import TestCycle

        try:
            cycle = TestCycle.objects.get(pk=pk)
            cycle.start()
            messages.success(request, f"Test cycle '{cycle.name}' started.")
        except TestCycle.DoesNotExist:
            messages.error(request, "Test cycle not found.")

        return redirect('admin_console:test_cycle_detail', pk=pk)


class TestCycleCompleteView(AdminRequiredMixin, View):
    """Complete a test cycle."""

    def post(self, request, pk):
        from .models import TestCycle

        try:
            cycle = TestCycle.objects.get(pk=pk)
            cycle.complete()
            messages.success(request, f"Test cycle '{cycle.name}' marked as completed.")
        except TestCycle.DoesNotExist:
            messages.error(request, "Test cycle not found.")

        return redirect('admin_console:test_cycle_detail', pk=pk)


class TestCyclePauseView(AdminRequiredMixin, View):
    """Pause an in-progress test cycle."""

    def post(self, request, pk):
        from .models import TestCycle

        try:
            cycle = TestCycle.objects.get(pk=pk)
            cycle.pause()
            messages.success(request, f"Test cycle '{cycle.name}' paused.")
        except TestCycle.DoesNotExist:
            messages.error(request, "Test cycle not found.")

        return redirect('admin_console:test_cycle_detail', pk=pk)


class TestCycleResumeView(AdminRequiredMixin, View):
    """Resume a paused test cycle."""

    def post(self, request, pk):
        from .models import TestCycle

        try:
            cycle = TestCycle.objects.get(pk=pk)
            cycle.resume()
            messages.success(request, f"Test cycle '{cycle.name}' resumed.")
        except TestCycle.DoesNotExist:
            messages.error(request, "Test cycle not found.")

        return redirect('admin_console:test_cycle_detail', pk=pk)


class TestCycleCancelView(AdminRequiredMixin, View):
    """Cancel an in-progress or paused test cycle."""

    def post(self, request, pk):
        from .models import TestCycle

        try:
            cycle = TestCycle.objects.get(pk=pk)
            cycle.cancel()
            messages.success(request, f"Test cycle '{cycle.name}' cancelled.")
        except TestCycle.DoesNotExist:
            messages.error(request, "Test cycle not found.")

        return redirect('admin_console:test_cycle_detail', pk=pk)


class TestPhaseCreateView(AdminRequiredMixin, CreateView):
    """Create a new test phase within a cycle."""
    template_name = "admin_console/test_plans/phase_form.html"

    def get_form_class(self):
        from django import forms
        from .models import TestPhase

        class TestPhaseForm(forms.ModelForm):
            class Meta:
                model = TestPhase
                fields = ['name', 'description', 'order']

        return TestPhaseForm

    def form_valid(self, form):
        from .models import TestCycle
        cycle = TestCycle.objects.get(pk=self.kwargs['cycle_pk'])
        form.instance.cycle = cycle
        response = super().form_valid(form)
        messages.success(self.request, f"Phase '{self.object.name}' created.")
        return response

    def get_success_url(self):
        return reverse_lazy('admin_console:test_cycle_detail', kwargs={'pk': self.kwargs['cycle_pk']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import TestCycle
        context['cycle'] = TestCycle.objects.get(pk=self.kwargs['cycle_pk'])
        return context


class TestPhaseDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a test phase."""
    template_name = "admin_console/test_plans/phase_confirm_delete.html"
    context_object_name = 'phase'

    def get_queryset(self):
        from .models import TestPhase
        return TestPhase.objects.all()

    def get_success_url(self):
        return reverse_lazy('admin_console:test_cycle_detail', kwargs={'pk': self.object.cycle.pk})

    def form_valid(self, form):
        phase_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f"Phase '{phase_name}' deleted.")
        return response


class TestItemCreateView(AdminRequiredMixin, CreateView):
    """Create a new test item within a phase."""
    template_name = "admin_console/test_plans/item_form.html"

    def get_form_class(self):
        from django import forms
        from .models import TestItem

        class TestItemForm(forms.ModelForm):
            class Meta:
                model = TestItem
                fields = ['name', 'description', 'expected_result', 'url', 'priority', 'order']

        return TestItemForm

    def form_valid(self, form):
        from .models import TestPhase
        phase = TestPhase.objects.select_related('cycle').get(pk=self.kwargs['phase_pk'])
        form.instance.phase = phase
        form.instance.cycle = phase.cycle
        response = super().form_valid(form)
        messages.success(self.request, f"Test item '{self.object.name}' created.")
        return response

    def get_success_url(self):
        return reverse_lazy('admin_console:test_cycle_detail', kwargs={'pk': self.object.cycle.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import TestPhase
        phase = TestPhase.objects.select_related('cycle').get(pk=self.kwargs['phase_pk'])
        context['phase'] = phase
        context['cycle'] = phase.cycle
        return context


class TestItemDeleteView(AdminRequiredMixin, DeleteView):
    """Delete a test item."""
    template_name = "admin_console/test_plans/item_confirm_delete.html"
    context_object_name = 'item'

    def get_queryset(self):
        from .models import TestItem
        return TestItem.objects.all()

    def get_success_url(self):
        return reverse_lazy('admin_console:test_cycle_detail', kwargs={'pk': self.object.cycle.pk})

    def form_valid(self, form):
        item_name = self.object.name
        response = super().form_valid(form)
        messages.success(self.request, f"Test item '{item_name}' deleted.")
        return response


class TestItemUpdateAPIView(AdminRequiredMixin, View):
    """
    API endpoint for inline test item updates.

    POST /admin-console/test-plans/api/item/<pk>/update/

    Accepts JSON body with any of:
    - status: string
    - actual_result: string
    - notes: string
    - priority: string
    """

    def post(self, request, pk):
        import json
        from .models import TestItem

        try:
            item = TestItem.objects.select_related('phase', 'cycle').get(pk=pk)
        except TestItem.DoesNotExist:
            return JsonResponse({'error': 'Test item not found'}, status=404)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Update allowed fields
        updated_fields = []
        if 'status' in data:
            old_status = item.status
            item.status = data['status']
            updated_fields.append('status')
            # Set tester on status change
            if data['status'] != old_status:
                item.tester = request.user

        if 'actual_result' in data:
            item.actual_result = data['actual_result']
            updated_fields.append('actual_result')

        if 'notes' in data:
            item.notes = data['notes']
            updated_fields.append('notes')

        if 'priority' in data:
            item.priority = data['priority']
            updated_fields.append('priority')

        if updated_fields:
            item.save()

        # Return updated stats
        phase_stats = item.phase.stats
        cycle_stats = item.cycle.stats

        return JsonResponse({
            'success': True,
            'item': {
                'id': item.pk,
                'status': item.status,
                'status_display': item.get_status_display(),
                'actual_result': item.actual_result,
                'notes': item.notes,
                'priority': item.priority,
                'priority_display': item.get_priority_display(),
                'tested_at': item.tested_at.isoformat() if item.tested_at else None,
                'tester': item.tester.email if item.tester else None,
            },
            'phase_stats': phase_stats,
            'phase_status': item.phase.status,
            'phase_progress': item.phase.progress,
            'cycle_stats': cycle_stats,
            'cycle_progress': item.cycle.progress,
        })


class TestItemBulkUpdateAPIView(AdminRequiredMixin, View):
    """
    API endpoint for bulk test item status updates.

    POST /admin-console/test-plans/api/bulk-update/

    Accepts JSON body with:
    - item_ids: list of item IDs
    - status: string
    """

    def post(self, request):
        import json
        from .models import TestItem

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        item_ids = data.get('item_ids', [])
        new_status = data.get('status')

        if not item_ids or not new_status:
            return JsonResponse({'error': 'item_ids and status required'}, status=400)

        # Update items
        from django.utils import timezone
        updated_count = TestItem.objects.filter(pk__in=item_ids).update(
            status=new_status,
            tester=request.user,
            tested_at=timezone.now() if new_status in [
                TestItem.STATUS_PASSED,
                TestItem.STATUS_FAILED,
                TestItem.STATUS_BLOCKED,
            ] else None
        )

        return JsonResponse({
            'success': True,
            'updated_count': updated_count,
        })


# ==============================================================================
# Admin Guide Views
# ==============================================================================

def _guide_sections_queryset():
    """Return active guide sections with their active articles prefetched."""
    return AdminGuideSection.objects.filter(
        is_active=True
    ).prefetch_related(
        models.Prefetch(
            'articles',
            queryset=AdminGuideArticle.objects.filter(is_active=True)
        )
    )


class AdminGuideHomeView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """Admin Guide home — shows sidebar + first section's first article."""
    template_name = "admin_console/admin_guide/home.html"
    help_context_id = "ADMIN_GUIDE_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sections = _guide_sections_queryset()
        context['sections'] = sections
        first_section = sections.first()
        if first_section:
            context['current_section'] = first_section
            context['current_article'] = first_section.articles.first()
        return context


class AdminGuideSectionView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """Display a section's first article."""
    template_name = "admin_console/admin_guide/home.html"
    help_context_id = "ADMIN_GUIDE_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sections = _guide_sections_queryset()
        context['sections'] = sections
        current_section = get_object_or_404(
            AdminGuideSection, section_key=self.kwargs['section_key'], is_active=True
        )
        context['current_section'] = current_section
        context['current_article'] = current_section.articles.filter(is_active=True).first()
        return context


class AdminGuideArticleView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """Display a specific article."""
    template_name = "admin_console/admin_guide/home.html"
    help_context_id = "ADMIN_GUIDE_HOME"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sections = _guide_sections_queryset()
        context['sections'] = sections
        current_section = get_object_or_404(
            AdminGuideSection, section_key=self.kwargs['section_key'], is_active=True
        )
        current_article = get_object_or_404(
            AdminGuideArticle,
            section=current_section, slug=self.kwargs['slug'], is_active=True
        )
        context['current_section'] = current_section
        context['current_article'] = current_article
        return context


class AdminGuideManageView(HelpContextMixin, AdminRequiredMixin, ListView):
    """List all guide articles for management."""
    template_name = "admin_console/admin_guide/manage.html"
    help_context_id = "ADMIN_GUIDE_MANAGE"
    context_object_name = 'articles'

    def get_queryset(self):
        return AdminGuideArticle.objects.filter(
            is_active=True
        ).select_related('section').order_by('section__order', 'order')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sections'] = AdminGuideSection.objects.filter(is_active=True)
        return context


class AdminGuideArticleEditView(HelpContextMixin, AdminRequiredMixin, UpdateView):
    """Edit a supplemental guide article (is_editable=True only)."""
    template_name = "admin_console/admin_guide/article_form.html"
    help_context_id = "ADMIN_GUIDE_MANAGE"
    model = AdminGuideArticle
    fields = ['title', 'content']

    def get_queryset(self):
        return AdminGuideArticle.objects.filter(is_editable=True)

    def get_success_url(self):
        from django.urls import reverse
        return reverse('admin_console:admin_guide_manage')

    def form_valid(self, form):
        messages.success(self.request, f"Article '{form.instance.title}' updated.")
        return super().form_valid(form)


class AdminGuideSyncCosView(AdminRequiredMixin, View):
    """Trigger on-demand sync of CoS documentation to admin guide."""

    def post(self, request):
        try:
            from apps.core.ai_docs.cos_doc_sync import sync_cos_admin_guide

            result = sync_cos_admin_guide(force=True)

            if result['synced']:
                messages.success(
                    request,
                    f"CoS docs synced: {result['articles_created']} created, "
                    f"{result['articles_updated']} updated, "
                    f"{result['articles_removed']} removed."
                )
            else:
                messages.info(request, f"Sync skipped: {result['reason']}")
        except Exception as e:
            messages.error(request, f"CoS doc sync failed: {e}")

        return redirect('admin_console:admin_guide_manage')


# ==============================================================================
# Test Results Ingest API (Local → Production sync)
# ==============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class TestResultIngestAPIView(APIRateLimitMixin, View):
    """
    API endpoint to ingest UI test results from remote environments.

    Authentication:
        Requires X-Test-Results-API-Key header matching settings.TEST_RESULTS_API_KEY

    Rate Limiting:
        - 30 requests per minute
        - 200 requests per hour

    POST /admin-console/api/test-results/ingest/

    Payload:
        {
            "run_id": "abc12345",
            "modules": ["goals"],
            "status": "passed",
            "total_cases": 4,
            "passed": 4,
            "failed": 0,
            "pass_rate": 100.0,
            "duration_seconds": 12.5,
            "environment": "local",
            "source_host": "dev-macbook",
            "source_user": "danny",
            "results": {"passed": [...], "failed": [...]},
            "output": "...",
            "children": [...]  // optional, for full-suite runs
        }

    Returns:
        201: {"status": "success", "id": <pk>}
        200: {"status": "already_exists", "id": <pk>}  (idempotent)
        400: {"error": "..."}
        401: {"error": "..."}
    """

    rate_limit_requests_per_minute = 30
    rate_limit_requests_per_hour = 200
    rate_limit_key_prefix = 'admin_api_test_results'

    REQUIRED_FIELDS = [
        'run_id', 'modules', 'status', 'total_cases',
        'passed', 'failed', 'pass_rate', 'duration_seconds',
    ]
    VALID_STATUSES = {'running', 'passed', 'failed', 'error'}

    def post(self, request):
        import json
        from django.conf import settings
        from apps.core.rate_limiting import secure_compare_api_key
        from .models import UITestRun

        # ── Authenticate ─────────────────────────────────────────────────
        api_key = request.headers.get('X-Test-Results-API-Key', '')

        if not settings.TEST_RESULTS_API_KEY:
            return JsonResponse(
                {'error': 'TEST_RESULTS_API_KEY not configured on server'},
                status=500,
            )

        if not secure_compare_api_key(api_key, settings.TEST_RESULTS_API_KEY):
            return JsonResponse(
                {'error': 'Invalid or missing API key. Include X-Test-Results-API-Key header.'},
                status=401,
            )

        # ── Parse payload ────────────────────────────────────────────────
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)

        if not isinstance(data, dict):
            return JsonResponse({'error': 'Payload must be a JSON object'}, status=400)

        # ── Validate required fields ─────────────────────────────────────
        missing = [f for f in self.REQUIRED_FIELDS if f not in data]
        if missing:
            return JsonResponse(
                {'error': f'Missing required fields: {", ".join(missing)}'},
                status=400,
            )

        status_val = data['status']
        if status_val not in self.VALID_STATUSES:
            return JsonResponse(
                {'error': f'Invalid status "{status_val}". Must be one of: {", ".join(sorted(self.VALID_STATUSES))}'},
                status=400,
            )

        # ── Idempotency check ────────────────────────────────────────────
        run_id = str(data['run_id'])
        source_host = str(data.get('source_host', ''))
        existing = UITestRun.objects.filter(
            run_id=run_id, source_host=source_host
        ).first()
        if existing:
            return JsonResponse(
                {'status': 'already_exists', 'id': existing.pk},
                status=200,
            )

        # ── Create UITestRun record ──────────────────────────────────────
        ui_run = UITestRun.objects.create(
            run_id=run_id,
            modules=data['modules'],
            status=status_val,
            total_cases=int(data['total_cases']),
            passed=int(data['passed']),
            failed=int(data['failed']),
            pass_rate=float(data['pass_rate']),
            duration_seconds=float(data['duration_seconds']),
            environment=str(data.get('environment', 'local'))[:20],
            source_host=source_host[:255],
            source_user=str(data.get('source_user', ''))[:255],
            case_results=data.get('results', {}),
            output=str(data.get('output', ''))[:50000],
        )

        # ── Handle full-suite children ───────────────────────────────────
        children = data.get('children', [])
        if children and isinstance(children, list):
            for child_data in children:
                if not isinstance(child_data, dict):
                    continue
                UITestRun.objects.create(
                    parent_run=ui_run,
                    run_id=str(child_data.get('run_id', ''))[:50],
                    modules=child_data.get('modules', []),
                    status=str(child_data.get('status', 'error'))[:10],
                    total_cases=int(child_data.get('total_cases', 0)),
                    passed=int(child_data.get('passed', 0)),
                    failed=int(child_data.get('failed', 0)),
                    pass_rate=float(child_data.get('pass_rate', 0)),
                    duration_seconds=float(child_data.get('duration_seconds', 0)),
                    environment=ui_run.environment,
                    source_host=ui_run.source_host,
                    source_user=ui_run.source_user,
                    case_results=child_data.get('results', {}),
                )

        return JsonResponse(
            {'status': 'success', 'id': ui_run.pk},
            status=201,
        )


class RestoreDeletedTasksAPIView(APIRateLimitMixin, View):
    """
    One-time API endpoint to restore tasks incorrectly deleted by AI.
    Authenticated via X-Claude-API-Key header.

    GET /admin-console/api/claude/restore-deleted-tasks/?user_email=...&start=YYYY-MM-DD&end=YYYY-MM-DD
    Optional: ?dry_run=true to preview without restoring.
    """

    rate_limit_requests_per_hour = 60
    rate_limit_key_prefix = 'admin_api_restore_tasks'

    def get(self, request):
        from django.conf import settings
        from apps.core.rate_limiting import secure_compare_api_key

        api_key = request.headers.get('X-Claude-API-Key', '')
        if not settings.CLAUDE_API_KEY:
            return JsonResponse({'error': 'CLAUDE_API_KEY not configured'}, status=500)
        if not secure_compare_api_key(api_key, settings.CLAUDE_API_KEY):
            return JsonResponse({'error': 'Invalid or missing API key.'}, status=401)

        user_email = request.GET.get('user_email', '')
        start_date = request.GET.get('start', '')
        end_date = request.GET.get('end', '')
        dry_run = request.GET.get('dry_run', '').lower() == 'true'

        if not user_email:
            return JsonResponse({'error': 'user_email parameter required'}, status=400)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(email=user_email)
        except User.DoesNotExist:
            return JsonResponse({'error': f'User {user_email} not found'}, status=404)

        from apps.life.models import Task
        from django.utils import timezone as tz
        import datetime

        # Diagnose mode: show all tasks + recurring templates + calendar events
        diagnose = request.GET.get('diagnose', '').lower() == 'true'
        if diagnose:
            all_tasks = Task.all_objects.filter(user=user).order_by('-updated_at')[:50]

            # Check routine tasks (is_routine=True, which are the recurring templates)
            routine_tasks = Task.all_objects.filter(
                user=user, is_routine=True
            ).order_by('-updated_at')[:30]
            recurring = [
                {
                    'id': r.id,
                    'title': r.title,
                    'status': r.status,
                    'is_completed': r.is_completed,
                    'scheduled_time': str(r.scheduled_time) if r.scheduled_time else None,
                    'due_date': str(r.due_date) if r.due_date else None,
                    'deleted_at': str(r.deleted_at) if r.deleted_at else None,
                    'updated_at': str(r.updated_at),
                }
                for r in routine_tasks
            ]

            # Check calendar events for today
            from apps.calendar_engine.models import CalendarEvent
            import datetime
            today = datetime.date.today()
            cal_events = CalendarEvent.objects.filter(
                user=user,
                start_dt__date=today,
            ).order_by('start_dt')[:30]

            return JsonResponse({
                'diagnose': True,
                'tasks_total': all_tasks.count(),
                'tasks': [
                    {
                        'id': t.id,
                        'title': t.title,
                        'status': t.status,
                        'is_completed': t.is_completed,
                        'is_routine': getattr(t, 'is_routine', False),
                        'due_date': str(t.due_date) if t.due_date else None,
                        'deleted_at': str(t.deleted_at) if t.deleted_at else None,
                        'updated_at': str(t.updated_at),
                    }
                    for t in all_tasks
                ],
                'recurring_templates': recurring,
                'todays_calendar_events': [
                    {
                        'id': e.id,
                        'title': e.title,
                        'event_kind': e.event_kind,
                        'source_type': e.source_type,
                        'source_id': e.source_id,
                        'start_dt': str(e.start_dt),
                        'status': e.status,
                    }
                    for e in cal_events
                ],
            })

        # Build filter
        qs = Task.all_objects.filter(user=user, status='deleted')

        if start_date:
            try:
                start_dt = tz.make_aware(
                    datetime.datetime.strptime(start_date, '%Y-%m-%d'),
                    datetime.timezone.utc,
                )
                qs = qs.filter(deleted_at__gte=start_dt)
            except ValueError:
                return JsonResponse({'error': f'Invalid start date: {start_date}'}, status=400)

        if end_date:
            try:
                end_dt = tz.make_aware(
                    datetime.datetime.strptime(end_date, '%Y-%m-%d'),
                    datetime.timezone.utc,
                ) + datetime.timedelta(days=1)
                qs = qs.filter(deleted_at__lt=end_dt)
            except ValueError:
                return JsonResponse({'error': f'Invalid end date: {end_date}'}, status=400)

        tasks = list(qs)
        task_info = [{'id': t.id, 'title': t.title, 'deleted_at': str(t.deleted_at)} for t in tasks]

        if dry_run:
            return JsonResponse({
                'dry_run': True,
                'found': len(tasks),
                'tasks': task_info,
            })

        restored = []
        for task in tasks:
            task.restore()
            restored.append({'id': task.id, 'title': task.title})

        return JsonResponse({
            'success': True,
            'restored': len(restored),
            'tasks': restored,
        })
