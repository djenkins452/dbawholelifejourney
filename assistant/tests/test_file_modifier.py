"""
Tests for the Safe File Modifier Service.
"""

import tempfile
from pathlib import Path
from unittest import TestCase

from assistant.file_modifier import (
    ALLOWED_FILES,
    FORBIDDEN_FILES,
    ModificationType,
    SafeFileModifier,
)


class TestValidateTargetFile(TestCase):
    """Tests for validate_target_file method."""

    def setUp(self):
        """Set up test fixtures with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.modifier = SafeFileModifier(base_path=self.temp_dir)

        # Create allowed test files
        for filename in ALLOWED_FILES:
            (Path(self.temp_dir) / filename).write_text('# test file\n')

    def test_allowed_file_passes(self):
        """Test that allowed files pass validation."""
        result = self.modifier.validate_target_file('intent_detector.py')
        self.assertTrue(result.success)
        self.assertIn('valid for modification', result.message)

    def test_forbidden_file_rejected(self):
        """Test that forbidden files are rejected."""
        result = self.modifier.validate_target_file('settings.py')
        self.assertFalse(result.success)
        self.assertIn('FORBIDDEN_FILES', result.message)

    def test_unlisted_file_rejected(self):
        """Test that files not in allowed list are rejected."""
        result = self.modifier.validate_target_file('random_file.py')
        self.assertFalse(result.success)
        self.assertIn('not in ALLOWED_FILES', result.message)

    def test_nonexistent_file_rejected(self):
        """Test that non-existent files are rejected."""
        # Remove the file first
        (Path(self.temp_dir) / 'intent_detector.py').unlink()
        result = self.modifier.validate_target_file('intent_detector.py')
        self.assertFalse(result.success)
        self.assertIn('does not exist', result.message)


class TestBackupAndRestore(TestCase):
    """Tests for backup_file and restore_from_backup methods."""

    def setUp(self):
        """Set up test fixtures with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.modifier = SafeFileModifier(base_path=self.temp_dir)

        # Create a test file
        self.test_file = Path(self.temp_dir) / 'intent_detector.py'
        self.original_content = '# original content\ndef test(): pass\n'
        self.test_file.write_text(self.original_content)

    def test_backup_creates_file(self):
        """Test that backup creates a .backup file."""
        result = self.modifier.backup_file('intent_detector.py')

        self.assertTrue(result.success)
        self.assertIsNotNone(result.backup_path)

        backup_path = Path(result.backup_path)
        self.assertTrue(backup_path.exists())
        self.assertEqual(backup_path.read_text(), self.original_content)

    def test_restore_reverts_changes(self):
        """Test that restore reverts file to backup state."""
        # Create backup
        self.modifier.backup_file('intent_detector.py')

        # Modify the file
        self.test_file.write_text('# modified content\n')

        # Restore
        result = self.modifier.restore_from_backup('intent_detector.py')

        self.assertTrue(result.success)
        self.assertEqual(self.test_file.read_text(), self.original_content)

    def test_restore_removes_backup(self):
        """Test that restore removes the backup file after restoring."""
        backup_result = self.modifier.backup_file('intent_detector.py')
        backup_path = Path(backup_result.backup_path)

        self.modifier.restore_from_backup('intent_detector.py')

        self.assertFalse(backup_path.exists())

    def test_restore_no_backup_fails(self):
        """Test that restore fails if no backup exists."""
        result = self.modifier.restore_from_backup('intent_detector.py')
        self.assertFalse(result.success)
        self.assertIn('No backup found', result.message)


class TestValidatePythonSyntax(TestCase):
    """Tests for validate_python_syntax method."""

    def setUp(self):
        """Set up test fixtures."""
        self.modifier = SafeFileModifier()

    def test_valid_syntax_passes(self):
        """Test that valid Python syntax passes."""
        content = '''
def hello():
    return "world"

class MyClass:
    def method(self):
        pass
'''
        result = self.modifier.validate_python_syntax(content)
        self.assertTrue(result.success)

    def test_invalid_syntax_fails(self):
        """Test that invalid Python syntax fails."""
        content = '''
def hello(
    return "missing closing paren"
'''
        result = self.modifier.validate_python_syntax(content)
        self.assertFalse(result.success)
        self.assertIn('Invalid Python syntax', result.message)

    def test_syntax_error_includes_line_number(self):
        """Test that syntax errors include line number."""
        content = '''line1
line2
def broken(
'''
        result = self.modifier.validate_python_syntax(content)
        self.assertFalse(result.success)
        self.assertIn('line', result.message.lower())


class TestInsertCodeAfterPattern(TestCase):
    """Tests for insert_code_after_pattern method."""

    def setUp(self):
        """Set up test fixtures."""
        self.modifier = SafeFileModifier()

    def test_insert_after_pattern(self):
        """Test inserting code after a pattern."""
        content = '''# Header
KEYWORDS = {
    'existing': 'value',
}
# Footer
'''
        result = self.modifier.insert_code_after_pattern(
            content,
            r"'existing': 'value',",
            "\n    'new': 'item',"
        )

        self.assertTrue(result.success)
        self.assertIn("'new': 'item'", result.modified_content)

    def test_pattern_not_found(self):
        """Test that missing pattern returns error."""
        content = '# no match here\n'
        result = self.modifier.insert_code_after_pattern(
            content,
            r'nonexistent_pattern',
            'new code'
        )

        self.assertFalse(result.success)
        self.assertIn('Pattern not found', result.message)

    def test_invalid_regex_pattern(self):
        """Test that invalid regex returns error."""
        result = self.modifier.insert_code_after_pattern(
            'content',
            r'[invalid(regex',
            'code'
        )

        self.assertFalse(result.success)
        self.assertIn('Invalid regex', result.message)


