# GUI-Qualitätsaufnahme — 2026-07-26

Baseline: `9a321dc`

## Aktuell verifiziert

- UI-Test-Runner: 647 passed in vier Chunks, kein nativer Crash.
- Architektur-/UI-Fokus: 15 passed.
- Preview-Fokus: 3 passed, 1 skipped.
- Deterministische Qt-Probes:
  - B-710 alter Stream stoppt neuen nach Seek.
  - B-716 Dock unsichtbar, Toggle bleibt checked.
  - B-717 Cockpit-SCHNITT erzeugt zwei Projekt-Pushes.
  - Topbar `NoFocus`: Space/Enter aktiviert fokussierten Button nicht.

## Sichtbarer App-Lauf

Letzter sichtbarer Lauf 2026-07-20: First-Run-Wizard, danach Director's
Cockpit mit vier Workspaces; CUDA GTX1060, Ollama und FFmpeg bereit;
Hauptfenster sauber beendet. B-664-VRAM-Anzeige wurde danach separat behoben.

## Nicht verifiziert

Kein frischer echter Medienworkflow. Vorgeschriebene Testmedien lagen nicht vor.
Darum keine Aussage „funktioniert“ für Import, Waveform, Thumbnails, Playback,
Audio-/Videoanalyse, Auto-Schnitt, Timeline oder Export.

Details und Priorisierung:
`docs/superpowers/synthesis/app-quality-audit-2026-07-26.md`.
