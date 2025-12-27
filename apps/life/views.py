"""
Life Module Views

The daily operating layer of a person's life.
Calm, integrated, and quietly powerful.
"""

import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q, Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
    View,
)

from .models import (
    Project,
    Task,
    LifeEvent,
    InventoryItem,
    InventoryPhoto,
    MaintenanceLog,
    Pet,
    PetRecord,
    Recipe,
    Document,
)


class LifeAccessMixin(LoginRequiredMixin):
    """Base mixin for Life module views."""
    pass


# =============================================================================
# Home / Dashboard
# =============================================================================

class LifeHomeView(LifeAccessMixin, TemplateView):
    """
    Life module dashboard.
    A calm overview of what matters today.
    """
    template_name = "life/home.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        from apps.core.utils import get_user_today
        today = get_user_today(user)

        # Active projects
        context['active_projects'] = Project.objects.filter(
            user=user,
            status='active'
        ).order_by('priority', '-updated_at')[:5]
        
        # Tasks by priority
        context['now_tasks'] = Task.objects.filter(
            user=user,
            is_completed=False,
            priority='now'
        )[:5]
        
        context['soon_tasks'] = Task.objects.filter(
            user=user,
            is_completed=False,
            priority='soon'
        )[:5]
        
        # Upcoming events (next 7 days)
        week_ahead = today + timezone.timedelta(days=7)
        context['upcoming_events'] = LifeEvent.objects.filter(
            user=user,
            start_date__gte=today,
            start_date__lte=week_ahead
        ).order_by('start_date', 'start_time')[:5]
        
        # Today's events
        context['todays_events'] = LifeEvent.objects.filter(
            user=user,
            start_date=today
        ).order_by('start_time')
        
        # Quick stats
        context['stats'] = {
            'active_projects': Project.objects.filter(user=user, status='active').count(),
            'pending_tasks': Task.objects.filter(user=user, is_completed=False).count(),
            'inventory_items': InventoryItem.objects.filter(user=user).count(),
            'pets': Pet.objects.filter(user=user, is_active=True).count(),
        }
        
        # Overdue tasks
        context['overdue_tasks'] = Task.objects.filter(
            user=user,
            is_completed=False,
            due_date__lt=today
        ).count()
        
        return context


# =============================================================================
# Projects
# =============================================================================

class ProjectListView(LifeAccessMixin, ListView):
    """List all projects."""
    model = Project
    template_name = "life/project_list.html"
    context_object_name = "projects"
    
    def get_queryset(self):
        queryset = Project.objects.filter(user=self.request.user)
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        else:
            # Default: show active and paused
            queryset = queryset.filter(status__in=['active', 'paused'])
        
        # Filter by priority
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        return queryset.annotate(
            task_total=Count('tasks'),
            task_done=Count('tasks', filter=Q(tasks__is_completed=True))
        ).order_by('priority', '-updated_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_status'] = self.request.GET.get('status', '')
        context['current_priority'] = self.request.GET.get('priority', '')
        return context


class ProjectDetailView(LifeAccessMixin, DetailView):
    """View a single project with its tasks."""
    model = Project
    template_name = "life/project_detail.html"
    context_object_name = "project"
    
    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tasks'] = self.object.tasks.order_by('is_completed', 'priority', '-created_at')
        context['events'] = self.object.events.order_by('start_date')[:5]
        return context


class ProjectCreateView(LifeAccessMixin, CreateView):
    """Create a new project."""
    model = Project
    template_name = "life/project_form.html"
    fields = [
        'title', 'description', 'purpose', 'status', 'priority',
        'start_date', 'target_date', 'category', 'cover_image'
    ]
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Project '{form.instance.title}' created.")
        return super().form_valid(form)


class ProjectUpdateView(LifeAccessMixin, UpdateView):
    """Edit a project."""
    model = Project
    template_name = "life/project_form.html"
    fields = [
        'title', 'description', 'purpose', 'status', 'priority',
        'start_date', 'target_date', 'completed_date', 'category',
        'cover_image', 'reflection'
    ]
    
    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, f"Project '{form.instance.title}' updated.")
        return super().form_valid(form)


class ProjectDeleteView(LifeAccessMixin, DeleteView):
    """Delete a project."""
    model = Project
    template_name = "life/project_confirm_delete.html"
    success_url = reverse_lazy('life:project_list')
    
    def get_queryset(self):
        return Project.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, f"Project '{self.object.title}' deleted.")
        return super().form_valid(form)


# =============================================================================
# Tasks
# =============================================================================

