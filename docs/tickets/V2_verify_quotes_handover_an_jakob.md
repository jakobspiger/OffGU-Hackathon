# V-2 · Übergabe an Jakob: `verify_quotes`-Normalisierung für T06

> Von: Kevin (T02-Review, Punkt **[V-2]**) · An: Jakob (T01/T06, Eigentümer von `src/models.py`)
> Status: **Vorschlag zur Übernahme in `feat/t06-parameter-extractor`**.
> Kevin ändert `src/models.py` bewusst **nicht** selbst — Vertragshoheit liegt bei
> Jakob, und dein T06-Branch fasst die Datei ohnehin an (kein Doppel-Edit/Konflikt).
> Analyse-Hintergrund: `docs/tickets/V2_verify_quotes_plan.md`.

## Worum es geht (kurz)

`ExtractionResult.verify_quotes` nutzt aktuell einen **exakt-byteweisen**
Substring-Vergleich:

```python
if any(fact.input_quote not in query for fact in self.stated_facts):
    raise ValueError("An extracted fact quotes text absent from the original request.")
```

Sobald der T06-Extraktor (LLM) ein korrektes Zitat mit leicht abweichender
**Typografie** zurückgibt, wirft dieser Check fälschlich einen Fehler und bricht
die Analyse ab — obwohl keine Halluzination vorliegt. Betroffen:

- smart quotes `„ " ' '` vs. ASCII `"` `'`
- NBSP (U+00A0), schmale Leerzeichen, doppelte/umbrochene Whitespaces
- en/em-dash `– —` und non-breaking hyphen `‑` vs. `-`
- Unicode NFC vs. NFD (z. B. `ü` als 1 vs. 2 Codepoints)

Das wird **akut, sobald T06 den echten Extraktions-Prompt/LLM-Aufruf** ergänzt
(dein nächster Schritt laut `docs/parameters.md`).

## Vorgeschlagene Lösung (konservativ, verlustarm)

Nur **Darstellungs-Unterschiede** glätten — **keine** Satzzeichen/Synonyme/
Stemming, damit der Halluzinationsschutz voll erhalten bleibt. `input_quote`
bleibt im Original gespeichert; nur der *Vergleich* normalisiert.

### Patch für `src/models.py`

Oben im Modul ein Import ergänzen:
```python
import unicodedata
```

Direkt vor `class ExtractionResult` eine modul-private Helferfunktion einfügen:
```python
# Quote verification tolerates presentation-only differences (smart quotes,
# NBSP, dash variants, Unicode form, case) without weakening the hallucination
# guard: no punctuation stripping, no synonyms, no stemming.
_QUOTE_TRANSLATION = str.maketrans(
    {
        "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
        "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u2032": "'",
        "\u2013": "-", "\u2014": "-", "\u2011": "-", "\u2212": "-",
        "\u00a0": " ", "\u202f": " ", "\u2009": " ", "\u200a": " ",
    }
)


def _normalize_for_quote_check(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text).translate(_QUOTE_TRANSLATION)
    return " ".join(normalized.split()).casefold()
```

Und `verify_quotes` so ersetzen:
```python
    def verify_quotes(self, query: str) -> None:
        """B2 calls this against the original request before handing data to B3.

        The check tolerates presentation-only differences (smart quotes, NBSP,
        dash/Unicode variants, case) but still rejects any quote whose text is
        not actually present in the original request.
        """
        haystack = _normalize_for_quote_check(query)
        if any(
            _normalize_for_quote_check(fact.input_quote) not in haystack
            for fact in self.stated_facts
        ):
            raise ValueError("An extracted fact quotes text absent from the original request.")
```

### Entscheidungen (nach Kevins Freigabe, Weg A)
- **`casefold()`: ja** (Zitate sind Belege, keine Fallunterscheidung). Falls du
  strenger willst, einfach das `.casefold()` streichen — Tests unten dann anpassen.
- **`input_quote` bleibt unverändert gespeichert** — es ist das Originalzitat;
  nur `verify_quotes` normalisiert beim Vergleich.
- Keine Normalisierung beim Anlegen von `ExtractedFact` (kein Datenverlust).

## Vorgeschlagene Tests — `tests/test_verify_quotes.py`

```python
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
```

## Regression-Sicherheit

`tests/test_foundation_models.py::test_quotes_must_exist_in_original_input`
bleibt grün: `"powder"` ist in `"Measure this powder."` enthalten (positiv), und
das `"liquid"`-Zitat fehlt in der powder-Query (negativ). Die Normalisierung
ändert an beiden Fällen nichts.

## Warum das T02 nicht berührt

T02s Ingestion erzeugt `Evidence`/`ReferenceRecord`, keine `ExtractedFact`/
`ExtractionResult`. V-2 ist rein ein T06-Belang (`src/models.py` + Extraktor).
Diese Übergabe enthält **nur Doku** — keine Änderung an `models.py` durch Kevin.

## Nächster Schritt

Jakob übernimmt Patch + Test in `feat/t06-parameter-extractor` (oder einen
kleinen Vorab-PR). Danke!
