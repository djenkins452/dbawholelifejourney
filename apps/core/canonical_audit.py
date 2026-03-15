"""
Canonical Query Audit Engine (Ops Wall 2.0 — Phase 7).

Detects direct ORM queries that bypass canonical domain services.
Used by the `audit_canonical_queries` management command and cached
for Ops Wall display.

Project: Whole Life Journey
Path: apps/core/canonical_audit.py
"""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# =========================================================================
# Violation & Result Data Structures
# =========================================================================

@dataclass
class Violation:
    """A single canonical query violation."""

    file: str
    line: int
    model: str
    query: str
    domain: str
    suggested_service: str


@dataclass
class AuditResult:
    """Result of a full canonical query audit."""

    violations: List[Violation] = field(default_factory=list)
    files_scanned: int = 0
    models_audited: int = 0

    @property
    def compliance_score(self) -> float:
        """Return compliance as a percentage (100 = no violations)."""
        if self.files_scanned == 0:
            return 100.0
        # Score based on violation density: penalize per violation
        # 100% = 0 violations, each violation reduces score
        if not self.violations:
            return 100.0
        # Simple: 100 - (violations / files_scanned * 100), floor at 0
        raw = 100.0 - (len(self.violations) / max(self.files_scanned, 1) * 100)
        return round(max(0.0, raw), 1)


# =========================================================================
# Global Exclusions — directories skipped entirely
# =========================================================================

EXCLUDED_PATHS = [
    "migrations/",
    "tests/",
    "test_",
    "conftest",
    "__pycache__/",
    "venv/",
    ".venv/",
    "node_modules/",
    ".claude/",
    ".git/",
    "docs/",
    "staticfiles/",
    "static/",
]


# =========================================================================
# Canonical Rules — models protected by service discipline
# =========================================================================

CANONICAL_RULES: Dict[str, dict] = {
    "Task": {
        "domain": "life",
        "canonical_service": "apps.life.services.task_queries.TaskQueries",
        "allowed_paths": [
            "apps/life/services/",
            "apps/life/models.py",
            "apps/life/admin.py",
            "apps/life/views.py",
            "apps/life/api/",
            "apps/core/ai_orchestrator/",
            "apps/core/ai_state/",
            "apps/core/ai_observability/",
            "apps/core/ai_scheduler/",
            "apps/ai/",
            "apps/admin_console/",
        ],
        "suggested_usage": "TaskQueries.pending(user), TaskQueries.overdue(user)",
    },
    "Insight": {
        "domain": "intelligence",
        "canonical_service": "apps.core.ai_insights.services",
        "allowed_paths": [
            "apps/core/ai_insights/",
            "apps/core/ai_orchestrator/",
            "apps/core/ai_observability/",
            "apps/core/ai_state/",
            "apps/ai/",
            "apps/admin_console/",
        ],
        "suggested_usage": "ai_insights.services.get_module_insight(user, module)",
    },
    "Prediction": {
        "domain": "intelligence",
        "canonical_service": "apps.core.ai_predictions",
        "allowed_paths": [
            "apps/core/ai_predictions/",
            "apps/core/ai_orchestrator/",
            "apps/core/ai_observability/",
            "apps/core/ai_state/",
            "apps/ai/",
            "apps/admin_console/",
        ],
        "suggested_usage": "ai_predictions.prediction_engine",
    },
    "GuidanceItem": {
        "domain": "guidance",
        "canonical_service": "apps.core.ai_guidance",
        "allowed_paths": [
            "apps/core/ai_guidance/",
            "apps/core/ai_orchestrator/",
            "apps/core/ai_observability/",
            "apps/core/ai_state/",
            "apps/ai/",
            "apps/admin_console/",
        ],
        "suggested_usage": "ai_guidance.guidance_engine",
    },
    "UserState": {
        "domain": "state",
        "canonical_service": "apps.core.ai_state.state_builder",
        "allowed_paths": [
            "apps/core/ai_state/",
            "apps/core/ai_orchestrator/",
            "apps/core/ai_observability/",
            "apps/ai/",
            "apps/admin_console/",
        ],
        "suggested_usage": "state_builder.get_or_build_state(user)",
    },
}


