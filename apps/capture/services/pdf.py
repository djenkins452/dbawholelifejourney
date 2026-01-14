"""PDF generation service for Capture entries."""

import logging
from io import BytesIO

from django.conf import settings
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def generate_pdf(capture_entry):
    """
    Generate a PDF document for a capture entry.

    Args:
        capture_entry: CaptureEntry model instance

    Returns:
        bytes: PDF file content as bytes

    Raises:
        ImportError: If WeasyPrint is not installed
        Exception: If PDF generation fails
    """
    try:
        from weasyprint import HTML
    except ImportError as e:
        logger.error("WeasyPrint not installed: %s", e)
        raise ImportError(
            "WeasyPrint is required for PDF generation. "
            "Install it with: pip install weasyprint"
        ) from e

    # Calculate formatted duration
    formatted_duration = None
    if capture_entry.duration_seconds:
        minutes = capture_entry.duration_seconds // 60
        seconds = capture_entry.duration_seconds % 60
        formatted_duration = f"{minutes}:{seconds:02d}"

    # Prepare context for template
    context = {
        'entry': capture_entry,
        'formatted_duration': formatted_duration,
    }

    # Render HTML template
    try:
        html_content = render_to_string('capture/pdf_template.html', context)
        logger.debug("HTML template rendered successfully for entry %s", capture_entry.id)
    except Exception as e:
        logger.exception("Failed to render HTML template for entry %s: %s", capture_entry.id, e)
        raise

    # Generate PDF with base_url for proper resource resolution
    pdf_buffer = BytesIO()

    # Get base URL for WeasyPrint to resolve relative paths
    # This is needed for fonts and any relative resources
    base_url = getattr(settings, 'SITE_URL', 'https://wholelifejourney.com')

    try:
        # Create HTML document with base_url and write to PDF
        html_doc = HTML(string=html_content, base_url=base_url)
        html_doc.write_pdf(pdf_buffer)
    except Exception as e:
        logger.exception("WeasyPrint failed to generate PDF for entry %s: %s", capture_entry.id, e)
        raise

    # Get PDF bytes
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    logger.info(
        "Generated PDF for capture entry %s (%d bytes)",
        capture_entry.id,
        len(pdf_bytes)
    )

    return pdf_bytes


def get_pdf_filename(capture_entry):
    """
    Generate a filename for the PDF download.

    Args:
        capture_entry: CaptureEntry model instance

    Returns:
        str: Sanitized filename for the PDF
    """
    # Use title or fallback to 'Capture'
    title = capture_entry.title or 'Capture'

    # Sanitize title for filename (remove/replace unsafe characters)
    safe_title = "".join(
        c if c.isalnum() or c in ' -_' else '_'
        for c in title
    )

    # Truncate if too long
    if len(safe_title) > 50:
        safe_title = safe_title[:50]

    # Remove leading/trailing spaces and underscores
    safe_title = safe_title.strip(' _')

    # Format: Title - WLJ Capture - Date.pdf
    date_str = capture_entry.created_at.strftime('%Y-%m-%d')

    return f"{safe_title} - WLJ Capture - {date_str}.pdf"
