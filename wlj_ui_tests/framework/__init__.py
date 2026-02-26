"""WLJ UI Test Framework."""

from .version import __version__
from .runner import SuiteRunner, LockError, generate_run_id
from .executor import ActionExecutor, ExecutionError
from .selectors import SelectorResolver, SelectorError, resolve_selector
from .reporting import ReportWriter
from .artifacts import ArtifactCapture
from .prompt_builder import PromptBuilder
from .schema_validator import SchemaValidator, ValidationError
from .safety import SafetyController, SafetyError, is_production
from .test_data_registry import TestDataRegistry
from .run_manifest import RunManifest
from .execution_orchestrator import ExecutionOrchestrator, OrchestratorError

__all__ = [
    "__version__",
    "SuiteRunner", "LockError", "generate_run_id",
    "ActionExecutor", "ExecutionError",
    "SelectorResolver", "SelectorError", "resolve_selector",
    "ReportWriter",
    "ArtifactCapture",
    "PromptBuilder",
    "SchemaValidator", "ValidationError",
    "SafetyController", "SafetyError", "is_production",
    "TestDataRegistry",
    "RunManifest",
    "ExecutionOrchestrator", "OrchestratorError",
]
