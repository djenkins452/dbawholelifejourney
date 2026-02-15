"""
ISE — Intelligence Scheduler Engine.

Centrally manages scheduled execution of all intelligence engines.
ISE does NOT generate intelligence — it orchestrates when engines run.
"""

from apps.core.ai_scheduler.scheduler_engine import run_scheduler_cycle

__all__ = ["run_scheduler_cycle"]
