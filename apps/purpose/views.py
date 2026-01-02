"""
Purpose Module Views

The strategic and spiritual compass for WLJ.
Visited seasonally, not daily.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import JsonResponse
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

from apps.help.mixins import HelpContextMixin

from .models import (
    LifeDomain,
    ReflectionPrompt,
    AnnualDirection,
    LifeGoal,
    ChangeIntention,
    Reflection,
    ReflectionResponse,
    PlanningAction,
    HabitGoal,
    HabitEntry,
)


class PurposeAccessMixin(LoginRequiredMixin):
    """Base mixin for Purpose module views."""
    pass


# =============================================================================
# Dashboard / Home
# =============================================================================

class PurposeHomeView(HelpContextMixin, PurposeAccessMixin, TemplateView):
    """
    Purpose module dashboard.
    Shows current direction, active goals, and intentions.
    """
    template_name = "purpose/home.html"
    help_context_id = "PURPOSE_HOME"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        current_year = timezone.now().year
        
        # Current annual direction
        context['current_direction'] = AnnualDirection.objects.filter(
            user=user,
            is_current=True
        ).first()
        
        # If no current, try to get this year's
        if not context['current_direction']:
            context['current_direction'] = AnnualDirection.objects.filter(
                user=user,
                year=current_year
            ).first()
        
        # Active goals by domain
        context['active_goals'] = LifeGoal.objects.filter(
            user=user,
            status='active'
        ).select_related('domain').order_by('domain__sort_order', 'sort_order')
        
        # Goals grouped by domain for display
        goals_by_domain = {}
        for goal in context['active_goals']:
            domain_name = goal.domain.name if goal.domain else 'Other'
            if domain_name not in goals_by_domain:
                goals_by_domain[domain_name] = []
            goals_by_domain[domain_name].append(goal)
        context['goals_by_domain'] = goals_by_domain
        
        # Active intentions
        context['active_intentions'] = ChangeIntention.objects.filter(
            user=user,
            status='active'
        ).order_by('sort_order')[:5]
        
        # Stats
        context['stats'] = {
            'total_goals': LifeGoal.objects.filter(user=user).count(),
            'active_goals': LifeGoal.objects.filter(user=user, status='active').count(),
            'completed_goals': LifeGoal.objects.filter(user=user, status='completed').count(),
            'active_intentions': ChangeIntention.objects.filter(user=user, status='active').count(),
        }
        
        # Domains for quick reference
        context['domains'] = LifeDomain.objects.filter(is_active=True)
        
        # Recent reflections
        context['recent_reflections'] = Reflection.objects.filter(
            user=user
        ).order_by('-year', '-created_at')[:3]
        
        return context


# =============================================================================
# Annual Direction
# =============================================================================

class DirectionListView(PurposeAccessMixin, ListView):
    """List all annual directions."""
    model = AnnualDirection
    template_name = "purpose/direction_list.html"
    context_object_name = "directions"
    
    def get_queryset(self):
        return AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')


class DirectionDetailView(PurposeAccessMixin, DetailView):
    """View annual direction details."""
    model = AnnualDirection
    template_name = "purpose/direction_detail.html"
    context_object_name = "direction"
    
    def get_queryset(self):
        return AnnualDirection.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get goals linked to this direction
        context['goals'] = self.object.goals.all()
        context['intentions'] = self.object.intentions.all()
        context['planning_actions'] = self.object.planning_actions.all()
        return context


class DirectionCreateView(PurposeAccessMixin, CreateView):
    """Create a new annual direction."""
    model = AnnualDirection
    template_name = "purpose/direction_form.html"
    fields = [
        'year', 'word_of_year', 'word_explanation',
        'theme', 'theme_description',
        'anchor_text', 'anchor_source', 'is_current'
    ]
    
    def get_initial(self):
        initial = super().get_initial()
        # Default to next year if creating in Q4, else current year
        today = timezone.now()
        if today.month >= 10:
            initial['year'] = today.year + 1
        else:
            initial['year'] = today.year
        return initial
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Direction for {form.instance.year} created.")
        return super().form_valid(form)


class DirectionUpdateView(PurposeAccessMixin, UpdateView):
    """Edit annual direction."""
    model = AnnualDirection
    template_name = "purpose/direction_form.html"
    fields = [
        'year', 'word_of_year', 'word_explanation',
        'theme', 'theme_description',
        'anchor_text', 'anchor_source', 'is_current'
    ]
    
    def get_queryset(self):
        return AnnualDirection.objects.filter(user=self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, f"Direction for {form.instance.year} updated.")
        return super().form_valid(form)


class DirectionDeleteView(PurposeAccessMixin, DeleteView):
    """Delete annual direction."""
    model = AnnualDirection
    template_name = "purpose/direction_confirm_delete.html"
    success_url = reverse_lazy('purpose:direction_list')
    
    def get_queryset(self):
        return AnnualDirection.objects.filter(user=self.request.user)


# =============================================================================
# Life Goals
# =============================================================================

class GoalListView(PurposeAccessMixin, ListView):
    """List all life goals."""
    model = LifeGoal
    template_name = "purpose/goal_list.html"
    context_object_name = "goals"
    
    def get_queryset(self):
        queryset = LifeGoal.objects.filter(
            user=self.request.user
        ).select_related('domain')
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        else:
            # Default: show active
            queryset = queryset.filter(status='active')
        
        # Filter by domain
        domain = self.request.GET.get('domain')
        if domain:
            queryset = queryset.filter(domain__slug=domain)
        
        return queryset.order_by('domain__sort_order', 'sort_order', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['domains'] = LifeDomain.objects.filter(is_active=True)
        context['current_status'] = self.request.GET.get('status', 'active')
        context['current_domain'] = self.request.GET.get('domain', '')
        
        # Group goals by domain
        goals_by_domain = {}
        for goal in context['goals']:
            domain_name = goal.domain.name if goal.domain else 'Other'
            if domain_name not in goals_by_domain:
                goals_by_domain[domain_name] = []
            goals_by_domain[domain_name].append(goal)
        context['goals_by_domain'] = goals_by_domain
        
        return context


class GoalDetailView(PurposeAccessMixin, DetailView):
    """View goal details."""
    model = LifeGoal
    template_name = "purpose/goal_detail.html"
    context_object_name = "goal"
    
    def get_queryset(self):
        return LifeGoal.objects.filter(user=self.request.user)


class GoalCreateView(PurposeAccessMixin, CreateView):
    """Create a new goal."""
    model = LifeGoal
    template_name = "purpose/goal_form.html"
    fields = [
        'title', 'description', 'why_it_matters', 'success_looks_like',
        'domain', 'timeframe', 'target_date', 'annual_direction'
    ]
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['domain'].queryset = LifeDomain.objects.filter(is_active=True)
        form.fields['annual_direction'].queryset = AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')
        return form
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Goal '{form.instance.title}' created.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('purpose:goal_list')


class GoalUpdateView(PurposeAccessMixin, UpdateView):
    """Edit a goal."""
    model = LifeGoal
    template_name = "purpose/goal_form.html"
    fields = [
        'title', 'description', 'why_it_matters', 'success_looks_like',
        'domain', 'timeframe', 'target_date', 'status', 'reflection',
        'annual_direction'
    ]
    
    def get_queryset(self):
        return LifeGoal.objects.filter(user=self.request.user)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['domain'].queryset = LifeDomain.objects.filter(is_active=True)
        form.fields['annual_direction'].queryset = AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')
        return form
    
    def form_valid(self, form):
        messages.success(self.request, f"Goal '{form.instance.title}' updated.")
        return super().form_valid(form)


class GoalDeleteView(PurposeAccessMixin, DeleteView):
    """Delete a goal."""
    model = LifeGoal
    template_name = "purpose/goal_confirm_delete.html"
    success_url = reverse_lazy('purpose:goal_list')
    
    def get_queryset(self):
        return LifeGoal.objects.filter(user=self.request.user)


class GoalToggleStatusView(PurposeAccessMixin, View):
    """Quick status toggle for goals."""
    
    def post(self, request, pk):
        goal = get_object_or_404(LifeGoal, pk=pk, user=request.user)
        action = request.POST.get('action')
        
        if action == 'complete':
            goal.mark_complete()
            messages.success(request, f"Goal '{goal.title}' marked complete!")
        elif action == 'release':
            goal.mark_released()
            messages.success(request, f"Goal '{goal.title}' released.")
        elif action == 'pause':
            goal.status = 'paused'
            goal.save(update_fields=['status', 'updated_at'])
            messages.info(request, f"Goal '{goal.title}' paused.")
        elif action == 'activate':
            goal.status = 'active'
            goal.save(update_fields=['status', 'updated_at'])
            messages.success(request, f"Goal '{goal.title}' activated.")

        # Return to referring page or goal list (with open redirect protection)
        from apps.core.utils import get_safe_redirect_url
        next_url = get_safe_redirect_url(request)
        if next_url:
            return redirect(next_url)
        return redirect('purpose:goal_list')


# =============================================================================
# Change Intentions
# =============================================================================

class IntentionListView(PurposeAccessMixin, ListView):
    """List all change intentions."""
    model = ChangeIntention
    template_name = "purpose/intention_list.html"
    context_object_name = "intentions"
    
    def get_queryset(self):
        queryset = ChangeIntention.objects.filter(user=self.request.user)
        
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        else:
            queryset = queryset.filter(status='active')
        
        return queryset.order_by('sort_order', '-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_status'] = self.request.GET.get('status', 'active')
        return context


class IntentionDetailView(PurposeAccessMixin, DetailView):
    """View intention details."""
    model = ChangeIntention
    template_name = "purpose/intention_detail.html"
    context_object_name = "intention"
    
    def get_queryset(self):
        return ChangeIntention.objects.filter(user=self.request.user)


class IntentionCreateView(PurposeAccessMixin, CreateView):
    """Create a new intention."""
    model = ChangeIntention
    template_name = "purpose/intention_form.html"
    fields = ['intention', 'description', 'motivation', 'annual_direction']
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['annual_direction'].queryset = AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')
        return form
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Intention '{form.instance.intention}' added.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('purpose:intention_list')


class IntentionUpdateView(PurposeAccessMixin, UpdateView):
    """Edit an intention."""
    model = ChangeIntention
    template_name = "purpose/intention_form.html"
    fields = ['intention', 'description', 'motivation', 'status', 'annual_direction']
    
    def get_queryset(self):
        return ChangeIntention.objects.filter(user=self.request.user)
    
    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['annual_direction'].queryset = AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')
        return form


class IntentionDeleteView(PurposeAccessMixin, DeleteView):
    """Delete an intention."""
    model = ChangeIntention
    template_name = "purpose/intention_confirm_delete.html"
    success_url = reverse_lazy('purpose:intention_list')
    
    def get_queryset(self):
        return ChangeIntention.objects.filter(user=self.request.user)


# =============================================================================
# Reflections
# =============================================================================

class ReflectionListView(PurposeAccessMixin, ListView):
    """List all reflections."""
    model = Reflection
    template_name = "purpose/reflection_list.html"
    context_object_name = "reflections"
    
    def get_queryset(self):
        return Reflection.objects.filter(
            user=self.request.user
        ).order_by('-year', '-created_at')


class ReflectionDetailView(PurposeAccessMixin, DetailView):
    """View reflection with all responses."""
    model = Reflection
    template_name = "purpose/reflection_detail.html"
    context_object_name = "reflection"
    
    def get_queryset(self):
        return Reflection.objects.filter(user=self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['responses'] = self.object.responses.all()
        return context


class ReflectionCreateView(PurposeAccessMixin, CreateView):
    """Start a new reflection."""
    model = Reflection
    template_name = "purpose/reflection_form.html"
    fields = ['reflection_type', 'year', 'quarter', 'title']
    
    def get_initial(self):
        initial = super().get_initial()
        initial['year'] = timezone.now().year
        return initial
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        
        # Create response placeholders for prompts of this type
        prompts = ReflectionPrompt.objects.filter(
            prompt_type=form.instance.reflection_type,
            is_active=True
        ).order_by('sort_order')
        
        for i, prompt in enumerate(prompts):
            ReflectionResponse.objects.create(
                reflection=self.object,
                prompt=prompt,
                question_text=prompt.question,
                sort_order=i
            )
        
        messages.success(self.request, "Reflection started. Take your time.")
        return response
    
    def get_success_url(self):
        return reverse('purpose:reflection_edit', kwargs={'pk': self.object.pk})


class ReflectionEditView(PurposeAccessMixin, TemplateView):
    """Edit reflection responses (custom view for better UX)."""
    template_name = "purpose/reflection_edit.html"
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reflection'] = get_object_or_404(
            Reflection, pk=self.kwargs['pk'], user=self.request.user
        )
        context['responses'] = context['reflection'].responses.all()
        return context
    
    def post(self, request, pk):
        reflection = get_object_or_404(Reflection, pk=pk, user=request.user)
        
        # Update each response
        for response in reflection.responses.all():
            field_name = f'response_{response.id}'
            if field_name in request.POST:
                response.response = request.POST[field_name]
                response.save()
        
        # Check if marking complete
        if request.POST.get('mark_complete'):
            reflection.mark_complete()
            messages.success(request, "Reflection completed. Well done on taking time to reflect.")
            return redirect('purpose:reflection_detail', pk=pk)
        
        messages.success(request, "Responses saved.")
        return redirect('purpose:reflection_edit', pk=pk)


class ReflectionDeleteView(PurposeAccessMixin, DeleteView):
    """Delete a reflection."""
    model = Reflection
    template_name = "purpose/reflection_confirm_delete.html"
    success_url = reverse_lazy('purpose:reflection_list')
    
    def get_queryset(self):
        return Reflection.objects.filter(user=self.request.user)


# =============================================================================
# Planning Actions
# =============================================================================

class PlanningActionCreateView(PurposeAccessMixin, CreateView):
    """Add a planning action to a direction."""
    model = PlanningAction
    template_name = "purpose/planning_action_form.html"
    fields = ['action_type', 'description', 'reason']
    
    def dispatch(self, request, *args, **kwargs):
        self.direction = get_object_or_404(
            AnnualDirection, pk=kwargs['direction_pk'], user=request.user
        )
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['direction'] = self.direction
        return context
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.annual_direction = self.direction
        messages.success(self.request, "Planning action added.")
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse('purpose:direction_detail', kwargs={'pk': self.direction.pk})


class PlanningActionDeleteView(PurposeAccessMixin, DeleteView):
    """Delete a planning action."""
    model = PlanningAction
    template_name = "purpose/planning_action_confirm_delete.html"

    def get_queryset(self):
        return PlanningAction.objects.filter(user=self.request.user)

    def get_success_url(self):
        return reverse('purpose:direction_detail', kwargs={'pk': self.object.annual_direction.pk})


# =============================================================================
# Habit Goals
# =============================================================================

class HabitGoalListView(PurposeAccessMixin, ListView):
    """List all habit goals."""
    model = HabitGoal
    template_name = "purpose/habit_goal_list.html"
    context_object_name = "habit_goals"

    def get_queryset(self):
        queryset = HabitGoal.objects.filter(
            user=self.request.user
        ).select_related('domain')

        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        else:
            # Default: show active
            queryset = queryset.filter(status='active')

        return queryset.order_by('-start_date', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['current_status'] = self.request.GET.get('status', 'active')
        return context


class HabitGoalDetailView(HelpContextMixin, PurposeAccessMixin, DetailView):
    """View habit goal details with matrix."""
    model = HabitGoal
    template_name = "purpose/habit_goal_detail.html"
    context_object_name = "goal"
    help_context_id = "HABIT_GOAL_DETAIL"

    def get_queryset(self):
        return HabitGoal.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()

        # Get matrix data organized as rows
        context['matrix_rows'] = self.object.get_matrix_as_rows()

        # Check if today is within goal range for "I Did It" button
        context['can_log_today'] = (
            self.object.start_date <= today <= self.object.end_date
            and self.object.habit_required
        )

        # Check if today already logged
        context['today_logged'] = self.object.habit_entries.filter(
            date=today, completed=True
        ).exists()

        # Get the min/max valid dates for the date picker
        context['min_date'] = self.object.start_date.isoformat()
        context['max_date'] = min(self.object.end_date, today).isoformat()

        return context


class HabitGoalCreateView(PurposeAccessMixin, CreateView):
    """Create a new habit goal."""
    model = HabitGoal
    template_name = "purpose/habit_goal_form.html"
    fields = [
        'name', 'purpose', 'description', 'success_criteria',
        'start_date', 'end_date', 'habit_required', 'domain',
        'annual_direction'
    ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['domain'].queryset = LifeDomain.objects.filter(is_active=True)
        form.fields['annual_direction'].queryset = AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Habit goal '{form.instance.name}' created.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('purpose:habit_goal_detail', kwargs={'pk': self.object.pk})


class HabitGoalUpdateView(PurposeAccessMixin, UpdateView):
    """Edit a habit goal."""
    model = HabitGoal
    template_name = "purpose/habit_goal_form.html"
    fields = [
        'name', 'purpose', 'description', 'success_criteria',
        'start_date', 'end_date', 'habit_required', 'domain',
        'status', 'annual_direction'
    ]

    def get_queryset(self):
        return HabitGoal.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['domain'].queryset = LifeDomain.objects.filter(is_active=True)
        form.fields['annual_direction'].queryset = AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')
        return form

    def form_valid(self, form):
        messages.success(self.request, f"Habit goal '{form.instance.name}' updated.")
        return super().form_valid(form)


class HabitGoalDeleteView(PurposeAccessMixin, DeleteView):
    """Delete a habit goal."""
    model = HabitGoal
    template_name = "purpose/habit_goal_confirm_delete.html"
    success_url = reverse_lazy('purpose:habit_goal_list')

    def get_queryset(self):
        return HabitGoal.objects.filter(user=self.request.user)


# =============================================================================
# Habit Logging Controls
# =============================================================================

class HabitLogTodayView(PurposeAccessMixin, View):
    """
    Log habit completion for today via AJAX.

    POST /purpose/habits/<pk>/log-today/
    Returns JSON with success status and updated box state.
    """

    def post(self, request, pk):
        goal = get_object_or_404(HabitGoal, pk=pk, user=request.user)
        today = timezone.now().date()

        # Validate goal has habit tracking
        if not goal.habit_required:
            return JsonResponse({
                'success': False,
                'error': 'This goal does not have habit tracking enabled.'
            }, status=400)

        # Validate today is within goal range
        if today < goal.start_date:
            return JsonResponse({
                'success': False,
                'error': 'Goal has not started yet.'
            }, status=400)

        if today > goal.end_date:
            return JsonResponse({
                'success': False,
                'error': 'Goal has already ended.'
            }, status=400)

        # Create or update today's entry
        entry, created = HabitEntry.objects.update_or_create(
            goal=goal,
            date=today,
            defaults={'completed': True}
        )

        # Calculate which box number this corresponds to
        day_number = (today - goal.start_date).days + 1

        return JsonResponse({
            'success': True,
            'created': created,
            'date': today.isoformat(),
            'day_number': day_number,
            'state': 'completed',
            'message': 'Great job! Habit logged for today.' if created else 'Already logged for today.'
        })


class HabitLogDateView(PurposeAccessMixin, View):
    """
    Log habit completion for a specific date via AJAX.

    POST /purpose/habits/<pk>/log-date/
    Body: {"date": "YYYY-MM-DD"}
    Returns JSON with success status and updated box state.
    """

    def post(self, request, pk):
        import json
        goal = get_object_or_404(HabitGoal, pk=pk, user=request.user)
        today = timezone.now().date()

        # Parse date from request body
        try:
            data = json.loads(request.body)
            date_str = data.get('date')
            if not date_str:
                return JsonResponse({
                    'success': False,
                    'error': 'Date is required.'
                }, status=400)

            from datetime import datetime
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (json.JSONDecodeError, ValueError) as e:
            return JsonResponse({
                'success': False,
                'error': f'Invalid date format. Use YYYY-MM-DD.'
            }, status=400)

        # Validate goal has habit tracking
        if not goal.habit_required:
            return JsonResponse({
                'success': False,
                'error': 'This goal does not have habit tracking enabled.'
            }, status=400)

        # Validate date is within goal range
        if selected_date < goal.start_date:
            return JsonResponse({
                'success': False,
                'error': f'Date cannot be before goal start date ({goal.start_date}).'
            }, status=400)

        if selected_date > goal.end_date:
            return JsonResponse({
                'success': False,
                'error': f'Date cannot be after goal end date ({goal.end_date}).'
            }, status=400)

        # Validate not future date
        if selected_date > today:
            return JsonResponse({
                'success': False,
                'error': 'Cannot log habits for future dates.'
            }, status=400)

        # Create or update entry for selected date
        entry, created = HabitEntry.objects.update_or_create(
            goal=goal,
            date=selected_date,
            defaults={'completed': True}
        )

        # Calculate which box number this corresponds to
        day_number = (selected_date - goal.start_date).days + 1

        return JsonResponse({
            'success': True,
            'created': created,
            'date': selected_date.isoformat(),
            'day_number': day_number,
            'state': 'completed',
            'message': f'Habit logged for {selected_date}.' if created else f'Already logged for {selected_date}.'
        })
