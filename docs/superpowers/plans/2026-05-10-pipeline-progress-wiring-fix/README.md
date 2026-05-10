# Pipeline Progress + Status Wiring Fix — Implementation Plan

**Datum:** 2026-05-10
**Branch:** `feat/schnitt-redesign-2026-05-09` (weiter — neuer Branch nach User-Wunsch möglich)
**Vorgeschichte:** Beim Live-Verify des SCHNITT-Wiring-Plans (2026-05-09) berichtet der User, dass die Video-Pipeline nur bis 88% läuft, Progress-Bars 0% zeigen, und einzelne Analyse-Buttons nicht klar machen welche Schritte noch fehlen. Audit am 2026-05-10 hat 6 Bugs lokalisiert (B-287 bis B-292).

**Ziel:** Jeder Klick auf einen Analyse-Button (groß oder einzeln) führt **alle** zugehörigen Schritte bis 100% durch, bewegt die UI-Progress-Bar live mit, und die User-Sicht zeigt eindeutig welche Schritte für ein Medium noch fehlen. Nichts skippen, nichts faken.

**User-Anforderung wörtlich (2026-05-10):**

> „ich klicke video-piplene der grosse gelbe button und danach werden die videos nur bis 88% analysiert ber wenn ich diesen buton klicke müssen alle analyse schritte erledigt werden jeder einzelne bis zu 100% und nichts darf übersprungen werden oder gefakt werden hast du das verstanden und wenn ichdie einzelnen analyse button schritte anklicke muss gekentzeichnet werden welche schritte zur 100% analyse noch fehlen"

**Out of scope:** Modell-Wechsel, Pipeline-Architektur-Umbau, Brain-V3-Veränderungen, neue Worker-Klassen. Reines Wiring + UI-Status + Step-Markierung. Keine LOCKED-Architektur-Touches.

---

## ⛔ HARTE REGELN — gelten für jede Sub-Task (R-1 bis R-12)

Aufbau identisch zum SCHNITT-Plan, plus zwei zusätzliche Regeln (R-11, R-12) speziell gegen das hier festgestellte Versteck-Muster „Worker emittiert sauber, UI ignoriert".

### R-1 — „Tests grün ≠ Done"

`pytest` grün ist notwendig, nicht hinreichend. Eine Phase ist erst dann abschließbar wenn:

- (a) Unit-Tests grün **und**
- (b) Production-Boot-Smoke-Test grün **und**
- (c) Manuell-Walk im laufenden GUI mit Test-Datensatz (Solo_Natur + Crusty Progressive Psy Set2.mp3).

Status `fixed` vergibt **nur** der User. Agent setzt `code-fix-pending-live-verification`.

### R-2 — Kein neuer Slot ohne Production-Wiring

Wenn ein neuer UI-Slot oder Service-Helper angelegt wird, muss vor dem Phase-Commit per Grep belegt sein, dass er außerhalb von Tests gerufen wird. `grep -rn "FunctionName(" --include="*.py" -- . | grep -v tests` muss > 0 Treffer haben.

### R-3 — Worker-Progress muss UI-Progress berühren

Jeder Slot, der `worker.progress(pct, msg)` empfängt, MUSS in der Implementierung mindestens einmal `progress_bar.setValue(pct)` (oder vergleichbares Widget-Update) aufrufen. Code-Inspection-Regel: Slot-Body grep nach `setValue`. Treffer < 1 → Slot ist Bug.

### R-4 — `min(99, ...)`-Cap nur mit explizitem 100%-Tick davor

Kein Worker darf seine Progress-Pipeline mit `min(99, ...)` clampen ohne unmittelbar vor `finished.emit(...)` ein `progress.emit(100, "fertig")` zu senden. Cap-Test: grep nach `min(99` in workers/. Pro Treffer prüfen ob `progress.emit(100` davor steht.

### R-5 — Kein Step gilt als „done" ohne `mark_done`-Call

