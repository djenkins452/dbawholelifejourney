"""
ENGINE_REGISTRY — Observability engine metadata (delegates to canonical registry).

Provides operational metadata for engine execution, manual triggers, and
observability tooling. Reads from the canonical engine registry at
apps/core/engine_registry.py and presents the same interface as before.

Used by:
  - TriggerEngineView (manual execution)
  - run_engine_task (Celery dispatch)
  - _action_rerun_engine (ops actions)
  - SAME auto-remediation

Project: Whole Life Journey
Path: apps/core/ai_observability/engine_registry.py
"""

import importlib
import logging

logger = logging.getLogger(__name__)

# Phase label mapping for backward compatibility
_PHASE_LABELS = {1: "Interpret", 2: "Execute", 3: "Post-Exec"}

# Execution mode mapping
_EXEC_MODE_MAP = {
    "synthetic": "synthetic",
    "batch": "batch",
    "on_demand": "on_demand",
}


def _build_compat_registry():
    """
    Build backward-compatible dict registry from the canonical EngineDefinition registry.

    Only includes engines that have can_manual_run=True or batch_runner set,
    matching the original scope of this module (operational execution metadata).
    """
    try:
        from apps.core.engine_registry import ENGINE_REGISTRY as CANONICAL
    except ImportError:
        logger.warning("Cannot import canonical engine registry — using empty registry")
        return {}

    registry = {}
    for code, engine in CANONICAL.items():
        # Only include engines with operational metadata (batch_runner or manual run)
        if not engine.can_manual_run and not engine.batch_runner:
            continue

        registry[code] = {
            "label": engine.name,
            "phase": int(engine.phase),
            "category": _PHASE_LABELS.get(int(engine.phase), "Post-Exec"),
            "can_manual_run": engine.can_manual_run,
            "batch_runner": engine.batch_runner,
            "per_user_func": engine.per_user_func,
            "needs_user_context": engine.per_user_func is not None,
            "execution_mode": _EXEC_MODE_MAP.get(engine.execution_mode, "on_demand"),
        }

    return registry


# Lazily built on first access
_cached_registry = None


def _get_registry():
    """Get or build the compatibility registry (cached)."""
    global _cached_registry
    if _cached_registry is None:
        _cached_registry = _build_compat_registry()
    return _cached_registry


# Backward-compatible module-level attribute
# Consumers that import ENGINE_REGISTRY directly will get the dict
class _LazyRegistryProxy(dict):
    """Lazy dict that builds from canonical registry on first access."""

    _initialized = False

    def _ensure_init(self):
        if not self._initialized:
            self._initialized = True
            self.update(_get_registry())

    def __getitem__(self, key):
        self._ensure_init()
        return super().__getitem__(key)

    def __contains__(self, key):
        self._ensure_init()
        return super().__contains__(key)

    def __iter__(self):
        self._ensure_init()
        return super().__iter__()

    def __len__(self):
        self._ensure_init()
        return super().__len__()

    def get(self, key, default=None):
        self._ensure_init()
        return super().get(key, default)

    def items(self):
        self._ensure_init()
        return super().items()

    def keys(self):
        self._ensure_init()
        return super().keys()

    def values(self):
        self._ensure_init()
        return super().values()


ENGINE_REGISTRY = _LazyRegistryProxy()


def get_engine_meta(engine_name):
    """Return metadata dict for a single engine, or None."""
    return _get_registry().get(engine_name)


def get_manual_engines():
    """Return list of engine codes that support manual execution."""
    return [name for name, meta in _get_registry().items() if meta["can_manual_run"]]


def resolve_batch_runner(engine_name):
    """
    Import and return the batch runner callable for an engine.

    Returns None if engine has no batch_runner configured.
    """
    meta = _get_registry().get(engine_name)
    if not meta or not meta.get("batch_runner"):
        return None

    dotted_path = meta["batch_runner"]
    module_path, func_name = dotted_path.rsplit(".", 1)

    try:
        module = importlib.import_module(module_path)
        return getattr(module, func_name)
    except (ImportError, AttributeError) as e:
        logger.error("Failed to resolve batch runner for %s: %s", engine_name, e)
        return None
