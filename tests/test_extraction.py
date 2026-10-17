import json

import pytest

from src.config import Settings
from src.engine.extraction import extract, scalar_value
from src.errors import ConfigurationError, ExtractionError, ProviderError


class FakeProvider:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def complete(self, system, query):
        self.calls.append((system, query))
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def draft(*facts, conflicts=None):
    return json.dumps(
        {
            "stated_facts": [
                {"parameter": parameter, "value": value, "input_quote": quote}
                for parameter, value, quote in facts
            ],
            "conflicts": conflicts or [],
        }
    )


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setattr("src.engine.extraction.time.sleep", lambda _: None)
    return Settings(_env_file=None, afs_max_retries=0)


def test_new_query_extracts_supported_facts_without_inventing_missing_numbers(settings):
    query = "Pulver nach dem Trockner; Temperatur 80 °C; Feuchtigkeit messen."
    provider = FakeProvider(
        draft(
            ("matrix", "Pulver", "Pulver"),
            ("measurement_location", "nach dem Trockner", "nach dem Trockner"),
            ("temperature", "80 °C", "80 °C"),
            ("target_quantity", "Feuchtigkeit", "Feuchtigkeit"),
        )
    )
    result = extract(query, provider=provider, settings=settings)
    assert result.assumptions == []
    assert "required_accuracy" in result.unknowns
    assert "target_range" in result.unknowns
    assert result.stated_facts[2].numeric_value.magnitude == 80.0
    assert result.stated_facts[2].numeric_value.unit == "°C"
    assert provider.calls[0][1] == query


@pytest.mark.parametrize(
    "fact",
    [
        ("temperature", "90 °C", "90 °C"),
        ("temperature", "80 °C", "Temperatur unbekannt"),
        ("matrix", "Pulver", "kein Pulver"),
    ],
)
def test_ungrounded_or_rewritten_values_are_rejected(settings, fact):
    with pytest.raises(ExtractionError):
        extract(
            "kein Pulver; Temperatur unbekannt",
            provider=FakeProvider(draft(fact)),
            settings=settings,
        )


def test_negation_and_uncertainty_remain_verbatim(settings):
    query = "Kein Raman vorhanden. Vermutlich 80 °C."
    result = extract(
        query,
        provider=FakeProvider(
            draft(
                ("existing_equipment", "Kein Raman vorhanden", "Kein Raman vorhanden"),
                ("temperature", "Vermutlich 80 °C", "Vermutlich 80 °C"),
            )
        ),
        settings=settings,
    )
    assert result.stated_facts[0].value == "Kein Raman vorhanden"
    assert result.stated_facts[1].numeric_value is None


def test_distinct_process_states_are_preserved_and_block_single_value_rules(settings):
    query = "Vorher 20 °C, nachher 80 °C."
    result = extract(
        query,
        provider=FakeProvider(
            draft(
                ("temperature", "Vorher 20 °C", "Vorher 20 °C"),
                ("temperature", "nachher 80 °C", "nachher 80 °C"),
            )
        ),
        settings=settings,
    )
    assert len(result.stated_facts) == 2
    assert result.conflicts[0].fact_indices == [0, 1]
    assert "temperature" in result.unknowns


@pytest.mark.parametrize("indices", [[0, 4], [0, 0]])
def test_invalid_conflict_links_are_rejected(settings, indices):
    payload = draft(
        ("temperature", "20 °C", "20 °C"),
        ("temperature", "80 °C", "80 °C"),
        conflicts=[{"parameter": "temperature", "fact_indices": indices, "reason": "Conflict"}],
    )
    with pytest.raises(ExtractionError):
        extract("20 °C oder 80 °C", provider=FakeProvider(payload), settings=settings)


def test_explicit_conflict_is_kept(settings):
    payload = draft(
        ("temperature", "20 °C", "20 °C"),
        ("temperature", "80 °C", "80 °C"),
        conflicts=[{"parameter": "temperature", "fact_indices": [0, 1], "reason": "Unclear"}],
    )
    result = extract("20 °C oder 80 °C", provider=FakeProvider(payload), settings=settings)
    assert len(result.conflicts) == 1
    assert result.conflicts[0].reason == "Unclear"


