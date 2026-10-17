# Architektur-Tickets

Die Dateien T01.md bis T15.md enthalten importierbare Issue-Beschreibungen. Ein Git-Push veröffentlicht diese Dateien, erzeugt aber keine GitHub-Issues.

## Reihenfolge

1. T01 Schnittstellen, danach T02 Quellenaufbereitung.
2. T03–T05 Wissensbasis und T06–T07 Extraktion/Lückenanalyse.
3. T08–T10 Synthese, Versuchsplan und Validierung.
4. T11 Orchestrierung und T12 UI früh mit vereinbarten Fixtures beginnen, anschließend vollständig integrieren.
5. T13 Entwicklungsevaluation, T14 finaler Batch, T15 Abgabe.

Die T-IDs sind lokale Planungskennungen, keine GitHub-Issue-Nummern. Abhängigkeiten stehen im jeweiligen Ticket. Verantwortliche werden im Team zugewiesen.

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
