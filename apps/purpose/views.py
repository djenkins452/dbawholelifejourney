"""
Purpose Module Views

The strategic and spiritual compass for WLJ.
Visited seasonally, not daily.
"""
import json

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Max
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

from apps.core.utils import get_user_today
from apps.core.views import SaveAddAnotherMixin
from apps.help.mixins import HelpContextMixin

from .models import (
    LifeDomain,
    ReflectionPrompt,
    AnnualDirection,
    LifeGoal,
    GoalMilestone,
    ChangeIntention,
    Reflection,
    ReflectionResponse,
    PlanningAction,
    HabitGoal,
    HabitEntry,
    GoalInsight,
)
from .services import streak_service, analytics_service, recommendation_service


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

        # Active habit goals
        context['active_habit_goals'] = HabitGoal.objects.filter(
            user=user,
            status='active'
        ).select_related('domain').order_by('start_date')[:5]

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

        # AI insight — engine-first: read latest PIE insight (no OpenAI)
        from apps.core.ai_insights.services import get_module_insight
        context['ai_insight'] = get_module_insight(user, 'purpose')
        context['ai_enabled'] = getattr(user.preferences, 'ai_enabled', False)

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
        from django.db import IntegrityError

        form.instance.user = self.request.user
        year = form.cleaned_data['year']

        # Check if user already has a direction for this year
        existing = AnnualDirection.objects.filter(
            user=self.request.user,
            year=year
        ).first()

        if existing:
            messages.info(
                self.request,
                f"You already have a direction for {year}. Redirecting to edit it."
            )
            return redirect('purpose:direction_update', pk=existing.pk)

        # Try to save, handle race condition if duplicate created between check and save
        try:
            messages.success(self.request, f"Direction for {year} created.")
            return super().form_valid(form)
        except IntegrityError:
            # Race condition - another request created the record
            existing = AnnualDirection.objects.filter(
                user=self.request.user,
                year=year
            ).first()
            if existing:
                messages.info(
                    self.request,
                    f"You already have a direction for {year}. Redirecting to edit it."
                )
                return redirect('purpose:direction_update', pk=existing.pk)
            raise  # Re-raise if it's a different IntegrityError


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
        return LifeGoal.objects.filter(user=self.request.user).prefetch_related('milestones')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Check if this goal is ready to be completed (all milestones done)
        goal_ready_pk = self.request.session.pop('goal_ready_to_complete', None)
        context['show_completion_modal'] = (
            goal_ready_pk == self.object.pk and
            self.object.all_milestones_complete and
            self.object.status == 'active'
        )

        return context


