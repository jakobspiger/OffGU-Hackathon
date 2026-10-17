from typing import get_args

import pytest
from pydantic import ValidationError

from src.models import ExtractedFact, ParameterName


@pytest.mark.parametrize("parameter", get_args(ParameterName))
def test_declared_parameter_survives_json_roundtrip(parameter):
    fact = ExtractedFact(parameter=parameter, value="synthetic", input_quote="synthetic")
    assert ExtractedFact.model_validate_json(fact.model_dump_json()) == fact


@pytest.mark.parametrize("parameter", ["temp", "sample_matrix", "accuracy", "", "invented"])
def test_undeclared_parameter_names_are_rejected(parameter):
    with pytest.raises(ValidationError):
        ExtractedFact(parameter=parameter, value="synthetic", input_quote="synthetic")