Jeder Step in `analysis_status_service.VIDEO_STEPS` und `AUDIO_STEPS` MUSS bei jeder relevanten Pipeline einmal explizit `analysis_status_service.mark_done(media_type, media_id, step_key, summary)` aufrufen. Source-Inspection-Test: für jeden Step einmal grep nach `mark_done.*step_key` ergibt mindestens 1 Treffer.

### R-6 — `infer_from_db` als Fallback nicht als Ersatz

`infer_from_db` darf retroaktiv Steps markieren, deren Daten in der DB liegen. Es darf aber **niemals** als Ersatz für einen ehrlichen `mark_started → mark_done`-Lauf der Pipeline dienen. Pipeline muss Steps **aktiv** durchführen und mark_done rufen, auch wenn das Resultat schon da wäre.

### R-7 — Vault-Pflicht pro Sub-Task

Nach jedem Commit: Living-Plan-Datei + `log.md` + Bug-File-Status auf `code-fix-pending-live-verification`. `status: fixed` nur durch User.

### R-8 — Conventional Commits, atomar, deutsch

Subject ≤ 50 Zeichen. Co-Author-Trailer wie projektüblich. Ein Sub-Task = ein Commit.

### R-9 — Conda-Env hart

Alle pytest-Aufrufe ausschließlich mit `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`. Kein .venv, kein System-Python.

### R-10 — Stop-and-Ask bei Unklarheit

Wenn ein Step-Name, ein Slot, eine UI-Bindung oder eine DB-Spalte nicht eindeutig ist: **stop, frag User**. Insbesondere falls die Step-Liste in `VIDEO_STEPS` / `AUDIO_STEPS` nicht zur tatsächlich gewollten Pipeline passt — Plan-Abweichung dokumentieren oder Step ergänzen, nicht raten.

### R-11 (NEU) — UI-Live-Beobachtung als Phase-Done-Beweis

Vor dem Phase-Commit muss der Agent (oder bei UI-bezogenen Phasen der User) **live im laufenden GUI** beobachten, dass:

- Progress-Bar physisch von 0 → 100 läuft (nicht nur Endwert).
- AnalysisStatusPanel die fehlenden Steps in Echtzeit auf done umschaltet.
- Cockpit-Cards nach Pipeline-Run als ready angezeigt werden.

Dieser Beweis wird im Living-Plan dokumentiert mit Zeitstempel + ggf. Screenshot-Pfad.

### R-12 (NEU) — Audit-Greps müssen am Ende leer sein

Vor User-Live-Verify Audit-Reproduktion mit denselben Symptom-Greps:

```bash
# Greps die das Symptom belegen — nach Fix müssen die Soll-Werte stimmen.
grep "metadata_extract" logs/pb_studio.log | head     # nach Pipeline-Lauf: muss Treffer haben
grep -n "min(99" workers/video.py                      # OK weil progress.emit(100) davor
grep -n "_on_pipeline_progress" ui/controllers/video_analysis.py  # Body muss setValue enthalten
grep -n "_on_stem.*progress\|progress.connect.*setValue" ui/controllers/stems.py
```

Output ins Vault als Beleg.

---

## Phasen-Übersicht

| # | Phase | Zweck | Geschätzt | Bugs |
|---|---|---|---|---|
| A | Pipeline-Worker mark_done Vollständigkeit | metadata_extract + 100%-Tick im Pipeline-Worker. | 30–45 min | B-287, B-289 |
| B | UI-Progress-Bar live binden | Video-Pipeline + Stems + Waveform: progress_bar.setValue im Slot. | 30 min | B-288, B-290, B-291 |
| C | AnalysisStatusPanel Sichtbarkeit + Step-Liste | Panel permanent in Material&Analyse, fehlende Steps gekennzeichnet. | 45–60 min | B-292 |
| D | Cockpit-Card-Detail | Tooltip mit fehlenden Step-Namen je Card. | 20–30 min | B-292 |
| E | Integration-Smoke-Tests | Source-Inspection-Tests R-3 / R-4 / R-5; Smoke-Boot mit fake-Worker. | 30–45 min | Schutz |
| F | User-Live-Verify | Solo_Natur + Crusty Progressive Psy Set2.mp3, 8-Punkte-Drehbuch. | User-Zeit | Abnahme |