class TaskListView(LifeAccessMixin, ListView):
    """List all tasks."""
    model = Task
    template_name = "life/task_list.html"
    context_object_name = "tasks"
    
    def get_queryset(self):
        queryset = Task.objects.filter(user=self.request.user)
        
        # Filter by completion
        show = self.request.GET.get('show', 'active')
        if show == 'active':
            queryset = queryset.filter(is_completed=False)
        elif show == 'completed':
            queryset = queryset.filter(is_completed=True)
        
        # Filter by priority
        priority = self.request.GET.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)
        
        # Filter by project
        project_id = self.request.GET.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        return queryset.select_related('project').order_by(
            'is_completed', 'priority', 'due_date', '-created_at'
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_show'] = self.request.GET.get('show', 'active')
        context['current_priority'] = self.request.GET.get('priority', '')
        context['projects'] = Project.objects.filter(
            user=self.request.user, status='active'
        )
        return context


class TaskCreateView(LifeAccessMixin, CreateView):
    """Create a new task."""
    model = Task
    template_name = "life/task_form.html"
    fields = ['title', 'notes', 'project', 'priority', 'effort', 'due_date', 'is_recurring', 'recurrence_pattern']
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['project'].queryset = Project.objects.filter(
            user=self.request.user, status='active'
        )
        return form
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Task '{form.instance.title}' created.")
        return super().form_valid(form)
    
    def get_success_url(self):
        next_url = self.request.GET.get('next')
        if next_url:
            return next_url
        return reverse_lazy('life:task_list')


class TaskUpdateView(LifeAccessMixin, UpdateView):
    """Edit a task."""
    model = Task
    template_name = "life/task_form.html"
    fields = ['title', 'notes', 'project', 'priority', 'effort', 'due_date', 'is_recurring', 'recurrence_pattern']
    
    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['project'].queryset = Project.objects.filter(
            user=self.request.user, status='active'
        )
        return form
    
    def get_success_url(self):
        return reverse_lazy('life:task_list')


class TaskDeleteView(LifeAccessMixin, DeleteView):
    """Delete a task."""
    model = Task
    template_name = "life/task_confirm_delete.html"
    success_url = reverse_lazy('life:task_list')
    
    def get_queryset(self):
        return Task.objects.filter(user=self.request.user)


class TaskToggleView(LifeAccessMixin, View):
    """Toggle task completion status."""
    
    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk, user=request.user)
        if task.is_completed:
            task.mark_incomplete()
        else:
            task.mark_complete()
        
        # Return to referring page or task list
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER')
        if next_url:
            return redirect(next_url)
        return redirect('life:task_list')


# =============================================================================
# Calendar & Events
# =============================================================================

class CalendarView(LifeAccessMixin, TemplateView):
    """Monthly calendar view."""
    template_name = "life/calendar.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today

        # Get month/year from query params or use current
        today = get_user_today(self.request.user)
        year = int(self.request.GET.get('year', today.year))
        month = int(self.request.GET.get('month', today.month))
        
        # Get events for this month
        from calendar import monthrange
        _, last_day = monthrange(year, month)
        
        start_date = timezone.datetime(year, month, 1).date()
        end_date = timezone.datetime(year, month, last_day).date()
        
        context['events'] = LifeEvent.objects.filter(
            user=self.request.user,
            start_date__gte=start_date,
            start_date__lte=end_date
        ).order_by('start_date', 'start_time')
        
        context['year'] = year
        context['month'] = month
        context['today'] = today
        
        # Google Calendar status
        credential = get_user_google_credential(self.request.user)
        context['google_calendar_connected'] = credential is not None and credential.is_connected
        if context['google_calendar_connected']:
            context['google_calendar_name'] = credential.selected_calendar_name
            context['google_last_sync'] = credential.last_sync
        
        return context


class EventCreateView(LifeAccessMixin, CreateView):
    """Create a new event."""
    model = LifeEvent
    template_name = "life/event_form.html"
    fields = [
        'title', 'description', 'event_type', 'start_date', 'start_time',
        'end_date', 'end_time', 'is_all_day', 'location', 'project'
    ]
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['project'].queryset = Project.objects.filter(
            user=self.request.user, status='active'
        )
        return form
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Event '{form.instance.title}' created.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('life:calendar')


class EventUpdateView(LifeAccessMixin, UpdateView):
    """Edit an event."""
    model = LifeEvent
    template_name = "life/event_form.html"
    fields = [
        'title', 'description', 'event_type', 'start_date', 'start_time',
        'end_date', 'end_time', 'is_all_day', 'location', 'project'
    ]
    
    def get_queryset(self):
        return LifeEvent.objects.filter(user=self.request.user)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['project'].queryset = Project.objects.filter(
            user=self.request.user, status='active'
        )
        return form
    
    def get_success_url(self):
        return reverse_lazy('life:calendar')