# =========================================================================
# Scan Functions
# =========================================================================

# Pattern: ModelName.objects.filter/get/exclude/all/create/update/...
_ORM_PATTERN_CACHE: Dict[str, re.Pattern] = {}


def _get_orm_pattern(model_name: str) -> re.Pattern:
    """Build and cache regex for detecting Model.objects.* calls."""
    if model_name not in _ORM_PATTERN_CACHE:
        _ORM_PATTERN_CACHE[model_name] = re.compile(
            rf"\b{re.escape(model_name)}\.objects\."
        )
    return _ORM_PATTERN_CACHE[model_name]


def _is_excluded_path(filepath: str) -> bool:
    """Check if a file path matches any global exclusion."""
    for excl in EXCLUDED_PATHS:
        if excl in filepath:
            return True
    return False


def _is_allowed_path(filepath: str, allowed_paths: List[str]) -> bool:
    """Check if a file is in the allowed paths for a rule."""
    for allowed in allowed_paths:
        if allowed in filepath:
            return True
    return False


def _is_comment_or_string(line: str, match_start: int) -> bool:
    """Heuristic: check if the match is in a comment or docstring."""
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return True
    # Check if match is inside a triple-quoted string (rough heuristic)
    prefix = line[:match_start]
    if prefix.count('"""') % 2 == 1 or prefix.count("'''") % 2 == 1:
        return True
    return False


def scan_file(
    filepath: str,
    rules: Optional[Dict[str, dict]] = None,
    base_dir: Optional[str] = None,
) -> List[Violation]:
    """
    Scan a single Python file for canonical query violations.

    Args:
        filepath: Path to the Python file (relative to project root or base_dir).
        rules: Canonical rules dict. Defaults to CANONICAL_RULES.
        base_dir: If provided, resolve filepath relative to this directory for reading.

    Returns:
        List of Violation objects found in this file.
    """
    if rules is None:
        rules = CANONICAL_RULES

    # Skip globally excluded paths
    if _is_excluded_path(filepath):
        return []

    violations = []

    # Resolve the actual file path for reading
    actual_path = os.path.join(base_dir, filepath) if base_dir else filepath

    try:
        with open(actual_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except (OSError, IOError):
        return []

    for model_name, rule in rules.items():
        # Skip if this file is in the allowed paths for this model
        if _is_allowed_path(filepath, rule.get("allowed_paths", [])):
            continue

        pattern = _get_orm_pattern(model_name)

        for line_num, line in enumerate(lines, start=1):
            match = pattern.search(line)
            if match and not _is_comment_or_string(line, match.start()):
                violations.append(
                    Violation(
                        file=filepath,
                        line=line_num,
                        model=model_name,
                        query=line.strip()[:120],
                        domain=rule["domain"],
                        suggested_service=rule.get("suggested_usage", rule["canonical_service"]),
                    )
                )

    return violations


def run_audit(
    base_dir: str,
    rules: Optional[Dict[str, dict]] = None,
) -> AuditResult:
    """
    Walk all Python files under base_dir and audit for canonical query violations.

    Args:
        base_dir: Root directory to scan (typically the project root).
        rules: Canonical rules dict. Defaults to CANONICAL_RULES.

    Returns:
        AuditResult with violations, files scanned, and compliance score.
    """
    if rules is None:
        rules = CANONICAL_RULES

    result = AuditResult(models_audited=len(rules))
    files_scanned = 0

    for dirpath, dirnames, filenames in os.walk(base_dir):
        # Early directory exclusion for speed
        rel_dir = os.path.relpath(dirpath, base_dir)
        dirnames[:] = [
            d for d in dirnames
            if not any(excl.rstrip("/") == d for excl in EXCLUDED_PATHS)
            and not d.startswith(".")
        ]

        for filename in filenames:
            if not filename.endswith(".py"):
                continue

            filepath = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(filepath, base_dir)

            # Skip globally excluded files
            if _is_excluded_path(rel_path):
                continue

            files_scanned += 1
            violations = scan_file(rel_path, rules, base_dir=base_dir)
            result.violations.extend(violations)

    result.files_scanned = files_scanned
    return result