Total Agent: ~3–4 h. Live-Verify User: ~15 min.

---

## Phase A — Pipeline-Worker mark_done Vollständigkeit (B-287, B-289)

**Ziel:** Pipeline-Worker ruft für jeden Clip alle 9 Steps explizit `mark_done`. Letzter `progress.emit` ist 100% bevor `finished` rausgeht.

### A.1 — `metadata_extract` Marker im Pipeline-Worker

Datei: `workers/video.py::VideoAnalysisPipelineWorker.run`. In der Hauptschleife direkt vor `run_full_pipeline(video_path=...)` pro Clip:

```python
from services import analysis_status_service
from database import VideoClip, nullpool_session

with nullpool_session() as s:
    clip_row = s.get(VideoClip, clip_id)
if clip_row and clip_row.duration and clip_row.width and clip_row.height and clip_row.fps:
    analysis_status_service.mark_done(
        "video", clip_id, "metadata_extract", {
            "duration": clip_row.duration,
            "resolution": f"{clip_row.width}x{clip_row.height}",
            "fps": clip_row.fps,
            "codec": clip_row.codec,
        }
    )
else:
    # Daten fehlen → ffprobe nachholen, KEIN Skip.
    from services.video_service import VideoService
    VideoService().analyze_and_store(clip_id, create_proxy=False)
```

R-6: kein reiner `infer_from_db`-Skip. Falls Daten fehlen, wird ffprobe nachgeholt.

### A.2 — 100%-Tick vor `finished.emit`

Datei: `workers/video.py:413` und `:451`. Direkt vor jedem `self.finished.emit(...)`:

```python
self.progress.emit(100, "Pipeline abgeschlossen")
self.finished.emit(last_clip_id, {...})
```

### A.3 — Pre-Commit-Greps (R-4, R-5)

```bash
# R-4: jedes min(99 muss einen progress.emit(100 in der Nähe haben
grep -n "min(99\|progress.emit(100" workers/video.py

# R-5: metadata_extract muss in workers/video.py oder pipeline-Service mark_done aufrufen
grep -rn "mark_done.*metadata_extract" --include="*.py" -- .
```

### A.4 — Test-Lauf

```text
"...python.exe" -m pytest tests/test_services/ -k "pipeline or status" -v --tb=short
```

### A.5 — Vault + Commit

- B-287, B-289 auf `code-fix-pending-live-verification`.
- Commit: `fix(pipeline): mark metadata_extract + 100%-tick in worker (B-287,B-289)`.

### A — Definition of Done

- [ ] `mark_done.*metadata_extract` grep ergibt > 0 Treffer auch in `workers/video.py` (oder via VideoService-Fallback).
- [ ] `progress.emit(100` in `workers/video.py` an Stellen der `finished.emit`-Calls.
- [ ] Tests grün, keine Regression.

---

## Phase B — UI Progress-Bar live binden (B-288, B-290, B-291)

**Ziel:** Drei Slots (`_on_pipeline_progress`, Stems, Waveform) updaten progress_bar live.

### B.1 — Video-Pipeline Slot

Datei: `ui/controllers/video_analysis.py:194-201`:

```python
def _on_pipeline_progress(self, pct: int, msg: str, task_id: str):
    self.window.progress_bar.setRange(0, 100)
    self.window.progress_bar.setValue(pct)
    self.window.progress_bar.setFormat(f"%p%% — {msg[:60]}")
    last_pct = getattr(self, '_pipeline_last_pct', -10)
    if abs(pct - last_pct) >= 10 or "wird analysiert" in msg:
        self.window._console_append(f"[Pipeline] {msg} ({pct}%)")
        self._pipeline_last_pct = pct
```

### B.2 — Stems Slot

Datei: `ui/controllers/stems.py:86-95`. Neuer benannter Slot statt Lambda:

```python
def _on_stem_progress(self, pct: int, msg: str):
    self.window.progress_bar.setRange(0, 100)
    self.window.progress_bar.setValue(pct)
    self.window.progress_bar.setFormat(f"KI-Stems: %p%% — {msg[:50]}")
    self.window._console_append(f"[Stems] {msg} ({pct}%)")

# Wiring:
worker.progress.connect(self._on_stem_progress, Qt.ConnectionType.QueuedConnection)
```

### B.3 — Waveform Slot

Datei: `ui/controllers/audio_analysis.py:272`:

```python
def _on_waveform_progress(self, pct: int, msg: str, task_id: str):
    self.window.progress_bar.setRange(0, 100)
    self.window.progress_bar.setValue(pct)
    self.window.progress_bar.setFormat(f"Waveform: %p%% — {msg[:50]}")
```

### B.4 — Pre-Commit-Grep R-3

```bash
# Jeder *_progress-Slot muss setValue enthalten.
for f in ui/controllers/video_analysis.py ui/controllers/stems.py ui/controllers/audio_analysis.py; do
  grep -nA 8 "def _on_.*progress" $f | grep "setValue" || echo "MISS: $f"
done
```

### B.5 — Test-Lauf + Commit

Tests grün laufen, dann Commit `fix(ui): bind worker progress to progress_bar (B-288,B-290,B-291)`.

### B — Definition of Done

- [ ] R-3 Grep zeigt `setValue` in jedem Progress-Slot.
- [ ] Tests grün.

---

## Phase C — AnalysisStatusPanel Sichtbarkeit + Step-Liste (B-292)

**Ziel:** AnalysisStatusPanel ist im Material&Analyse-Tab permanent sichtbar (kollabierbar OK, aber nicht versteckt). User sieht für aktiv selektiertes Medium genau welche Steps done/running/missing sind. Live-Update via `analysis_status_service.register_completion_listener` (existiert bereits).

### C.1 — Diagnose

R-10-Pflicht: Vor C.2 prüfen wie AnalysisStatusPanel aktuell eingehängt ist (sichtbar / versteckt / collapsed). Code-Lesung von `ui/workspaces/media_workspace.py:581, 852`.

### C.2 — Sichtbarkeit erzwingen

Falls Panel hidden ist: `setVisible(True)` oder Layout anpassen. Falls Panel nur in Sub-Sub-Tab: in Haupt-Layout heben.

### C.3 — Live-Update an Selection

`media_table_controller`-Selection-Wechsel → `panel.set_media(media_type, media_id)` ruft `analysis_status_service.get_completion_percent(...)` und rendert die Step-Liste mit Symbol pro Step:
- ✅ done
- ⏳ running
- ❌ error
- ⚪ pending

### C.4 — Step-Klick navigiert zu zugehörigem Button

