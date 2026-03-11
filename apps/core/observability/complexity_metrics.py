"""
Complexity Drift Metrics — Automated system complexity measurement.

Project: Whole Life Journey
Path: apps/core/observability/complexity_metrics.py
Purpose: Produce a System Complexity Score (0-10) measuring architectural
         health across multiple dimensions. Used by the architecture audit
         framework and the observability dashboard.

Usage:
    from apps.core.observability.complexity_metrics import compute_complexity_score

    result = compute_complexity_score()
    print(result["score"])        # 0-10 (lower is better)
    print(result["grade"])        # A-F
    print(result["dimensions"])   # Per-dimension breakdown

Copyright:
    (c) Whole Life Journey. All rights reserved.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


# =========================================================================
# Thresholds — What "good" looks like
# =========================================================================

# File size thresholds (lines) — above these triggers concern
FILE_SIZE_THRESHOLDS = {
    "apps/ai/personal_assistant.py": 5000,
    "apps/core/ai_orchestrator/cos_context.py": 4000,
    "apps/ai/action_handlers.py": 4000,
    "apps/ai/intent_service.py": 2000,
}

# Structural targets
TARGET_ENGINE_COUNT = 60            # Max named engines
TARGET_SCHEDULED_TASKS = 50         # Max ISE scheduled tasks
TARGET_CONTEXT_BUILDERS = 20        # Max context builders in build_cos_context
TARGET_SYSTEM_PROMPT_LAYERS = 10    # Max system prompt layers


@dataclass
class DimensionResult:
    """Result for a single complexity dimension."""
    name: str
    score: float                    # 0-10 (0=excellent, 10=critical)
    weight: float                   # Contribution weight
    details: Dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def _get_base_path() -> Path:
    """Get the base project path."""
    return Path(settings.BASE_DIR)


def _count_lines(filepath: Path) -> int:
    """Count lines in a file, returning 0 if not found."""
    try:
        if filepath.exists():
            return sum(1 for _ in filepath.open("r", encoding="utf-8", errors="ignore"))
    except Exception:
        pass
    return 0


def _count_python_files(directory: Path) -> int:
    """Count .py files in a directory tree."""
    if not directory.exists():
        return 0
    return sum(1 for _ in directory.rglob("*.py"))


def _count_classes_in_file(filepath: Path) -> int:
    """Count class definitions in a Python file."""
    count = 0
    try:
        if filepath.exists():
            for line in filepath.open("r", encoding="utf-8", errors="ignore"):
                stripped = line.lstrip()
                if stripped.startswith("class ") and ":" in stripped:
                    count += 1
    except Exception:
        pass
    return count


def _count_functions_in_file(filepath: Path) -> int:
    """Count function/method definitions in a Python file."""
    count = 0
    try:
        if filepath.exists():
            for line in filepath.open("r", encoding="utf-8", errors="ignore"):
                stripped = line.lstrip()
                if stripped.startswith("def ") and ":" in stripped:
                    count += 1
    except Exception:
        pass
    return count


# =========================================================================
# Dimension Scorers
# =========================================================================

def _score_file_sizes(base: Path) -> DimensionResult:
    """
    Dimension 1: Key File Sizes.
    Measures whether critical files are within maintainable size limits.
    """
    warnings = []
    details = {}
    total_excess = 0.0

    for rel_path, threshold in FILE_SIZE_THRESHOLDS.items():
        filepath = base / rel_path
        lines = _count_lines(filepath)
        details[rel_path] = {"lines": lines, "threshold": threshold}

        if lines > threshold:
            excess_pct = (lines - threshold) / threshold
            total_excess += excess_pct
            warnings.append(
                f"{rel_path}: {lines} lines (threshold: {threshold}, "
                f"{excess_pct * 100:.0f}% over)"
            )

    # Score: 0 if all under threshold, scales up with excess
    # Each 50% over threshold adds ~2 points
    score = min(10.0, total_excess * 4.0)

    return DimensionResult(
        name="File Size Complexity",
        score=round(score, 1),
        weight=0.25,
        details=details,
        warnings=warnings,
    )


def _score_engine_count(base: Path) -> DimensionResult:
    """
    Dimension 2: Engine Proliferation.
    Measures total engine count and directory sprawl.
    """
    warnings = []
    details = {}

    # Count ai_* directories
    core_path = base / "apps" / "core"
    ai_dirs = []
    if core_path.exists():
        ai_dirs = [d for d in core_path.iterdir()
                    if d.is_dir() and d.name.startswith("ai_")]

    # Count blueprint files
    blueprint_path = core_path / "blueprint"
    blueprint_files = _count_python_files(blueprint_path)

    # Count total engine Python files
    total_engine_files = sum(_count_python_files(d) for d in ai_dirs) + blueprint_files

    # Get engine count from registry if available
    engine_count = 0
    try:
        from apps.core.engine_registry import get_engine_count
        engine_count = get_engine_count()
    except ImportError:
        # Registry not yet available — estimate from directories
        engine_count = len(ai_dirs) + 10  # rough estimate

    # Get scheduled task count
    scheduled_count = 0
    try:
        from apps.core.engine_registry import get_scheduled_engines
        scheduled_count = len(get_scheduled_engines())
    except ImportError:
        scheduled_count = 30  # rough estimate

    details = {
        "ai_directories": len(ai_dirs),
        "engine_count": engine_count,
        "total_engine_files": total_engine_files,
        "blueprint_files": blueprint_files,
        "scheduled_tasks": scheduled_count,
    }

    if engine_count > TARGET_ENGINE_COUNT:
        warnings.append(
            f"Engine count {engine_count} exceeds target {TARGET_ENGINE_COUNT}"
        )
    if scheduled_count > TARGET_SCHEDULED_TASKS:
        warnings.append(
            f"Scheduled tasks {scheduled_count} exceeds target {TARGET_SCHEDULED_TASKS}"
        )

    # Score: ratio of actual to target, scaled
    engine_ratio = max(0, (engine_count - TARGET_ENGINE_COUNT)) / TARGET_ENGINE_COUNT
    schedule_ratio = max(0, (scheduled_count - TARGET_SCHEDULED_TASKS)) / TARGET_SCHEDULED_TASKS
    score = min(10.0, (engine_ratio + schedule_ratio) * 8.0)

    return DimensionResult(
        name="Engine Proliferation",
        score=round(score, 1),
        weight=0.20,
        details=details,
        warnings=warnings,
    )


def _score_dependency_depth(base: Path) -> DimensionResult:
    """
    Dimension 3: Dependency Depth.
    Measures inter-engine imports and coupling.
    """
    warnings = []
    details = {}

    core_path = base / "apps" / "core"
    cross_imports = 0
    checked_files = 0

    if core_path.exists():
        ai_dirs = [d for d in core_path.iterdir()
                    if d.is_dir() and d.name.startswith("ai_")]

        for ai_dir in ai_dirs:
            for py_file in ai_dir.rglob("*.py"):
                if py_file.name.startswith("test"):
                    continue
                checked_files += 1
                try:
                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                    for other_dir in ai_dirs:
                        if other_dir.name == ai_dir.name:
                            continue
                        import_pattern = f"from apps.core.{other_dir.name}"
                        if import_pattern in content:
                            cross_imports += 1
                            break  # Count once per file
                except Exception:
                    pass

    details = {
        "checked_files": checked_files,
        "files_with_cross_imports": cross_imports,
        "coupling_ratio": round(cross_imports / max(checked_files, 1), 3),
    }

    if cross_imports > 20:
        warnings.append(
            f"{cross_imports} engine files import from other engine directories"
        )

    # Score: coupling ratio * 20 (so 50% coupling = score 10)
    coupling_ratio = cross_imports / max(checked_files, 1)
    score = min(10.0, coupling_ratio * 20.0)

    return DimensionResult(
        name="Inter-Engine Coupling",
        score=round(score, 1),
        weight=0.20,
        details=details,
        warnings=warnings,
    )


def _score_method_complexity(base: Path) -> DimensionResult:
    """
    Dimension 4: Method Complexity.
    Measures function count in the largest files as a proxy for complexity.
    """
    warnings = []
    details = {}

    key_files = [
        "apps/ai/personal_assistant.py",
        "apps/core/ai_orchestrator/cos_context.py",
        "apps/ai/action_handlers.py",
        "apps/ai/intent_service.py",
    ]

    total_functions = 0
    max_functions = 0

    for rel_path in key_files:
        filepath = base / rel_path
        func_count = _count_functions_in_file(filepath)
        total_functions += func_count
        max_functions = max(max_functions, func_count)
        details[rel_path] = {"functions": func_count}

        if func_count > 40:
            warnings.append(f"{rel_path}: {func_count} functions (high complexity)")

    # Score: based on average function count in key files
    avg_functions = total_functions / max(len(key_files), 1)
    # 20 functions = 0, 60 functions = 5, 100+ = 10
    score = min(10.0, max(0.0, (avg_functions - 20) / 8.0))

    return DimensionResult(
        name="Method Complexity",
        score=round(score, 1),
        weight=0.20,
        details=details,
        warnings=warnings,
    )


def _score_duplication_risk(base: Path) -> DimensionResult:
    """
    Dimension 5: Duplication Risk.
    Measures patterns that indicate copy-paste or duplicated logic.
    Checks for duplicate constant patterns across engine directories.
    """
    warnings = []
    details = {}

    core_path = base / "apps" / "core"
    threshold_defs = 0
    constant_files = 0

    if core_path.exists():
        for py_file in core_path.rglob("constants.py"):
            constant_files += 1
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                # Count lines that look like threshold definitions
                for line in content.splitlines():
                    stripped = line.strip()
                    if (stripped and not stripped.startswith("#")
                            and "=" in stripped
                            and any(kw in stripped.upper() for kw in
                                    ["THRESHOLD", "LIMIT", "MAX_", "MIN_", "TIMEOUT", "TTL"])):
                        threshold_defs += 1
            except Exception:
                pass

    details = {
        "constant_files": constant_files,
        "threshold_definitions": threshold_defs,
    }

    if threshold_defs > 50:
        warnings.append(
            f"{threshold_defs} threshold constants scattered across {constant_files} files"
        )

    # Score: based on number of scattered threshold definitions
    # Under 20 = good, 20-50 = moderate, 50+ = high
    score = min(10.0, max(0.0, (threshold_defs - 20) / 6.0))

    return DimensionResult(
        name="Configuration Scatter",
        score=round(score, 1),
        weight=0.15,
        details=details,
        warnings=warnings,
    )


# =========================================================================
# Main Scoring Function
# =========================================================================

def _score_to_grade(score: float) -> str:
    """Convert 0-10 score to letter grade (lower score = better grade)."""
    if score <= 2.0:
        return "A"
    elif score <= 4.0:
        return "B"
    elif score <= 6.0:
        return "C"
    elif score <= 8.0:
        return "D"
    else:
        return "F"


def compute_complexity_score(base_path: Optional[str] = None) -> Dict:
    """
    Compute the System Complexity Score.

    Returns a dict with:
        - score: float (0-10, lower is better)
        - grade: str (A-F)
        - dimensions: list of dimension results
        - warnings: aggregated warnings
        - details: per-dimension details

    Score interpretation:
        0-2:  A  — Excellent: complexity well-managed
        2-4:  B  — Good: manageable, some areas to simplify
        4-6:  C  — Acceptable: growing complexity, attention needed
        6-8:  D  — Concerning: significant refactoring needed
        8-10: F  — Critical: complexity impeding development
    """
    base = Path(base_path) if base_path else _get_base_path()

    dimensions = [
        _score_file_sizes(base),
        _score_engine_count(base),
        _score_dependency_depth(base),
        _score_method_complexity(base),
        _score_duplication_risk(base),
    ]

    # Weighted average
    weighted_sum = sum(d.score * d.weight for d in dimensions)
    total_weight = sum(d.weight for d in dimensions)
    overall_score = weighted_sum / total_weight if total_weight > 0 else 5.0

    # Aggregate warnings
    all_warnings = []
    for d in dimensions:
        all_warnings.extend(d.warnings)

    result = {
        "score": round(overall_score, 1),
        "grade": _score_to_grade(overall_score),
        "dimensions": [
            {
                "name": d.name,
                "score": d.score,
                "weight": d.weight,
                "grade": _score_to_grade(d.score),
                "details": d.details,
                "warnings": d.warnings,
            }
            for d in dimensions
        ],
        "warnings": all_warnings,
        "total_dimensions": len(dimensions),
    }

    logger.info(
        "System Complexity Score: %.1f/10 (Grade: %s) — %d warnings",
        result["score"], result["grade"], len(all_warnings),
    )

    return result
