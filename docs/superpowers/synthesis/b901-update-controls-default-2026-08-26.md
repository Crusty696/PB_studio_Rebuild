# B-901 — Update-Controls im Defaultpfad

Datum: 2026-08-26
Status: `code-fix-pending-live-verification`

## Root Cause

- `main.py` deaktivierte Versionsprüfung im Repo-Default mit `ENABLE_VERSION_CHECK = False`.
- Fallback-API zeigte auf nicht-kanonisches GitHub-Repository `PB-Studio/pb-studio-rebuild`.
- Vorhandener Worker-, Banner- und Signalpfad war dadurch im Defaultpfad nicht erreichbar.

## Code-Fix

- Versionsprüfung im Defaultpfad aktiviert.
- Fallback-API auf kanonisches Repository `Crusty696/PB_studio_Rebuild` korrigiert.
- `PBSTUDIO_UPDATE_API_URL` als expliziter Override unverändert erhalten.

## Verifikation

- Zieltest: `tests/test_services/test_b901_version_check_default.py` → `2 passed`.
- Syntax: `py_compile` für beide Produktdateien und Zieltest → grün.
- Patch-Prüfung: `git diff --check` → grün; nur bestehende Zeilenende-Warnungen.

## Offen

- Kein echter App-Start mit verfügbarer neuer Release-Version.
- Update-Banner, Download-Aktion, Fehler- und Abbruchpfad nicht live verifiziert.
- Deshalb kein Status `fixed`.