class EventDeleteView(LifeAccessMixin, DeleteView):
    """Delete an event."""
    model = LifeEvent
    template_name = "life/event_confirm_delete.html"
    success_url = reverse_lazy('life:calendar')
    
    def get_queryset(self):
        return LifeEvent.objects.filter(user=self.request.user)


# =============================================================================
# Inventory
# =============================================================================

class InventoryListView(LifeAccessMixin, ListView):
    """List all inventory items."""
    model = InventoryItem
    template_name = "life/inventory_list.html"
    context_object_name = "items"
    
    def get_queryset(self):
        queryset = InventoryItem.objects.filter(user=self.request.user)
        
        # Filter by category
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Filter by location
        location = self.request.GET.get('location')
        if location:
            queryset = queryset.filter(location=location)
        
        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(description__icontains=search) |
                Q(brand__icontains=search)
            )
        
        return queryset.order_by('category', 'name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_items = InventoryItem.objects.filter(user=self.request.user)
        
        # Get unique categories and locations for filters
        context['categories'] = user_items.values_list(
            'category', flat=True
        ).distinct().order_by('category')
        context['locations'] = user_items.values_list(
            'location', flat=True
        ).exclude(location='').distinct().order_by('location')
        
        # Total value
        context['total_value'] = user_items.aggregate(
            total=Sum('estimated_value')
        )['total'] or 0
        
        return context


class InventoryDetailView(LifeAccessMixin, DetailView):
    """View inventory item details."""
    model = InventoryItem
    template_name = "life/inventory_detail.html"
    context_object_name = "item"
    
    def get_queryset(self):
        return InventoryItem.objects.filter(user=self.request.user)


class InventoryCreateView(LifeAccessMixin, CreateView):
    """Add new inventory item."""
    model = InventoryItem
    template_name = "life/inventory_form.html"
    fields = [
        'name', 'description', 'category', 'location',
        'purchase_date', 'purchase_price', 'estimated_value',
        'condition', 'brand', 'model_number', 'serial_number',
        'warranty_expiration', 'warranty_info', 'notes'
    ]
    success_url = reverse_lazy('life:inventory_list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"'{form.instance.name}' added to inventory.")
        return super().form_valid(form)


class InventoryUpdateView(LifeAccessMixin, UpdateView):
    """Edit inventory item."""
    model = InventoryItem
    template_name = "life/inventory_form.html"
    fields = [
        'name', 'description', 'category', 'location',
        'purchase_date', 'purchase_price', 'estimated_value',
        'condition', 'brand', 'model_number', 'serial_number',
        'warranty_expiration', 'warranty_info', 'notes'
    ]
    
    def get_queryset(self):
        return InventoryItem.objects.filter(user=self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('life:inventory_detail', kwargs={'pk': self.object.pk})


class InventoryDeleteView(LifeAccessMixin, DeleteView):
    """Delete inventory item."""
    model = InventoryItem
    template_name = "life/inventory_confirm_delete.html"
    success_url = reverse_lazy('life:inventory_list')
    
    def get_queryset(self):
        return InventoryItem.objects.filter(user=self.request.user)


# =============================================================================
# Inventory Photos
# =============================================================================

class InventoryPhotoCreateView(LifeAccessMixin, CreateView):
    """Add a photo to an inventory item."""
    model = InventoryPhoto
    template_name = "life/inventory_photo_form.html"
    fields = ['image', 'caption', 'is_primary']
    
    def dispatch(self, request, *args, **kwargs):
        self.item = get_object_or_404(InventoryItem, pk=kwargs['item_pk'], user=request.user)
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item'] = self.item
        return context
    
    def form_valid(self, form):
        form.instance.item = self.item
        
        # If marked as primary, unset other primary photos
        if form.cleaned_data.get('is_primary'):
            InventoryPhoto.objects.filter(item=self.item, is_primary=True).update(is_primary=False)
        
        messages.success(self.request, "Photo added.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('life:inventory_detail', kwargs={'pk': self.item.pk})


class InventoryPhotoDeleteView(LifeAccessMixin, DeleteView):
    """Delete an inventory photo."""
    model = InventoryPhoto
    template_name = "life/inventory_photo_confirm_delete.html"
    
    def get_queryset(self):
        return InventoryPhoto.objects.filter(item__user=self.request.user)
    
    def get_success_url(self):
        return reverse('life:inventory_detail', kwargs={'pk': self.object.item.pk})


class InventoryPhotoSetPrimaryView(LifeAccessMixin, View):
    """Set a photo as the primary photo for an item."""
    
    def post(self, request, pk):
        photo = get_object_or_404(InventoryPhoto, pk=pk, item__user=request.user)
        
        # Unset all other primary photos
        InventoryPhoto.objects.filter(item=photo.item, is_primary=True).update(is_primary=False)
        
        # Set this one as primary
        photo.is_primary = True
        photo.save()
        
        messages.success(request, "Primary photo updated.")
        return redirect('life:inventory_detail', pk=photo.item.pk)


# =============================================================================
# Pets
# =============================================================================

class PetListView(LifeAccessMixin, ListView):
    """List all pets."""
    model = Pet
    template_name = "life/pet_list.html"
    context_object_name = "pets"
    
    def get_queryset(self):
        return Pet.objects.filter(user=self.request.user)


class PetDetailView(LifeAccessMixin, DetailView):
    """View pet profile."""
    model = Pet
    template_name = "life/pet_detail.html"
    context_object_name = "pet"
    
    def get_queryset(self):
        return Pet.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['records'] = self.object.records.order_by('-date')[:10]
        return context


class PetCreateView(LifeAccessMixin, CreateView):
    """Add a new pet."""
    model = Pet
    template_name = "life/pet_form.html"
    fields = [
        'name', 'species', 'breed', 'birth_date', 'adoption_date',
        'color', 'weight', 'microchip_id', 'veterinarian', 'vet_phone',
        'photo', 'notes'
    ]
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Welcome, {form.instance.name}!")
        return super().form_valid(form)


class PetUpdateView(LifeAccessMixin, UpdateView):
    """Edit pet profile."""
    model = Pet
    template_name = "life/pet_form.html"
    fields = [
        'name', 'species', 'breed', 'birth_date', 'adoption_date',
        'color', 'weight', 'microchip_id', 'veterinarian', 'vet_phone',
        'photo', 'notes', 'is_active', 'passed_date'
    ]
    
    def get_queryset(self):
        return Pet.objects.filter(user=self.request.user)


# =============================================================================
# Pet Records
# =============================================================================

class PetRecordCreateView(LifeAccessMixin, CreateView):
    """Add a record to a pet."""
    model = PetRecord
    template_name = "life/pet_record_form.html"
    fields = ['record_type', 'date', 'title', 'description', 'cost', 'next_due_date']
    
    def dispatch(self, request, *args, **kwargs):
        self.pet = get_object_or_404(Pet, pk=kwargs['pet_pk'], user=request.user)
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pet'] = self.pet
        return context
    
    def form_valid(self, form):
        form.instance.pet = self.pet
        messages.success(self.request, f"Record added for {self.pet.name}.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('life:pet_detail', kwargs={'pk': self.pet.pk})


class PetRecordUpdateView(LifeAccessMixin, UpdateView):
    """Edit a pet record."""
    model = PetRecord
    template_name = "life/pet_record_form.html"
    fields = ['record_type', 'date', 'title', 'description', 'cost', 'next_due_date']
    
    def get_queryset(self):
        return PetRecord.objects.filter(pet__user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pet'] = self.object.pet
        return context
    
    def get_success_url(self):
        return reverse('life:pet_detail', kwargs={'pk': self.object.pet.pk})


class PetRecordDeleteView(LifeAccessMixin, DeleteView):
    """Delete a pet record."""
    model = PetRecord
    template_name = "life/pet_record_confirm_delete.html"
    
    def get_queryset(self):
        return PetRecord.objects.filter(pet__user=self.request.user)
    
    def get_success_url(self):
        return reverse('life:pet_detail', kwargs={'pk': self.object.pet.pk})


# =============================================================================
# Recipes
# =============================================================================

class RecipeListView(LifeAccessMixin, ListView):
    """List all recipes."""
    model = Recipe
    template_name = "life/recipe_list.html"
    context_object_name = "recipes"
    
    def get_queryset(self):
        queryset = Recipe.objects.filter(user=self.request.user)
        
        # Filter by category
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Filter favorites
        if self.request.GET.get('favorites'):
            queryset = queryset.filter(is_favorite=True)
        
        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(ingredients__icontains=search)
            )
        
        return queryset.order_by('-is_favorite', 'title')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = Recipe.objects.filter(
            user=self.request.user
        ).exclude(category='').values_list(
            'category', flat=True
        ).distinct().order_by('category')
        return context


class RecipeDetailView(LifeAccessMixin, DetailView):
    """View recipe details."""
    model = Recipe
    template_name = "life/recipe_detail.html"
    context_object_name = "recipe"
    
    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)


class RecipeCreateView(LifeAccessMixin, CreateView):
    """Add a new recipe."""
    model = Recipe
    template_name = "life/recipe_form.html"
    fields = [
        'title', 'description', 'ingredients', 'instructions',
        'prep_time_minutes', 'cook_time_minutes', 'servings',
        'difficulty', 'category', 'source', 'source_url',
        'image', 'notes', 'is_favorite'
    ]
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Recipe '{form.instance.title}' saved.")
        return super().form_valid(form)


class RecipeUpdateView(LifeAccessMixin, UpdateView):
    """Edit a recipe."""
    model = Recipe
    template_name = "life/recipe_form.html"
    fields = [
        'title', 'description', 'ingredients', 'instructions',
        'prep_time_minutes', 'cook_time_minutes', 'servings',
        'difficulty', 'category', 'source', 'source_url',
        'image', 'notes', 'is_favorite'
    ]
    
    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)


class RecipeDeleteView(LifeAccessMixin, DeleteView):
    """Delete a recipe."""
    model = Recipe
    template_name = "life/recipe_confirm_delete.html"
    success_url = reverse_lazy('life:recipe_list')
    
    def get_queryset(self):
        return Recipe.objects.filter(user=self.request.user)


class RecipeToggleFavoriteView(LifeAccessMixin, View):
    """Toggle recipe favorite status."""
    
    def post(self, request, pk):
        recipe = get_object_or_404(Recipe, pk=pk, user=request.user)
        recipe.is_favorite = not recipe.is_favorite
        recipe.save(update_fields=['is_favorite', 'updated_at'])
        return redirect('life:recipe_detail', pk=pk)


# =============================================================================
# Maintenance Logs
# =============================================================================

class MaintenanceLogListView(LifeAccessMixin, ListView):
    """List all maintenance logs."""
    model = MaintenanceLog
    template_name = "life/maintenance_list.html"
    context_object_name = "logs"
    
    def get_queryset(self):
        queryset = MaintenanceLog.objects.filter(user=self.request.user)
        
        # Filter by type
        log_type = self.request.GET.get('type')
        if log_type:
            queryset = queryset.filter(log_type=log_type)
        
        # Filter by area
        area = self.request.GET.get('area')
        if area:
            queryset = queryset.filter(area=area)
        
        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(area__icontains=search)
            )
        
        return queryset.order_by('-date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today
        user_logs = MaintenanceLog.objects.filter(user=self.request.user)

        # Get unique areas for filter
        context['areas'] = user_logs.values_list(
            'area', flat=True
        ).distinct().order_by('area')

        # Total spent
        context['total_spent'] = user_logs.aggregate(
            total=Sum('cost')
        )['total'] or 0

        # Upcoming follow-ups
        today = get_user_today(self.request.user)
        context['upcoming_followups'] = user_logs.filter(
            follow_up_date__gte=today
        ).order_by('follow_up_date')[:5]

        return context


class MaintenanceLogDetailView(LifeAccessMixin, DetailView):
    """View maintenance log details."""
    model = MaintenanceLog
    template_name = "life/maintenance_detail.html"
    context_object_name = "log"
    
    def get_queryset(self):
        return MaintenanceLog.objects.filter(user=self.request.user)


class MaintenanceLogCreateView(LifeAccessMixin, CreateView):
    """Create a new maintenance log."""
    model = MaintenanceLog
    template_name = "life/maintenance_form.html"
    fields = [
        'title', 'description', 'log_type', 'area', 'date',
        'cost', 'provider', 'provider_contact', 'inventory_item',
        'notes', 'follow_up_date'
    ]
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['inventory_item'].queryset = InventoryItem.objects.filter(
            user=self.request.user
        )
        return form
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Maintenance log '{form.instance.title}' added.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('life:maintenance_list')


class MaintenanceLogUpdateView(LifeAccessMixin, UpdateView):
    """Edit a maintenance log."""
    model = MaintenanceLog
    template_name = "life/maintenance_form.html"
    fields = [
        'title', 'description', 'log_type', 'area', 'date',
        'cost', 'provider', 'provider_contact', 'inventory_item',
        'notes', 'follow_up_date'
    ]
    
    def get_queryset(self):
        return MaintenanceLog.objects.filter(user=self.request.user)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['inventory_item'].queryset = InventoryItem.objects.filter(
            user=self.request.user
        )
        return form
    
    def get_success_url(self):
        return reverse('life:maintenance_detail', kwargs={'pk': self.object.pk})


class MaintenanceLogDeleteView(LifeAccessMixin, DeleteView):
    """Delete a maintenance log."""
    model = MaintenanceLog
    template_name = "life/maintenance_confirm_delete.html"
    success_url = reverse_lazy('life:maintenance_list')
    
    def get_queryset(self):
        return MaintenanceLog.objects.filter(user=self.request.user)


# =============================================================================
# Documents
# =============================================================================

class DocumentListView(LifeAccessMixin, ListView):
    """List all documents."""
    model = Document
    template_name = "life/document_list.html"
    context_object_name = "documents"
    
    def get_queryset(self):
        queryset = Document.objects.filter(user=self.request.user)
        
        # Filter by archived
        show_archived = self.request.GET.get('archived')
        if not show_archived:
            queryset = queryset.filter(is_archived=False)
        
        # Filter by category
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category=category)
        
        # Search
        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(notes__icontains=search)
            )
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.core.utils import get_user_today

        # Category choices for filter
        context['categories'] = Document.CATEGORY_CHOICES

        # Expiring soon
        today = get_user_today(self.request.user)
        thirty_days = today + timedelta(days=30)
        context['expiring_soon'] = Document.objects.filter(
            user=self.request.user,
            is_archived=False,
            expiration_date__isnull=False,
            expiration_date__lte=thirty_days,
            expiration_date__gte=today
        ).count()

        return context


class DocumentDetailView(LifeAccessMixin, DetailView):
    """View document details."""
    model = Document
    template_name = "life/document_detail.html"
    context_object_name = "document"
    
    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)


