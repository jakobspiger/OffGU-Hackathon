# Entwicklungsumgebung und Prüfung von T01

Alle Befehle werden im Repository-Hauptordner `OffGU-Hackathon` ausgeführt. Für Installation und erstmaligen Python-Download ist Internet nötig. Tests und Startbildschirm benötigen weder API-Key noch Fachquellenzugriff.

## Windows / PowerShell

Empfohlen: [uv installieren](https://docs.astral.sh/uv/getting-started/installation/), beispielsweise mit `winget install --id astral-sh.uv --exact`; danach das Terminal neu öffnen.

```powershell
uv sync --locked
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked streamlit run app.py
```

uv verwendet die Python-Version aus `.python-version` und erstellt eine isolierte `.venv`. Eine PowerShell-Aktivierung der Umgebung ist nicht erforderlich. Linux/macOS verwenden dieselben uv-Kommandos. Auf diesem Rechner wurde Python 3.12 getestet; andere Betriebssysteme und Python-Versionen sind noch nicht praktisch geprüft.

### Bereits vorbereitete lokale Werkzeuge auf Jakobs Rechner

Da `python` nur auf einen nicht nutzbaren Windows-App-Alias zeigte, wurden uv und Python ausschließlich unter ignorierten Projektordnern eingerichtet. Es wurde kein systemweiter PATH geändert.

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.python"
./.tools/uv.exe sync --locked
./.tools/uv.exe run --locked pytest -q
./.tools/uv.exe run --locked streamlit run app.py
```

Alternativ nach erfolgreichem Setup direkt `.venv/Scripts/python.exe -m pytest -q` oder `.venv/Scripts/python.exe -m streamlit run app.py` aufrufen. `.tools`, `.python`, `.uv-cache` und `.venv` werden nicht committed; Kevin verwendet ein eigenes uv-Setup. Die Python-Umgebung ist lokal und sollte nicht zwischen Rechnern kopiert werden.

## Konfiguration

Für T01 sind keine Einstellungen erforderlich. Für spätere Live-Analyse `.env.example` einmal nach `.env` kopieren, sofern `.env` noch nicht existiert, und lokal ausfüllen. Bestehende `.env` nicht überschreiben.

| Variable | Bedeutung |
|---|---|
| `OPENAI_API_KEY` | Secret des späteren Modellproviders |
| `OPENAI_MODEL` | Tatsächlich verfügbarer Modellname; kein Default |
| `OPENAI_BASE_URL` | Optionaler kompatibler Endpoint, ohne Credentials/Query |
| `AFS_REQUEST_TIMEOUT_SECONDS` | Positiver Timeout, maximal 300 Sekunden |
| `AFS_MAX_RETRIES` | 0–5 zusätzliche Versuche, Standard 2 |
| `AFS_RETRIEVAL_K` | 1–50 Treffer, Standard 8 |
| `AFS_SOURCE_DIR` | Quellordner, Standard `materials` |
| `AFS_INDEX_DIR` | Lokaler Index, Standard `data/index` |
| `AFS_EMBEDDING_MODEL` | Leer = lexikalisch. Vektor-Index: `qwen3-embedding-4b` |

Diese Konfiguration ist ein Vertrag, noch kein implementierter Provider-/Retrieval-Client. Tests und Startbildschirm funktionieren ohne Schlüssel. Relative Pfade beziehen sich auf die Projektwurzel. Umgebungsvariablen überschreiben `.env`. Unbekannte Schlüssel in `.env` werden abgelehnt; beliebige zusätzliche Betriebssystemvariablen werden nicht geprüft.

Nie API-Keys in Logs, State, Testdaten oder Commit-Beschreibungen übernehmen. `.env` und lokale Laufzeitordner werden von `.gitignore` ausgeschlossen. Bereits versionierte Materialien bleiben unverändert.

## Abhängigkeiten ändern

Jakob koordiniert Änderungen am Manifest. Neue direkte Abhängigkeit mit `uv add <paket>` ergänzen, Entwicklungstool mit `uv add --dev <paket>`. Manifest und `uv.lock` gemeinsam prüfen und committen. Keine handgeschriebenen Änderungen am Lockfile. Danach lokale Prüfungen ausführen.

Eine automatische CI-Pipeline wurde nicht eingerichtet. Vor jedem Merge mindestens Tests, Lint und Formatprüfung ausführen. Für T01 wird zusätzlich der Paketbau mit `uv build` geprüft.

## Was die Prüfungen nachweisen

- Negative Vertragsfälle: falsche Statuswerte, unbekannte Felder, ungültige Seiten und unzulässige Quellen-IDs.
- Datentrennung: Unternehmenskontext/Forschung, Few-Shot-IDs und Herkunft extrahierter Fakten.
- Spektrale Einheiten, endliche Werte und nachvollziehbare Quellenlisten.
- Konfiguration: Vorrang von Umgebungsvariablen, Secret-Ausschluss, Pfadauflösung, Fehler bei ungültigen Einstellungen.
- Ein echter minimaler LangGraph akzeptiert den gemeinsamen State und partielle Updates.
- Streamlits AppTest startet den Startbildschirm ohne API-Key.
- Öffentliche Stubs erzeugen explizite Fehler statt erfundener Analyseergebnisse.

Die Prüfungen sind synthetisch und behaupten keine fachliche Machbarkeit. Echte Retrieval-Qualität, Provider-Zugang, wissenschaftliche Bewertung und vollständige Pipeline werden in späteren Tickets geprüft.

## Einstieg für Kevin und Jakob

1. [Architekturentscheidungen](architecture.md) und [Datenvertrag](contracts.md) gemeinsam durchgehen.
2. Kevin kann Evidence/Quellenkatalog und Retrieval implementieren; Jakob kann Extraktion und Analyse gegen dieselben Modelle aufbauen.
3. Änderungen an gemeinsamen Typen im selben Pull Request mit Tests und Vertragsdokumentation pflegen.
4. Eine `ComponentNotReadyError` aus `analyze`/`retrieve` ist im T01-Stand erwartetes Verhalten, kein fehlgeschlagenes Setup.