class GoalCreateView(SaveAddAnotherMixin, PurposeAccessMixin, CreateView):
    """Create a new goal."""
    model = LifeGoal
    template_name = "purpose/goal_form.html"
    fields = [
        'title', 'description', 'why_it_matters', 'success_looks_like',
        'domain', 'timeframe', 'target_date', 'annual_direction'
    ]
    save_add_another_message = "Goal '{title}' created. Add another!"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['domain'].queryset = LifeDomain.objects.filter(is_active=True)
        form.fields['annual_direction'].queryset = AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        if 'save_add_another' not in self.request.POST:
            messages.success(self.request, f"Goal '{form.instance.title}' created.")
        response = super().form_valid(form)
        from apps.core.ai_orchestrator.intelligence_hook import fire_intelligence
        fire_intelligence(self.request.user, "purpose", self.object.id, "create_goal")
        return response

    def get_success_url(self):
        return reverse('purpose:goal_detail', kwargs={'pk': self.object.pk})


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
            try:
                from apps.cos.services.completion_service import CosCompletionService
                CosCompletionService.on_goal_completed(goal)
            except Exception:
                pass
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
        # Annotate each goal with streak data for display
        for goal in context['habit_goals']:
            goal.streak_info = streak_service.get_streak_data(goal)
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
        today = get_user_today(self.request.user)
        goal = self.object

        # Get matrix data organized as rows
        context['matrix_rows'] = goal.get_matrix_as_rows()

        # Check if today is within goal range for "I Did It" button
        context['can_log_today'] = (
            goal.start_date <= today <= goal.end_date
            and goal.habit_required
        )

        # Check if today already logged
        context['today_logged'] = goal.habit_entries.filter(
            date=today, completed=True
        ).exists()

        # Get the min/max valid dates for the date picker
        context['min_date'] = goal.start_date.isoformat()
        context['max_date'] = min(goal.end_date, today).isoformat()

        # ── Measurement Engine Context ──
        context['measurement_type'] = goal.measurement_type
        context['is_duration'] = goal.is_duration
        context['is_count'] = goal.is_count
        context['is_binary'] = goal.is_binary
        context['is_target'] = goal.is_target

        # Streak data
        context['streak_data'] = streak_service.get_streak_data(goal)

        # Target and unit info
        context['target_value'] = goal.target_value
        context['target_unit'] = goal.target_unit_display
        context['sessions_per_week'] = goal.sessions_per_week
        context['weekly_sessions'] = goal.get_weekly_session_count()
        context['weekly_progress'] = goal.weekly_progress_percent

        # Measurement-specific stats
        if goal.is_duration:
            context['avg_duration'] = goal.avg_duration
        elif goal.is_count:
            context['total_count'] = goal.total_count
        elif goal.is_target:
            context['running_total'] = goal.running_total

        # Today's entry value (for pre-filling UI)
        today_entry = goal.habit_entries.filter(date=today).first()
        context['today_entry'] = today_entry

        # Active insights
        context['insights'] = recommendation_service.get_active_insights(goal)[:5]

        # Show upgrade banner for binary goals created before measurement
        # types were added. Hide once the user has edited the goal (updated_at
        # after the feature deploy indicates they've seen the new options).
        from datetime import datetime
        from django.utils import timezone as tz
        measurement_feature_date = tz.make_aware(datetime(2026, 2, 14, 20, 0, 0))
        context['show_upgrade_banner'] = (
            goal.is_binary
            and goal.target_value is None
            and goal.habit_required
            and goal.status == 'active'
            and goal.updated_at < measurement_feature_date
        )

        return context


TARGET_UNIT_CHOICES = [
    ('', '— Select unit —'),
    ('minutes', 'Minutes'),
    ('hours', 'Hours'),
    ('pages', 'Pages'),
    ('reps', 'Reps'),
    ('sets', 'Sets'),
    ('miles', 'Miles'),
    ('km', 'Kilometers'),
    ('steps', 'Steps'),
    ('glasses', 'Glasses'),
    ('oz', 'Ounces'),
    ('calories', 'Calories'),
    ('words', 'Words'),
    ('laps', 'Laps'),
    ('sessions', 'Sessions'),
    ('items', 'Items'),
    ('dollars', 'Dollars'),
    ('percent', 'Percent'),
]


def _apply_goal_form_widgets(form):
    """Apply shared widget customizations for habit goal forms."""
    from django.forms import DateInput, Select
    # Native date pickers
    for field_name in ('start_date', 'end_date'):
        form.fields[field_name].widget = DateInput(
            attrs={'type': 'date', 'class': 'date-input'}
        )
    # Target unit dropdown
    form.fields['target_unit'].widget = Select(choices=TARGET_UNIT_CHOICES)


class HabitGoalCreateView(PurposeAccessMixin, CreateView):
    """Create a new habit goal."""
    model = HabitGoal
    template_name = "purpose/habit_goal_form.html"
    fields = [
        'name', 'purpose', 'description', 'success_criteria',
        'start_date', 'end_date', 'habit_required',
        'measurement_type', 'frequency_type', 'target_value',
        'target_unit', 'sessions_per_week', 'category',
        'domain', 'annual_direction',
    ]

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['domain'].queryset = LifeDomain.objects.filter(is_active=True)
        form.fields['annual_direction'].queryset = AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')
        _apply_goal_form_widgets(form)
        return form

    def form_valid(self, form):
        form.instance.user = self.request.user
        messages.success(self.request, f"Habit goal '{form.instance.name}' created.")
        response = super().form_valid(form)
        from apps.core.ai_orchestrator.intelligence_hook import fire_intelligence
        fire_intelligence(self.request.user, "purpose", self.object.id, "create_habit")
        return response

    def get_success_url(self):
        return reverse('purpose:habit_goal_detail', kwargs={'pk': self.object.pk})


