"""
WLJ Personal Data Query System - Assistant Module.

This module provides utilities for detecting and parsing user queries
related to personal wellness data.
"""

from .intent_detector import detect_personal_data_intent

__all__ = ['detect_personal_data_intent']
