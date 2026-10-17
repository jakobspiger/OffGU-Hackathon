"""V-2: verify_quotes tolerates presentation-only differences, still catches
genuinely absent quotes. Synthetic inputs only."""

import pytest

from src.models import ExtractedFact, ExtractionResult


def _result(quote: str) -> ExtractionResult:
    return ExtractionResult(
        stated_facts=[ExtractedFact(parameter="matrix", value="x", input_quote=quote)],
        assumptions=[],
        unknowns=[],
    )


@pytest.mark.parametrize(
    "query, quote",
    [
        # smart double quotes in the query, ASCII in the extracted quote
        ("Der Kunde nennt \u201eMilchkonzentrat\u201c.", '"Milchkonzentrat"'),
        # NBSP + collapsed whitespace
        ("water\u00a0content   in the  line", "water content in the line"),
        # en-dash vs hyphen
        ("range 780\u20132500 nm", "780-2500 nm"),
        # NFD vs NFC (decomposed vs composed umlaut)
        ("Me\u0301thode fu\u0308r Pru\u0308fung", "M\u00e9thode f\u00fcr Pr\u00fcfung"),
        # case difference
        ("Measure the POWDER blend", "powder"),
    ],
)
def test_presentation_differences_are_tolerated(query, quote):
    _result(quote).verify_quotes(query)  # must not raise


@pytest.mark.parametrize(
    "query, quote",
    [
        ("Measure this powder.", "liquid"),
        ("clear whey stream", "opaque milk concentrate"),
        ("", "anything"),
    ],
)
def test_genuinely_absent_quotes_still_rejected(query, quote):
    with pytest.raises(ValueError):
        _result(quote).verify_quotes(query)
