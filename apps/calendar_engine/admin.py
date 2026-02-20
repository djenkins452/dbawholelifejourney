from django.contrib import admin

from .models import CalendarEvent, CalendarOverrideLog, RecurrenceException, RecurrenceRule


class RecurrenceRuleInline(admin.StackedInline):
    model = RecurrenceRule
    extra = 0


class RecurrenceExceptionInline(admin.TabularInline):
    model = RecurrenceException
    extra = 0


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'event_kind', 'source_type', 'start_dt', 'end_dt', 'status', 'is_protected']
    list_filter = ['event_kind', 'source_type', 'status', 'is_protected', 'domain']
    search_fields = ['title', 'description', 'source_id']
    raw_id_fields = ['user', 'domain']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [RecurrenceRuleInline, RecurrenceExceptionInline]


@admin.register(RecurrenceRule)
class RecurrenceRuleAdmin(admin.ModelAdmin):
    list_display = ['event', 'frequency', 'interval', 'until_dt']
    list_filter = ['frequency']


@admin.register(CalendarOverrideLog)
class CalendarOverrideLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'event', 'overridden_event', 'created_at']
    raw_id_fields = ['user', 'event', 'overridden_event']
    readonly_fields = ['created_at']
