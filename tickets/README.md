# Architektur-Tickets

Die Dateien T01.md bis T15.md enthalten importierbare Issue-Beschreibungen. Ein Git-Push veröffentlicht diese Dateien, erzeugt aber keine GitHub-Issues.

## Reihenfolge

1. T01 Schnittstellen, danach T02 Quellenaufbereitung.
2. T03–T05 Wissensbasis und T06–T07 Extraktion/Lückenanalyse.
3. T08–T10 Synthese, Versuchsplan und Validierung.
4. T11 Orchestrierung und T12 UI früh mit vereinbarten Fixtures beginnen, anschließend vollständig integrieren.
5. T13 Entwicklungsevaluation, T14 finaler Batch, T15 Abgabe.

Die T-IDs sind lokale Planungskennungen, keine GitHub-Issue-Nummern. Abhängigkeiten, Verantwortliche und konkrete Kollisionsrisiken stehen im jeweiligen Ticket.

## Aufteilung zwischen Kevin und Jakob

| Verantwortlich | Tickets | Bereich |
|---|---|---|
| Kevin | T02, T03, T04, T05, T10, T13 | Wissen, Regeln, Retrieval, Beispiele, Gate, Evaluation |
| Jakob | T01, T06, T07, T08, T09, T11, T12, T14 | Schnittstellen, Analyse, Orchestrierung, UI, finaler Batch |
| Jakob federführend; Kevin unterstützt | T15 | Integration und Abgabe |

Jakob pflegt gemeinsame Modelle, Graph-State, Konfiguration, Abhängigkeiten und README. Kevin pflegt Wissensmodule, Daten, Indexbau sowie ausdrücklich auch `src/engine/validators.py` und `scripts/check_citations.py`. Die übrigen Engine-Dateien gehören Jakob. Änderungen außerhalb des eigenen Bereichs vorab abstimmen.

Jeder schreibt Modultests für seinen Bereich in getrennten Dateien. Kevin betreut zusätzlich die übergreifende Evaluation. Gemeinsame Test-Fixtures wie `conftest.py` nur nach Absprache durch eine Person ändern.

Vor dem parallelen Start gemeinsam Evidence, Extraktionsergebnis, Regel- und Validierungsbefunde sowie Funktionssignaturen festlegen. Mit vereinbarten Testdaten kann die Umsetzung vor Fertigstellung aller Abhängigkeiten beginnen. Keine direkten Dateikonflikte bedeutet nicht, dass keine Integrationsabstimmung nötig ist.

Ohne CI: pro Ticket ein Branch, kleine Pull Requests, gegenseitige Prüfung, betroffene Tests lokal vor dem Merge und gemeinsamer Smoke-Test nach Integration. T02 und T04 ändern beide den Indexbau und werden von Kevin aufeinander aufbauend integriert.

Die Namen in den Tickets sind textliche Zuständigkeiten. GitHub-Assignees werden vom Importskript nicht gesetzt. Bereits veröffentlichte Issues werden durch Änderungen dieser Dateien oder erneuten Import nicht aktualisiert.

## Echte GitHub-Issues erstellen

Voraussetzung: GitHub CLI (https://cli.github.com/) und Schreibzugriff auf das Zielrepository. Unter Windows kann die CLI beispielsweise mit `winget install --id GitHub.cli --exact` installiert werden. Danach gegebenenfalls ein neues Terminal öffnen.

Im Repository-Hauptordner:

```powershell
gh auth login
./tickets/publish-issues.ps1 -DryRun
./tickets/publish-issues.ps1
```

Falls die lokale PowerShell-Ausführungsrichtlinie Skripts blockiert, kann der Aufruf ohne dauerhafte Richtlinienänderung in einem eigenen Prozess erfolgen:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./tickets/publish-issues.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File ./tickets/publish-issues.ps1
```

Die Vorschau funktioniert auch ohne GitHub CLI und verändert nichts. Der normale Aufruf erstellt echte Issues direkt in `jakobspiger/OffGU-Hackathon`. Ein vorheriger Commit oder Push der Dateien ist dafür nicht erforderlich. Mit `-Repository owner/repo` lässt sich das Ziel ausdrücklich ändern.

Das Skript liest vorhandene offene und geschlossene Issues und überspringt identische Titel. Es verändert bestehende Issues nicht. Titel nach dem Import möglichst beibehalten; umbenannte Issues werden nicht als Duplikate erkannt. Nicht gleichzeitig mehrfach starten.

## Sichtbarkeit auf GitHub

Erstellte Issues erscheinen unter https://github.com/jakobspiger/OffGU-Hackathon/issues.

Ein GitHub Projects Board ist eine separate Ansicht: Dort die Issues über „Add item“ aus dem Repository hinzufügen oder einen passenden Auto-add-Workflow einrichten. Der Import fügt keine Issues zu einem Project hinzu und legt keine Project-Statusfelder, Assignees oder Labels fest.

Empfohlene Board-Spalten: Backlog, Ready, In Progress, In Review, Done. Pro Ticket einen Branch und einen Pull Request verwenden. `Closes #<echte Issue-Nummer>` in der PR-Beschreibung verknüpft die Arbeit mit dem Issue.

## Dateien versionieren

```powershell
git add tickets
git commit -m "docs: add architecture implementation tickets"
git push
```

Der Push und der Issue-Import sind unabhängige Schritte. GitHub-Issues werden durch spätere Änderungen an den Markdown-Dateien nicht automatisch aktualisiert.
