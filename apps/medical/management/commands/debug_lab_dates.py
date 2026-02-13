"""
One-time debug command: dump extracted text date lines and test parsing.
Safe to run — read-only, no data changes.
"""
import re
import logging
from django.core.management.base import BaseCommand
from apps.medical.models import MedicalDocument
from apps.medical.services.lab_parser import (
    _parse_portal_date,
    _parse_portal_format,
    _is_portal_format,
    _is_table_format,
    parse_lab_text,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Debug: show extracted text date lines and parser results"

    def handle(self, *args, **options):
        docs = MedicalDocument.objects.all().order_by("-created_at")[:3]

        if not docs:
            self.stdout.write("No medical documents found.")
            return

        for doc in docs:
            self.stdout.write(f"\n{'='*70}")
            self.stdout.write(f"Doc: {doc.original_filename} (created {doc.created_at})")
            self.stdout.write(f"Extraction method: {doc.extraction_method}")
            self.stdout.write(f"Text length: {len(doc.extracted_text or '')}")

            text = doc.extracted_text or ""
            if not text:
                self.stdout.write("  NO EXTRACTED TEXT")
                continue

            # Detect format
            is_portal = _is_portal_format(text)
            is_table = _is_table_format(text)
            self.stdout.write(f"Format detection: portal={is_portal}, table={is_table}")

            # Show ALL lines (first 100) for full context
            lines = text.split('\n')
            self.stdout.write(f"\n--- First 100 lines of extracted text ---")
            for i, line in enumerate(lines[:100]):
                self.stdout.write(f"  {i:3d}: {repr(line[:200])}")

            # Show lines with Date
            self.stdout.write(f"\n--- Lines containing 'Date' ---")
            for i, line in enumerate(lines):
                if 'Date' in line or 'date' in line:
                    self.stdout.write(f"  Line {i}: {repr(line[:300])}")

            # Show lines with 'Collected'
            self.stdout.write(f"\n--- Lines containing 'Collected' ---")
            for i, line in enumerate(lines):
                if 'Collected' in line or 'collected' in line:
                    self.stdout.write(f"  Line {i}: {repr(line[:300])}")

            # Test the date regex on each Date line
            self.stdout.write(f"\n--- Date regex test ---")
            date_regex = re.compile(
                r'^Date:\s*(.+?)(?:\s+Reference Range(?:\s*\([^)]*\))?:\s*(.+))?\s*$'
            )
            for i, line in enumerate(lines):
                stripped = line.strip()
                if 'Date' in stripped:
                    m = date_regex.match(stripped)
                    if m:
                        date_str = m.group(1).strip()
                        ref = m.group(2)
                        parsed = _parse_portal_date(date_str)
                        self.stdout.write(
                            f"  Line {i}: MATCH date_str={repr(date_str)} "
                            f"ref={repr(ref)} parsed={parsed}"
                        )
                    else:
                        self.stdout.write(f"  Line {i}: NO MATCH on {repr(stripped[:200])}")

            # Run actual parser and show results
            self.stdout.write(f"\n--- Parser results ---")
            results = parse_lab_text(text)
            self.stdout.write(f"Total parsed: {len(results)}")
            for r in results[:10]:
                self.stdout.write(
                    f"  {r.test_name}: value={r.value} "
                    f"collected_at={r.collected_at} "
                    f"range={r.reference_range} "
                    f"flag={r.abnormal_flag}"
                )
            if len(results) > 10:
                self.stdout.write(f"  ... and {len(results) - 10} more")