class HabitGoalUpdateView(PurposeAccessMixin, UpdateView):
    """Edit a habit goal."""
    model = HabitGoal
    template_name = "purpose/habit_goal_form.html"
    fields = [
        'name', 'purpose', 'description', 'success_criteria',
        'start_date', 'end_date', 'habit_required',
        'measurement_type', 'frequency_type', 'target_value',
        'target_unit', 'sessions_per_week', 'category',
        'domain', 'status', 'annual_direction',
    ]

    def get_queryset(self):
        return HabitGoal.objects.filter(user=self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['domain'].queryset = LifeDomain.objects.filter(is_active=True)
        form.fields['annual_direction'].queryset = AnnualDirection.objects.filter(
            user=self.request.user
        ).order_by('-year')
        _apply_goal_form_widgets(form)
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
        today = get_user_today(request.user)

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

        # Build defaults for manual logging.
        # For non-binary goals, set measurement value to target so auto-calc
        # in save() correctly marks as completed.
        defaults = {'completed': True}
        if goal.target_value:
            if goal.is_duration:
                defaults['duration_minutes'] = goal.target_value
            elif goal.is_count:
                defaults['count_value'] = goal.target_value

        try:
            # Create or update today's entry (session_number=1 for manual logging)
            entry, created = HabitEntry.objects.update_or_create(
                goal=goal,
                date=today,
                session_number=1,
                defaults=defaults,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("HabitLogTodayView error")
            return JsonResponse({
                'success': False,
                'error': f'Failed to log habit: {str(e)}'
            }, status=500)

        # Calculate which box number this corresponds to
        day_number = (today - goal.start_date).days + 1

        # Fire intelligence chain
        from apps.core.ai_orchestrator.intelligence_hook import fire_intelligence
        fire_intelligence(request.user, "purpose", entry.id, "log_habit")

        # Sync with CoS — cancel pre-prompt, schedule reflection
        try:
            from apps.cos.services.completion_service import CosCompletionService
            CosCompletionService.on_habit_logged(goal, today, request.user)
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'created': created,
            'date': today.isoformat(),
            'day_number': day_number,
            'state': 'completed',
            'message': 'Great job! Habit logged for today.' if created else 'Already logged for today.',
            'stats': {
                'completed_days': goal.completed_days,
                'completion_rate': round(goal.completion_rate),
                'current_streak': goal.current_streak,
            }
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
        today = get_user_today(request.user)

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
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({
                'success': False,
                'error': 'Invalid date format. Use YYYY-MM-DD.'
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

        # Build defaults for manual logging.
        defaults = {'completed': True}
        if goal.target_value:
            if goal.is_duration:
                defaults['duration_minutes'] = goal.target_value
            elif goal.is_count:
                defaults['count_value'] = goal.target_value

        # Create or update entry for selected date (session_number=1 for manual logging)
        entry, created = HabitEntry.objects.update_or_create(
            goal=goal,
            date=selected_date,
            session_number=1,
            defaults=defaults,
        )

        # Calculate which box number this corresponds to
        day_number = (selected_date - goal.start_date).days + 1

        # Sync with CoS — cancel pre-prompt, schedule reflection
        try:
            from apps.cos.services.completion_service import CosCompletionService
            CosCompletionService.on_habit_logged(goal, selected_date, request.user)
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'created': created,
            'date': selected_date.isoformat(),
            'day_number': day_number,
            'state': 'completed',
            'message': f'Habit logged for {selected_date}.' if created else f'Already logged for {selected_date}.',
            'stats': {
                'completed_days': goal.completed_days,
                'completion_rate': round(goal.completion_rate),
                'current_streak': goal.current_streak,
            }
        })


class HabitLogDatesView(PurposeAccessMixin, View):
    """
    Log habit completion for multiple dates at once via AJAX.

    POST /purpose/habits/<pk>/log-dates/
    Body: {"dates": ["YYYY-MM-DD", "YYYY-MM-DD", ...]}
    Returns JSON with success status and updated stats.
    """

    def post(self, request, pk):
        import json
        goal = get_object_or_404(HabitGoal, pk=pk, user=request.user)
        today = get_user_today(request.user)

        # Parse dates from request body
        try:
            data = json.loads(request.body)
            date_strings = data.get('dates')
            if not date_strings or not isinstance(date_strings, list):
                return JsonResponse({
                    'success': False,
                    'error': 'A list of dates is required.'
                }, status=400)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON.'
            }, status=400)

        if len(date_strings) > 366:
            return JsonResponse({
                'success': False,
                'error': 'Too many dates. Maximum 366 per request.'
            }, status=400)

        if not goal.habit_required:
            return JsonResponse({
                'success': False,
                'error': 'This goal does not have habit tracking enabled.'
            }, status=400)

        # Parse and validate all dates first
        from datetime import datetime
        parsed_dates = []
        errors = []
        for date_str in date_strings:
            try:
                d = datetime.strptime(date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                errors.append(f'Invalid date format: {date_str}')
                continue

            if d < goal.start_date:
                errors.append(f'{date_str} is before goal start date.')
                continue
            if d > goal.end_date:
                errors.append(f'{date_str} is after goal end date.')
                continue
            if d > today:
                errors.append(f'{date_str} is in the future.')
                continue

            parsed_dates.append(d)

        if not parsed_dates:
            return JsonResponse({
                'success': False,
                'error': errors[0] if errors else 'No valid dates provided.'
            }, status=400)

        # Build defaults for manual logging.
        defaults = {'completed': True}
        if goal.target_value:
            if goal.is_duration:
                defaults['duration_minutes'] = goal.target_value
            elif goal.is_count:
                defaults['count_value'] = goal.target_value

        # Bulk create/update entries (session_number=1 for manual logging)
        logged = []
        for d in parsed_dates:
            try:
                entry, created = HabitEntry.objects.update_or_create(
                    goal=goal,
                    date=d,
                    session_number=1,
                    defaults=defaults,
                )
            except HabitEntry.MultipleObjectsReturned:
                # Clean up duplicate entries from before unique constraint change
                dupes = HabitEntry.objects.filter(
                    goal=goal, date=d, session_number=1
                ).order_by('pk')
                entry = dupes.first()
                for field, value in defaults.items():
                    setattr(entry, field, value)
                entry.save()
                # Delete the extra duplicates
                dupes.exclude(pk=entry.pk).delete()
                created = False
            day_number = (d - goal.start_date).days + 1
            logged.append({
                'date': d.isoformat(),
                'day_number': day_number,
                'state': 'completed',
                'created': created,
            })

        return JsonResponse({
            'success': True,
            'logged': logged,
            'count': len(logged),
            'errors': errors,
            'message': f'Logged {len(logged)} date{"s" if len(logged) != 1 else ""}.',
            'stats': {
                'completed_days': goal.completed_days,
                'completion_rate': round(goal.completion_rate),
                'current_streak': goal.current_streak,
            }
        })


class HabitUnlogDatesView(PurposeAccessMixin, View):
    """
    Remove habit entries for specified dates (undo support).

    POST /purpose/habits/<pk>/unlog-dates/
    Body: {"dates": ["YYYY-MM-DD", ...]}
    Returns JSON with success status and updated stats.
    """

    def post(self, request, pk):
        import json
        goal = get_object_or_404(HabitGoal, pk=pk, user=request.user)
        today = get_user_today(request.user)

        try:
            data = json.loads(request.body)
            date_strings = data.get('dates')
            if not date_strings or not isinstance(date_strings, list):
                return JsonResponse({
                    'success': False,
                    'error': 'A list of dates is required.'
                }, status=400)
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON.'
            }, status=400)

        from datetime import datetime
        parsed_dates = []
        for date_str in date_strings:
            try:
                d = datetime.strptime(date_str, '%Y-%m-%d').date()
                parsed_dates.append(d)
            except (ValueError, TypeError):
                continue

        deleted_count, _ = HabitEntry.objects.filter(
            goal=goal,
            date__in=parsed_dates,
        ).delete()

        # Build state info for each date so frontend can revert boxes
        reverted = []
        for d in parsed_dates:
            day_number = (d - goal.start_date).days + 1
            if d == today:
                state = 'today'
            elif d < today:
                state = 'missed'
            else:
                state = 'future'
            reverted.append({
                'date': d.isoformat(),
                'day_number': day_number,
                'state': state,
            })

        return JsonResponse({
            'success': True,
            'reverted': reverted,
            'count': deleted_count,
            'message': f'Undid {deleted_count} date{"s" if deleted_count != 1 else ""}.',
            'stats': {
                'completed_days': goal.completed_days,
                'completion_rate': round(goal.completion_rate),
                'current_streak': goal.current_streak,
            }
        })


