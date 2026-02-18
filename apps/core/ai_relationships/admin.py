"""
AI Relationships — Admin Registration
"""

from django.contrib import admin

from .models import InteractionSignal, Person, Relationship


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'person_type', 'user', 'is_active', 'created_at')
    list_filter = ('person_type', 'is_active')
    search_fields = ('display_name', 'user__email')
    raw_id_fields = ('user',)


@admin.register(Relationship)
class RelationshipAdmin(admin.ModelAdmin):
    list_display = ('person', 'relationship_type', 'importance_tier', 'cadence_target', 'last_interaction', 'user')
    list_filter = ('importance_tier', 'cadence_target')
    raw_id_fields = ('user', 'person')


@admin.register(InteractionSignal)
class InteractionSignalAdmin(admin.ModelAdmin):
    list_display = ('person', 'signal_date', 'signal_type', 'source_type', 'confidence', 'user')
    list_filter = ('signal_type', 'source_type')
    raw_id_fields = ('user', 'person')
