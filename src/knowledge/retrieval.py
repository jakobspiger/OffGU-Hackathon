"""Public retrieval entry point. Kevin implements the real adapter in T04."""

from src.errors import ComponentNotReadyError
from src.models import Evidence


def retrieve(query: str, k: int = 8) -> list[Evidence]:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string.")
    if type(k) is not int or not 1 <= k <= 50:
        raise ValueError("k must be an integer between 1 and 50.")
    raise ComponentNotReadyError("Knowledge retrieval is not implemented yet (T02-T04).")
