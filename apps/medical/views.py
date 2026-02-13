"""
Whole Life Journey - Medical Views

Project: Whole Life Journey
Path: apps/medical/views.py
Purpose: Views for medical lab upload, import results, and labs summary
"""

import csv
import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Count
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from .forms import LabResultFilterForm, LabUploadForm
from .models import (
    ImportBatch,
    ImportErrorRow,
    LabEducationContent,
    LabPanel,
    LabResult,
    LabTestCatalog,
    MedicalAuditLog,
    MedicalDocument,
)
from .services.importer import ingest_lab_pdf

logger = logging.getLogger(__name__)


class MedicalAccessMixin(LoginRequiredMixin):
    """Base mixin for medical views — ensures user can only see their own data."""

    def get_client_ip(self):
        x_forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")


# =============================================================================
# Upload
# =============================================================================

class LabUploadView(MedicalAccessMixin, TemplateView):
    """Upload a lab PDF and run ingestion."""

    template_name = "medical/upload.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = LabUploadForm()
        ctx["recent_imports"] = ImportBatch.objects.filter(
            user=self.request.user
        ).select_related("medical_document")[:5]
        return ctx

    def post(self, request, *args, **kwargs):
        form = LabUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        uploaded_file = form.cleaned_data["file"]
        result = ingest_lab_pdf(
            user=request.user,
            uploaded_file=uploaded_file,
            ip_address=self.get_client_ip(),
        )

        if not result.success and not result.import_batch:
            messages.error(request, result.error_message)
            return self.render_to_response(self.get_context_data(form=form))

        if result.import_batch:
            return redirect("medical:import_detail", pk=result.import_batch.pk)

        messages.error(request, result.error_message or "Import failed unexpectedly.")
        return self.render_to_response(self.get_context_data(form=form))


# =============================================================================
# Import Results
# =============================================================================

class ImportDetailView(MedicalAccessMixin, DetailView):
    """Show import batch results: counts, errors, imported results."""

    template_name = "medical/import_detail.html"
    context_object_name = "batch"

    def get_queryset(self):
        return ImportBatch.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        batch = self.object
        ctx["errors"] = batch.error_rows.all()
        ctx["imported_results"] = LabResult.objects.filter(
            user=self.request.user, import_batch=batch
        ).select_related("canonical_test")[:50]
        return ctx


class ImportErrorCSVView(MedicalAccessMixin, View):
    """Download import errors as CSV."""

    def get(self, request, pk):
        batch = get_object_or_404(
            ImportBatch, pk=pk, user=request.user
        )
        errors = batch.error_rows.all()

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="import_errors_{pk}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "Row #", "Test Name", "Value", "Unit", "Range",
            "Error Type", "Error Message", "Raw Line",
        ])
        for err in errors:
            writer.writerow([
                err.row_number, err.raw_test_name, err.raw_value,
                err.raw_unit, err.raw_range, err.error_type,
                err.error_message, err.raw_line,
            ])

        # Audit log
        MedicalAuditLog.objects.create(
            user=request.user,
            action="export",
            detail=f"Exported error CSV for batch {pk}",
            ip_address=self.get_client_ip(),
        )

        return response

    def get_client_ip(self):
        x_forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")


# =============================================================================
# Labs Summary
# =============================================================================

