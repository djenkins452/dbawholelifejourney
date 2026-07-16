"""Admin for the canonical Person domain."""

from django.contrib import admin

from .models import (
    Person, PersonEvent, PersonMembership, PersonPhoto, PersonSourceLink,
    RecognitionPhrase,
)


class RecognitionPhraseInline(admin.TabularInline):
    model = RecognitionPhrase
    extra = 0
    fields = ("phrase", "normalized", "source", "learned_from")
    readonly_fields = ("normalized",)


class PersonSourceLinkInline(admin.TabularInline):
    model = PersonSourceLink
    extra = 0
    fields = ("source_domain", "source_pk", "created_at")
    readonly_fields = ("created_at",)


class PersonEventInline(admin.TabularInline):
    model = PersonEvent
    extra = 0
    fields = ("event_type", "at", "actor", "detail")
    readonly_fields = ("at",)
    ordering = ("-at",)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "origin", "is_self", "is_deceased", "status")
    list_filter = ("origin", "is_self", "is_deceased", "status")
    search_fields = ("display_name", "first_name", "last_name", "email")
    inlines = [RecognitionPhraseInline, PersonSourceLinkInline, PersonEventInline]


@admin.register(PersonMembership)
class PersonMembershipAdmin(admin.ModelAdmin):
    list_display = ("person", "granted_via", "granted_at")
    list_filter = ("granted_via",)


@admin.register(RecognitionPhrase)
class RecognitionPhraseAdmin(admin.ModelAdmin):
    list_display = ("phrase", "person", "source", "normalized")
    list_filter = ("source",)
    search_fields = ("phrase", "normalized")


@admin.register(PersonPhoto)
class PersonPhotoAdmin(admin.ModelAdmin):
    list_display = ("person", "is_primary", "caption")


@admin.register(PersonEvent)
class PersonEventAdmin(admin.ModelAdmin):
    list_display = ("person", "event_type", "at", "actor")
    list_filter = ("event_type", "actor")
    date_hierarchy = "at"


@admin.register(PersonSourceLink)
class PersonSourceLinkAdmin(admin.ModelAdmin):
    list_display = ("person", "source_domain", "source_pk", "created_at")
    list_filter = ("source_domain",)
