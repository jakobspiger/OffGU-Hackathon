"""Public entry point. The real orchestration is implemented in T11."""

from src.errors import ComponentNotReadyError
from src.models import AnalysisResult


def analyze(query: str) -> AnalysisResult:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")
    raise ComponentNotReadyError("Analysis pipeline is not implemented yet (T06-T11).")
