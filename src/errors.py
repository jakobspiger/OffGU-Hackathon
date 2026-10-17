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


class ExtractionError(AnalysisError):
    """No valid grounded extraction could be obtained."""


class SynthesisError(AnalysisError):
    """No valid grounded synthesis result could be obtained."""


class ProviderError(AnalysisError):
    """A sanitized provider failure; response bodies and credentials are omitted."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable
