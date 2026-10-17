param(
    [string]$Repository = 'jakobspiger/OffGU-Hackathon',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ticketFiles = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter 'T??.md' | Sort-Object Name)
if ($ticketFiles.Count -eq 0) { throw 'Keine Ticketdateien gefunden.' }

if (-not $DryRun) {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw 'GitHub CLI fehlt. Installiere gh und führe gh auth login aus. Siehe README.md.'
    }
    & gh auth status
    if ($LASTEXITCODE -ne 0) { throw 'GitHub-Anmeldung fehlt: gh auth login' }
    # Pagination includes open and closed issues; pull requests are excluded below.
    $existingJson = & gh api --paginate --slurp "repos/$Repository/issues?state=all&per_page=100"
    if ($LASTEXITCODE -ne 0) { throw 'Vorhandene Issues konnten nicht gelesen werden.' }
    $pages = ($existingJson -join "`n") | ConvertFrom-Json
    $existing = @{}
    foreach ($page in $pages) {
        foreach ($issue in $page) {
            if (-not $issue.pull_request) { $existing[$issue.title] = $issue.html_url }
        }
    }
}

foreach ($file in $ticketFiles) {
    $firstLine = Get-Content -LiteralPath $file.FullName -Encoding UTF8 -TotalCount 1
    if ($firstLine -notmatch '^# (.+)$') { throw "Ungültiger Titel: $($file.Name)" }
    $title = $Matches[1]
    if ($DryRun) {
        Write-Output "Vorschau: $Repository | $title | $($file.Name)"
        continue
    }
    if ($existing.ContainsKey($title)) {
        Write-Output "Bereits vorhanden: $title $($existing[$title])"
        continue
    }
    $created = & gh issue create --repo $Repository --title $title --body-file $file.FullName
    if ($LASTEXITCODE -ne 0) { throw "Anlegen fehlgeschlagen: $title. Bereits angelegte Issues bleiben erhalten." }
    $existing[$title] = ($created -join "`n")
    Write-Output $created
}
