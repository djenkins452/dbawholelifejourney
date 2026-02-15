"""
Human Temporal Intelligence Engine (HTIE)

Standalone module for interpreting natural human time expressions
into precise, timezone-aware timestamps.

Public API:
    interpret_human_time(user_input, user_timezone=None) -> dict
    get_current_time(timezone_str=None) -> datetime
"""

from apps.core.time.interpreter import interpret_human_time
from apps.core.time.system_clock import get_current_time

__all__ = ["interpret_human_time", "get_current_time"]
