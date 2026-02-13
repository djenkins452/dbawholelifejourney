"""
Lab result parser.

Turns raw extracted text into structured ParsedResult objects.
Handles multiple lab report formats:
  - Table-based (column headers: Test Name | Result | Flag | Units | Reference Range)
  - Patient portal format (UT Medical / MyChart style: test header + date/value entries)
  - Line-based text formats

Each parser strategy returns a list of ParsedResult dataclass instances.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ParsedResult:
    """A single parsed lab result from a PDF."""
    test_name: str
    value: str
    unit: str = ""
    reference_range: str = ""
    range_low: Optional[str] = None
    range_high: Optional[str] = None
    abnormal_flag: str = ""
    collected_at: Optional[datetime] = None
    reported_at: Optional[datetime] = None
    panel_name: str = ""
    raw_line: str = ""
    row_number: int = 0
    confidence: float = 1.0  # 0.0-1.0, lower means less confident


def _clean_text(text: str) -> str:
    """Remove unicode icons/symbols that portal PDFs often contain."""
    # Remove private-use-area Unicode chars (U+E000-U+F8FF) and other symbols
    return re.sub(r'[\ue000-\uf8ff\ufffd]', '', text)


def parse_lab_text(text: str) -> list[ParsedResult]:
    """
    Main entry point. Detects format and dispatches to appropriate parser.

    Args:
        text: Full extracted text from PDF.

    Returns:
        List of ParsedResult objects.
    """
    if not text or not text.strip():
        return []

    # Clean unicode artifacts
    text = _clean_text(text)

    # Detect format
    if _is_portal_format(text):
        logger.info("Detected patient portal format")
        return _parse_portal_format(text)
    elif _is_table_format(text):
        logger.info("Detected table-based lab format")
        return _parse_table_format(text)
    else:
        logger.info("Using generic line parser")
        return _parse_generic_lines(text)


def _is_portal_format(text: str) -> bool:
    """Detect UT Medical / MyChart portal format."""
    indicators = [
        "Learn more about this",
        "View all for this result",
        "Labs and Vitals",
        "Reference Range:",
    ]
    count = sum(1 for ind in indicators if ind in text)
    return count >= 2


def _is_table_format(text: str) -> bool:
    """Detect standard column-based table format."""
    header_patterns = [
        r"Test\s+Name\s+Result",
        r"Test\s+Result\s+Flag",
        r"Component\s+Your\s+Value",
        r"Analyte\s+Result",
    ]
    for pattern in header_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# ============================================================================
# Portal Format Parser (UT Medical / MyChart)
# ============================================================================

def _parse_portal_format(text: str) -> list[ParsedResult]:
    """
    Parse patient portal format (UT Medical / MyChart).

    Pattern:
        TestName Learn more about this [icon]
        VALUE UNIT [icon]
        Date: ... Reference Range: ...
        VALUE UNIT
        Date: ...
        View all for this result
    """
    results = []
    lines = text.split('\n')
    current_test = None
    current_section = ""
    row_num = 0

    # Skip sections that are vitals, not lab results
    skip_sections = {
        "height/weight/bmi", "blood pressure (sbp/dbp)",
        "oxygen data", "all results",
    }
    skipping = False

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip empty, URL, page header lines
        if (not line or
            line.startswith("http") or
            re.match(r'^\d+/\d+/\d+,\s+\d+:\d+\s+[AP]M', line) or
            "iqhealth.com" in line):
            i += 1
            continue

        # "View all for this result" — boundary
        if "View all for this result" in line:
            i += 1
            continue

        # Section headers
        section_match = re.match(
            r'^(Chem Profiles|Lipids|Hematology|CBC|Calc Values/?Osm|'
            r'Diabetes|Thyroid|Urinalysis|Blood Counts|Coagulation|'
            r'Other|Cardiac|Renal|Liver|Hepatic|Height/Weight/BMI|'
            r'Blood Pressure \(SBP/DBP\)|Oxygen Data|All results|'
            r'Diff|POCT|Calc Values)\s*$',
            line, re.IGNORECASE
        )
        if section_match:
            current_section = section_match.group(1).strip()
            skipping = current_section.lower() in skip_sections
            i += 1
            continue

        if skipping:
            i += 1
            continue

        # Test name header: "TestName Learn more about this"
        test_match = re.match(r'^(.+?)\s+Learn more about (?:this|.+?)\s*$', line)
        if test_match:
            current_test = test_match.group(1).strip()
            # Clean up test names like "Sodium-Na" → keep as is for alias matching
            i += 1
            continue

        # "Learn more about X" on its own line (secondary)
        if line.startswith("Learn more about"):
            i += 1
            continue

        # Value line — try to parse
        if current_test:
            value_parsed = _parse_portal_value_line(line)
            if value_parsed:
                value, unit, flag = value_parsed
                # Look for date on next line(s) — may be past a page break
                collected_at = None
                ref_range = ""
                date_line_offset = 0

                # Search up to 4 lines ahead to find "Date:" line
                # (page breaks insert URL, page number, timestamp, header)
                for look_ahead in range(1, 5):
                    if i + look_ahead >= len(lines):
                        break
                    candidate = lines[i + look_ahead].strip()

                    # Skip page-break noise lines
                    if (not candidate or
                        candidate.startswith("http") or
                        re.match(r'^\d+/\d+/\d+,\s+\d+:\d+\s+[AP]M', candidate) or
                        "iqhealth.com" in candidate or
                        re.match(r'^\d+/\d+$', candidate) or
                        candidate == "UT Medical - Labs and Vitals"):
                        continue

                    # Found a Date: line
                    date_match = re.match(
                        r'^Date:\s*(.+?)(?:\s+Reference Range(?:\s*\([^)]*\))?:\s*(.+))?\s*$',
                        candidate
                    )
                    if date_match:
                        date_str = date_match.group(1).strip()
                        ref_raw = date_match.group(2)
                        collected_at = _parse_portal_date(date_str)
                        if collected_at is None:
                            logger.warning(
                                "Date extraction failed for test '%s', date line: %r",
                                current_test, candidate
                            )
                        if ref_raw:
                            ref_range = ref_raw.strip()
                        date_line_offset = look_ahead
                        break
                    elif candidate.startswith('Date'):
                        logger.warning(
                            "Date line didn't match expected format for test '%s': %r",
                            current_test, candidate
                        )
                        date_line_offset = look_ahead
                        break
                    else:
                        # Hit a non-noise, non-date line — stop looking
                        break

                if date_line_offset:
                    i += date_line_offset  # Skip past the date line

                range_low, range_high = _parse_reference_range(ref_range)

                row_num += 1
                results.append(ParsedResult(
                    test_name=current_test,
                    value=value,
                    unit=unit,
                    reference_range=ref_range,
                    range_low=range_low,
                    range_high=range_high,
                    abnormal_flag=_normalize_flag(flag),
                    collected_at=collected_at,
                    panel_name=current_section,
                    raw_line=line,
                    row_number=row_num,
                ))

        i += 1

    return results


def _parse_portal_value_line(line: str):
    """
    Parse a portal value line.

    Returns: (value, unit, flag) tuple or None if not a value line.
    """
    line = line.strip()

    # Skip lines that are clearly not values
    if line.startswith(('Date:', 'View all', 'http', 'PLEASE', 'If you', 'This section', 'These items')):
        return None
    if 'Learn more' in line:
        return None

    # Qualitative values
    qual_match = re.match(
        r'^(Negative|Positive|Trace|Normal|Clear|Yellow|Amber|Red|Straw|Dark|'
        r'Room Air|Not Detected|Detected)\s*(?:\((\w+)\))?\s*$',
        line, re.IGNORECASE
    )
    if qual_match:
        return (qual_match.group(1), "", qual_match.group(2) or "")

    # Combined BP value: "136 / 76 mmHg"
    bp_match = re.match(
        r'^(\d+\s*/\s*\d+)\s+(\w+)\s*(?:\((\w+)\))?\s*$', line
    )
    if bp_match:
        return (bp_match.group(1), bp_match.group(2), bp_match.group(3) or "")

    # Standard: "VALUE UNIT (FLAG)" or "VALUE UNIT"
    # e.g., "140 mEq/L", "3.0 mEq/L (Low)", "4.0 Ratio"
    val_match = re.match(
        r'^([<>=]*[\d.,]+(?:\.\d+)?)\s+'  # value
        r'([\w/%^.]+(?:/[\w/%^.]+)*)\s*'  # unit
        r'(?:\((\w+)\))?\s*$',  # optional (Flag)
        line
    )
    if val_match:
        return (val_match.group(1), val_match.group(2), val_match.group(3) or "")

    # Value with % as unit: "98 %"
    pct_match = re.match(r'^([<>=]*[\d.,]+)\s+(%)\s*(?:\((\w+)\))?\s*$', line)
    if pct_match:
        return (pct_match.group(1), pct_match.group(2), pct_match.group(3) or "")

    # Value only (no unit): "40.57"
    num_only = re.match(r'^([<>=]*[\d.,]+(?:\.\d+)?)\s*(?:\((\w+)\))?\s*$', line)
    if num_only:
        return (num_only.group(1), "", num_only.group(2) or "")

    return None


def _parse_portal_date(date_str: str) -> Optional[datetime]:
    """Parse portal date strings like 'Feb 06, 2026 07:56 a.m. EST'."""
    # Remove timezone abbreviation (2-5 uppercase letters at end, e.g. EST, CDT, AEST)
    cleaned = re.sub(r'\s+[A-Z]{2,5}\s*$', '', date_str.strip())
    # Normalize am/pm variants
    cleaned = cleaned.replace('a.m.', 'AM').replace('p.m.', 'PM')
    cleaned = cleaned.replace(' am', ' AM').replace(' pm', ' PM')
    # Strip any trailing whitespace or punctuation
    cleaned = cleaned.strip().rstrip('.')

    formats = [
        "%b %d, %Y %I:%M %p",      # "Feb 06, 2026 07:56 AM"
        "%b %d, %Y %H:%M",          # "Feb 06, 2026 07:56"
        "%B %d, %Y %I:%M %p",       # "February 06, 2026 07:56 AM"
        "%B %d, %Y %H:%M",          # "February 06, 2026 07:56"
        "%b %d, %Y",                 # "Feb 06, 2026"
        "%B %d, %Y",                 # "February 06, 2026"
        "%b %d %Y %I:%M %p",        # "Feb 06 2026 07:56 AM" (no comma)
        "%b %d %Y %H:%M",           # "Feb 06 2026 07:56" (no comma)
        "%b %d %Y",                  # "Feb 06 2026" (no comma)
        "%m/%d/%Y %I:%M %p",        # "02/06/2026 07:56 AM"
        "%m/%d/%Y %H:%M",           # "02/06/2026 07:56"
        "%m/%d/%Y",                  # "02/06/2026"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue

    logger.warning("Could not parse portal date: %r (cleaned: %r)", date_str, cleaned)
    return None


# ============================================================================
# Table Format Parser
# ============================================================================

def _parse_table_format(text: str) -> list[ParsedResult]:
    """
    Parse standard lab table format.

    Columns: Test Name | Result | [Flag] | [Units] | [Reference Range]
    Separated by spaces (varying count).
    """
    results = []
    lines = text.split('\n')
    current_panel = ""
    row_num = 0
    collected_at = None
    reported_at = None

    # Extract collection/report dates from header
    for line in lines[:20]:
        date_match = re.search(
            r'Collected:\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\s*(?:AM|PM)?)',
            line, re.IGNORECASE
        )
        if date_match:
            collected_at = _parse_standard_date(date_match.group(1))

        report_match = re.search(
            r'Reported:\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}\s*(?:AM|PM)?)',
            line, re.IGNORECASE
        )
        if report_match:
            reported_at = _parse_standard_date(report_match.group(1))

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Skip metadata lines
        if re.match(r'^(Patient|Account|Physician|Collected|Reported|DOB|---|\*|This report|Lab Director|CLIA)', stripped, re.IGNORECASE):
            continue

        # Panel section headers (ALL CAPS, possibly with parentheses)
        panel_match = re.match(
            r'^([A-Z][A-Z /()&,]+(?:WITH DIFFERENTIAL)?)\s*$', stripped
        )
        if panel_match:
            candidate = panel_match.group(1).strip()
            if len(candidate) >= 3 and candidate != "Test Name Result Flag Units Reference Range":
                current_panel = candidate
                continue

        # Table header line
        if re.match(r'^Test\s+Name\s+Result', stripped, re.IGNORECASE):
            continue

        # Try to parse as data row
        parsed = _parse_table_row(stripped, current_panel, collected_at, reported_at)
        if parsed:
            row_num += 1
            parsed.row_number = row_num
            results.append(parsed)

    return results


def _parse_table_row(line: str, panel: str, collected: Optional[datetime],
                     reported: Optional[datetime]) -> Optional[ParsedResult]:
    """
    Parse a single table row.

    Examples:
        "WBC 7.2 x10^3/uL 4.0-11.0"
        "Glucose 105 H mg/dL 70-99"
        "eGFR >60 mL/min/1.73m2 >60"
        "Color Yellow Yellow"
        "A/G Ratio 1.5 1.0-2.5"
        "BUN/Creatinine Ratio 19 6-22"
    """
    # Strategy: work backwards from end of line to identify range, unit, flag, value
    # Then everything before value is the test name

    parts = line.split()
    if len(parts) < 2:
        return None

    # Try to identify the value position by finding the first numeric-like token
    # after potential multi-word test names
    value_idx = None
    for idx in range(len(parts)):
        token = parts[idx]
        # Is this a value? (numeric or comparison+numeric or qualitative)
        if re.match(r'^[<>=]*\d', token) or token.lower() in (
            'negative', 'positive', 'trace', 'clear', 'yellow', 'normal'
        ):
            # Make sure what comes before looks like a test name (at least one alpha token)
            name_parts = parts[:idx]
            if name_parts and any(re.match(r'[A-Za-z]', p) for p in name_parts):
                value_idx = idx
                break

    if value_idx is None:
        return None

    test_name = " ".join(parts[:value_idx])
    value = parts[value_idx]

    # Now parse remaining tokens after value: [flag] [unit] [range]
    remaining = parts[value_idx + 1:]

    flag = ""
    unit = ""
    ref_range = ""

    if remaining:
        # Check if first remaining token is a flag (H, L, HH, LL, A)
        if remaining[0] in ("H", "L", "HH", "LL", "A"):
            flag = remaining[0]
            remaining = remaining[1:]

        # Check for unit
        if remaining:
            # Is the first remaining token a unit?
            if re.match(r'^[a-zA-Z%/^]', remaining[0]) and not re.match(r'^[\d<>=]', remaining[0]):
                unit = remaining[0]
                remaining = remaining[1:]

        # Everything else is reference range
        if remaining:
            ref_range = " ".join(remaining)

    if not test_name or len(test_name) < 2:
        return None

    range_low, range_high = _parse_reference_range(ref_range)

    return ParsedResult(
        test_name=test_name,
        value=value,
        unit=unit,
        reference_range=ref_range,
        range_low=range_low,
        range_high=range_high,
        abnormal_flag=_normalize_flag(flag),
        collected_at=collected,
        reported_at=reported,
        panel_name=panel,
        raw_line=line,
    )


# ============================================================================
# Generic Line Parser (fallback)
# ============================================================================

def _parse_generic_lines(text: str) -> list[ParsedResult]:
    """Generic fallback parser for unrecognized formats."""
    results = []
    lines = text.split('\n')
    row_num = 0

    for line in lines:
        stripped = line.strip()
        if not stripped or len(stripped) < 5:
            continue

        match = re.match(
            r'^([A-Za-z][A-Za-z /(),-]+?)\s+'
            r'([<>=]*\d[\d.,]*)\s*'
            r'([\w/%^.]+(?:/[\w/%^.]+)*)?\s*'
            r'(?:Reference Range:?\s*)?'
            r'([\d.,<>=]+\s*(?:[-]\s*[\d.,]+)?\s*[\w/%^.]*)?',
            stripped
        )
        if match:
            name = match.group(1).strip()
            value = match.group(2).strip()
            unit = (match.group(3) or "").strip()
            ref = (match.group(4) or "").strip()

            if len(name) >= 2 and not name.startswith(('Date', 'Page', 'http')):
                row_num += 1
                range_low, range_high = _parse_reference_range(ref)
                results.append(ParsedResult(
                    test_name=name,
                    value=value,
                    unit=unit,
                    reference_range=ref,
                    range_low=range_low,
                    range_high=range_high,
                    raw_line=stripped,
                    row_number=row_num,
                    confidence=0.5,
                ))

    return results


# ============================================================================
# Utility Functions
# ============================================================================

def _parse_reference_range(range_text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse reference range text into low/high values.

    Examples:
        "70-99" -> ("70", "99")
        "<200" -> (None, "200")
        ">40" -> ("40", None)
        "<= 55 U/L" -> (None, "55")
        ">= 40 mg/dL" -> ("40", None)
        "134 mEq/L - 144 mEq/L" -> ("134", "144")
        "Negative" -> (None, None)
    """
    if not range_text:
        return (None, None)

    range_text = range_text.strip()

    # Skip qualitative ranges
    if range_text.lower() in ('negative', 'positive', 'normal', 'clear', 'yellow'):
        return (None, None)

    # "134 mEq/L - 144 mEq/L" pattern (with units in range)
    m = re.match(
        r'([<>=]*\s*[\d.,]+)\s*[\w/%^.]*\s*[-–]\s*([<>=]*\s*[\d.,]+)\s*[\w/%^.]*',
        range_text
    )
    if m:
        low = re.sub(r'[<>=\s]', '', m.group(1))
        high = re.sub(r'[<>=\s]', '', m.group(2))
        return (low or None, high or None)

    # Simple range: "70-99"
    m = re.match(r'^([\d.,]+)\s*[-–]\s*([\d.,]+)$', range_text)
    if m:
        return (m.group(1), m.group(2))

    # Less than: "<200", "<= 55"
    m = re.match(r'^[<≤]=?\s*([\d.,]+)', range_text)
    if m:
        return (None, m.group(1))

    # Greater than: ">40", ">= 40"
    m = re.match(r'^[>≥]=?\s*([\d.,]+)', range_text)
    if m:
        return (m.group(1), None)

    return (None, None)


def _normalize_flag(flag: str) -> str:
    """Normalize abnormal flag text to standard codes."""
    if not flag:
        return ""
    flag_upper = flag.strip().upper()
    mapping = {
        "H": "H",
        "HIGH": "H",
        "HI": "H",
        "L": "L",
        "LOW": "L",
        "LO": "L",
        "HH": "HH",
        "CRITICAL HIGH": "HH",
        "LL": "LL",
        "CRITICAL LOW": "LL",
        "A": "A",
        "ABN": "A",
        "ABNORMAL": "A",
    }
    return mapping.get(flag_upper, "A" if flag_upper else "")


def _parse_standard_date(date_str: str) -> Optional[datetime]:
    """Parse standard date formats from lab reports."""
    if not date_str:
        return None

    formats = [
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_numeric_value(value_text: str) -> Optional[Decimal]:
    """
    Try to parse a numeric value from text.
    Handles: "7.2", ">60", "<0.5", "120", "Negative" -> None
    """
    if not value_text:
        return None

    cleaned = re.sub(r'^[<>=≤≥]+\s*', '', value_text.strip())
    cleaned = cleaned.replace(',', '')

    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None
