"""Contract v1.0: validated JSON boundaries, not a scientific correctness proof."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SCHEMA_VERSION = "1.0"
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SourceID = Literal["S01", "S02", "S03", "S04", "S05", "S06"]
CatalogSourceID = Literal["BRIEF", "S01", "S02", "S03", "S04", "S05", "S06", "XLSX", "DOCX"]
DecisionStatus = Literal["provisional", "insufficient_information", "out_of_scope"]
ParameterName = Literal[
    "matrix",
    "sample_composition",
    "target_substance",
    "target_quantity",
    "target_range",
    "temperature",
    "pressure",
    "flow_conditions",
    "measurement_location",
    "measurement_mode",
    "existing_equipment",
    "optical_access",
    "required_accuracy",
    "required_response_time",
    "reference_method",
    "process_constraints",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class SourceReference(ContractModel):
    source_id: SourceID
    page: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def check_page(self) -> Self:
        if self.source_id == "S06":
            if self.page is not None:
                raise ValueError("S06 is a text link, not a paginated PDF.")
        elif self.page is None:
            raise ValueError("S01-S05 require a 1-based PDF page.")
        return self


class Evidence(SourceReference):
    evidence_id: Text
    text: Text
    kind: Literal["pdf", "curated_note", "text", "table_transcription"]
    purpose: Literal["technical", "research", "business_context"]
    origin_source_id: CatalogSourceID
    review_status: Literal["unreviewed", "pending_visual_check", "reviewed"] = "unreviewed"
    review_note: Text | None = None
    score: Annotated[float, Field(allow_inf_nan=False)] | None = None

    @model_validator(mode="after")
    def check_source_scope(self) -> Self:
        if self.kind == "table_transcription":
            if (self.source_id, self.page, self.origin_source_id) != ("S01", 6, "XLSX"):
                raise ValueError("Table transcription originates in XLSX and cites S01 page 6.")
        elif self.origin_source_id != self.source_id:
            raise ValueError("Non-table evidence must originate in the cited source.")
        if self.review_status == "reviewed" and not self.review_note:
            raise ValueError("Reviewed evidence requires a documented review note.")
        if self.source_id in ("S05", "S06") and self.purpose != "business_context":
            raise ValueError("S05/S06 provide business context, not performance evidence.")
        if self.source_id in ("S03", "S04") and self.purpose != "research":
            raise ValueError("S03/S04 must retain their research scope.")
        if (self.source_id == "S06") != (self.kind == "text"):
            raise ValueError("Only S06 uses kind=text.")
        return self


class SourceCatalogEntry(ContractModel):
    """Input inventory includes documents which are not scientific evidence."""

    source_id: CatalogSourceID
    filename: Text
    present: bool
    kind: Text
    rank: Text
    pages: Text | None = None
    description: str = ""
    citation_hint: str = ""


class ReferenceRecord(ContractModel):
    """Raw task/development text kept outside the scientific evidence index."""

    record_id: Text
    source_id: Literal["BRIEF", "DOCX"]
    text: Text
    page: Annotated[int, Field(ge=1)] | None = None


class NumericValue(ContractModel):
    """Only an exact scalar with an explicit supported unit; no conversion."""

    magnitude: Annotated[float, Field(allow_inf_nan=False)]
    unit: Literal["°C", "K", "bar(a)", "bar(g)", "s", "ms"]


class ExtractedFact(ContractModel):
    parameter: ParameterName
    value: Text
    input_quote: Text
    numeric_value: NumericValue | None = None


class ParameterConflict(ContractModel):
    parameter: ParameterName
    fact_indices: Annotated[list[Annotated[int, Field(ge=0)]], Field(min_length=2)]
    reason: Text


class ExtractionResult(ContractModel):
    stated_facts: list[ExtractedFact]
    assumptions: list[Text]
    unknowns: list[Text]
    extraction_version: Literal["1.1"] = "1.1"
    conflicts: list[ParameterConflict] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_conflict_references(self) -> Self:
        for conflict in self.conflicts:
            if len(set(conflict.fact_indices)) != len(conflict.fact_indices):
                raise ValueError("Conflict references must be distinct.")
            for index in conflict.fact_indices:
                if index >= len(self.stated_facts):
                    raise ValueError("Conflict refers to a missing fact.")
                if self.stated_facts[index].parameter != conflict.parameter:
                    raise ValueError("Conflict parameter does not match its facts.")
        return self

    def verify_quotes(self, query: str) -> None:
        """B2 calls this against the original request before handing data to B3."""
        if any(fact.input_quote not in query for fact in self.stated_facts):
            raise ValueError("An extracted fact quotes text absent from the original request.")


class ClarificationQuestion(ContractModel):
    question: Text
    why_it_matters: Text
    priority: Annotated[int, Field(ge=1)]
    blocking: bool


class RuleFinding(ContractModel):
    rule_id: Text
    outcome: Literal["excluded", "conditional", "unknown"]
    reason: Text
    source_refs: Annotated[list[SourceReference], Field(min_length=1)]


class ValidationFinding(ContractModel):
    code: Text
    severity: Literal["error", "warning", "not_checked"]
    message: Text
    field_path: Text
    evidence_ids: list[Text] = Field(default_factory=list)


class ValidationReport(ContractModel):
    findings: list[ValidationFinding]

    @property
    def has_errors(self) -> bool:
        return any(item.severity == "error" for item in self.findings)


class SpectralRange(ContractModel):
    lower: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    upper: Annotated[float, Field(gt=0, allow_inf_nan=False)]
    unit: Literal["nm", "cm^-1"]
    quantity: Literal["wavelength", "wavenumber", "raman_shift"]
    scope: Literal["nominal_method_only", "verified_instrument"]
    compatibility_note: Text

    @model_validator(mode="after")
    def check_units(self) -> Self:
        if self.lower >= self.upper:
            raise ValueError("Spectral endpoints must be in ascending order.")
        if (self.quantity == "wavelength") != (self.unit == "nm"):
            raise ValueError("Wavelength uses nm; wavenumber and Raman shift use cm^-1.")
        return self


class Recommendation(ContractModel):
    method: Text
    role: Literal["primary_candidate", "alternative", "complementary"]
    why: Text
    conditions: Annotated[list[Text], Field(min_length=1)]
    measurement_geometry: Text
    spectral_range: SpectralRange | None
    source_refs: Annotated[list[SourceReference], Field(min_length=1)]
    evidence_ids: Annotated[list[Text], Field(min_length=1)]


class FeasibilityStep(ContractModel):
    step: Annotated[int, Field(ge=1)]
    action: Text
    evidence_needed: Text


class AnalysisResult(ContractModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    decision_status: DecisionStatus
    stated_facts: list[Text]
    assumptions: list[Text]
    unknowns: list[Text]
    clarification_questions: list[ClarificationQuestion]
    recommendations: list[Recommendation]
    measurement_concept: Text
    risks_and_limits: list[Text]
    feasibility_plan: list[FeasibilityStep]
    go_no_go_criteria: list[Text]
    overall_sources: list[SourceReference]
    validation_findings: list[ValidationFinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_recommendation_sources(self) -> Self:
        listed = {(ref.source_id, ref.page) for ref in self.overall_sources}
        for recommendation in self.recommendations:
            if any((ref.source_id, ref.page) not in listed for ref in recommendation.source_refs):
                raise ValueError("Recommendation sources must also appear in overall_sources.")
        return self


class FewShotExample(ContractModel):
    example_id: Annotated[str, StringConstraints(pattern=r"^D0[1-8]$")]
    query: Text
    reference_answer: Text | None
    provenance: Text
