# ==============================================================================
# File: apps/admin_console/views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Admin console views for site management and project task intake
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01 (Prepopulate Phase Dropdown 1-20)
# ==============================================================================
"""
Admin Views - Custom admin interface for site management.

These views provide a user-friendly admin interface that matches
the app's design, rather than using Django's default admin.
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import (
    CreateView,
    DeleteView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from apps.core.models import Category, SiteConfiguration, Theme
from apps.core.models import ChoiceCategory, ChoiceOption
from apps.help.mixins import HelpContextMixin


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin to ensure user is staff/admin."""
    
    def test_func(self):
        return self.request.user.is_staff
    
    def handle_no_permission(self):
        messages.error(self.request, "You don't have permission to access the admin area.")
        return redirect('dashboard:home')


class AdminDashboardView(HelpContextMixin, AdminRequiredMixin, TemplateView):
    """
    Main admin dashboard - overview of site management options.
    """
    template_name = "admin_console/dashboard.html"
    help_context_id = "ADMIN_CONSOLE_HOME"
    
    def get_context_data(self, **kwargs):
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
        
        # Handle logo upload
        if 'logo' in request.FILES:
            config.logo = request.FILES['logo']
        elif request.POST.get('clear_logo') == 'on':
            config.logo = None
        
        # Handle favicon upload
        if 'favicon' in request.FILES:
            config.favicon = request.FILES['favicon']
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
        category_pk = self.object.category.pk
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
                messages.warning(request, f"Tests completed with failures. Check the results below.")

        except subprocess.TimeoutExpired:
            messages.error(request, "Test execution timed out after 5 minutes.")
        except FileNotFoundError:
            messages.error(request, "Could not find run_tests.py script.")
        except Exception as e:
            messages.error(request, f"Error running tests: {str(e)}")

        return redirect('admin_console:test_run_list')


# ============================================================
# Project Phase Views
# ============================================================

class ProjectPhaseListView(AdminRequiredMixin, ListView):
    """List all project phases."""
    template_name = "admin_console/project_phase_list.html"
    context_object_name = "phases"

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

