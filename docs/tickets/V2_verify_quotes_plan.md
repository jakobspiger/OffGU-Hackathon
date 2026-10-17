# V-2 · `verify_quotes`-Normalisierung — Analyse & Plan

> Ausgelöst durch Review-Punkt **[V-2]** aus `T02_T01_schnittstellen_review.md`.
> Auftrag Kevin: „V-2 machen und auf T06 anpassen, damit es wieder passt. Erst Plan."
> **Noch kein Code.** Dieser Plan legt die beste Lösung + die Zuständigkeitsfrage dar.

## 1. Das Problem (präzise)

`src/models.py`:
```python
class ExtractionResult(ContractModel):
    def verify_quotes(self, query: str) -> None:
        if any(fact.input_quote not in query for fact in self.stated_facts):
            raise ValueError("An extracted fact quotes text absent from the original request.")
```

`input_quote not in query` ist ein **exakter, bytegenauer Substring-Vergleich**.
Das ist als Halluzinationsschutz gut gemeint (ein Fakt muss wörtlich in der
Anfrage stehen), hat aber **False-Negative-Risiken**, sobald sich Tippografie
zwischen Anfrage und extrahiertem Zitat minimal unterscheidet:

- **Anführungszeichen:** `"` vs. `„…"` vs. `'` vs. `'…'` (LLMs normalisieren gern smart quotes).
- **Whitespace:** doppelte Leerzeichen, Zeilenumbrüche, Tabs, **NBSP (U+00A0)**.
- **Unicode-Formen:** NFC vs. NFD (z. B. `ü` als 1 vs. 2 Codepoints), Ligaturen.
- **Bindestriche:** `-` (Hyphen) vs. `–` (en-dash) vs. `‑` (non-breaking hyphen).

Ergebnis: Der Extraktor (B2/T06) zitiert korrekt, aber `verify_quotes` wirft
fälschlich `ValueError` → die ganze Analyse bricht ab, obwohl kein
Halluzinations­problem vorliegt.

## 2. Warum das JETZT relevant ist (T06-Kontext)

Jakob hat in `feat/t06-parameter-extractor` gerade `ExtractedFact.parameter` von
freiem `Text` auf das geschlossene Literal `ParameterName` (16 Werte) verengt
(siehe `docs/parameters.md`). Der **nächste** T06-Schritt ist laut dieser Doku
„Extraktionsprompt, Modellaufruf, Zahlenparser". Genau dann läuft ein LLM gegen
`verify_quotes` — und genau dann schlägt der exakte Substring-Match in der
Praxis zu. V-2 muss **vor** diesem Schritt gelöst sein, damit T06 „wieder passt".

## 3. ZUSTÄNDIGKEIT — die entscheidende Vorfrage

`verify_quotes` liegt in **`src/models.py`** = Jakobs geteilte Vertragsdatei
(T01/T06). Jakobs eigenes `docs/contracts.md`:
> „Gemeinsame Änderungen laufen über Jakob; niemand kopiert und verändert einen
> eigenen Vertragsstand."

Zusätzlich: Jakobs **T06-Branch ist offen und unge­merged** und fasst `models.py`
bereits an. Wenn ich parallel dieselbe Datei/Klasse ändere, gibt es einen
**sicheren Merge-Konflikt** mit seiner laufenden Arbeit.

→ **Deshalb zwei mögliche Wege. Kevin entscheidet.**

## 4. Lösungs-Design (die beste Variante inhaltlich)

Unabhängig vom Weg ist die fachlich beste Normalisierung eine **konservative,
verlustarme** Funktion, die nur echte „Darstellungs-" Unterschiede glättet und
**keine** semantischen (sie darf Halluzination weiter fangen):

