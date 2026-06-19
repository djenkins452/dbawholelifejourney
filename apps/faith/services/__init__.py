"""Faith domain services package.

Re-exports the canonical faith metrics entry point so callers can keep
using ``from apps.faith.services import get_faith_metrics``. Previously a
top-level ``apps/faith/services.py`` module coexisted with this package;
the package shadowed the module on import, making ``get_faith_metrics``
unreachable and breaking every consumer. The module now lives at
``apps/faith/services/faith_metrics.py`` to remove that ambiguity.
"""

from .faith_metrics import get_faith_metrics

__all__ = ["get_faith_metrics"]