class TestAppendToDict(TestCase):
    """Tests for append_to_dict method."""

    def setUp(self):
        """Set up test fixtures."""
        self.modifier = SafeFileModifier()

    def test_append_to_simple_dict(self):
        """Test appending to a simple dictionary."""
        content = '''KEYWORDS = {
    'key1': 'value1',
    'key2': 'value2',
}
'''
        result = self.modifier.append_to_dict(
            content,
            r'KEYWORDS = \{',
            "'key3': 'value3',"
        )

        self.assertTrue(result.success)
        self.assertIn("'key3': 'value3'", result.modified_content)

    def test_dict_pattern_not_found(self):
        """Test error when dictionary pattern not found."""
        content = '# no dict here\n'
        result = self.modifier.append_to_dict(
            content,
            r'MISSING_DICT = \{',
            "'key': 'value',"
        )

        self.assertFalse(result.success)
        self.assertIn('not found', result.message)


class TestAppendMethodToClass(TestCase):
    """Tests for append_method_to_class method."""

    def setUp(self):
        """Set up test fixtures."""
        self.modifier = SafeFileModifier()

    def test_append_method_to_class(self):
        """Test appending a method to a class."""
        content = '''class MyClass:
    def existing_method(self):
        pass
'''
        method_code = '''def new_method(self):
    return "new"'''

        result = self.modifier.append_method_to_class(
            content,
            'MyClass',
            method_code
        )

        self.assertTrue(result.success)
        self.assertIn('new_method', result.modified_content)

    def test_class_not_found(self):
        """Test error when class not found."""
        content = '# no class here\n'
        result = self.modifier.append_method_to_class(
            content,
            'NonexistentClass',
            'def method(): pass'
        )

        self.assertFalse(result.success)
        self.assertIn('not found', result.message)


class TestApplyModification(TestCase):
    """Tests for apply_modification main entry point."""

    def setUp(self):
        """Set up test fixtures with temporary directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.modifier = SafeFileModifier(base_path=self.temp_dir)

        # Create a valid test file
        self.test_file = Path(self.temp_dir) / 'intent_detector.py'
        self.test_file.write_text('# test file\ndef existing(): pass\n')

    def test_append_modification(self):
        """Test APPEND modification type."""
        result = self.modifier.apply_modification(
            'intent_detector.py',
            ModificationType.APPEND,
            'def new_func(): pass'
        )

        self.assertTrue(result.success)
        content = self.test_file.read_text()
        self.assertIn('new_func', content)

    def test_insert_after_modification(self):
        """Test INSERT_AFTER modification type."""
        result = self.modifier.apply_modification(
            'intent_detector.py',
            ModificationType.INSERT_AFTER,
            '\ndef inserted(): pass',
            pattern=r'def existing\(\): pass'
        )

        self.assertTrue(result.success)
        content = self.test_file.read_text()
        self.assertIn('inserted', content)

    def test_replace_modification(self):
        """Test REPLACE modification type."""
        result = self.modifier.apply_modification(
            'intent_detector.py',
            ModificationType.REPLACE,
            'def replaced(): pass',
            pattern=r'def existing\(\): pass'
        )

        self.assertTrue(result.success)
        content = self.test_file.read_text()
        self.assertIn('replaced', content)
        self.assertNotIn('existing', content)

    def test_forbidden_file_rejected(self):
        """Test that forbidden files are rejected."""
        result = self.modifier.apply_modification(
            'settings.py',
            ModificationType.APPEND,
            'DANGEROUS_CODE = True'
        )

        self.assertFalse(result.success)
        self.assertIn('FORBIDDEN_FILES', result.message)

    def test_invalid_syntax_rollback(self):
        """Test that invalid syntax triggers rollback."""
        original_content = self.test_file.read_text()

        result = self.modifier.apply_modification(
            'intent_detector.py',
            ModificationType.APPEND,
            'def broken(:'  # Invalid syntax
        )

        self.assertFalse(result.success)
        self.assertIn('invalid Python', result.message.lower())

        # File should be restored to original
        self.assertEqual(self.test_file.read_text(), original_content)

    def test_creates_backup(self):
        """Test that modification creates backup."""
        result = self.modifier.apply_modification(
            'intent_detector.py',
            ModificationType.APPEND,
            'def new(): pass'
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.backup_path)

    def test_insert_after_requires_pattern(self):
        """Test that INSERT_AFTER requires pattern parameter."""
        result = self.modifier.apply_modification(
            'intent_detector.py',
            ModificationType.INSERT_AFTER,
            'code'
            # No pattern provided
        )

        self.assertFalse(result.success)
        self.assertIn('Pattern required', result.message)


class TestFileModifierConstants(TestCase):
    """Tests for module constants."""

    def test_allowed_files_contains_expected(self):
        """Test ALLOWED_FILES contains expected files."""
        self.assertIn('intent_detector.py', ALLOWED_FILES)
        self.assertIn('data_service.py', ALLOWED_FILES)
        self.assertIn('context_builder.py', ALLOWED_FILES)
        self.assertIn('date_parser.py', ALLOWED_FILES)

    def test_forbidden_files_contains_expected(self):
        """Test FORBIDDEN_FILES contains expected files."""
        self.assertIn('settings.py', FORBIDDEN_FILES)
        self.assertIn('models.py', FORBIDDEN_FILES)
        self.assertIn('views.py', FORBIDDEN_FILES)
        self.assertIn('urls.py', FORBIDDEN_FILES)
        self.assertIn('manage.py', FORBIDDEN_FILES)

    def test_no_overlap_between_lists(self):
        """Test that no files appear in both lists."""
        overlap = set(ALLOWED_FILES) & set(FORBIDDEN_FILES)
        self.assertEqual(len(overlap), 0, f"Overlap found: {overlap}")