def test_duplicate_identical_facts_are_not_conflicts(settings):
    result = extract(
        "Pulver",
        provider=FakeProvider(
            draft(
                ("matrix", "Pulver", "Pulver"),
                ("matrix", "Pulver", "Pulver"),
            )
        ),
        settings=settings,
    )
    assert not result.conflicts


@pytest.mark.parametrize("query", ["", "  ", None, "x" * 20001])
def test_bad_input_never_calls_provider(settings, query):
    provider = FakeProvider()
    with pytest.raises(ValueError):
        extract(query, provider=provider, settings=settings)
    assert not provider.calls


def test_irrelevant_text_marks_parameters_unknown(settings):
    result = extract("Hallo!", provider=FakeProvider(draft()), settings=settings)
    assert not result.stated_facts
    assert len(result.unknowns) == 16


def test_invalid_json_is_retried_once_and_corrected(settings):
    settings.afs_max_retries = 1
    provider = FakeProvider("not json", draft(("matrix", "Pulver", "Pulver")))
    assert extract("Pulver", provider=provider, settings=settings).stated_facts
    assert len(provider.calls) == 2


def test_retry_budget_shared_by_transport_and_validation_failures(settings):
    settings.afs_max_retries = 1
    provider = FakeProvider(ProviderError("temporary", retryable=True), "invalid")
    with pytest.raises(ExtractionError):
        extract("Pulver", provider=provider, settings=settings)
    assert len(provider.calls) == 2


def test_auth_error_not_retried(settings):
    settings.afs_max_retries = 2
    provider = FakeProvider(ProviderError("HTTP 401"))
    with pytest.raises(ProviderError):
        extract("Pulver", provider=provider, settings=settings)
    assert len(provider.calls) == 1


def test_missing_credentials_prevent_live_call(monkeypatch):
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigurationError):
        extract("Pulver", settings=Settings(_env_file=None))


@pytest.mark.parametrize(
    "parameter,value,unit,magnitude",
    [
        ("temperature", "80 °C", "°C", 80.0),
        ("temperature", "-20 °C", "°C", -20.0),
        ("temperature", "300 K", "K", 300.0),
        ("pressure", "2.5 bar(a)", "bar(a)", 2.5),
        ("pressure", "-0.5 bar(g)", "bar(g)", -0.5),
        ("required_response_time", "100 ms", "ms", 100.0),
    ],
)
def test_supported_scalars_keep_units(parameter, value, unit, magnitude):
    result = scalar_value(parameter, value)
    assert result.unit == unit
    assert result.magnitude == magnitude


@pytest.mark.parametrize(
    "parameter,value",
    [
        ("temperature", "80"),
        ("temperature", "ca. 80 °C"),
        ("temperature", "20–80 °C"),
        ("temperature", "nicht 80 °C"),
        ("temperature", "1,000 °C"),
        ("temperature", "-1 K"),
        ("temperature", "-300 °C"),
        ("pressure", "2 bar"),
        ("required_accuracy", "2 %"),
        ("target_range", "20 ppm"),
        ("required_response_time", "-2 s"),
        ("pressure", "-1 bar(a)"),
    ],
)
def test_ambiguous_or_unsupported_numbers_abstain(parameter, value):
    assert scalar_value(parameter, value) is None


def test_extra_provider_fields_rejected(settings):
    raw = json.loads(draft())
    raw["accuracy"] = "99%"
    with pytest.raises(ExtractionError):
        extract("Hallo", provider=FakeProvider(json.dumps(raw)), settings=settings)


def test_fenced_json_from_non_json_mode_endpoint_is_accepted(settings):
    # Endpoints without native JSON mode may wrap the object in a code fence.
    fenced = "```json\n" + draft(("matrix", "Pulver", "Pulver")) + "\n```"
    result = extract("Pulver", provider=FakeProvider(fenced), settings=settings)
    assert [f.parameter for f in result.stated_facts] == ["matrix"]


def test_prose_wrapped_json_is_accepted(settings):
    wrapped = "Here is the JSON:\n" + draft(("matrix", "Pulver", "Pulver")) + "\nDone."
    result = extract("Pulver", provider=FakeProvider(wrapped), settings=settings)
    assert result.stated_facts[0].value == "Pulver"


def test_unparseable_response_still_fails(settings):
    with pytest.raises(ExtractionError):
        extract("Pulver", provider=FakeProvider("no json here at all"), settings=settings)
