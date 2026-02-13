"""
Whole Life Journey - Medical Admin

Project: Whole Life Journey
Path: apps/medical/admin.py
Purpose: Django admin configuration for medical models
"""

from django.contrib import admin

from .models import (
    ImportBatch,
    ImportErrorRow,
    LabEducationContent,
    LabPanel,
    LabResult,
    LabTestAlias,
    LabTestCatalog,
    MedicalAuditLog,
    MedicalDocument,
)


@admin.register(LabTestCatalog)
class LabTestCatalogAdmin(admin.ModelAdmin):
    list_display = ["name", "short_name", "category", "is_system_seeded", "needs_review"]
    list_filter = ["category", "is_system_seeded", "needs_review"]
    search_fields = ["name", "short_name", "loinc_code"]
    readonly_fields = ["id", "created_at", "updated_at"]
    actions = ["mark_reviewed"]

    @admin.action(description="Mark selected tests as reviewed")
    def mark_reviewed(self, request, queryset):
        queryset.update(needs_review=False)


@admin.register(LabTestAlias)
class LabTestAliasAdmin(admin.ModelAdmin):
    list_display = ["alias", "canonical_test"]
    search_fields = ["alias", "canonical_test__name"]
    list_filter = ["canonical_test__category"]
    raw_id_fields = ["canonical_test"]


class NeedsEducationFilter(admin.SimpleListFilter):
    """Filter for LabTestCatalog entries that lack education content."""
    title = "education status"
    parameter_name = "needs_education"

    def lookups(self, request, model_admin):
        return [
            ("yes", "Needs Education"),
            ("no", "Has Education"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(education__isnull=True)
        if self.value() == "no":
            return queryset.filter(education__isnull=False)
        return queryset


# Add NeedsEducationFilter to LabTestCatalogAdmin
LabTestCatalogAdmin.list_filter = ["category", "is_system_seeded", "needs_review", NeedsEducationFilter]


@admin.register(LabEducationContent)
class LabEducationContentAdmin(admin.ModelAdmin):
    list_display = [
        "lab_test", "summary_plain_name", "typical_panel",
        "is_system_generated", "reviewed_at",
    ]
    list_filter = ["is_system_generated", "typical_panel"]
    search_fields = ["lab_test__name", "summary_plain_name", "typical_panel"]
    raw_id_fields = ["lab_test"]
    readonly_fields = ["id", "created_at", "updated_at"]
    fieldsets = (
        (None, {
            "fields": ("lab_test", "summary_plain_name", "typical_panel"),
        }),
        ("Educational Content", {
            "fields": (
                "what_it_measures",
                "what_it_reflects",
                "low_general_associations",
                "high_general_associations",
                "common_influencing_factors",
            ),
        }),
        ("Review Status", {
            "fields": ("is_system_generated", "reviewed_at"),
        }),
        ("Metadata", {
            "classes": ("collapse",),
            "fields": ("id", "created_at", "updated_at"),
        }),
    )
    actions = ["mark_reviewed"]

    @admin.action(description="Mark selected education content as reviewed")
    def mark_reviewed(self, request, queryset):
        from django.utils import timezone
        queryset.update(reviewed_at=timezone.now())


@admin.register(LabPanel)
class LabPanelAdmin(admin.ModelAdmin):
    list_display = ["panel_type", "name", "user", "collected_at"]
    list_filter = ["panel_type"]
    search_fields = ["name", "user__email"]
    raw_id_fields = ["user"]


@admin.register(MedicalDocument)
class MedicalDocumentAdmin(admin.ModelAdmin):
    list_display = ["original_filename", "user", "extraction_method", "page_count", "created_at"]
    list_filter = ["extraction_method"]
    search_fields = ["original_filename", "user__email"]
    raw_id_fields = ["user", "organize_document"]


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = [
        "id", "user", "status", "total_rows_found", "rows_imported",
        "rows_skipped_duplicate", "rows_failed", "created_at"
    ]
    list_filter = ["status"]
    search_fields = ["user__email"]
    raw_id_fields = ["user", "medical_document"]


@admin.register(ImportErrorRow)
class ImportErrorRowAdmin(admin.ModelAdmin):
    list_display = ["import_batch", "row_number", "raw_test_name", "error_type", "error_message"]
    list_filter = ["error_type"]
    search_fields = ["raw_test_name", "error_message"]
    raw_id_fields = ["import_batch"]


@admin.register(LabResult)
class LabResultAdmin(admin.ModelAdmin):
    list_display = [
        "raw_test_name", "value_text", "unit", "abnormal_flag",
        "collected_at", "user", "result_status"
    ]
    list_filter = ["abnormal_flag", "result_status"]
    search_fields = ["raw_test_name", "user__email"]
    raw_id_fields = ["user", "canonical_test", "panel", "medical_document", "import_batch"]
    readonly_fields = ["fingerprint"]


@admin.register(MedicalAuditLog)
class MedicalAuditLogAdmin(admin.ModelAdmin):
    list_display = ["user", "action", "created_at", "ip_address"]
    list_filter = ["action"]
    search_fields = ["user__email", "detail"]
    readonly_fields = ["id", "created_at", "updated_at"]