# =============================================================================
# Goal Milestones
# =============================================================================

class MilestoneCreateView(PurposeAccessMixin, View):
    """Create a milestone for a goal."""

    def post(self, request, goal_pk):
        goal = get_object_or_404(LifeGoal, pk=goal_pk, user=request.user)

        # Only allow adding milestones to active goals
        if goal.status != 'active':
            messages.error(request, "Cannot add milestones to inactive goals.")
            return redirect('purpose:goal_detail', pk=goal_pk)

        title = request.POST.get('title', '').strip()
        if not title:
            messages.error(request, "Milestone title is required.")
            return redirect('purpose:goal_detail', pk=goal_pk)

        target_date_str = request.POST.get('target_date', '').strip()
        target_date = None
        if target_date_str:
            try:
                from datetime import datetime
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        description = request.POST.get('description', '').strip()

        # Get next sort order
        max_order = goal.milestones.aggregate(
            max_order=Max('sort_order')
        )['max_order'] or 0

        GoalMilestone.objects.create(
            goal=goal,
            title=title,
            description=description,
            target_date=target_date,
            sort_order=max_order + 1
        )

        messages.success(request, f"Milestone '{title}' added.")
        return redirect('purpose:goal_detail', pk=goal_pk)


class MilestoneToggleView(PurposeAccessMixin, View):
    """Toggle milestone completion status."""

    def post(self, request, pk):
        milestone = get_object_or_404(GoalMilestone, pk=pk, goal__user=request.user)

        # Only allow toggling on active goals
        if milestone.goal.status != 'active':
            messages.error(request, "Cannot modify milestones on inactive goals.")
            return redirect('purpose:goal_detail', pk=milestone.goal.pk)

        if milestone.completed:
            milestone.mark_incomplete()
            messages.info(request, f"Milestone '{milestone.title}' marked incomplete.")
        else:
            milestone.mark_complete()
            try:
                from apps.cos.services.completion_service import CosCompletionService
                CosCompletionService.on_milestone_completed(milestone)
            except Exception:
                pass
            messages.success(request, f"Milestone '{milestone.title}' completed!")

            # Fire intelligence chain
            from apps.core.ai_orchestrator.intelligence_hook import fire_intelligence
            fire_intelligence(request.user, "purpose", milestone.id, "complete_milestone")

            # Check if all milestones are now complete
            if milestone.goal.all_milestones_complete:
                # Add a special session flag for the celebration modal
                request.session['goal_ready_to_complete'] = milestone.goal.pk
                messages.info(
                    request,
                    "All milestones complete! Consider marking the goal as complete."
                )

        return redirect('purpose:goal_detail', pk=milestone.goal.pk)