class LabsSummaryView(MedicalAccessMixin, ListView):
    """
    Labs & Vitals summary page.

    Section A: Abnormal results (most recent first)
    Section B: All results with filters
    """

    template_name = "medical/labs_summary.html"
    context_object_name = "results"
    paginate_by = 50

    def get_queryset(self):
        qs = LabResult.objects.filter(
            user=self.request.user
        ).select_related("canonical_test", "panel")

        # Apply filters
        form = LabResultFilterForm(self.request.GET)
        if form.is_valid():
            data = form.cleaned_data
            if data.get("date_from"):
                qs = qs.filter(collected_at__date__gte=data["date_from"])
            if data.get("date_to"):
                qs = qs.filter(collected_at__date__lte=data["date_to"])
            if data.get("panel_type"):
                qs = qs.filter(panel__panel_type=data["panel_type"])
            if data.get("category"):
                qs = qs.filter(canonical_test__category=data["category"])
            if data.get("abnormal_only"):
                qs = qs.exclude(abnormal_flag="")
            if data.get("search"):
                search = data["search"]
                qs = qs.filter(
                    Q(raw_test_name__icontains=search)
                    | Q(canonical_test__name__icontains=search)
                    | Q(canonical_test__short_name__icontains=search)
                )

        return qs.order_by("-collected_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        ctx["filter_form"] = LabResultFilterForm(self.request.GET)

        # Abnormal results (always unfiltered, top 20)
        ctx["abnormal_results"] = LabResult.objects.filter(
            user=user
        ).exclude(
            abnormal_flag=""
        ).select_related("canonical_test").order_by("-collected_at")[:20]

        # Stats
        ctx["total_results"] = LabResult.objects.filter(user=user).count()
        ctx["total_abnormal"] = LabResult.objects.filter(user=user).exclude(abnormal_flag="").count()
        ctx["total_panels"] = LabPanel.objects.filter(user=user).count()
        ctx["total_documents"] = MedicalDocument.objects.filter(user=user).count()

        # Recent panels
        ctx["recent_panels"] = LabPanel.objects.filter(
            user=user
        ).order_by("-collected_at")[:5]

        # Unique tests for trend links
        ctx["unique_tests"] = LabTestCatalog.objects.filter(
            results__user=user
        ).distinct().order_by("name")

        # Medical documents link (for Organize integration)
        ctx["has_medical_docs"] = MedicalDocument.objects.filter(user=user).exists()

        # Audit: record view
        MedicalAuditLog.objects.create(
            user=user,
            action="view",
            detail="Viewed labs summary",
            ip_address=self.get_client_ip(),
        )

        return ctx

    def get_client_ip(self):
        x_forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")


# =============================================================================
# Detail Views
# =============================================================================

class ResultDetailView(MedicalAccessMixin, DetailView):
    """Single lab result detail."""

    template_name = "medical/result_detail.html"
    context_object_name = "result"

    def get_queryset(self):
        return LabResult.objects.filter(
            user=self.request.user
        ).select_related("canonical_test", "panel", "medical_document", "import_batch")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        result = self.object
        # Historical values for this test
        if result.canonical_test:
            ctx["history"] = LabResult.objects.filter(
                user=self.request.user,
                canonical_test=result.canonical_test,
            ).order_by("-collected_at")[:20]
            # Education content
            try:
                ctx["education"] = result.canonical_test.education
            except LabEducationContent.DoesNotExist:
                ctx["education"] = None
        return ctx


class EducationDetailView(MedicalAccessMixin, DetailView):
    """Return education content for a lab test (for AJAX modal)."""

    template_name = "medical/partials/education_panel.html"
    context_object_name = "education"

    def get_queryset(self):
        return LabEducationContent.objects.select_related("lab_test")

    def get_object(self, queryset=None):
        """Look up education by lab_test (LabTestCatalog) pk."""
        test_id = self.kwargs["test_id"]
        qs = self.get_queryset()
        try:
            return qs.get(lab_test_id=test_id)
        except LabEducationContent.DoesNotExist:
            return None

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["abnormal_flag"] = self.request.GET.get("flag", "")
        return ctx

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)


class PanelDetailView(MedicalAccessMixin, DetailView):
    """Panel detail — shows all results in a panel."""

    template_name = "medical/panel_detail.html"
    context_object_name = "panel"

    def get_queryset(self):
        return LabPanel.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["results"] = self.object.results.select_related(
            "canonical_test"
        ).order_by("canonical_test__sort_order", "raw_test_name")
        return ctx


class DocumentDetailView(MedicalAccessMixin, DetailView):
    """Medical document detail."""

    template_name = "medical/document_detail.html"
    context_object_name = "document"

    def get_queryset(self):
        return MedicalDocument.objects.filter(
            user=self.request.user
        ).select_related("organize_document")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        doc = self.object
        ctx["import_batches"] = doc.import_batches.all()
        ctx["result_count"] = doc.results.count()
        return ctx


