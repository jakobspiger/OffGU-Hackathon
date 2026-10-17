"""Shared LangGraph state. Nodes return partial updates; no concurrent writers in v1."""

from typing import NotRequired, TypedDict

from src.models import (
    AnalysisResult,
    ClarificationQuestion,
    Evidence,
    ExtractionResult,
    FewShotExample,
    RuleFinding,
    ValidationReport,
)


class PipelineState(TypedDict):
    query: str
    extraction: NotRequired[ExtractionResult]
    questions: NotRequired[list[ClarificationQuestion]]
    rules: NotRequired[list[RuleFinding]]
    evidence: NotRequired[list[Evidence]]
    examples: NotRequired[list[FewShotExample]]
    draft: NotRequired[AnalysisResult]
    validation: NotRequired[ValidationReport]
    result: NotRequired[AnalysisResult]
    revision_count: NotRequired[int]
