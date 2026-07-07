# Session-Monitoring und Schnitt-Analyse — Anleitung fuer Agenten und User

**Stand:** 2026-07-07 (Fixplan `PB-STUDIO-SCHNITT-CLIPAUSWAHL-FIXPLAN-2026-07-07`)
**Zweck:** Jede manuelle Test-Session der App wird vollstaendig und OHNE
laufenden KI-Agenten aufgezeichnet. Jeder Agent (Claude, Codex, Gemini, …)
kann eine Session anhand dieser Dateien nachvollziehen und den Schnitt
objektiv bewerten — ohne dass der User etwas wiederholen muss.

---

## 1. Start — eine Aktion, alles laeuft

```
start_pb_studio_clicklog.bat   (Doppelklick)
```

Das Skript startet automatisch **drei** Dinge:

| Komponente | Was es tut |
|---|---|
| PB Studio (DEBUG) | App mit `PB_LOG_LEVEL=DEBUG` + `PB_CLICK_LOG=1` — jeder Klick (`[CLICK]`), jede Taste (`[KEY]`), alle Pipeline-/Worker-/GPU-Events landen im Log |
| Session-Monitor | `scripts\diag\session_log_monitor.ps1` — laeuft minimiert parallel, filtert das grosse Log live auf Kern-Events, beendet sich ~15 s nach App-Ende selbst |
| Tee-Mitschnitt | kompletter stdout/stderr der App |

## 2. Erzeugte Dateien pro Session

| Datei | Inhalt | Fuer wen |
|---|---|---|
| `logs\monitor_<ts>.log` | **Kompakte Kern-Events** (siehe Marker-Liste unten) — zuerst lesen! | Agent |
| `logs\clicklog_<ts>.log` | Kompletter App-Output (stdout+stderr, UTF-16) | Agent (Detail) |
| `logs\pb_studio.log` | Rotierendes Voll-Log (5 MB × 3) | Agent (Detail) |
| `<projekt>\pb_studio.db` | Timeline, Szenen, Analyse-Daten | Analyse-Skript |

`<ts>` = Session-Zeitstempel, wird beim Start im Konsolenfenster angezeigt.

## 3. Kern-Events im Monitor-Log (Marker)

- **Fehler:** `ERROR`, `CRITICAL`, `Traceback`, `UNHANDLED`
- **Auto-Edit/Pacing:** `Phase 3 Auto-Edit`, `Phase 3: N Segmente`,
  `finalize_cut_beats` (Beat-Snap/Pflicht-Cuts/Ende), `Mindestdauer:`,
  `Sektionen aus Struktur-Analyse`, `Schritt-3-Diversitaet` (Cap/Seed),
  `Caption-Mood-Anreicherung`, `apply_auto_edit_segments`,
  `Timeline-Integritaet repariert`
- **Timeline-Budget:** `plan_video_timeline_add` (angefragt/akzeptiert/
  Duplikate/ueber Budget), `Nicht hinzugefuegt`, `nicht uebergeben`
- **Vision:** `Starte Vision-Captioning` (Modellname!),
  `Vision-Captioning abgeschlossen: X/Y`
- **Bedienung:** `[CLICK] PRESS …QPushButton` (welcher Button wann),
  `[KEY] PRESS`
- **Render:** `GpuSerializer holder='render'`, `Export`, `output.mp4`

## 4. Schnitt-Qualitaet objektiv messen

Nach einem Auto-Edit (Timeline in der Projekt-DB):

```powershell
%USERPROFILE%\miniconda3\envs\pb-studio\python.exe `
  scripts\diag\pacing_quality_report.py <projektordner>\pb_studio.db
```

Der Report liefert 5 Kennzahlen mit Soll-Werten:

| Kennzahl | Soll (Stand 2026-07-07) |
|---|---|
| 1. Cuts auf Beat (±70 ms) | **~100 %** |
| 2. Segment-Laenge pro Section | DROP/BUILDUP deutlich kuerzer als INTRO/BREAKDOWN |
| 3. Energie ↔ Laenge (Korrelation r) | negativ (≈ −0.6) |
| 4. Mood-Passung (0..1) | ≥ 0.85 (WARMUP niedriger, wenn ruhiges Material fehlt) |
| 5. Struktur-Grenzen mit Cut | **alle** (n/n) |
| Timeline-Ende | exakt = Audio-Dauer |

Weichen die Werte stark ab → zuerst `monitor_<ts>.log` nach
`Timeline-Integritaet repariert` mit `gaps_closed > 0` durchsuchen
(Material-Kappung; siehe Commit 397e960) und pruefen, ob die App mit dem
aktuellen Code-Stand gestartet wurde (Code wirkt erst nach App-Neustart).

## 5. Weitere Analyse-/Reparatur-Werkzeuge

| Skript | Zweck |
|---|---|
| `scripts\diag\pacing_quality_report.py` | Schnitt vs. Musik (5 Kennzahlen, Abschnitt 4) |
| `scripts\diag\fixplan_reanalyze_motion_captions.py` | Motion-Scores + Vision-Captions einer Projekt-DB neu berechnen (`--recaption-all`, `--skip-motion`) |

## 6. Regeln fuer Agenten

1. **Immer zuerst** `logs\monitor_<ts>.log` der juengsten Session lesen —
   erst bei Bedarf ins Voll-Log.
2. Render-Ergebnisse nur bewerten, wenn der Auto-Edit **nach** dem
   relevanten Code-Stand lief (App-Neustart-Zeit vs. Commit-Zeit pruefen).
3. Befunde gehoeren in den Vault
   (`…\Brain-Bug\projects\pb-studio\log.md`) — siehe `AGENTS.md`.
4. Ollama-Modell-Voraussetzungen: `docs/PRODUCTION_CONFIG.md`,
   Abschnitt „Ollama Models".
