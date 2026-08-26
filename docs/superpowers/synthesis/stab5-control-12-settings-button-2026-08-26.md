# STAB-5 Control #12 — Einstellungen-Button

Datum: 2026-08-26
Status: `target-test-pass-live-pending`

## Pfad

Produktiv gebauter sichtbarer `Einstellungen`-Button → echter Mausclick →
lokales Produkt-Wiring → `ProjectManagementController._show_settings()` →
Dialogkonstruktion → Signalconnect → exec → deleteLater.

## Ergebnis

- Candidate-Refs waren semantisch fremd; Dialogtests belegten keinen Top-Bar-Click.
- Test verwendet echten Builder und echten ProjectManagementController.
- Nur SettingsDialog ist isoliert; zwei Clicks erzeugen zwei getrennte Instanzen.
- Pro Instanz: Parent ist Host, Ollama-Slot korrekt, exec 1, deleteLater 1.
- Genau ein sichtbarer Button mit Text `Einstellungen`.
- Gezielter Test `1 passed in 1.27s`; drei Reviewlinien PASS.
- Kein Produktcode geändert.

## Offen

Echter SettingsDialog-Inhalt, QSettings-Schreibpfad und Modal-/PBWindow-Live
fehlen. Daher nicht `fixed`.