class DocumentCreateView(LifeAccessMixin, CreateView):
    """Upload a new document."""
    model = Document
    template_name = "life/document_form.html"
    fields = [
        'title', 'description', 'category', 'file',
        'document_date', 'expiration_date',
        'related_inventory_item', 'related_pet', 'notes'
    ]
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['related_inventory_item'].queryset = InventoryItem.objects.filter(
            user=self.request.user
        )
        form.fields['related_pet'].queryset = Pet.objects.filter(
            user=self.request.user
        )
        return form
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Document '{form.instance.title}' uploaded.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('life:document_list')


class DocumentUpdateView(LifeAccessMixin, UpdateView):
    """Edit document metadata."""
    model = Document
    template_name = "life/document_form.html"
    fields = [
        'title', 'description', 'category',
        'document_date', 'expiration_date',
        'related_inventory_item', 'related_pet', 'notes', 'is_archived'
    ]
    
    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['related_inventory_item'].queryset = InventoryItem.objects.filter(
            user=self.request.user
        )
        form.fields['related_pet'].queryset = Pet.objects.filter(
            user=self.request.user
        )
        return form
    
    def get_success_url(self):
        return reverse('life:document_detail', kwargs={'pk': self.object.pk})


class DocumentDeleteView(LifeAccessMixin, DeleteView):
    """Delete a document."""
    model = Document
    template_name = "life/document_confirm_delete.html"
    success_url = reverse_lazy('life:document_list')
    
    def get_queryset(self):
        return Document.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        # Delete the file from storage
        if self.object.file:
            self.object.file.delete(save=False)
        messages.success(self.request, f"Document '{self.object.title}' deleted.")
        return super().form_valid(form)


