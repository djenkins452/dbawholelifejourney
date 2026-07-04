from django.contrib import admin

from apps.legacy.models import (
    Contributor, ImportBatch, ImportChunk, LifeMilestone, Media, Memory, Output, Person,
    Place, Relationship, RelationshipAlias,
)


@admin.register(RelationshipAlias)
class RelationshipAliasAdmin(admin.ModelAdmin):
    list_display = ("label", "alias", "person", "user")
    search_fields = ("alias", "label")
    raw_id_fields = ("person", "user")


@admin.register(Memory)
class MemoryAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "entry_type", "entry_state", "occurred_on", "status", "created_at")
    list_filter = ("entry_type", "entry_state", "status", "source_kind")
    search_fields = ("title", "body")
    raw_id_fields = ("attributed_to", "contributor", "primary_media")


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "relationship_label", "birth_year", "death_year", "status")
    search_fields = ("display_name", "also_known_as")


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "location_text", "status")
    search_fields = ("name", "location_text")


@admin.register(Media)
class MediaAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "media_type", "taken_on", "status")
    list_filter = ("media_type", "status")


@admin.register(Relationship)
class RelationshipAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "relationship_type", "status")


@admin.register(Contributor)
class ContributorAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "permission_level", "invite_status", "status")
    list_filter = ("permission_level", "invite_status")


@admin.register(Output)
class OutputAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "output_type", "scope_kind", "generation_status", "status")
    list_filter = ("output_type", "generation_status")


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("source_name", "user", "source_type", "import_status", "imported_count", "total_chunks", "created_at")
    list_filter = ("source_type", "import_status")


@admin.register(ImportChunk)
class ImportChunkAdmin(admin.ModelAdmin):
    list_display = ("__str__", "batch", "index", "status", "memory")
    list_filter = ("status",)


@admin.register(LifeMilestone)
class LifeMilestoneAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "kind", "year", "status")
    list_filter = ("kind",)
    search_fields = ("title",)