class MilestoneUpdateView(PurposeAccessMixin, View):
    """Update a milestone."""

    def post(self, request, pk):
        milestone = get_object_or_404(GoalMilestone, pk=pk, goal__user=request.user)

        # Only allow editing milestones on active goals
        if milestone.goal.status != 'active':
            messages.error(request, "Cannot edit milestones on inactive goals.")
            return redirect('purpose:goal_detail', pk=milestone.goal.pk)

        title = request.POST.get('title', '').strip()
        if not title:
            messages.error(request, "Milestone title is required.")
            return redirect('purpose:goal_detail', pk=milestone.goal.pk)

        target_date_str = request.POST.get('target_date', '').strip()
        target_date = None
        if target_date_str:
            try:
                from datetime import datetime
                target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        description = request.POST.get('description', '').strip()

        milestone.title = title
        milestone.description = description
        milestone.target_date = target_date
        milestone.save()

        messages.success(request, f"Milestone '{title}' updated.")
        return redirect('purpose:goal_detail', pk=milestone.goal.pk)


class MilestoneDeleteView(PurposeAccessMixin, View):
    """Delete a milestone."""

    def post(self, request, pk):
        milestone = get_object_or_404(GoalMilestone, pk=pk, goal__user=request.user)
        goal_pk = milestone.goal.pk
        title = milestone.title

        # Only allow deleting milestones on active goals
        if milestone.goal.status != 'active':
            messages.error(request, "Cannot delete milestones on inactive goals.")
            return redirect('purpose:goal_detail', pk=goal_pk)

        milestone.delete()
        messages.success(request, f"Milestone '{title}' deleted.")
        return redirect('purpose:goal_detail', pk=goal_pk)