class DocumentDownloadView(LifeAccessMixin, View):
    """Download a document file."""
    
    def get(self, request, pk):
        document = get_object_or_404(Document, pk=pk, user=request.user)
        
        if document.file:
            response = FileResponse(
                document.file.open('rb'),
                as_attachment=True,
                filename=document.file.name.split('/')[-1]
            )
            return response
        
        messages.error(request, "File not found.")
        return redirect('life:document_detail', pk=pk)


# =============================================================================
# Google Calendar Integration
# =============================================================================

def get_user_google_credential(user):
    """Get the user's Google Calendar credential from database, or None."""
    from apps.life.models import GoogleCalendarCredential
    try:
        return user.google_calendar_credential
    except GoogleCalendarCredential.DoesNotExist:
        return None


class GoogleCalendarSettingsView(LifeAccessMixin, TemplateView):
    """Settings page for Google Calendar integration."""
    template_name = "life/google_calendar_settings.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Check if Google is configured in settings
        from django.conf import settings as django_settings
        context['is_configured'] = bool(
            getattr(django_settings, 'GOOGLE_CALENDAR_CLIENT_ID', None)
        )
        
        # Get credentials from database
        credential = get_user_google_credential(self.request.user)
        context['is_connected'] = credential is not None and credential.is_connected
        
        if context['is_connected'] and context['is_configured']:
            # Check if token needs refresh
            if credential.is_token_expired and credential.refresh_token:
                try:
                    self._refresh_token(credential)
                except Exception as e:
                    messages.warning(self.request, f"Could not refresh token: {str(e)}")
            
            # Get user's calendars
            try:
                from apps.life.services.google_calendar import GoogleCalendarService
                service = GoogleCalendarService()
                context['calendars'] = service.list_calendars(credential.get_credentials_dict())
            except Exception as e:
                context['calendars'] = []
                messages.warning(self.request, f"Could not load calendars: {str(e)}")
            
            # Get sync settings from database
            context['selected_calendar'] = credential.selected_calendar_id
            context['selected_calendar_name'] = credential.selected_calendar_name
            context['sync_direction'] = credential.sync_direction
            context['days_past'] = credential.days_past
            context['days_future'] = credential.days_future
            context['sync_types'] = credential.get_sync_event_types()
            context['auto_sync'] = credential.auto_sync_enabled
            context['last_sync'] = credential.last_sync
            context['last_sync_status'] = credential.last_sync_status
        
        # Available event types for the form
        context['available_event_types'] = [
            ('personal', 'Personal'),
            ('family', 'Family'),
            ('work', 'Work'),
            ('health', 'Health'),
            ('social', 'Social'),
            ('travel', 'Travel'),
            ('household', 'Household'),
            ('faith', 'Faith'),
            ('other', 'Other'),
        ]
        
        return context
    
    def _refresh_token(self, credential):
        """Refresh an expired access token."""
        from apps.life.services.google_calendar import GoogleCalendarService
        service = GoogleCalendarService()
        new_credentials = service.refresh_credentials(credential.get_credentials_dict())
        if new_credentials:
            credential.update_from_credentials(new_credentials)


