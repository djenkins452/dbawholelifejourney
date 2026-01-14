"""Word document generation service for Capture entries."""

import logging
from io import BytesIO

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE

logger = logging.getLogger(__name__)


def generate_docx(capture_entry):
    """
    Generate a Word document for a capture entry.

    Args:
        capture_entry: CaptureEntry model instance

    Returns:
        bytes: DOCX file content as bytes
    """
    document = Document()

    # Set up styles
    style = document.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(11)

    # Add header
    header = document.add_paragraph()
    header_run = header.add_run('Whole Life Journey')
    header_run.bold = True
    header_run.font.size = Pt(14)
    header_run.font.color.rgb = RGBColor(99, 102, 241)  # Indigo color
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER

    subtitle = document.add_paragraph()
    subtitle_run = subtitle.add_run('Capture Summary')
    subtitle_run.font.size = Pt(10)
    subtitle_run.font.color.rgb = RGBColor(107, 114, 128)  # Gray
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Add horizontal line (using a paragraph with bottom border)
    document.add_paragraph()

    # Title
    title = document.add_heading(capture_entry.title or 'Untitled Recording', level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT

    # Metadata section
    meta_para = document.add_paragraph()

    # Date
    meta_para.add_run('Date: ').bold = True
    meta_para.add_run(capture_entry.created_at.strftime('%A, %B %d, %Y'))
    meta_para.add_run('\n')

    # Duration
    if capture_entry.duration_seconds:
        minutes = capture_entry.duration_seconds // 60
        seconds = capture_entry.duration_seconds % 60
        meta_para.add_run('Duration: ').bold = True
        meta_para.add_run(f'{minutes}:{seconds:02d}')
        meta_para.add_run('\n')

    # Category
    if capture_entry.category:
        meta_para.add_run('Category: ').bold = True
        category_text = capture_entry.get_category_display()
        if capture_entry.subcategory:
            category_text += f' / {capture_entry.get_subcategory_display()}'
        meta_para.add_run(category_text)

    document.add_paragraph()  # Spacing

    # Summary section
    if capture_entry.summary:
        summary_heading = document.add_heading('Summary', level=2)

        # Split summary into paragraphs and add them
        summary_paragraphs = capture_entry.summary.split('\n\n')
        for para_text in summary_paragraphs:
            if para_text.strip():
                # Check if it's a header (starts with **)
                if para_text.strip().startswith('**') and '**' in para_text.strip()[2:]:
                    # Extract header text
                    end_idx = para_text.strip().index('**', 2)
                    header_text = para_text.strip()[2:end_idx]
                    rest_text = para_text.strip()[end_idx+2:].strip()

                    p = document.add_paragraph()
                    p.add_run(header_text).bold = True
                    if rest_text:
                        p.add_run('\n' + rest_text)
                else:
                    document.add_paragraph(para_text.strip())

        document.add_paragraph()  # Spacing

    # Transcript section
    if capture_entry.transcript:
        transcript_heading = document.add_heading('Full Transcript', level=2)

        transcript_para = document.add_paragraph(capture_entry.transcript)
        transcript_para.style.font.size = Pt(10)
        transcript_para.style.font.color.rgb = RGBColor(107, 114, 128)

    # Footer
    document.add_paragraph()
    footer = document.add_paragraph()
    footer_run = footer.add_run(f'Generated from wholelifejourney.com')
    footer_run.font.size = Pt(9)
    footer_run.font.color.rgb = RGBColor(107, 114, 128)
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    date_footer = document.add_paragraph()
    date_run = date_footer.add_run(
        f'{capture_entry.created_at.strftime("%B %d, %Y")} at {capture_entry.created_at.strftime("%I:%M %p")}'
    )
    date_run.font.size = Pt(8)
    date_run.font.color.rgb = RGBColor(156, 163, 175)
    date_footer.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Save to bytes
    docx_buffer = BytesIO()
    document.save(docx_buffer)
    docx_bytes = docx_buffer.getvalue()
    docx_buffer.close()

    logger.info(
        "Generated DOCX for capture entry %s (%d bytes)",
        capture_entry.id,
        len(docx_bytes)
    )

    return docx_bytes


def get_docx_filename(capture_entry):
    """
    Generate a filename for the DOCX download.

    Args:
        capture_entry: CaptureEntry model instance

    Returns:
        str: Sanitized filename for the DOCX
    """
    # Use title or fallback to 'Capture'
    title = capture_entry.title or 'Capture'

    # Sanitize title for filename
    safe_title = "".join(
        c if c.isalnum() or c in ' -_' else '_'
        for c in title
    )

    # Truncate if too long
    if len(safe_title) > 50:
        safe_title = safe_title[:50]

    # Remove leading/trailing spaces and underscores
    safe_title = safe_title.strip(' _')

    # Format: Title - WLJ Capture - Date.docx
    date_str = capture_entry.created_at.strftime('%Y-%m-%d')

    return f"{safe_title} - WLJ Capture - {date_str}.docx"