Wenn User auf einen ⚪-Step klickt, navigiert UI zum entsprechenden Einzel-Button (z. B. „Bewegung" → `btn_motion_analysis`). Tooltip „Klicken um diesen Schritt einzeln auszuführen".

### C.5 — Test-Lauf + Commit

`tests/ui/test_analysis_status_panel.py` (existiert ggf.) + neuer Test für sichtbarkeit + step_state.

Commit: `fix(ui): analysis_status_panel sichtbar + step-liste live (B-292)`.

### C — Definition of Done

- [ ] Panel ist im Material&Analyse-Tab im Default-Layout sichtbar.
- [ ] Step-Liste rendert für selektiertes Medium alle Steps + Status-Symbol.
- [ ] Klick auf ⚪-Step setzt Fokus auf zugehörigen Einzel-Button.

---

## Phase D — Cockpit-Card-Detail (B-292 Folge)

**Ziel:** Cockpit-Cards (PROJEKT-Tab) zeigen bei `blocked` einen Tooltip mit den **konkret fehlenden Step-Namen**, nicht nur „Audioanalyse fehlt".

### D.1 — Cockpit-Orchestrator erweitern

`services/cockpit_orchestrator.py::get_cockpit_readiness` zusätzlich `missing_steps_per_card` befüllen — Listen pro Karte.

### D.2 — Dashboard-UI

`ui/workspaces/workflow_pages.py::ProjectDashboard` setzt Tooltip an jede Card.

### D.3 — Test + Commit

Commit: `fix(cockpit): card tooltip mit fehlenden steps (B-292)`.

---

## Phase E — Integration-Smoke-Tests (Schutz)

`tests/ui/test_pipeline_progress_wiring.py` neu — analog zu `test_schnitt_integration_boot.py`. Drei Test-Klassen:

### E.1 — Source-Inspection

- Slot-Body enthält setValue (R-3).
- Pipeline-Worker emittiert vor `finished` 100% (R-4).
- `mark_done.*metadata_extract` ist im Pipeline-Pfad referenziert (R-5).

### E.2 — Live-Smoke

`scripts/phase_e_pipeline_smoke.py` — fake-Worker mit `progress(50)` → progress_bar.value() == 50. fake-Worker mit `finished` → progress_bar versteckt.

### E.3 — Status-Panel Live-Smoke

`AnalysisStatusPanel` mit gemocktem analysis_status_service → step-icons müssen umschalten.

---

## Phase F — User-Live-Verify (durch dich, David)

Drehbuch:

1. App via `start_pb_studio.bat` starten.
2. Solo_Natur (103 Videos) importieren.
3. **MATERIAL & ANALYSE > Video > Video-Pipeline (Szenen + KI)** klicken.
4. Beobachten: progress_bar wandert 0 → 100, Status-Panel zeigt jeden Step in Echtzeit als running → done, **letzter Step `Metadaten` ebenfalls done**.
5. Ende: Status-Panel 9/9 ✅, Cockpit-Card Video → ready.
6. Audio-Track auswählen, **Stem-Separation** starten — progress_bar bewegt sich live.
7. Einzel-Klick auf `btn_lufs_analyze` (oder anderen Audio-Button) — Status-Panel markiert genau diesen Step als running, am Ende done.
8. Cockpit-Card mit „blocked" → Tooltip zeigt namentlich welche Steps fehlen.

Bei 8/8 ✅: User vergibt `status: fixed` für B-287/B-288/B-289/B-290/B-291/B-292.

---

## Risiken & Trade-Offs

| ID | Risiko | Gegenmaßnahme |
|---|---|---|
| W-1 | metadata_extract ist beim Import bereits gesetzt — Doppel-mark verursacht Race | mark_done ist idempotent, keine Race |
| W-2 | min(99,...) entfernt → Worker zeigt kurzzeitig 100% bevor letzter Step durch ist | progress.emit(100) bewusst nur unmittelbar vor finished.emit |
| W-3 | AnalysisStatusPanel-Refactor stört bestehendes Layout | Phase C minimal-invasiv, kein Layout-Umbau |
| W-4 | Demucs hat keine echte Progress-Stages → gestubbte Werte | Demucs-Output parsen oder Tick-Interpolation |
| W-5 | Live-Verify findet weitere Bugs außerhalb dieses Plans | strikt im Scope, neue B-XXX, separate Plans |

---

## Plan-Anker

- Bug-Files: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-287..B-292*.md`.
- Vorgänger-Plan: `docs/superpowers/plans/2026-05-09-schnitt-integration-wiring-fix/README.md`.
- Living-Plan-Update wird in `wiki/synthesis/schnitt-workspace-redesign-2026-05-09.md` referenziert + neuer Living-Plan für Pipeline-Wiring optional.
- Test-Datensatz: Solo_Natur (103 Videos) + Crusty Progressive Psy Set2.mp3.
- Conda-Env: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`.

---

## Anti-Patterns (Verbot)

- `infer_from_db` als Stille-Lösung statt mark_done (R-6).
- progress_bar.setVisible(True) ohne setValue/setRange (B-288 Klasse).
- min(99, ...) ohne anschließenden 100%-Tick (R-4).
- „Pipeline läuft, fertig" ohne live UI-Beobachtung (R-11).
- Source-Inspection-Test allein als Phase-Done (R-1, R-11).
- Skill-Auto-Trigger entgegen User-Regel.

---

## Freigabe

Plan-Status: **draft, awaiting user approval**.

Agent rührt keinen Code an, bis User explizit „start Phase A" / „Plan freigegeben" sagt. Bis dahin: keine Code-Änderung, kein Commit am Worker oder UI.