class GoogleCalendarSaveSettingsView(LifeAccessMixin, View):
    """Save Google Calendar sync settings to database."""
    
    def post(self, request):
        credential = get_user_google_credential(request.user)
        
        if not credential:
            messages.error(request, "Please connect Google Calendar first.")
            return redirect('life:google_calendar_settings')
        
        # Update settings in database
        credential.selected_calendar_id = request.POST.get('calendar_id', 'primary')
        credential.sync_direction = request.POST.get('sync_direction', 'import')
        credential.days_past = int(request.POST.get('days_past', 0))
        credential.days_future = int(request.POST.get('days_future', 30))
        credential.auto_sync_enabled = request.POST.get('auto_sync') == 'on'
        
        # Sync types (checkboxes)
        sync_types = request.POST.getlist('sync_types')
        if sync_types:
            credential.set_sync_event_types(sync_types)
        
        # Get calendar name for display
        try:
            from apps.life.services.google_calendar import GoogleCalendarService
            service = GoogleCalendarService()
            calendars = service.list_calendars(credential.get_credentials_dict())
            for cal in calendars:
                if cal.get('id') == credential.selected_calendar_id:
                    credential.selected_calendar_name = cal.get('summary', '')
                    break
        except Exception:
            pass
        
        credential.save()
        messages.success(request, "Google Calendar settings saved.")
        
        return redirect('life:google_calendar_settings')