```python
import unicodedata

def _normalize_for_quote_check(s: str) -> str:
    s = unicodedata.normalize("NFC", s)          # kanonische Unicode-Form
    # typografische Anführungszeichen/Bindestriche auf ASCII-Basis bringen
    trans = {
        "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
        "\u2018": "'", "\u2019": "'", "\u201a": "'",
        "\u2013": "-", "\u2014": "-", "\u2011": "-",
        "\u00a0": " ", "\u202f": " ", "\u2009": " ",  # NBSP/thin spaces
    }
    s = s.translate(str.maketrans(trans))
    s = " ".join(s.split())                       # Whitespace kollabieren
    return s.casefold()                           # robust gegen Groß/Klein
```
und der Check:
```python
def verify_quotes(self, query: str) -> None:
    haystack = _normalize_for_quote_check(query)
    for fact in self.stated_facts:
        if _normalize_for_quote_check(fact.input_quote) not in haystack:
            raise ValueError("An extracted fact quotes text absent from the original request.")
```

**Bewusst NICHT normalisiert:** keine Entfernung von Satzzeichen/Zahlen, keine
Stemming/Synonyme, kein Trimmen ganzer Wörter — sonst würde der Schutz gegen
erfundene Fakten aufweichen. `casefold()` ist vertretbar (Zitate sind Belege,
keine Fallunterscheidung), ließe sich aber auch weglassen, wenn Jakob strenger
will. → **offener Parameter für Jakob.**

**Kompatibilität mit bestehenden Tests:** `tests/test_foundation_models.py`
`test_quotes_must_exist_in_original_input` bleibt grün (positiv: `"powder"` in
`"Measure this powder."`; negativ: `"liquid"`-Zitat fehlt in powder-Query). Die
Normalisierung ändert an diesen Fällen nichts.

## 5. Zwei Wege — mit Empfehlung

### Weg A (EMPFOHLEN): an Jakob übergeben, in T06 einfließen lassen
- Ich schreibe die fertige Funktion + 2–3 gezielte Tests (smart quotes, NBSP,
  NFD) als **Vorschlag** in dieses Doc / einen kurzen Patch-Block und
  **kommentiere es an Jakobs T06-PR** (bzw. gebe es Kevin zum Weiterreichen).
- Jakob übernimmt es in `feat/t06-parameter-extractor` (es ist *sein* Modul und
  er fasst `models.py` dort ohnehin an) → **kein Merge-Konflikt, Vertragshoheit
  gewahrt.**
- **Vorteil:** sauber nach Teamregel, keine Doppelbearbeitung von `models.py`.
- **Nachteil:** die eigentliche Code-Änderung macht formal Jakob.

### Weg B: Ich ändere `models.py` selbst auf einem Branch + PR
- Branch `fix/verify-quotes-normalization` von aktuellem `main`, nur
  `src/models.py` + ein neuer Test `tests/test_verify_quotes.py`.
- PR gegen `main`, **Jakob als Reviewer** (er muss zustimmen — es ist sein Vertrag).
- **Risiko:** Jakobs offener T06-Branch ändert dieselbe Datei → wer zuerst
  mergt, zwingt dem anderen einen Rebase/Konflikt auf. Deshalb **nur sinnvoll,
  wenn** wir das mit Jakob abstimmen oder sein T06-PR zuerst gemergt wird.
- **Vorteil:** V-2 ist sofort als eigener, nachvollziehbarer Fix dokumentiert.
- **Nachteil:** berührt fremde Vertragshoheit; Konfliktgefahr mit T06.

## 6. Empfehlung

**Weg A**, inhaltlich mit der Normalisierung aus Abschnitt 4. Falls du (Kevin)
aber willst, dass ich es direkt umsetze und als PR mit Jakob-Review liefere →
**Weg B**, und ich baue ihn so, dass er gegen den aktuellen `main` sauber ist
und Jakob im PR explizit um Freigabe + Reihenfolge-Abstimmung mit T06 bitte.

## 7. Offene Entscheidungen für Kevin
1. **Weg A oder B?**
2. `casefold()` (case-insensitiv) mitnehmen — ja/nein? (Default: ja.)
3. Soll die Normalisierung auch **innerhalb** von `ExtractedFact` beim
   Anlegen wirken, oder nur im `verify_quotes`-Vergleich? (Empfehlung: nur im
   Vergleich — `input_quote` bleibt als Originalzitat unverändert gespeichert.)