class AdminTaskListView(AdminRequiredMixin, ListView):
    """
    List all admin tasks with filtering.

    Phase 12 requirements:
    - Display: title, phase number, status, priority, created_by, created_at
    - Order by: priority ASC, created_at ASC
    - Filterable by: phase, status (optional)
    - Read-only list (no inline editing required)
    - Includes Mark Ready control for backlog tasks
    """
    template_name = "admin_console/admin_task_list.html"
    context_object_name = "tasks"

    def get_queryset(self):
        from apps.admin_console.models import AdminTask

        queryset = AdminTask.objects.select_related('phase').all()

        # Filter by phase if provided
        phase_filter = self.request.GET.get('phase')
        if phase_filter:
            try:
                queryset = queryset.filter(phase_id=int(phase_filter))
            except (ValueError, TypeError):
                pass

        # Filter by status if provided
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Order by priority ASC, created_at ASC (per Phase 12 spec)
        return queryset.order_by('priority', 'created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.admin_console.models import AdminProjectPhase, AdminTask

        context['phases'] = AdminProjectPhase.objects.all().order_by('phase_number')
        context['status_choices'] = AdminTask.STATUS_CHOICES

        # Preserve filter values
        context['current_phase_filter'] = self.request.GET.get('phase', '')
        context['current_status_filter'] = self.request.GET.get('status', '')

        # Ready tasks warning (soft guardrail)
        ready_count = AdminTask.objects.filter(status='ready').count()
        context['ready_count'] = ready_count
        context['show_ready_warning'] = ready_count >= READY_TASKS_WARNING_THRESHOLD
        context['ready_warning_threshold'] = READY_TASKS_WARNING_THRESHOLD

        return context


class AdminTaskCreateView(AdminRequiredMixin, CreateView):
    """Create a new admin task."""
    template_name = "admin_console/admin_task_form.html"
    success_url = reverse_lazy('admin_console:admin_task_list')
    fields = ['title', 'description', 'category', 'priority', 'status', 'effort', 'phase', 'created_by']

    def get_queryset(self):
        from apps.admin_console.models import AdminTask
        return AdminTask.objects.all()

    def get_form_class(self):
        from django import forms
        from apps.admin_console.models import AdminTask

        class AdminTaskForm(forms.ModelForm):
            class Meta:
                model = AdminTask
                fields = ['title', 'description', 'category', 'priority', 'status', 'effort', 'phase', 'created_by']

        return AdminTaskForm

    def form_valid(self, form):
        messages.success(self.request, f"Task '{form.instance.title}' created.")
        return super().form_valid(form)


class AdminTaskUpdateView(AdminRequiredMixin, UpdateView):
    """Edit an admin task."""
    template_name = "admin_console/admin_task_form.html"
    success_url = reverse_lazy('admin_console:admin_task_list')
    fields = ['title', 'description', 'category', 'priority', 'status', 'effort', 'phase', 'created_by']

    def get_queryset(self):
        from apps.admin_console.models import AdminTask
        return AdminTask.objects.all()

    def form_valid(self, form):
        messages.success(self.request, f"Task '{form.instance.title}' updated.")
        return super().form_valid(form)


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


class TaskIntakeView(AdminRequiredMixin, TemplateView):
    """
    Task Intake page for admin to create new tasks.

    GET: Display the task intake form
    POST: Create a new AdminTask

    Safety rules:
    - created_by is always set to 'human'
    - Status defaults to 'backlog', not auto-set to 'ready'
    - Validates required fields
    - Requires a phase to be selected
    """
    template_name = "admin_console/task_intake.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.admin_console.models import AdminProjectPhase, AdminTask
        from .services import get_active_phase

        # Get phases for dropdown
        context['phases'] = AdminProjectPhase.objects.all().order_by('phase_number')

        # Get active phase as default
        active_phase = get_active_phase()
        context['active_phase'] = active_phase

        # Category and effort choices
        context['category_choices'] = AdminTask.CATEGORY_CHOICES
        context['effort_choices'] = AdminTask.EFFORT_CHOICES

        # Check if there's a warning about ready tasks count
        ready_count = AdminTask.objects.filter(status='ready').count()
        context['ready_count'] = ready_count
        context['show_ready_warning'] = ready_count >= READY_TASKS_WARNING_THRESHOLD
        context['ready_warning_threshold'] = READY_TASKS_WARNING_THRESHOLD

        return context

    def post(self, request):
        from django import forms
        from apps.admin_console.models import AdminProjectPhase, AdminTask

        # Extract form data
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        phase_id = request.POST.get('phase')
        priority = request.POST.get('priority', '3')
        status = request.POST.get('status', 'backlog')
        category = request.POST.get('category', '')
        effort = request.POST.get('effort', '')

        # Validate required fields
        errors = []
        if not title:
            errors.append("Title is required.")
        if not description:
            errors.append("Description is required.")
        if not phase_id:
            errors.append("Phase is required. Cannot create a task without a phase.")

        # Validate phase exists
        phase = None
        if phase_id:
            try:
                phase = AdminProjectPhase.objects.get(pk=phase_id)
            except AdminProjectPhase.DoesNotExist:
                errors.append(f"Phase with ID {phase_id} does not exist.")

        # Validate priority
        try:
            priority = int(priority)
            if priority < 1 or priority > 5:
                errors.append("Priority must be between 1 and 5.")
        except (ValueError, TypeError):
            priority = 3

        # Validate status - only backlog or ready allowed on intake
        if status not in ('backlog', 'ready'):
            status = 'backlog'

        if errors:
            for error in errors:
                messages.error(request, error)
            return redirect('admin_console:task_intake')

        # Create the task
        task = AdminTask.objects.create(
            title=title,
            description=description,
            phase=phase,
            priority=priority,
            status=status,
            category=category if category else 'feature',
            effort=effort if effort else 'M',
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

class NextTasksAPIView(View):
    """
    API endpoint to get next tasks from the active phase.

    GET /api/admin/project/next-tasks/
    Query params:
        - limit (optional, default 5): Maximum tasks to return

    Returns JSON array of task objects.
    Returns 403 if user is not admin.
    """

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


class ProjectMetricsAPIView(View):
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
    """

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


class SystemStateAPIView(View):
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
    """

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


# ============================================================
# Phase 10 - Hardening & Fail-Safes API Views
# ============================================================

class SystemIssuesAPIView(View):
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
    """

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


class ResetPhaseOverrideAPIView(View):
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
    - 403: Permission denied
    - 404: Phase not found
    """

    def post(self, request):
        import json
        from .models import AdminProjectPhase
        from .services import reset_active_phase

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

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


class UnblockTaskOverrideAPIView(View):
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
    - 403: Permission denied
    - 404: Task not found
    """

    def post(self, request):
        import json
        from .models import AdminTask
        from .services import force_unblock_task

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

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


class RecheckPhaseOverrideAPIView(View):
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
    - 403: Permission denied
    - 404: Phase not found
    """

    def post(self, request):
        import json
        from .models import AdminProjectPhase
        from .services import recheck_phase_completion

        # Check admin permission
        if not request.user.is_authenticated or not request.user.is_staff:
            return JsonResponse(
                {'error': 'Permission denied'},
                status=403
            )

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

class PreflightCheckAPIView(View):
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
    """

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


class SeedPhasesAPIView(View):
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
    """

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
    API endpoint for inline status updates (backlog <-> ready only).

    PATCH /api/admin/project/tasks/<id>/inline-status/

    This is a simplified endpoint for inline editing that:
    - Only allows transitions between 'backlog' and 'ready'
    - Does NOT allow setting in_progress, blocked, or done
    - Saves immediately without confirmation

    Request body:
    {
        "status": "backlog" | "ready"
    }

    Returns:
    - 200: Success with updated task info
    - 400: Invalid status or transition not allowed
    - 403: Permission denied (not admin)
    - 404: Task not found
    """

    # Allowed inline transitions: only backlog <-> ready
    ALLOWED_INLINE_STATUSES = ['backlog', 'ready']

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

        # Get status from body
        new_status = body.get('status')
        if not new_status:
            return JsonResponse(
                {'error': 'Missing required field: status'},
                status=400
            )

        # Validate status is allowed for inline editing
        if new_status not in self.ALLOWED_INLINE_STATUSES:
            return JsonResponse(
                {'error': f"Inline editing only allows: {self.ALLOWED_INLINE_STATUSES}. "
                          f"Use the full edit form for other status changes."},
                status=400
            )

        # Validate current status is also in allowed list
        if task.status not in self.ALLOWED_INLINE_STATUSES:
            return JsonResponse(
                {'error': f"Cannot change status inline when current status is '{task.status}'. "
                          f"Only tasks in 'backlog' or 'ready' can be changed inline."},
                status=400
            )

        # No change needed
        if task.status == new_status:
            return JsonResponse({
                'success': True,
                'task': {
                    'id': task.id,
                    'title': task.title,
                    'status': task.status,
                    'phase_number': task.phase.phase_number
                },
                'changed': False
            })

        # Update the task
        old_status = task.status
        task.status = new_status
        task.save()

        # Log the change
        AdminActivityLog.objects.create(
            task=task,
            action=f"Status changed from '{old_status}' to '{new_status}' via inline edit.",
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
                'phase_number': task.phase.phase_number
            },
            'changed': True,
            'ready_count': ready_count,
            'show_warning': ready_count >= READY_TASKS_WARNING_THRESHOLD
        })


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

class ProjectsRunbookView(AdminRequiredMixin, TemplateView):
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