class GoogleCalendarConnectView(LifeAccessMixin, View):
    """Initiate Google Calendar OAuth2 flow."""
    
    def get(self, request):
        try:
            from apps.life.services.google_calendar import GoogleCalendarService
            
            service = GoogleCalendarService()
            state = secrets.token_urlsafe(32)
            request.session['google_oauth_state'] = state
            
            authorization_url, _ = service.get_authorization_url(state=state)
            return redirect(authorization_url)
            
        except ImportError as e:
            messages.error(request, str(e))
            return redirect('life:google_calendar_settings')
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('life:google_calendar_settings')


class GoogleCalendarCallbackView(LifeAccessMixin, View):
    """Handle Google Calendar OAuth2 callback and store credentials in database."""
    
    def get(self, request):
        from apps.life.models import GoogleCalendarCredential
        
        state = request.GET.get('state')
        stored_state = request.session.get('google_oauth_state')
        
        if state != stored_state:
            messages.error(request, "Invalid OAuth state. Please try again.")
            return redirect('life:google_calendar_settings')
        
        error = request.GET.get('error')
        if error:
            messages.error(request, f"Google Calendar authorization failed: {error}")
            return redirect('life:google_calendar_settings')
        
        code = request.GET.get('code')
        if not code:
            messages.error(request, "No authorization code received.")
            return redirect('life:google_calendar_settings')
        
        try:
            from apps.life.services.google_calendar import GoogleCalendarService
            
            service = GoogleCalendarService()
            credentials_dict = service.exchange_code_for_credentials(code)
            
            # Store credentials in database (create or update)
            credential, created = GoogleCalendarCredential.objects.update_or_create(
                user=request.user,
                defaults={
                    'access_token': credentials_dict.get('token', ''),
                    'refresh_token': credentials_dict.get('refresh_token', ''),
                    'token_uri': credentials_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'client_id': credentials_dict.get('client_id', ''),
                    'client_secret': credentials_dict.get('client_secret', ''),
                }
            )
            
            # Set expiry if available
            if credentials_dict.get('expiry'):
                credential.token_expiry = credentials_dict['expiry']
            
            if credentials_dict.get('scopes'):
                credential.set_scopes_list(credentials_dict['scopes'])
            
            credential.save()
            
            # Clear OAuth state from session
            if 'google_oauth_state' in request.session:
                del request.session['google_oauth_state']
            
            messages.success(request, "Google Calendar connected successfully! Configure your sync settings below.")
            return redirect('life:google_calendar_settings')
            
        except Exception as e:
            messages.error(request, f"Failed to connect Google Calendar: {str(e)}")
            return redirect('life:google_calendar_settings')


