# STAB-5 Control #24 — About-Dokumentation

Datum: 2026-08-27
Status: `target-test-pass-live-pending`

## Pfad

Echter `AboutDialog` → sichtbarer/aktiver QPushButton `Dokumentation` → echter
Mausclick → `_open_docs` → lokale README-Oeffnung oder sichtbare Warnung.

## Ergebnis

- Bestehender B-902-Test rief `_open_docs` direkt auf und umging Button.
- Echter Dialog besitzt genau einen sichtbaren/aktiven Dokumentationsbutton.
- QTest-Mausclick reicht vorhandene README an `QDesktopServices.openUrl` weiter.
- Zweiter Mausclick bei fehlender README zeigt `Dokumentation fehlt`.
- Gezielte Datei `1 passed in 1.37s`.
- Kein Produktcodeedit.

## Offen

Frozen-/Installer-Bundle und realer OS-Viewer bleiben STAB-6-Livegate. Daher
nicht `fixed`.
