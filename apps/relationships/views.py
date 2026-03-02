"""
Whole Life Journey - Relationships Views

Project: Whole Life Journey
Path: apps/relationships/views.py
Purpose: Views for Person CRUD, interaction history, and autocomplete API

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import json
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from .forms import PersonForm, QuickPersonForm
from .models import Person
from .services import RelationalHealthService, RelationshipAnalyticsService

logger = logging.getLogger(__name__)


# =============================================================================
# PERSON CRUD
# =============================================================================


class PersonListView(LoginRequiredMixin, ListView):
    model = Person
    template_name = 'relationships/person_list.html'
    context_object_name = 'people'
    paginate_by = 25

    def get_queryset(self):
        from django.db.models import Q
        qs = Person.objects.filter(owner=self.request.user)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) | Q(last_name__icontains=q)
            )
        rel_type = self.request.GET.get('type', '').strip()
        if rel_type:
            qs = qs.filter(relationship_type=rel_type)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['relationship_types'] = Person.RELATIONSHIP_TYPE_CHOICES
        ctx['current_type'] = self.request.GET.get('type', '')
        ctx['search_query'] = self.request.GET.get('q', '')
        return ctx


class PersonCreateView(LoginRequiredMixin, CreateView):
    model = Person
    form_class = PersonForm
    template_name = 'relationships/person_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('relationships:person_list')


class PersonDetailView(LoginRequiredMixin, DetailView):
    model = Person
    template_name = 'relationships/person_detail.html'
    context_object_name = 'person'

    def get_queryset(self):
        return Person.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        person = self.object
        ctx['summary'] = RelationshipAnalyticsService.get_summary(person)
        ctx['days_since'] = RelationshipAnalyticsService.days_since_last_interaction(person)
        ctx['breakdown'] = RelationshipAnalyticsService.context_breakdown(person)
        # Recent interactions
        from .models import RelationshipInteraction
        ctx['recent_interactions'] = (
            RelationshipInteraction.objects
            .filter(person=person)
            .select_related('content_type')
            [:20]
        )
        return ctx


class PersonUpdateView(LoginRequiredMixin, UpdateView):
    model = Person
    form_class = PersonForm
    template_name = 'relationships/person_form.html'

    def get_queryset(self):
        return Person.objects.filter(owner=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse_lazy('relationships:person_detail', kwargs={'pk': self.object.pk})


class PersonDeleteView(LoginRequiredMixin, View):
    """Soft-delete a person contact."""

    def post(self, request, pk):
        person = get_object_or_404(Person, pk=pk, owner=request.user)
        person.soft_delete()
        return redirect('relationships:person_list')


# =============================================================================
# AUTOCOMPLETE API
# =============================================================================


class PersonAutocompleteView(LoginRequiredMixin, View):
    """
    AJAX endpoint for @mention autocomplete.

    GET /relationships/autocomplete/?q=<query>

    Returns JSON array of matching contacts:
    [{"id": 1, "name": "John Smith", "type": "friend"}, ...]
    """

    def get(self, request):
        q = request.GET.get('q', '').strip()
        if len(q) < 1:
            return JsonResponse([], safe=False)

        from django.db.models import Q
        people = (
            Person.objects
            .filter(owner=request.user)
            .filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(display_name__icontains=q)
            )
            [:10]
        )

        results = [
            {
                'id': p.pk,
                'name': p.get_display_name(),
                'first_name': p.first_name,
                'type': p.relationship_type,
            }
            for p in people
        ]
        return JsonResponse(results, safe=False)


class PersonQuickCreateView(LoginRequiredMixin, View):
    """
    AJAX endpoint for creating a new Person inline from autocomplete.

    POST /relationships/quick-create/
    Body: {"first_name": "...", "last_name": "...", "relationship_type": "..."}

    Returns JSON: {"id": 1, "name": "John Smith", "type": "friend"}
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        first_name = data.get('first_name', '').strip()
        if not first_name:
            return JsonResponse({'error': 'first_name required'}, status=400)

        person = Person.objects.create(
            owner=request.user,
            first_name=first_name,
            last_name=data.get('last_name', '').strip(),
            relationship_type=data.get('relationship_type', 'other'),
        )

        return JsonResponse({
            'id': person.pk,
            'name': person.get_display_name(),
            'first_name': person.first_name,
            'type': person.relationship_type,
        }, status=201)


# =============================================================================
# RELATIONSHIP INSIGHTS (Phase R2)
# =============================================================================


class RelationshipInsightsView(LoginRequiredMixin, TemplateView):
    """Full relationship insights dashboard."""

    template_name = 'relationships/insights.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        health = RelationalHealthService.compute_health(self.request.user)
        ctx['health'] = health
        return ctx
