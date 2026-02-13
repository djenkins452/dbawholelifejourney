"""
Error reporting for import batches.

Stores ImportErrorRow records and provides CSV export.
"""

import csv
import io
import logging

from apps.medical.models import ImportErrorRow

logger = logging.getLogger(__name__)


def record_error(import_batch, row_number, raw_test_name="", raw_value="",
                 raw_unit="", raw_range="", raw_line="",
                 error_type="parse_error", error_message=""):
    """Record a single import error."""
    return ImportErrorRow.objects.create(
        import_batch=import_batch,
        row_number=row_number,
        raw_test_name=raw_test_name,
        raw_value=raw_value,
        raw_unit=raw_unit,
        raw_range=raw_range,
        raw_line=raw_line,
        error_type=error_type,
        error_message=error_message,
    )


def export_errors_csv(import_batch) -> str:
    """
    Export all errors for an import batch as CSV string.

    Returns CSV content as string.
    """
    errors = ImportErrorRow.objects.filter(import_batch=import_batch).order_by("row_number")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Row #", "Test Name", "Value", "Unit", "Range",
        "Error Type", "Error Message", "Raw Line"
    ])

    for err in errors:
        writer.writerow([
            err.row_number,
            err.raw_test_name,
            err.raw_value,
            err.raw_unit,
            err.raw_range,
            err.error_type,
            err.error_message,
            err.raw_line[:200],  # Truncate long lines
        ])

    return output.getvalue()


def get_error_summary(import_batch) -> dict:
    """Get a summary of errors by type."""
    errors = ImportErrorRow.objects.filter(import_batch=import_batch)
    summary = {}
    for err in errors:
        summary[err.error_type] = summary.get(err.error_type, 0) + 1
    return summary
