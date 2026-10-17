# Gemeinsame Parameternamen für T06 und T03

Vertrag: `ParameterName` in `src/models.py`. Verantwortlich für Änderungen: Jakob.
Diese Liste wurde für T06 festgelegt; Kevin verwendet dieselben Namen in T03.
Die frühere freie Zeichenkette in `ExtractedFact.parameter` ist jetzt ein geschlossenes Literal.

| Name | Bedeutung / Abgrenzung |
|---|---|
| `matrix` | Physische/optische Probenform: Pulver, klare Flüssigkeit, trübe Suspension usw. |
| `sample_composition` | Genannte Bestandteile oder Rezeptur der Probe; nicht automatisch der Zielstoff. |
| `target_substance` | Zu untersuchender Stoff oder ausdrücklich benannte Stoffgruppe. |
| `target_quantity` | Gesuchte Messgröße: Feuchtigkeit, Konzentration, Identität, Biomasse usw. |
| `target_range` | Genannter erwarteter Messbereich der Zielgröße, mit ursprünglicher Einheit. |
| `temperature` | Genannte Probentemperatur/Prozesstemperatur, einschließlich Bereich und Bezug. |
| `pressure` | Genannter Prozessdruck; absolut/relativ nur übernehmen, wenn angegeben. |
| `flow_conditions` | Durchfluss, Strömung, Stillstand oder sonstige genannte Fließbedingungen. |
| `measurement_location` | Räumlicher Messort, etwa hinter einem Trockner. |
| `measurement_mode` | Gewünschte Einbindung: in-line, on-line, at-line oder Labor; nicht Messgeometrie. |
| `existing_equipment` | Bereits vorhandene Sensoren, Sonden, Fasern, Geräte oder Kalibrierungen. |
| `optical_access` | Genannter Zugang zur Probe: Fenster, Kontaktmöglichkeit, Abstand, Zugänglichkeit. |
| `required_accuracy` | Geforderte Genauigkeit/Unsicherheit; keine zugesicherte Geräteleistung. |
| `required_response_time` | Geforderte Antwortzeit oder Messfrequenz mit ursprünglicher Einheit. |
| `reference_method` | Verfügbares oder vorgesehenes unabhängiges Referenzverfahren. |
| `process_constraints` | Weitere ausdrücklich genannte Grenzen: Hygiene, Reinigung, Ex-Schutz, Budget usw. |

## Regeln für beide Implementierungen

- `value` bleibt in diesem Schritt Text. Zahlen, Einheiten, Bereiche, Näherungen und Verneinungen aus der Anfrage erhalten. Keine stillen Umrechnungen oder erfundenen Einheiten.
- Regeln dürfen diese Texte nicht unkontrolliert numerisch vergleichen. Erforderliche Normalisierung/Einheitenkonvertierung später explizit validieren; bei unklarer Bedeutung bleibt das Ergebnis unbekannt.
- Jeder Fakt braucht ein Originalzitat in `input_quote`. Keine aus Fachwissen abgeleiteten Fakten: Aus „Milch“ darf ohne ausdrückliche Angabe nicht „opak“ werden.
- `target_substance` und `target_quantity` sind getrennt. Feuchtigkeit als Zielgröße bedeutet nicht, dass der Kunde einen Zahlenbereich angegeben hat.
- Mehrere Fakten mit demselben Parameter sind zulässig. Bezug und unterschiedliche Prozesszustände im Wert erhalten; widersprüchliche Werte nicht durch Überschreiben verlieren. Eine eigene Widerspruchsstruktur folgt erst in der weiteren T06-Umsetzung.
- Fehlende Angaben erzeugen keinen Fakt mit `value="unknown"`. In `unknowns` für einen vollständig fehlenden Parameter seinen exakten Namen verwenden; konkrete Mehrdeutigkeiten dürfen weiterhin beschreibenden Text enthalten. `unknowns` bleibt vorerst `list[str]`.
- Nicht jede Anfrage muss alle 16 Parameter liefern. B3/T07 entscheidet später, welche Lücken für die konkrete Methodenwahl relevant sind.
- Annahmen bleiben in `assumptions`; T06 soll unbelegte Ergänzungen bevorzugt unterlassen.
- Keine alternativen Schlüssel wie `sample_matrix`, `temp` oder `accuracy` einführen. Änderungen an dieser Liste gemeinsam dokumentieren und testen.

## Umfang dieses Schritts

Nur Parameternamen, Semantik und Typvalidierung sind umgesetzt. Noch kein Extraktionsprompt, Modellaufruf, Zahlenparser oder fachliches Regelwerk. Die neue Einschränkung betrifft alle Erzeuger von `ExtractedFact`; die übrigen Verträge bleiben unverändert.

## Vertrags-Erweiterung in T06-Schritt 2 (Extraktion, `extraction_version = "1.1"`)

Der zweite T06-Schritt ergänzt den eigentlichen Extraktor (`src/engine/extraction.py`,
`src/engine/provider.py`). Dabei wächst der gemeinsame Vertrag in `src/models.py`
rückwärtskompatibel; alle neuen Felder haben Defaults. Für Kevins Regelbau (T03)
gilt die ausführliche [Übergabe T06 → Kevin](t06-handover-an-kevin.md). Datenfluss,
Fehlertypen und eine Symptom-Ursache-Tabelle stehen in der
[technischen Referenz & Fehlerdiagnose](t06-extraction-reference.md).

- **`ExtractedFact.numeric_value: NumericValue | None`** — optionaler, exakt
  geparster Skalar mit expliziter Einheit (`°C`, `K`, `bar(a)`, `bar(g)`, `s`,
  `ms`). Konservativ: nur ein einzelner Dezimalwert mit Punkt und unterstützter
  Einheit. Bereiche, Näherungen (`ca.`), Verneinungen, Komma-Dezimale, fehlende
  Einheit und physikalisch unmögliche Werte ergeben `None`. Keine Umrechnung.
  Der Textwert in `value` bleibt immer die maßgebliche Angabe.
- **`ExtractionResult.conflicts: list[ParameterConflict]`** — explizit markierte
  Widersprüche zum selben Parameter mit `parameter`, `fact_indices`
  (0-basiert, mindestens zwei, verschieden) und `reason`. Mehrere verschiedene
  Werte zum selben Parameter werden deterministisch als Konflikt markiert, statt
  stillschweigend überschrieben zu werden.
- **`ExtractionResult.extraction_version: Literal["1.1"]`** — Versionskennzeichen
  der Extraktionsstruktur.
- **`unknowns` jetzt mit Parameternamen** — ein vollständig fehlender Parameter
  erscheint mit seinem exakten `ParameterName` in `unknowns`. Zusätzlich erscheint
  ein konflikt-behafteter Parameter in `unknowns`, obwohl er Fakten besitzt:
  seine Bedeutung ist bis zur Klärung offen.
- **`verify_quotes` toleriert reine Darstellungsunterschiede** (smart quotes,
  NBSP, En-/Em-Dash, NFC/NFD, Groß/Klein) über eine konservative Normalisierung
  (V-2, Issue #3). `input_quote` bleibt im Original gespeichert; nur der Vergleich
  normalisiert. Satzzeichen, Synonyme und Stemming bleiben unangetastet, damit der
  Halluzinationsschutz voll erhalten bleibt.

`assumptions` bleibt in diesem Schritt bewusst leer: T06 unterlässt unbelegte
Ergänzungen und bevorzugt `unknowns` gegenüber geratenen Annahmen.
