# ------------------------------------------------------------------
# AICarmine Broker Error Handling Framework
# ------------------------------------------------------------------
# This module provides comprehensive error handling for the broker,
# including runtime error management, regression detection, and
# user-friendly error display.
# ------------------------------------------------------------------

from .core import (
    BrokerError,
    PlannerError,
    OllamaError,
    RerankerError,
    DatabaseError,
    ValidationError,
    ConfigurationError,
    RuntimeError,
    RegressionError,
    ErrorRegistry,
    ErrorCategory,
    ErrorSeverity,
    ErrorReport,
    ErrorSummary,
)

from .runtime import (
    RuntimeErrorTracker,
    ErrorMiddleware,
    ErrorContext,
    ErrorContextManager,
)

from .display import (
    ErrorDisplayFormatter,
    UserFriendlyErrorDisplay,
    TerminalErrorDisplay,
    JSONErrorDisplay,
)

from .preplanner import (
    PreplannerError,
    PreplannerNotFoundError,
    PreplannerStateManager,
    PreplannerHealthCheck,
)

from .validator import (
    ValidatorError,
    ValidatorNotFoundError,
    ValidatorStateManager,
    ValidatorHealthCheck,
)

from .planner import (
    PlannerNotFoundError,
    PlannerStateManager,
    PlannerHealthCheck,
)

from .evidence import (
    EvidenceError,
    EvidenceNotFoundError,
    EvidenceStateManager,
    EvidenceHealthCheck,
)

from .tools import (
    ToolsError,
    ToolsNotFoundError,
    ToolsStateManager,
    ToolsHealthCheck,
)

from .ollama import (
    OllamaConnectionError,
    OllamaModelNotFoundError,
    OllamaStateManager,
    OllamaHealthCheck,
)

from .reranker import (
    RerankerNotFoundError,
    RerankerStateManager,
    RerankerHealthCheck,
)

from .database import (
    DatabaseNotFoundError,
    DatabaseStateManager,
    DatabaseHealthCheck,
)

from .integration import (
    ErrorIntegrationMiddleware,
    ErrorIntegrationManager,
    safe_execute,
    safe_read_file,
    safe_json_loads,
    safe_sqlite_query,
    safe_sqlite_insert,
)

from .migrate import (
    ErrorHandlingMigrator,
    migrate_bare_except,
    migrate_sqlite_except,
    migrate_json_except,
)

from .apply import (
    ErrorHandlingApplier,
    apply_to_file,
    apply_to_directory,
)

from .logging import (
    ErrorLogger,
    SilentErrorGuard,
    ensure_error_not_silent,
    get_global_logger,
    log_critical_error,
)

__all__ = [
    # Core
    "BrokerError",
    "PlannerError",
    "OllamaError",
    "RerankerError",
    "DatabaseError",
    "ValidationError",
    "ConfigurationError",
    "RuntimeError",
    "RegressionError",
    "ErrorRegistry",
    "ErrorCategory",
    "ErrorSeverity",
    "ErrorReport",
    "ErrorSummary",
    # Runtime
    "RuntimeErrorTracker",
    "ErrorMiddleware",
    "ErrorContext",
    "ErrorContextManager",
    # Display
    "ErrorDisplayFormatter",
    "UserFriendlyErrorDisplay",
    "TerminalErrorDisplay",
    "JSONErrorDisplay",
    # Preplanner
    "PreplannerError",
    "PreplannerNotFoundError",
    "PreplannerStateManager",
    "PreplannerHealthCheck",
    # Validator
    "ValidatorError",
    "ValidatorNotFoundError",
    "ValidatorStateManager",
    "ValidatorHealthCheck",
    # Planner
    "PlannerNotFoundError",
    "PlannerStateManager",
    "PlannerHealthCheck",
    # Evidence
    "EvidenceError",
    "EvidenceNotFoundError",
    "EvidenceStateManager",
    "EvidenceHealthCheck",
    # Tools
    "ToolsError",
    "ToolsNotFoundError",
    "ToolsStateManager",
    "ToolsHealthCheck",
    # Ollama
    "OllamaConnectionError",
    "OllamaModelNotFoundError",
    "OllamaStateManager",
    "OllamaHealthCheck",
    # Reranker
    "RerankerNotFoundError",
    "RerankerStateManager",
    "RerankerHealthCheck",
    # Database
    "DatabaseNotFoundError",
    "DatabaseStateManager",
    "DatabaseHealthCheck",
    # Integration
    "ErrorIntegrationMiddleware",
    "ErrorIntegrationManager",
    "safe_execute",
    "safe_read_file",
    "safe_json_loads",
    "safe_sqlite_query",
    "safe_sqlite_insert",
    # Migration
    "ErrorHandlingMigrator",
    "migrate_bare_except",
    "migrate_sqlite_except",
    "migrate_json_except",
    # Apply
    "ErrorHandlingApplier",
    "apply_to_file",
    "apply_to_directory",
    # Logging - ENSURE ERRORS ARE NEVER SILENTLY SWALLOWED
    "ErrorLogger",
    "SilentErrorGuard",
    "ensure_error_not_silent",
    "get_global_logger",
    "log_critical_error",
]
