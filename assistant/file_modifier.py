"""
Safe File Modifier Service for validated Python file modifications.

Provides safe, validated file modification capabilities for the Personal Assistant
improvement workflow. Includes syntax validation, backup/restore, and restricted
file access.
"""

import ast
import re
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


# Files that can be modified by the improvement system
ALLOWED_FILES = [
    'intent_detector.py',
    'data_service.py',
    'context_builder.py',
    'date_parser.py',
]

# Files that must never be modified automatically
FORBIDDEN_FILES = [
    'settings.py',
    'models.py',
    'views.py',
    'urls.py',
    'manage.py',
]


class ModificationType(Enum):
    """Types of file modifications supported."""
    APPEND = 'append'
    INSERT_AFTER = 'insert_after'
    REPLACE = 'replace'


@dataclass
class ModificationResult:
    """Result of a file modification operation."""
    success: bool
    message: str
    backup_path: Optional[str] = None
    modified_content: Optional[str] = None


class SafeFileModifier:
    """
    Service for safely modifying Python files with validation.

    Ensures files are in the allowed list, creates backups before changes,
    validates Python syntax, and provides rollback capabilities.
    """

    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize the file modifier.

        Args:
            base_path: Base path for the assistant module. Defaults to current directory.
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()

    def validate_target_file(self, file_path: str) -> ModificationResult:
        """
        Validate that a file can be modified.

        Args:
            file_path: Path to the file to validate.

        Returns:
            ModificationResult with success=True if file is allowed.
        """
        path = Path(file_path)
        filename = path.name

        # Check forbidden files
        if filename in FORBIDDEN_FILES:
            return ModificationResult(
                success=False,
                message=f"File '{filename}' is in FORBIDDEN_FILES and cannot be modified"
            )

        # Check allowed files
        if filename not in ALLOWED_FILES:
            return ModificationResult(
                success=False,
                message=f"File '{filename}' is not in ALLOWED_FILES. "
                        f"Allowed: {', '.join(ALLOWED_FILES)}"
            )

        # Check file exists
        full_path = self.base_path / file_path if not path.is_absolute() else path
        if not full_path.exists():
            return ModificationResult(
                success=False,
                message=f"File does not exist: {full_path}"
            )

        return ModificationResult(
            success=True,
            message=f"File '{filename}' is valid for modification"
        )

    def backup_file(self, file_path: str) -> ModificationResult:
        """
        Create a backup of a file before modification.

        Args:
            file_path: Path to the file to backup.

        Returns:
            ModificationResult with backup_path if successful.
        """
        path = Path(file_path)
        full_path = self.base_path / file_path if not path.is_absolute() else path
        backup_path = full_path.with_suffix(full_path.suffix + '.backup')

        try:
            shutil.copy2(full_path, backup_path)
            return ModificationResult(
                success=True,
                message=f"Backup created at {backup_path}",
                backup_path=str(backup_path)
            )
        except Exception as e:
            return ModificationResult(
                success=False,
                message=f"Failed to create backup: {e}"
            )

    def restore_from_backup(self, file_path: str) -> ModificationResult:
        """
        Restore a file from its backup.

        Args:
            file_path: Path to the file to restore.

        Returns:
            ModificationResult indicating success or failure.
        """
        path = Path(file_path)
        full_path = self.base_path / file_path if not path.is_absolute() else path
        backup_path = full_path.with_suffix(full_path.suffix + '.backup')

        if not backup_path.exists():
            return ModificationResult(
                success=False,
                message=f"No backup found at {backup_path}"
            )

        try:
            shutil.copy2(backup_path, full_path)
            backup_path.unlink()  # Remove backup after restore
            return ModificationResult(
                success=True,
                message="File restored from backup"
            )
        except Exception as e:
            return ModificationResult(
                success=False,
                message=f"Failed to restore from backup: {e}"
            )

    def validate_python_syntax(self, content: str) -> ModificationResult:
        """
        Validate that content is valid Python syntax.

        Args:
            content: Python code to validate.

        Returns:
            ModificationResult with success=True if syntax is valid.
        """
        try:
            ast.parse(content)
            return ModificationResult(
                success=True,
                message="Python syntax is valid"
            )
        except SyntaxError as e:
            return ModificationResult(
                success=False,
                message=f"Invalid Python syntax at line {e.lineno}: {e.msg}"
            )

    def insert_code_after_pattern(
        self,
        content: str,
        pattern: str,
        code_to_insert: str
    ) -> ModificationResult:
        """
        Insert code after a regex pattern match.

        Args:
            content: Original file content.
            pattern: Regex pattern to find.
            code_to_insert: Code to insert after the pattern.

        Returns:
            ModificationResult with modified_content if successful.
        """
        try:
            regex = re.compile(pattern, re.MULTILINE)
            match = regex.search(content)

            if not match:
                return ModificationResult(
                    success=False,
                    message=f"Pattern not found: {pattern}"
                )

            # Insert after the match
            insert_pos = match.end()
            modified = content[:insert_pos] + code_to_insert + content[insert_pos:]

            return ModificationResult(
                success=True,
                message="Code inserted successfully",
                modified_content=modified
            )
        except re.error as e:
            return ModificationResult(
                success=False,
                message=f"Invalid regex pattern: {e}"
            )

    def append_to_dict(
        self,
        content: str,
        dict_pattern: str,
        new_entry: str
    ) -> ModificationResult:
        """
        Append an entry to a dictionary definition.

        Args:
            content: Original file content.
            dict_pattern: Regex pattern to identify the dictionary (should match opening).
            new_entry: The new key-value entry to add (e.g., "'new_key': 'value',").

        Returns:
            ModificationResult with modified_content if successful.
        """
        try:
            # Find the dictionary opening
            regex = re.compile(dict_pattern, re.MULTILINE)
            match = regex.search(content)

            if not match:
                return ModificationResult(
                    success=False,
                    message=f"Dictionary pattern not found: {dict_pattern}"
                )

            # Find the closing brace by counting braces
            start_pos = match.end()
            brace_count = 1
            pos = start_pos

            while pos < len(content) and brace_count > 0:
                if content[pos] == '{':
                    brace_count += 1
                elif content[pos] == '}':
                    brace_count -= 1
                pos += 1

            if brace_count != 0:
                return ModificationResult(
                    success=False,
                    message="Could not find matching closing brace for dictionary"
                )

            # Insert before the closing brace
            closing_brace_pos = pos - 1

            # Find proper indentation by looking at the line before
            line_start = content.rfind('\n', 0, closing_brace_pos) + 1
            existing_indent = ''
            for char in content[line_start:closing_brace_pos]:
                if char in ' \t':
                    existing_indent += char
                else:
                    break

            # Add the new entry with proper indentation
            formatted_entry = f"\n{existing_indent}    {new_entry}"
            modified = content[:closing_brace_pos] + formatted_entry + content[closing_brace_pos:]

            return ModificationResult(
                success=True,
                message="Entry appended to dictionary",
                modified_content=modified
            )
        except Exception as e:
            return ModificationResult(
                success=False,
                message=f"Failed to append to dictionary: {e}"
            )

    def append_method_to_class(
        self,
        content: str,
        class_name: str,
        method_code: str
    ) -> ModificationResult:
        """
        Append a new method to an existing class.

        Args:
            content: Original file content.
            class_name: Name of the class to add the method to.
            method_code: The complete method definition to add.

        Returns:
            ModificationResult with modified_content if successful.
        """
        try:
            # Parse the AST to find the class
            tree = ast.parse(content)

            class_node = None
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    class_node = node
                    break

            if not class_node:
                return ModificationResult(
                    success=False,
                    message=f"Class '{class_name}' not found"
                )

            # Find the end of the class (last line of last method/attribute)
            class_end_line = class_node.end_lineno
            lines = content.split('\n')

            # Determine indentation from existing class methods
            indent = '    '  # Default 4 spaces
            for node in class_node.body:
                if isinstance(node, ast.FunctionDef):
                    method_line = lines[node.lineno - 1]
                    indent = method_line[:len(method_line) - len(method_line.lstrip())]
                    break

            # Format the method code with proper indentation
            method_lines = method_code.strip().split('\n')
            indented_method = '\n'.join(
                indent + line if line.strip() else line
                for line in method_lines
            )

            # Insert after the class
            lines.insert(class_end_line, '')
            lines.insert(class_end_line + 1, indented_method)

            modified = '\n'.join(lines)

            return ModificationResult(
                success=True,
                message=f"Method appended to class '{class_name}'",
                modified_content=modified
            )
        except SyntaxError as e:
            return ModificationResult(
                success=False,
                message=f"Syntax error in file: {e}"
            )
        except Exception as e:
            return ModificationResult(
                success=False,
                message=f"Failed to append method to class: {e}"
            )

    def apply_modification(
        self,
        file_path: str,
        modification_type: ModificationType,
        code: str,
        pattern: Optional[str] = None,
        class_name: Optional[str] = None,
        dict_pattern: Optional[str] = None
    ) -> ModificationResult:
        """
        Apply a modification to a file with full validation.

        This is the main entry point for file modifications.

        Args:
            file_path: Path to the file to modify.
            modification_type: Type of modification to apply.
            code: The code to insert/append/replace.
            pattern: Regex pattern for INSERT_AFTER modifications.
            class_name: Class name for appending methods.
            dict_pattern: Dictionary pattern for append_to_dict.

        Returns:
            ModificationResult indicating success or failure.
        """
        # Step 1: Validate target file
        validation = self.validate_target_file(file_path)
        if not validation.success:
            return validation

        # Get full path
        path = Path(file_path)
        full_path = self.base_path / file_path if not path.is_absolute() else path

        # Step 2: Create backup
        backup_result = self.backup_file(file_path)
        if not backup_result.success:
            return backup_result

        try:
            # Read current content
            content = full_path.read_text(encoding='utf-8')

            # Step 3: Apply modification based on type
            if modification_type == ModificationType.APPEND:
                modified_content = content + '\n' + code

            elif modification_type == ModificationType.INSERT_AFTER:
                if not pattern:
                    return ModificationResult(
                        success=False,
                        message="Pattern required for INSERT_AFTER modification"
                    )
                result = self.insert_code_after_pattern(content, pattern, code)
                if not result.success:
                    self.restore_from_backup(file_path)
                    return result
                modified_content = result.modified_content

            elif modification_type == ModificationType.REPLACE:
                if not pattern:
                    return ModificationResult(
                        success=False,
                        message="Pattern required for REPLACE modification"
                    )
                try:
                    modified_content = re.sub(pattern, code, content)
                except re.error as e:
                    self.restore_from_backup(file_path)
                    return ModificationResult(
                        success=False,
                        message=f"Invalid regex pattern: {e}"
                    )

            else:
                self.restore_from_backup(file_path)
                return ModificationResult(
                    success=False,
                    message=f"Unknown modification type: {modification_type}"
                )

            # Step 4: Validate Python syntax
            syntax_result = self.validate_python_syntax(modified_content)
            if not syntax_result.success:
                self.restore_from_backup(file_path)
                return ModificationResult(
                    success=False,
                    message=f"Modification would create invalid Python: {syntax_result.message}"
                )

            # Step 5: Write modified content
            full_path.write_text(modified_content, encoding='utf-8')

            return ModificationResult(
                success=True,
                message="File modified successfully",
                backup_path=backup_result.backup_path,
                modified_content=modified_content
            )

        except Exception as e:
            # Restore from backup on any error
            self.restore_from_backup(file_path)
            return ModificationResult(
                success=False,
                message=f"Modification failed: {e}"
            )
