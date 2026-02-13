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
