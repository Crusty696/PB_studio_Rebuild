# STAB-5 Control #23 — A/B-Vergleich ausfuehren

Datum: 2026-08-27
Status: `target-test-pass-live-pending`

## Pfad

Echter `ABCompareDialog` → sichtbarer Accent-QPushButton
`Vergleich ausfuehren` → echter Mausclick → `_on_run` → Scorer-Ergebnis oder
sichtbare Fehlermeldung.

## Ergebnis

- Bestehende T2.5.6-Tests riefen `_on_run` direkt auf und umgingen Button.
- Echter Button besitzt korrekten Text/ObjectName, ist sichtbar/aktiv.
- QTest-Mausclick erreicht realen Scorer-/Renderingpfad bei isoliertem DB-Loader;
  Ergebnis zeigt drei Kandidaten sowie Profil A/B ohne Fehler.
- Separater Mausclick mit Loaderfehler rendert exakt sichtbare Fehlermeldung.
- Gezielte Datei `2 passed in 1.30s`.
- Kein Produktcodeedit.

## Offen

Echter aktiver Projekt-/DB-Kontext und sichtbarer Benutzer-Liveworkflow fehlen.
Daher nicht `fixed`.
