"""
UAL — Universal Arbitration Layer.

Central reasoning layer that sits between multi-engine signal generation
and user-facing intervention. Collects signals from all active engines,
classifies the dominant scenario, fuses cross-domain signals, selects
ONE executive narrative, and decides intervention level.

Public API:
    run_arbitration(user) -> ArbitrationResult
"""
from apps.core.ai_arbitration.arbitration_engine import run_arbitration

__all__ = ["run_arbitration"]
