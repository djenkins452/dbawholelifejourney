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

from .forms import ContactImportForm, PersonForm, PersonGroupForm, QuickPersonForm
from .models import Person, PersonGroup
from .services import ContactImportService, RelationalHealthService, RelationshipAnalyticsService

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

        results = []

        # Groups matching the query (shown first)
        groups = (
            PersonGroup.objects
            .filter(owner=request.user, name__icontains=q)
            .prefetch_related('members')
            [:5]
        )
        for g in groups:
            count = g.members.count()
            results.append({
                'id': g.pk,
                'name': g.name,
                'type': f'group · {count} member{"s" if count != 1 else ""}',
                'is_group': True,
            })

        # People matching the query
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
        for p in people:
            results.append({
                'id': p.pk,
                'name': p.get_display_name(),
                'first_name': p.first_name,
                'type': p.relationship_type,
                'is_group': False,
            })

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
# PERSON GROUP CRUD
# =============================================================================


class GroupListView(LoginRequiredMixin, ListView):
    """List all groups for the current user."""

    model = PersonGroup
    template_name = 'relationships/group_list.html'
    context_object_name = 'groups'

    def get_queryset(self):
        return (
            PersonGroup.objects
            .filter(owner=self.request.user)
            .prefetch_related('members')
        )


class GroupCreateView(LoginRequiredMixin, CreateView):
    """Create a new person group."""

    model = PersonGroup
    form_class = PersonGroupForm
    template_name = 'relationships/group_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['selected_member_ids'] = []
        return ctx

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('relationships:group_detail', kwargs={'pk': self.object.pk})


class GroupDetailView(LoginRequiredMixin, DetailView):
    """View group details and members."""

    model = PersonGroup
    template_name = 'relationships/group_detail.html'
    context_object_name = 'group'

    def get_queryset(self):
        return (
            PersonGroup.objects
            .filter(owner=self.request.user)
            .prefetch_related('members')
        )


class GroupUpdateView(LoginRequiredMixin, UpdateView):
    """Edit a person group."""

    model = PersonGroup
    form_class = PersonGroupForm
    template_name = 'relationships/group_form.html'

    def get_queryset(self):
        return PersonGroup.objects.filter(owner=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['selected_member_ids'] = list(
            self.object.members.values_list('pk', flat=True)
        )
        return ctx

    def get_success_url(self):
        return reverse_lazy('relationships:group_detail', kwargs={'pk': self.object.pk})


class GroupDeleteView(LoginRequiredMixin, View):
    """Soft-delete a person group."""

    def post(self, request, pk):
        group = get_object_or_404(PersonGroup, pk=pk, owner=request.user)
        group.soft_delete()
        return redirect('relationships:group_list')


class GroupQuickCreateView(LoginRequiredMixin, View):
    """
    AJAX endpoint for creating a group from multi-select.

    POST /relationships/groups/quick-create/
    Body: {"name": "...", "person_ids": [1, 2, 3]}
    Returns JSON: {"id": 1, "name": "...", "member_count": 3}
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Group name is required'}, status=400)

        # Check for duplicate group name
        if PersonGroup.objects.filter(owner=request.user, name__iexact=name).exists():
            return JsonResponse({'error': f'A group named "{name}" already exists'}, status=400)

        person_ids = data.get('person_ids', [])
        if not isinstance(person_ids, list):
            return JsonResponse({'error': 'person_ids must be a list'}, status=400)

        # Validate all person IDs belong to this user
        people = Person.objects.filter(owner=request.user, pk__in=person_ids)

        group = PersonGroup.objects.create(
            owner=request.user,
            name=name,
        )
        group.members.set(people)

        return JsonResponse({
            'id': group.pk,
            'name': group.name,
            'member_count': group.members.count(),
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


# =============================================================================
# CONTACT IMPORT (Phase 5)
# =============================================================================


class ContactImportView(LoginRequiredMixin, TemplateView):
    """Upload a vCard (.vcf) file to import contacts."""

    template_name = 'relationships/import_contacts.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if 'form' not in ctx:
            ctx['form'] = ContactImportForm()
        return ctx

    def post(self, request, *args, **kwargs):
        form = ContactImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        uploaded_file = form.cleaned_data['file']

        # Read file content, handling encoding
        try:
            content = uploaded_file.read().decode('utf-8')
        except UnicodeDecodeError:
            try:
                uploaded_file.seek(0)
                content = uploaded_file.read().decode('latin-1')
            except Exception:
                form.add_error('file', 'Could not read file. Please ensure it is a valid vCard file.')
                return self.render_to_response(self.get_context_data(form=form))

        result = ContactImportService.import_vcf(request.user, content)

        ctx = self.get_context_data(form=ContactImportForm())
        ctx['result'] = result
        return self.render_to_response(ctx)
