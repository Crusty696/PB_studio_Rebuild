# B-902 — About-Dokumentation im installierten Build

Status: `code-fix-pending-live-verification`

## Root Cause

`README.md` war kein PyInstaller-Datenartefakt. About oeffnete nur eine bereits
vorhandene Datei und blieb bei fehlender Datei ohne sichtbare Rueckmeldung.

## Aenderung

- `pb_studio.spec`: `README.md` ins Bundle aufgenommen.
- `ui/dialogs/about.py`: lokale Datei via `QDesktopServices` oeffnen.
- Fehlende oder abgelehnte Oeffnung zeigt sichtbare Warnung.

## Verifikation

- Syntax/Import: gruen.
- Fokussierter Test: `tests/ui/test_b902_about_docs.py`, 1 passed.
- Frozen-/Installer-Livetest fehlt und bleibt STAB-6-Gate.