# =============================================================================
# Bulk Delete Views
# =============================================================================

class BulkDeleteGoalsView(LoginRequiredMixin, View):
    """Bulk delete goals."""

    def post(self, request):
        try:
            data = json.loads(request.body)
            ids = data.get('ids', [])
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if not ids:
            return JsonResponse({'success': False, 'error': 'No items selected'}, status=400)

        entries = LifeGoal.objects.filter(user=request.user, pk__in=ids)
        count = entries.count()

        if count == 0:
            return JsonResponse({'success': False, 'error': 'No entries found'}, status=404)

        for entry in entries:
            entry.soft_delete()

        return JsonResponse({
            'success': True,
            'message': f'{count} goal{"" if count == 1 else "s"} deleted',
            'count': count
        })


# =============================================================================
# Goal Engine — Measurement Logging Views
# =============================================================================

class GoalLogDurationView(PurposeAccessMixin, View):
    """
    Log a duration session for a DURATION goal.

    POST /purpose/habits/<pk>/log-duration/
    Body: {"duration_minutes": 30.5, "date": "YYYY-MM-DD" (optional), "notes": ""}
    """

    def post(self, request, pk):
        goal = get_object_or_404(HabitGoal, pk=pk, user=request.user)

        if not goal.is_duration:
            return JsonResponse({
                'success': False,
                'error': 'This goal does not use duration tracking.'
            }, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

        duration = data.get('duration_minutes')
        if duration is None or float(duration) <= 0:
            return JsonResponse({
                'success': False,
                'error': 'Duration must be a positive number.'
            }, status=400)

        from datetime import datetime
        from decimal import Decimal
        date_str = data.get('date')
        if date_str:
            try:
                log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                log_date = get_user_today(request.user)
        else:
            log_date = get_user_today(request.user)

        notes = data.get('notes', '')
        duration_dec = Decimal(str(duration))

        # Validate date is within goal range
        if log_date < goal.start_date:
            return JsonResponse({
                'success': False,
                'error': f'Date cannot be before goal start date ({goal.start_date}).'
            }, status=400)
        if goal.end_date and log_date > goal.end_date:
            return JsonResponse({
                'success': False,
                'error': f'Date cannot be after goal end date ({goal.end_date}).'
            }, status=400)

        # Determine session number
        existing = HabitEntry.objects.filter(goal=goal, date=log_date).count()
        session_num = existing + 1

        # Auto-completed if meets target
        completed = True
        if goal.target_value:
            completed = duration_dec >= goal.target_value

        try:
            entry = HabitEntry(
                goal=goal,
                date=log_date,
                duration_minutes=duration_dec,
                completed=completed,
                notes=notes,
                session_number=session_num,
            )
            entry.save()
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'error': str(e.message_dict if hasattr(e, 'message_dict') else e.messages)
            }, status=400)

        day_number = (log_date - goal.start_date).days + 1

        return JsonResponse({
            'success': True,
            'entry_id': entry.pk,
            'date': log_date.isoformat(),
            'day_number': day_number,
            'duration_minutes': float(duration_dec),
            'completed': completed,
            'stats': {
                'completed_days': goal.completed_days,
                'completion_rate': round(goal.completion_rate),
                'current_streak': goal.current_streak,
                'avg_duration': goal.avg_duration,
                'weekly_sessions': goal.get_weekly_session_count(),
                'weekly_progress': goal.weekly_progress_percent,
            }
        })


