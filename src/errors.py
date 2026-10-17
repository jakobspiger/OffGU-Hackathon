"""Stable errors for UI, CLI and later production adapters."""


class AFSError(Exception):
    """Base for expected application errors."""


class ConfigurationError(AFSError):
    """Required runtime configuration is missing or invalid."""


class ComponentNotReadyError(AFSError):
    """A planned component has not been implemented yet."""


class RetrievalError(AFSError):
    """Knowledge index is unavailable or retrieval failed."""


class AnalysisError(AFSError):
    """Provider or pipeline failed; not a scientific decision status."""
