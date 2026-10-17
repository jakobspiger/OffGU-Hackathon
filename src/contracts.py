"""Callable contracts; adapters stay in their owners' implementation modules."""

from typing import Protocol

from src.models import (
    AnalysisResult,
    Evidence,
    ExtractionResult,
    FewShotExample,
    RuleFinding,
    ValidationReport,
)


class Analyzer(Protocol):
    def __call__(self, query: str) -> AnalysisResult: ...


class Retriever(Protocol):
    def __call__(self, query: str, k: int = 8) -> list[Evidence]: ...


class RuleEvaluator(Protocol):
    def __call__(self, extraction: ExtractionResult) -> list[RuleFinding]: ...


class ExampleSelector(Protocol):
    def __call__(self, query: str, k: int = 2) -> list[FewShotExample]: ...


class ResultValidator(Protocol):
    def __call__(
        self, result: AnalysisResult, evidence: list[Evidence], rules: list[RuleFinding]
    ) -> ValidationReport: ...
