"""
Unified AI Orchestrator (UAIO)

Central brain for the AI Assistant. Coordinates:
- Intent understanding
- Context resolution (SLCME)
- Time resolution (HTIE)
- Safety validation
- Action execution
- Post-action learning
- Audit logging

Public API:
    process_user_input(user, user_input, page_context=None) -> OrchestratorResult
"""

from apps.core.ai_orchestrator.orchestrator import process_user_input

__all__ = ["process_user_input"]