class GoogleCalendarDisconnectView(LifeAccessMixin, View):
    """Disconnect Google Calendar by removing credentials from database."""
    
    def post(self, request):
        from apps.life.models import GoogleCalendarCredential
        
        # Delete credentials from database
        GoogleCalendarCredential.objects.filter(user=request.user).delete()
        
        messages.success(request, "Google Calendar disconnected.")
        return redirect('life:google_calendar_settings')


class GoogleCalendarSyncView(LifeAccessMixin, View):
    """Sync events with Google Calendar using database-stored credentials."""
    
    def post(self, request):
        credential = get_user_google_credential(request.user)
        
        if not credential or not credential.is_connected:
            messages.error(request, "Please connect Google Calendar first.")
            return redirect('life:google_calendar_settings')
        
        # Refresh token if needed
        if credential.is_token_expired and credential.refresh_token:
            try:
                from apps.life.services.google_calendar import GoogleCalendarService
                service = GoogleCalendarService()
                new_creds = service.refresh_credentials(credential.get_credentials_dict())
                if new_creds:
                    credential.update_from_credentials(new_creds)
            except Exception as e:
                messages.error(request, f"Could not refresh token: {str(e)}")
                return redirect('life:google_calendar_settings')
        
        # Get sync settings from database
        credentials_dict = credential.get_credentials_dict()
        sync_action = request.POST.get('sync_action', credential.sync_direction)
        calendar_id = credential.selected_calendar_id
        days_past = credential.days_past
        days_future = credential.days_future
        
        stats = {'imported': 0, 'exported': 0, 'updated': 0}
        
        try:
            from apps.life.services.google_calendar import CalendarSyncService
            
            sync_service = CalendarSyncService(request.user)
            
            # Import from Google
            if sync_action in ('import', 'both'):
                created, updated = sync_service.sync_from_google(
                    credentials_dict,
                    calendar_id=calendar_id,
                    days_past=days_past,
                    days_ahead=days_future
                )
                stats['imported'] = created
                stats['updated'] += updated
            
            # Export to Google
            if sync_action in ('export', 'both'):
                exported = sync_service.sync_to_google_bulk(
                    credentials_dict,
                    calendar_id=calendar_id,
                    days_past=days_past,
                    days_ahead=days_future,
                    event_types=credential.get_sync_event_types()
                )
                stats['exported'] = exported
            
            # Record sync in database
            msg_parts = []
            if stats['imported']:
                msg_parts.append(f"{stats['imported']} imported")
            if stats['exported']:
                msg_parts.append(f"{stats['exported']} exported")
            if stats['updated']:
                msg_parts.append(f"{stats['updated']} updated")
            
            credential.record_sync(
                success=True,
                message=', '.join(msg_parts) if msg_parts else 'No changes'
            )
            
            if msg_parts:
                messages.success(request, f"Sync complete: {', '.join(msg_parts)}.")
            else:
                messages.info(request, "Sync complete. No changes needed.")
            
        except Exception as e:
            credential.record_sync(success=False, message=str(e))
            messages.error(request, f"Sync failed: {str(e)}")
        
        return redirect('life:google_calendar_settings')


class GoogleCalendarPushEventView(LifeAccessMixin, View):
    """Push a single event to Google Calendar."""
    
    def post(self, request, pk):
        credential = get_user_google_credential(request.user)
        
        if not credential or not credential.is_connected:
            messages.error(request, "Please connect Google Calendar first.")
            return redirect('life:event_update', pk=pk)
        
        calendar_id = credential.selected_calendar_id
        
        try:
            event = LifeEvent.objects.get(pk=pk, user=request.user)
            
            from apps.life.services.google_calendar import CalendarSyncService
            
            sync_service = CalendarSyncService(request.user)
            result = sync_service.sync_to_google(event, credential.get_credentials_dict(), calendar_id)
            
            if result:
                messages.success(request, "Event synced to Google Calendar.")
            else:
                messages.error(request, "Failed to sync event.")
            
        except LifeEvent.DoesNotExist:
            messages.error(request, "Event not found.")
        except Exception as e:
            messages.error(request, f"Sync failed: {str(e)}")
        
        return redirect('life:calendar')