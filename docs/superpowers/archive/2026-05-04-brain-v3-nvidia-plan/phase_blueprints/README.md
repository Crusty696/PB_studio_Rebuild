# Phase-Blueprints für Brain V3 (NVIDIA-Plan)

Detaillierte Build-Anweisungen pro Phase — gedacht als **Briefing für
Claude Code** (oder einen anderen Implementation-Agenten).

Format pro Blueprint:
1. **Ziel + Erfolgsdefinition** (eine harte Aussage)
2. **Voraussetzungen** (welche Phasen müssen DONE sein)
3. **Architektur** (welche Module + ihre Verantwortung)
4. **Datei-für-Datei-Spezifikation** (Pfad + Imports + Public-API + Inhalt)
5. **SQL-Migrations** (falls vorhanden)
6. **App-Eingriffspunkte** (V1/V2-naher Code, was angefasst werden muss)
7. **Test-Spezifikation** (welche Tests, welche Asserts)
8. **Definition of Done** (kalibriert mit Spike-Realdaten wo verfügbar)
9. **Risiken + Mitigationen**
10. **Verifikations-Strategie** (welche Spike-Skripte, welche Live-Tests)
11. **Reihenfolge der Implementation** (Foundation → Module → Tests)

Status der Phasen (Stand 2026-05-05):

| Phase | Blueprint-Datei | Implementations-Status |
|---|---|---|
| 3 — Brain-Core (Beta-Bernoulli) | `phase_3_brain_core.md` | 🟢 **DONE** — 112/112 pytest, Verify-Mode |
| 4 — Pacing-Integration | `phase_4_pacing_integration.md` | 🔴 TODO — Build-Mode |
| 5 — PySide6-UI | `phase_5_pyside6_ui.md` | 🔴 TODO — Build-Mode |
| 6 — Härtung | `phase_6_haertung.md` | 🔴 TODO — Build-Mode |

**Vor jedem Phase-Start prüfen:** Blueprint hat **State-Banner ganz oben**
(🟢 DONE → Verify-Mode | 🟡 IN_PROGRESS → Drift-Check | 🔴 TODO → Build-Mode).
Banner referenziert die zugehörige Synthesis-Doc unter
`docs/superpowers/synthesis/`.

---

## Bezug zum Übergeordneten Plan

Diese Blueprints konkretisieren `06_PHASES.md` (Übersicht). Sie sind
**verbindlich, keine Vorschläge** — Claude Code hält sich an die Datei-Pfade,
API-Signaturen und DoDs. Bei Unklarheit: zurück zum übergeordneten Plan
(`README.md`, `01_ARCHITECTURE.md`, etc.) UND nachfragen.

## Nicht in den Blueprints

- App-eigene Architektur-Entscheidungen (gehören in 01–07)
- Technologie-Wahl (steht in 02_DECISIONS, 03_TECH_STACK)
- Risiko-Matrix (steht in 07_RISKS)
- Externe Quellen (08_VERIFICATION)

Blueprints sind **rein implementierungsorientiert** und greifen nur die
Plan-Entscheidungen auf, ohne sie neu zu rechtfertigen.

---

## Wichtige Cross-Cuts (alle Phasen)

- **V1/V2-Refactor freigegeben** (User-Direktive 2026-05-05, F2 —
  Plan-Doc 02 #24). Pro Refactor ist eine Live-Verifikation der
  V1/V2-Funktion erforderlich. V3 lebt parallel strikt unter
  `services/brain_v3/` und `tests/test_services/test_brain_v3_*.py`,
  V3-DBs unter eigenen Subfoldern.
- **Tests pro Modul** als pytest-Files (live-verifiziert via
  `run_pytest_brain_v3.bat`).
- **Vault-Pflicht** nach jeder abgeschlossenen Phase: Synthesis-Doc
  unter `docs/superpowers/synthesis/` ablegen.
- **CLAUDE.md OBERSTE REGEL**: bei Annahmen nicht raten, sondern messen
  oder Quellen zitieren.
