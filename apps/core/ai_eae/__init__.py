"""
EAE — Executive Arbitration Engine.

Kernel layer that deterministically decides what intelligence is surfaced,
when, where, and how — across chat, push delivery, executive briefings,
and the Command Center.

Core principle: Compute everything. Surface very little.

Public API:
    arbitrate(user, channel, recent_deliveries) -> EAEResult
"""


def __getattr__(name):
    """Lazy import to avoid AppRegistryNotReady during app loading."""
    if name in ("arbitrate", "EAEResult"):
        from apps.core.ai_eae.eae_engine import EAEResult, arbitrate
        return {"arbitrate": arbitrate, "EAEResult": EAEResult}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["arbitrate", "EAEResult"]
