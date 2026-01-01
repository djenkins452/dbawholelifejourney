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
        messages.success(self.request, f"Phase '{self.object.name}' deleted.")
        return super().form_valid(form)


# ============================================================
# Admin Task Views
# ============================================================

class AdminTaskListView(AdminRequiredMixin, ListView):
    """List all admin tasks."""
    template_name = "admin_console/admin_task_list.html"
    context_object_name = "tasks"

    def get_queryset(self):
        from apps.admin_console.models import AdminTask
        return AdminTask.objects.select_related('phase').all().order_by('priority', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.admin_console.models import AdminProjectPhase
        context['phases'] = AdminProjectPhase.objects.all()
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
        messages.success(self.request, f"Task '{self.object.title}' deleted.")
        return super().form_valid(form)


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