class GoalLogCountView(PurposeAccessMixin, View):
    """
    Log a count entry for a COUNT goal.

    POST /purpose/habits/<pk>/log-count/
    Body: {"count_value": 15, "date": "YYYY-MM-DD" (optional), "notes": ""}
    """

    def post(self, request, pk):
        goal = get_object_or_404(HabitGoal, pk=pk, user=request.user)

        if not goal.is_count:
            return JsonResponse({
                'success': False,
                'error': 'This goal does not use count tracking.'
            }, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

        count_val = data.get('count_value')
        if count_val is None or float(count_val) < 0:
            return JsonResponse({
                'success': False,
                'error': 'Count must be a non-negative number.'
            }, status=400)

        from datetime import datetime
        from decimal import Decimal
        date_str = data.get('date')
        if date_str:
            try:
                log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                log_date = get_user_today(request.user)
        else:
            log_date = get_user_today(request.user)

        notes = data.get('notes', '')
        count_dec = Decimal(str(count_val))

        # Validate date is within goal range
        if log_date < goal.start_date:
            return JsonResponse({
                'success': False,
                'error': f'Date cannot be before goal start date ({goal.start_date}).'
            }, status=400)
        if goal.end_date and log_date > goal.end_date:
            return JsonResponse({
                'success': False,
                'error': f'Date cannot be after goal end date ({goal.end_date}).'
            }, status=400)

        # Update existing entry for today or create new
        try:
            entry, created = HabitEntry.objects.update_or_create(
                goal=goal,
                date=log_date,
                session_number=1,
                defaults={
                    'count_value': count_dec,
                    'completed': count_dec >= goal.target_value if goal.target_value else True,
                    'notes': notes,
                }
            )
        except HabitEntry.MultipleObjectsReturned:
            dupes = HabitEntry.objects.filter(
                goal=goal, date=log_date, session_number=1
            ).order_by('pk')
            entry = dupes.first()
            entry.count_value = count_dec
            entry.completed = count_dec >= goal.target_value if goal.target_value else True
            entry.notes = notes
            entry.save()
            dupes.exclude(pk=entry.pk).delete()
            created = False
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'error': str(e.message_dict if hasattr(e, 'message_dict') else e.messages)
            }, status=400)

        day_number = (log_date - goal.start_date).days + 1

        return JsonResponse({
            'success': True,
            'entry_id': entry.pk,
            'date': log_date.isoformat(),
            'day_number': day_number,
            'count_value': float(count_dec),
            'completed': entry.completed,
            'stats': {
                'completed_days': goal.completed_days,
                'completion_rate': round(goal.completion_rate),
                'current_streak': goal.current_streak,
                'total_count': goal.total_count,
            }
        })


