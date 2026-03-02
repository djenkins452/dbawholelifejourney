"""
Whole Life Journey - Relationships Admin

Project: Whole Life Journey
Path: apps/relationships/admin.py
Purpose: Admin registration for relationship intelligence models

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

from django.contrib import admin

from .models import Mention, Person, RelationshipInteraction


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = [
        'first_name', 'last_name', 'relationship_type', 'owner',
        'last_interaction_date', 'interaction_count', 'status',
    ]
    list_filter = ['relationship_type', 'status', 'household']
    search_fields = ['first_name', 'last_name', 'display_name', 'owner__email']
    raw_id_fields = ['owner', 'household']
    readonly_fields = [
        'display_name', 'last_interaction_date', 'interaction_count',
        'created_at', 'updated_at', 'deleted_at',
    ]

    def get_queryset(self, request):
        return Person.all_objects.all()


@admin.register(RelationshipInteraction)
class RelationshipInteractionAdmin(admin.ModelAdmin):
    list_display = [
        'person', 'user', 'context_type_label', 'interaction_date', 'created_at',
    ]
    list_filter = ['context_type_label', 'interaction_date']
    search_fields = ['person__first_name', 'person__last_name', 'user__email']
    raw_id_fields = ['person', 'user']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'interaction_date'


@admin.register(Mention)
class MentionAdmin(admin.ModelAdmin):
    list_display = ['person', 'content_type', 'object_id', 'created_at']
    list_filter = ['content_type']
    search_fields = ['person__first_name', 'person__last_name']
    raw_id_fields = ['person']
    readonly_fields = ['created_at', 'updated_at']
