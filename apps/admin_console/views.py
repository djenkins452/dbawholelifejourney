"""
Admin Views - Custom admin interface for site management.

These views provide a user-friendly admin interface that matches
the app's design, rather than using Django's default admin.
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import UserPassesTestMixin
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


class AdminRequiredMixin(UserPassesTestMixin):
    """Mixin to ensure user is staff/admin."""
    
    def test_func(self):
        return self.request.user.is_staff
    
    def handle_no_permission(self):
        messages.error(self.request, "You don't have permission to access the admin area.")
        return redirect('dashboard:home')


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    """
    Main admin dashboard - overview of site management options.
    """
    template_name = "admin_console/dashboard.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
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
        
        return context


# ============================================================
# Site Configuration Views
# ============================================================

class SiteConfigView(AdminRequiredMixin, TemplateView):
    """
    Edit site configuration (singleton).
    """
    template_name = "admin_console/site_config.html"
    
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

class ThemeListView(AdminRequiredMixin, ListView):
    """List all themes."""
    model = Theme
    template_name = "admin_console/theme_list.html"
    context_object_name = "themes"
    
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

class UserListView(AdminRequiredMixin, ListView):
    """List all users."""
    template_name = "admin_console/user_list.html"
    context_object_name = "users"
    paginate_by = 50
    
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
            except:
                detail.failed_tests_list = []
            try:
                detail.error_tests_list = json.loads(detail.error_tests) if detail.error_tests else []
            except:
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