class GoalLogTargetView(PurposeAccessMixin, View):
    """
    Log a target measurement for a TARGET goal.

    POST /purpose/habits/<pk>/log-target/
    Body: {"target_value": 185.5, "date": "YYYY-MM-DD" (optional), "notes": ""}
    """

    def post(self, request, pk):
        goal = get_object_or_404(HabitGoal, pk=pk, user=request.user)

        if not goal.is_target:
            return JsonResponse({
                'success': False,
                'error': 'This goal does not use target tracking.'
            }, status=400)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

        target_val = data.get('target_value')
        if target_val is None:
            return JsonResponse({
                'success': False,
                'error': 'Target value is required.'
            }, status=400)

        from datetime import datetime
        from decimal import Decimal
        date_str = data.get('date')
        if date_str:
            try:
                log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                log_date = get_user_today(request.user)
        else:
            log_date = get_user_today(request.user)

        notes = data.get('notes', '')
        target_dec = Decimal(str(target_val))

        # Validate date is within goal range
        if log_date < goal.start_date:
            return JsonResponse({
                'success': False,
                'error': f'Date cannot be before goal start date ({goal.start_date}).'
            }, status=400)
        if goal.end_date and log_date > goal.end_date:
            return JsonResponse({
                'success': False,
                'error': f'Date cannot be after goal end date ({goal.end_date}).'
            }, status=400)

        try:
            entry, created = HabitEntry.objects.update_or_create(
                goal=goal,
                date=log_date,
                session_number=1,
                defaults={
                    'target_value': target_dec,
                    'completed': True,  # Any entry counts as completed for target goals
                    'notes': notes,
                }
            )
        except HabitEntry.MultipleObjectsReturned:
            dupes = HabitEntry.objects.filter(
                goal=goal, date=log_date, session_number=1
            ).order_by('pk')
            entry = dupes.first()
            entry.target_value = target_dec
            entry.completed = True
            entry.notes = notes
            entry.save()
            dupes.exclude(pk=entry.pk).delete()
            created = False
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'error': str(e.message_dict if hasattr(e, 'message_dict') else e.messages)
            }, status=400)

        day_number = (log_date - goal.start_date).days + 1

        return JsonResponse({
            'success': True,
            'entry_id': entry.pk,
            'date': log_date.isoformat(),
            'day_number': day_number,
            'target_value': float(target_dec),
            'running_total': goal.running_total,
            'stats': {
                'completed_days': goal.completed_days,
                'completion_rate': round(goal.completion_rate),
                'current_streak': goal.current_streak,
            }
        })


# =============================================================================
# Goal Engine — Analytics & Insights API Views
# =============================================================================

class GoalAnalyticsView(PurposeAccessMixin, View):
    """
    Return analytics JSON for a goal.

    GET /purpose/habits/<pk>/analytics/?days=30
    """

    def get(self, request, pk):
        goal = get_object_or_404(HabitGoal, pk=pk, user=request.user)
        days = int(request.GET.get('days', 30))
        analytics = analytics_service.get_analytics(goal, days=days)

        # Also generate any new insights
        recommendation_service.generate_insights(goal)

        return JsonResponse({
            'success': True,
            'analytics': analytics_service.analytics_to_dict(analytics),
        })


class GoalInsightsView(PurposeAccessMixin, View):
    """
    Return active insights for a goal.

    GET /purpose/habits/<pk>/insights/
    """

    def get(self, request, pk):
        goal = get_object_or_404(HabitGoal, pk=pk, user=request.user)
        insights = recommendation_service.get_active_insights(goal)

        return JsonResponse({
            'success': True,
            'insights': [
                {
                    'id': i.pk,
                    'type': i.insight_type,
                    'title': i.title,
                    'message': i.message,
                    'suggestion_data': i.suggestion_data,
                    'created_at': i.created_at.isoformat(),
                }
                for i in insights
            ],
        })


class GoalInsightDismissView(PurposeAccessMixin, View):
    """
    Dismiss an insight.

    POST /purpose/insights/<pk>/dismiss/
    """

    def post(self, request, pk):
        insight = get_object_or_404(GoalInsight, pk=pk, goal__user=request.user)
        insight.is_dismissed = True
        insight.save(update_fields=['is_dismissed'])
        return JsonResponse({'success': True})


class GoalInsightApplyView(PurposeAccessMixin, View):
    """
    Apply an insight's suggestion to the goal.

    POST /purpose/insights/<pk>/apply/
    """

    def post(self, request, pk):
        insight = get_object_or_404(GoalInsight, pk=pk, goal__user=request.user)
        success = recommendation_service.apply_insight(insight.pk)
        return JsonResponse({'success': success})
