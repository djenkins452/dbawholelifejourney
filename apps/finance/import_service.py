# ==============================================================================
# File: apps/finance/import_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Service for parsing and importing transaction files (CSV, OFX, QFX)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================
"""
Transaction Import Service

Handles parsing of various transaction file formats:
- CSV (various bank formats)
- OFX/QFX (Open Financial Exchange)
- QIF (Quicken Interchange Format)

The service attempts to auto-detect column mappings for CSV files
and provides a standardized interface for all formats.
"""

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.utils import timezone


@dataclass
class ParsedTransaction:
    """Represents a parsed transaction from an import file."""
    date: datetime
    amount: Decimal
    description: str
    payee: str = ''
    reference: str = ''
    memo: str = ''
    category: str = ''
    check_number: str = ''
    is_debit: Optional[bool] = None  # None means infer from amount sign


class ImportError(Exception):
    """Exception raised during import processing."""
    pass


class TransactionImportService:
    """
    Service for parsing transaction files and creating transactions.
    """

    # Common CSV column name patterns
    DATE_PATTERNS = [
        'date', 'posted date', 'post date', 'transaction date', 'trans date',
        'posting date', 'effective date', 'trade date'
    ]
    AMOUNT_PATTERNS = [
        'amount', 'transaction amount', 'trans amount', 'debit/credit',
        'credit/debit'
    ]
    DEBIT_PATTERNS = ['debit', 'withdrawal', 'withdrawals', 'debit amount']
    CREDIT_PATTERNS = ['credit', 'deposit', 'deposits', 'credit amount']
    DESCRIPTION_PATTERNS = [
        'description', 'memo', 'transaction description', 'trans description',
        'details', 'particulars', 'narrative', 'name'
    ]
    PAYEE_PATTERNS = ['payee', 'merchant', 'vendor', 'recipient']
    REFERENCE_PATTERNS = [
        'reference', 'ref', 'reference number', 'confirmation',
        'transaction id', 'trans id', 'id'
    ]
    CHECK_NUMBER_PATTERNS = ['check', 'check number', 'check #', 'cheque']
    CATEGORY_PATTERNS = ['category', 'type', 'transaction type', 'trans type']

    # Date format patterns to try
    DATE_FORMATS = [
        '%m/%d/%Y',      # 01/15/2024
        '%Y-%m-%d',      # 2024-01-15
        '%m-%d-%Y',      # 01-15-2024
        '%d/%m/%Y',      # 15/01/2024
        '%Y/%m/%d',      # 2024/01/15
        '%m/%d/%y',      # 01/15/24
        '%d-%m-%Y',      # 15-01-2024
        '%b %d, %Y',     # Jan 15, 2024
        '%B %d, %Y',     # January 15, 2024
        '%d %b %Y',      # 15 Jan 2024
        '%m.%d.%Y',      # 01.15.2024
        '%Y%m%d',        # 20240115
    ]

    def __init__(self, user, account):
        """
        Initialize the import service.

        Args:
            user: The user performing the import
            account: The FinancialAccount to import into
        """
        self.user = user
        self.account = account
        self.errors = []
        self.warnings = []

    def detect_file_type(self, filename: str, content: bytes) -> str:
        """
        Detect the file type from filename and content.

        Returns:
            One of: 'csv', 'ofx', 'qfx', 'qif'
        """
        filename_lower = filename.lower()

        if filename_lower.endswith('.csv'):
            return 'csv'
        elif filename_lower.endswith('.ofx'):
            return 'ofx'
        elif filename_lower.endswith('.qfx'):
            return 'qfx'
        elif filename_lower.endswith('.qif'):
            return 'qif'

        # Try to detect from content
        content_start = content[:500].decode('utf-8', errors='ignore').upper()

        if 'OFXHEADER' in content_start or '<OFX>' in content_start:
            return 'ofx'
        elif content_start.startswith('!'):
            return 'qif'

        # Default to CSV
        return 'csv'

    def parse_file(self, file_content: bytes, file_type: str) -> list:
        """
        Parse a transaction file and return parsed transactions.

        Args:
            file_content: Raw file content as bytes
            file_type: Type of file ('csv', 'ofx', 'qfx', 'qif')

        Returns:
            List of ParsedTransaction objects
        """
        if file_type == 'csv':
            return self._parse_csv(file_content)
        elif file_type in ('ofx', 'qfx'):
            return self._parse_ofx(file_content)
        elif file_type == 'qif':
            return self._parse_qif(file_content)
        else:
            raise ImportError(f"Unsupported file type: {file_type}")

    def _parse_csv(self, content: bytes) -> list:
        """Parse a CSV file into transactions."""
        # Try different encodings
        text = None
        for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            raise ImportError("Unable to decode file. Please ensure it's a valid CSV.")

        # Parse CSV
        reader = csv.DictReader(io.StringIO(text))

        if not reader.fieldnames:
            raise ImportError("CSV file appears to be empty or has no header row.")

        # Detect column mappings
        columns = {name.lower().strip(): name for name in reader.fieldnames}
        mapping = self._detect_csv_columns(columns)

        if not mapping.get('date'):
            raise ImportError(
                "Could not find a date column. "
                f"Available columns: {', '.join(reader.fieldnames)}"
            )

        if not mapping.get('amount') and not (
            mapping.get('debit') or mapping.get('credit')
        ):
            raise ImportError(
                "Could not find amount, debit, or credit columns. "
                f"Available columns: {', '.join(reader.fieldnames)}"
            )

        # Parse rows
        transactions = []
        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
            try:
                parsed = self._parse_csv_row(row, mapping, row_num)
                if parsed:
                    transactions.append(parsed)
            except Exception as e:
                self.errors.append({
                    'row': row_num,
                    'error': str(e),
                    'data': dict(row)
                })

        return transactions

    def _detect_csv_columns(self, columns: dict) -> dict:
        """Detect column mappings from column names."""
        mapping = {}

        for pattern_list, key in [
            (self.DATE_PATTERNS, 'date'),
            (self.AMOUNT_PATTERNS, 'amount'),
            (self.DEBIT_PATTERNS, 'debit'),
            (self.CREDIT_PATTERNS, 'credit'),
            (self.DESCRIPTION_PATTERNS, 'description'),
            (self.PAYEE_PATTERNS, 'payee'),
            (self.REFERENCE_PATTERNS, 'reference'),
            (self.CHECK_NUMBER_PATTERNS, 'check_number'),
            (self.CATEGORY_PATTERNS, 'category'),
        ]:
            for pattern in pattern_list:
                if pattern in columns:
                    mapping[key] = columns[pattern]
                    break

        return mapping

    def _parse_csv_row(self, row: dict, mapping: dict, row_num: int) -> ParsedTransaction:
        """Parse a single CSV row into a ParsedTransaction."""
        # Parse date
        date_str = row.get(mapping['date'], '').strip()
        if not date_str:
            raise ImportError(f"Row {row_num}: Missing date")

        date = self._parse_date(date_str)
        if not date:
            raise ImportError(f"Row {row_num}: Invalid date format: {date_str}")

        # Parse amount
        amount = None
        is_debit = None

        if mapping.get('amount'):
            amount_str = row.get(mapping['amount'], '').strip()
            amount = self._parse_amount(amount_str)
        elif mapping.get('debit') or mapping.get('credit'):
            debit_str = row.get(mapping.get('debit', ''), '').strip()
            credit_str = row.get(mapping.get('credit', ''), '').strip()

            debit = self._parse_amount(debit_str) if debit_str else None
            credit = self._parse_amount(credit_str) if credit_str else None

            if debit and debit > 0:
                amount = -abs(debit)  # Debits are negative
                is_debit = True
            elif credit and credit > 0:
                amount = abs(credit)  # Credits are positive
                is_debit = False
            elif debit == Decimal('0') and credit:
                amount = abs(credit)
                is_debit = False
            elif credit == Decimal('0') and debit:
                amount = -abs(debit)
                is_debit = True

        if amount is None:
            raise ImportError(f"Row {row_num}: Could not parse amount")

        # Parse other fields
        description = row.get(mapping.get('description', ''), '').strip()
        if not description:
            # Try to construct from other fields
            description = row.get(mapping.get('payee', ''), '').strip()
            if not description:
                description = "Imported transaction"

        payee = row.get(mapping.get('payee', ''), '').strip()
        reference = row.get(mapping.get('reference', ''), '').strip()
        check_number = row.get(mapping.get('check_number', ''), '').strip()
        category = row.get(mapping.get('category', ''), '').strip()

        return ParsedTransaction(
            date=date,
            amount=amount,
            description=description,
            payee=payee,
            reference=reference or check_number,
            category=category,
            is_debit=is_debit
        )

    def _parse_ofx(self, content: bytes) -> list:
        """Parse an OFX/QFX file into transactions."""
        # Decode content
        text = content.decode('utf-8', errors='replace')

        # Simple OFX parser - looks for STMTTRN elements
        transactions = []
        pattern = r'<STMTTRN>(.*?)</STMTTRN>'

        for match in re.finditer(pattern, text, re.DOTALL | re.IGNORECASE):
            trn_text = match.group(1)
            try:
                parsed = self._parse_ofx_transaction(trn_text)
                if parsed:
                    transactions.append(parsed)
            except Exception as e:
                self.errors.append({
                    'error': str(e),
                    'data': trn_text[:100]
                })

        # Also try SGML-style OFX (without closing tags)
        if not transactions:
            transactions = self._parse_ofx_sgml(text)

        return transactions

    def _parse_ofx_transaction(self, trn_text: str) -> ParsedTransaction:
        """Parse a single OFX STMTTRN element."""
        def get_value(tag):
            pattern = rf'<{tag}>(.*?)(?:<|$)'
            match = re.search(pattern, trn_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
            return ''

        # Required fields
        date_str = get_value('DTPOSTED')
        amount_str = get_value('TRNAMT')

        if not date_str or not amount_str:
            return None

        # Parse date (YYYYMMDD format in OFX)
        try:
            date = datetime.strptime(date_str[:8], '%Y%m%d')
        except ValueError:
            raise ImportError(f"Invalid OFX date: {date_str}")

        # Parse amount
        amount = self._parse_amount(amount_str)
        if amount is None:
            raise ImportError(f"Invalid OFX amount: {amount_str}")

        # Optional fields
        description = get_value('NAME') or get_value('MEMO') or 'OFX Transaction'
        memo = get_value('MEMO')
        payee = get_value('PAYEE') or get_value('NAME')
        reference = get_value('FITID') or get_value('REFNUM')
        check_number = get_value('CHECKNUM')

        return ParsedTransaction(
            date=date,
            amount=amount,
            description=description,
            memo=memo,
            payee=payee,
            reference=reference,
            check_number=check_number
        )

    def _parse_ofx_sgml(self, text: str) -> list:
        """Parse SGML-style OFX (without closing tags)."""
        transactions = []
        lines = text.split('\n')

        current_trn = {}
        in_transaction = False

        for line in lines:
            line = line.strip()

            if '<STMTTRN>' in line.upper():
                in_transaction = True
                current_trn = {}
            elif '</STMTTRN>' in line.upper() or (
                in_transaction and line.startswith('<') and
                not any(tag in line.upper() for tag in
                        ['<TRNTYPE', '<DTPOSTED', '<TRNAMT', '<FITID',
                         '<NAME', '<MEMO', '<CHECKNUM', '<PAYEE', '<REFNUM'])
            ):
                if current_trn:
                    try:
                        parsed = self._parse_ofx_dict(current_trn)
                        if parsed:
                            transactions.append(parsed)
                    except Exception:
                        pass
                in_transaction = False
                current_trn = {}
            elif in_transaction:
                for tag in ['DTPOSTED', 'TRNAMT', 'NAME', 'MEMO',
                            'FITID', 'CHECKNUM', 'PAYEE', 'REFNUM']:
                    if f'<{tag}>' in line.upper():
                        value = line.split('>')[-1].strip()
                        current_trn[tag] = value

        return transactions

    def _parse_ofx_dict(self, data: dict) -> ParsedTransaction:
        """Parse a dict of OFX values into a ParsedTransaction."""
        date_str = data.get('DTPOSTED', '')
        amount_str = data.get('TRNAMT', '')

        if not date_str or not amount_str:
            return None

        try:
            date = datetime.strptime(date_str[:8], '%Y%m%d')
        except ValueError:
            return None

        amount = self._parse_amount(amount_str)
        if amount is None:
            return None

        return ParsedTransaction(
            date=date,
            amount=amount,
            description=data.get('NAME', '') or data.get('MEMO', '') or 'OFX Transaction',
            memo=data.get('MEMO', ''),
            payee=data.get('PAYEE', '') or data.get('NAME', ''),
            reference=data.get('FITID', '') or data.get('REFNUM', ''),
            check_number=data.get('CHECKNUM', '')
        )

    def _parse_qif(self, content: bytes) -> list:
        """Parse a QIF file into transactions."""
        text = content.decode('utf-8', errors='replace')
        transactions = []

        current_trn = {}
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('^'):
                # End of transaction
                if current_trn:
                    try:
                        parsed = self._parse_qif_transaction(current_trn)
                        if parsed:
                            transactions.append(parsed)
                    except Exception as e:
                        self.errors.append({
                            'error': str(e),
                            'data': current_trn
                        })
                current_trn = {}
            elif line.startswith('!'):
                # Header line, skip
                continue
            elif len(line) > 1:
                code = line[0]
                value = line[1:].strip()
                current_trn[code] = value

        return transactions

    def _parse_qif_transaction(self, data: dict) -> ParsedTransaction:
        """Parse a QIF transaction dict."""
        date_str = data.get('D', '')
        amount_str = data.get('T', '') or data.get('U', '')

        if not date_str or not amount_str:
            return None

        date = self._parse_date(date_str)
        if not date:
            return None

        amount = self._parse_amount(amount_str)
        if amount is None:
            return None

        return ParsedTransaction(
            date=date,
            amount=amount,
            description=data.get('P', '') or data.get('M', '') or 'QIF Transaction',
            payee=data.get('P', ''),
            memo=data.get('M', ''),
            reference=data.get('N', ''),
            category=data.get('L', '')
        )

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Try to parse a date string using multiple formats."""
        if not date_str:
            return None

        date_str = date_str.strip()

        # Handle QIF date format with apostrophe (1/15'24)
        date_str = date_str.replace("'", "/20")

        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def _parse_amount(self, amount_str: str) -> Optional[Decimal]:
        """Parse an amount string into a Decimal."""
        if not amount_str:
            return None

        # Clean the string
        amount_str = amount_str.strip()

        # Handle parentheses for negative (accounting format)
        if amount_str.startswith('(') and amount_str.endswith(')'):
            amount_str = '-' + amount_str[1:-1]

        # Remove currency symbols and spaces
        amount_str = re.sub(r'[$£€¥\s,]', '', amount_str)

        # Handle CR/DR suffixes
        is_credit = amount_str.upper().endswith('CR')
        is_debit = amount_str.upper().endswith('DR')
        amount_str = re.sub(r'(CR|DR)$', '', amount_str, flags=re.IGNORECASE)

        try:
            amount = Decimal(amount_str)
            if is_debit and amount > 0:
                amount = -amount
            elif is_credit and amount < 0:
                amount = -amount
            return amount
        except InvalidOperation:
            return None

    def create_transactions(self, parsed_transactions: list, import_record) -> dict:
        """
        Create Transaction objects from parsed transactions.

        Args:
            parsed_transactions: List of ParsedTransaction objects
            import_record: TransactionImport record to link to

        Returns:
            Dict with counts: {'imported': int, 'skipped': int, 'failed': int}
        """
        from .models import Transaction

        imported = 0
        skipped = 0
        failed = 0
        errors = []

        for idx, parsed in enumerate(parsed_transactions):
            try:
                # Check for duplicates
                exists = Transaction.objects.filter(
                    user=self.user,
                    account=self.account,
                    date=parsed.date.date() if isinstance(parsed.date, datetime) else parsed.date,
                    amount=parsed.amount,
                    description=parsed.description,
                    status='active'
                ).exists()

                if exists:
                    skipped += 1
                    continue

                # Create the transaction
                Transaction.objects.create(
                    user=self.user,
                    account=self.account,
                    date=parsed.date.date() if isinstance(parsed.date, datetime) else parsed.date,
                    amount=parsed.amount,
                    description=parsed.description,
                    payee=parsed.payee or '',
                    reference=parsed.reference or '',
                    notes=parsed.memo or '',
                    import_record=import_record
                )
                imported += 1

            except Exception as e:
                failed += 1
                errors.append({
                    'index': idx,
                    'error': str(e),
                    'data': {
                        'date': str(parsed.date),
                        'amount': str(parsed.amount),
                        'description': parsed.description
                    }
                })

        return {
            'imported': imported,
            'skipped': skipped,
            'failed': failed,
            'errors': errors
        }