class DocumentRenameView(MedicalAccessMixin, View):
    """Rename a medical document's filename and linked Organize Document title."""

    def post(self, request, pk):
        doc = get_object_or_404(MedicalDocument, pk=pk, user=request.user)
        new_name = request.POST.get("filename", "").strip()
        if not new_name:
            messages.error(request, "Filename cannot be empty.")
            return redirect("medical:document_detail", pk=pk)

        old_name = doc.original_filename
        doc.original_filename = new_name
        doc.save(update_fields=["original_filename", "updated_at"])

        # Also update the linked Organize Document title
        if doc.organize_document:
            doc.organize_document.title = new_name
            doc.organize_document.save(update_fields=["title", "updated_at"])

        MedicalAuditLog.objects.create(
            user=request.user,
            action="view",  # rename is a non-destructive action
            detail=f"Renamed document from '{old_name}' to '{new_name}'",
            ip_address=self._get_client_ip(),
        )

        messages.success(request, f"Document renamed to '{new_name}'.")
        return redirect("medical:document_detail", pk=pk)

    def _get_client_ip(self):
        x_forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")


class TestTrendView(MedicalAccessMixin, TemplateView):
    """Single test trend view — values over time."""

    template_name = "medical/test_trend.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        test_id = self.kwargs["test_id"]
        test = get_object_or_404(LabTestCatalog, pk=test_id)
        ctx["test"] = test
        ctx["results"] = LabResult.objects.filter(
            user=self.request.user,
            canonical_test=test,
        ).order_by("collected_at")
        return ctx


# =============================================================================
# Delete Views
# =============================================================================

class DocumentDeleteView(MedicalAccessMixin, View):
    """Delete a medical document AND all associated lab results (soft delete)."""

    def post(self, request, pk):
        doc = get_object_or_404(MedicalDocument, pk=pk, user=request.user)

        # Count results before deleting
        result_count = LabResult.objects.filter(
            user=request.user, medical_document=doc
        ).count()

        # Soft-delete all lab results from this document
        for result in LabResult.objects.filter(user=request.user, medical_document=doc):
            result.soft_delete()

        # Soft-delete all import batches from this document
        for batch in doc.import_batches.all():
            batch.delete()

        # Soft-delete the medical document
        doc.soft_delete()

        # Audit
        MedicalAuditLog.objects.create(
            user=request.user,
            action="delete_doc",
            detail=f"Deleted medical document and {result_count} associated lab results",
            ip_address=self._get_client_ip(),
        )

        messages.success(
            request,
            f"Document and {result_count} lab result{'s' if result_count != 1 else ''} deleted."
        )
        return redirect("medical:home")

    def _get_client_ip(self):
        x_forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")


class ImportDeleteView(MedicalAccessMixin, View):
    """Delete an import batch and all its lab results (soft delete)."""

    def post(self, request, pk):
        batch = get_object_or_404(ImportBatch, pk=pk, user=request.user)
        med_doc = batch.medical_document

        # Count and soft-delete all results from this batch
        results = LabResult.objects.filter(user=request.user, import_batch=batch)
        result_count = results.count()
        for result in results:
            result.soft_delete()

        # Delete error rows
        batch.error_rows.all().delete()

        # Delete the batch itself
        batch.delete()

        # Soft-delete the associated medical document (so file hash doesn't block re-upload)
        if med_doc:
            # Check if there are other active batches for this document
            other_batches = ImportBatch.objects.filter(
                medical_document=med_doc
            ).exclude(pk=pk).exists()
            if not other_batches:
                med_doc.soft_delete()

        # Audit
        MedicalAuditLog.objects.create(
            user=request.user,
            action="delete_results",
            detail=f"Deleted import batch, {result_count} lab results, and associated document",
            ip_address=self._get_client_ip(),
        )

        messages.success(
            request,
            f"Import and {result_count} lab result{'s' if result_count != 1 else ''} deleted."
        )
        return redirect("medical:home")

    def _get_client_ip(self):
        x_forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")


class ResultDeleteView(MedicalAccessMixin, View):
    """Delete a single lab result (soft delete)."""

    def post(self, request, pk):
        result = get_object_or_404(LabResult, pk=pk, user=request.user)
        result.soft_delete()

        MedicalAuditLog.objects.create(
            user=request.user,
            action="delete_results",
            detail="Deleted single lab result",
            ip_address=self._get_client_ip(),
        )

        messages.success(request, "Lab result deleted.")
        return redirect("medical:home")

    def _get_client_ip(self):
        x_forwarded = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")
