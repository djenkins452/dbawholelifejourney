"""
Guard test: Fail the build if hardcoded OpenAI model strings appear in service code.

Model names must only exist in:
  - config/settings.py          (single source of truth)
  - apps/owner_finance/         (pricing / billing data)
  - **/tests/**  or test_*.py   (test fixtures and assertions)
  - **/management/commands/**   (seed data / fixtures)
  - **/fixtures/**              (JSON fixture data)
  - backups/                    (archived code)

Everything else must use settings.OPENAI_MODEL, settings.OPENAI_VISION_MODEL,
or settings.COS_MODEL.
"""
import os
import re
import unittest

# Patterns that indicate a hardcoded model string in Python source
MODEL_PATTERN = re.compile(r"""['"]gpt-[^'"]+['"]""")

# Root of the project
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))

# Directories / path fragments that are allowed to contain model strings
ALLOWED_PATHS = (
    os.path.join('config', 'settings.py'),
    os.path.join('apps', 'owner_finance'),
    os.sep + 'tests' + os.sep,
    os.path.join('management', 'commands'),
    os.sep + 'fixtures' + os.sep,
    os.sep + 'backups' + os.sep,
    os.sep + 'migrations' + os.sep,
)


def _is_allowed(filepath: str) -> bool:
    """Check whether a file is in an allowed location."""
    rel = os.path.relpath(filepath, PROJECT_ROOT)
    # Check path fragments
    if any(fragment in rel for fragment in ALLOWED_PATHS):
        return True
    # Check filename: test_*.py or tests_*.py
    basename = os.path.basename(filepath)
    if basename.startswith('test_') or basename.startswith('tests_'):
        return True
    return False


def _model_string_only_in_comment(line: str) -> bool:
    """Return True if all model strings on this line are inside a # comment."""
    stripped = line.lstrip()
    # Entire line is a comment
    if stripped.startswith('#'):
        return True
    # Check if there's an inline comment and the model string is only in it
    comment_idx = _find_inline_comment(line)
    if comment_idx == -1:
        return False
    code_part = line[:comment_idx]
    return not MODEL_PATTERN.search(code_part)


def _find_inline_comment(line: str) -> int:
    """Find the index of an inline # comment, respecting strings."""
    in_single = False
    in_double = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '\\' and (in_single or in_double):
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == '#' and not in_single and not in_double:
            return i
        i += 1
    return -1


class TestNoHardcodedModels(unittest.TestCase):
    """Ensure no hardcoded 'gpt-*' model strings leak into service code."""

    def test_no_hardcoded_model_strings_in_service_code(self):
        violations = []

        for dirpath, _dirnames, filenames in os.walk(PROJECT_ROOT):
            # Skip hidden dirs, venv, node_modules, backups
            if any(skip in dirpath for skip in ('.git', '__pycache__', 'node_modules',
                                                 '.venv', 'venv', 'backups', '.claude')):
                continue

            for filename in filenames:
                if not filename.endswith('.py'):
                    continue

                filepath = os.path.join(dirpath, filename)
                if _is_allowed(filepath):
                    continue

                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        for lineno, line in enumerate(f, 1):
                            if _model_string_only_in_comment(line):
                                continue
                            if MODEL_PATTERN.search(line):
                                rel = os.path.relpath(filepath, PROJECT_ROOT)
                                violations.append(f"  {rel}:{lineno}: {line.strip()}")
                except (OSError, UnicodeDecodeError):
                    continue

        if violations:
            msg = (
                f"\n\nFound {len(violations)} hardcoded model string(s) in service code.\n"
                "Model names must only exist in config/settings.py. "
                "Use settings.OPENAI_MODEL or settings.OPENAI_VISION_MODEL instead.\n\n"
                + "\n".join(violations)
            )
            self.fail(msg)
