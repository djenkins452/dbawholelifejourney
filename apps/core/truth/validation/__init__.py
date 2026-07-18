# ==============================================================================
# File: apps/core/truth/validation/__init__.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Truth Validation Center — deterministic comparison engine package.
#   Given a discovery prompt, resolve the deterministic WLJ truth object it is about
#   (via the SAME truth surfaces the model calls), extract the structured values a
#   faithful answer must carry, and compare them against the Chief-of-Staff response.
#   The scoring is 100% deterministic — WLJ is always the authority. No AI grades AI.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Truth Validation comparison engine.

Public surface:
    resolve_expected_object(user, prompt)  -> ExpectedObject  (surface.py)
    compare_object(expected, response)     -> [Check]         (comparison.py)
    grade_checks(checks)                   -> ObjectGrade     (comparison.py)
    suites_for_changed_paths(paths)        -> [scope]         (recommend.py)
"""
from apps.core.truth.validation.comparison import (  # noqa: F401
    Check,
    ExpectedValue,
    ObjectGrade,
    compare_object,
    flatten_entity,
    grade_checks,
)
from apps.core.truth.validation.surface import (  # noqa: F401
    ExpectedObject,
    parse_surface,
    resolve_expected_object,
)
