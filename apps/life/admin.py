from django.contrib import admin

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
    SignificantEvent,
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'status', 'priority', 'created_at']
    list_filter = ['status', 'priority', 'created_at']
    search_fields = ['title', 'description']


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'project', 'priority', 'is_completed', 'due_date']
    list_filter = ['priority', 'is_completed', 'created_at']
    search_fields = ['title', 'notes']


@admin.register(LifeEvent)
class LifeEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'event_type', 'start_date', 'is_all_day']
    list_filter = ['event_type', 'start_date']
    search_fields = ['title', 'description']


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'category', 'location', 'estimated_value']
    list_filter = ['category', 'condition']
    search_fields = ['name', 'description', 'brand']


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'log_type', 'area', 'date', 'cost']
    list_filter = ['log_type', 'date']
    search_fields = ['title', 'description', 'area']


@admin.register(Pet)
class PetAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'species', 'breed', 'is_active']
    list_filter = ['species', 'is_active']
    search_fields = ['name', 'breed']


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'category', 'difficulty', 'is_favorite']
    list_filter = ['category', 'difficulty', 'is_favorite']
    search_fields = ['title', 'description', 'ingredients']


@admin.register(SignificantEvent)
class SignificantEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'event_type', 'event_date', 'person_name', 'sms_reminder_enabled']
    list_filter = ['event_type', 'sms_reminder_enabled', 'created_at']
    search_fields = ['title', 'person_name', 'description']
    ordering = ['event_date']
