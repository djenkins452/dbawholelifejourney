"""
WLJ Personal Data Query System - Assistant Module.

This module provides utilities for detecting and parsing user queries
related to personal wellness data.
"""

from .intent_detector import detect_personal_data_intent
from .date_parser import extract_date_from_message
from .data_service import PersonalDataService, invalidate_user_data_cache
from .views import process_assistant_message, handle_data_visibility_confirmation
from .context_builder import build_personal_context
from .gap_detector import (
    GapType,
    GapSeverity,
    detect_knowledge_gap,
    extract_potential_keywords,
    categorize_gap_severity,
)
from .task_generator import (
    ImprovementTask,
    generate_improvement_task,
    generate_code_template,
    generate_test_template,
)

__all__ = [
    'detect_personal_data_intent',
    'extract_date_from_message',
    'PersonalDataService',
    'invalidate_user_data_cache',
    'process_assistant_message',
    'handle_data_visibility_confirmation',
    'build_personal_context',
    'GapType',
    'GapSeverity',
    'detect_knowledge_gap',
    'extract_potential_keywords',
    'categorize_gap_severity',
    'ImprovementTask',
    'generate_improvement_task',
    'generate_code_template',
    'generate_test_template',
]
