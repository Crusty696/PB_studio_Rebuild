# main.py Monolith Transition Plan

> Zerlegungsplan fuer die 5.386-Zeilen main.py.
> Erstellt: 2026-03-25 | Status: ENTWURF

---

## Ist-Zustand

**main.py** enthaelt 26 Klassen in einer Datei:

| Kategorie | Klassen | Zeilen | Anteil |
|-----------|---------|--------|--------|
| Task Management | TaskInfo, GlobalTaskManager | 72-411 | ~340 |
| Worker Mixin | CancellableMixin | 418-426 | ~9 |
| Worker Classes | 14 Worker-Klassen | 429-1126 | ~700 |
| Worker Registration | register_worker_types() | 1134-1190 | ~57 |
| Timeline Widgets | AnchorMarkerItem, TimelineClipItem, InteractiveTimeline | 1197-1788 | ~600 |
| Custom Widgets | PacingCurveWidget, VideoPreviewWidget | 1795-2036 | ~240 |
| Dialogs | AboutDialog | 2043-2082 | ~40 |
| Dock Widgets | TaskManagerDock | 2089-2340 | ~250 |
| Navigation | WorkspaceNavBar | 2347-2398 | ~52 |
| **PBWindow (God Class)** | PBWindow | 2405-5306 | **~2900** |

---

## Ziel-Architektur

```
main.py                          (~200 Zeilen: App-Start, PBWindow Instanz)
services/task_manager.py         (~340 Zeilen: TaskInfo + GlobalTaskManager)
workers/                         (neues Package)
  __init__.py
  base.py                       (CancellableMixin)
  analysis.py                   (AnalysisWorker, WaveformAnalysisWorker)
  video.py                      (VideoAnalysisWorker, VideoAnalysisPipelineWorker, FrameExtractWorker)
  audio.py                      (StemSeparationWorker, AutoDuckingWorker)
  import_export.py              (ExportWorker, FolderImportWorker, BatchConvertWorker, ProxyCreationWorker)
  edit.py                       (AutoEditWorker, SemanticSearchWorker)
  debug.py                      (DummyProgressWorker)
  registry.py                   (register_worker_types)
ui/timeline.py                   (~600 Zeilen: AnchorMarkerItem, TimelineClipItem, InteractiveTimeline)
ui/widgets/pacing_curve.py       (~136 Zeilen)
ui/widgets/video_preview.py      (~100 Zeilen)
ui/widgets/task_manager_dock.py  (~250 Zeilen)
ui/widgets/nav_bar.py            (~52 Zeilen)
ui/dialogs/about.py              (~40 Zeilen)
```

**Ergebnis:** main.py schrumpft von ~5400 auf ~2900 Zeilen (PBWindow + Imports).
Phase 2 wuerde PBWindow weiter zerlegen.

---

## Extraktions-Reihenfolge

### Schritt 1: Workers (HOHE Prioritaet, NIEDRIGES Risiko)

**Warum zuerst:** Null UI-Kopplung. Jeder Worker importiert nur Services.
Kein Signal/Slot Rewiring noetig — die Verbindungen bleiben in PBWindow.

**Ziel-Dateien:**
- `workers/base.py` — CancellableMixin
- `workers/analysis.py` — AnalysisWorker, WaveformAnalysisWorker
- `workers/video.py` — VideoAnalysisWorker, VideoAnalysisPipelineWorker, FrameExtractWorker
- `workers/audio.py` — StemSeparationWorker, AutoDuckingWorker
- `workers/import_export.py` — ExportWorker, FolderImportWorker, BatchConvertWorker, ProxyCreationWorker
- `workers/edit.py` — AutoEditWorker, SemanticSearchWorker
- `workers/debug.py` — DummyProgressWorker
- `workers/registry.py` — register_worker_types() + Worker-Import-Map

**Aenderung in main.py:**
```python
# ALT (inline)
class AnalysisWorker(QObject, CancellableMixin): ...

# NEU
from workers.analysis import AnalysisWorker
from workers.video import VideoAnalysisWorker, FrameExtractWorker
# ... etc
```

**Geschaetzter Gewinn:** ~770 Zeilen aus main.py

---

### Schritt 2: GlobalTaskManager (HOHE Prioritaet, NIEDRIGES Risiko)

**Warum:** Self-contained Singleton. Wird von Workers UND UI genutzt,
aber hat keine UI-Abhaengigkeiten selbst.

**Ziel:** `services/task_manager.py`

**Aenderung in main.py:**
```python
# ALT
task_manager = None  # Modul-Variable

# NEU
from services.task_manager import task_manager, GlobalTaskManager, TaskInfo
```

**Abhaengigkeiten beachten:**
- `TaskManagerDock` nutzt `task_manager` Signale → Import anpassen
- `PBWindow._start_worker_thread` nutzt `task_manager` → Import anpassen
- `register_worker_types()` nutzt `task_manager` → Import anpassen

**Geschaetzter Gewinn:** ~340 Zeilen

---

### Schritt 3: Timeline Widgets (MITTLERE Prioritaet, MITTLERES Risiko)

**Warum:** Kohaesive visuelle Komponente. `InteractiveTimeline` + `TimelineClipItem`
+ `AnchorMarkerItem` gehoeren zusammen.

**Ziel:** `ui/timeline.py`

**Abhaengigkeiten:**
- `PIXELS_PER_SECOND`, `TRACK_HEIGHT` Konstanten (Zeilen 1360-1365) → mit extrahieren
- `WaveformGraphicsItem` Import aus `ui/waveform_item.py` → bleibt
- `database.py` Imports (TimelineEntry, Beatgrid, ClipAnchor) → bleiben
- `PBWindow` referenziert `self.timeline` → bleibt als Import

**Risiko:** `InteractiveTimeline` hat direkte DB-Zugriffe (Session queries).
Diese sollten idealerweise durch Service-Calls ersetzt werden, aber das
ist ein separates Refactoring.

**Geschaetzter Gewinn:** ~600 Zeilen

---

### Schritt 4: Kleinere Widgets (NIEDRIGE Prioritaet, NIEDRIGES Risiko)

**Extraktionen:**
- `PacingCurveWidget` → `ui/widgets/pacing_curve.py` (136 Zeilen)
- `VideoPreviewWidget` → `ui/widgets/video_preview.py` (100 Zeilen)
- `TaskManagerDock` → `ui/widgets/task_manager_dock.py` (250 Zeilen)
- `WorkspaceNavBar` → `ui/widgets/nav_bar.py` (52 Zeilen)
- `AboutDialog` → `ui/dialogs/about.py` (40 Zeilen)

**Geschaetzter Gewinn:** ~578 Zeilen

---

### Schritt 5: PBWindow Workspace Builder (NIEDRIGE Prioritaet, HOHES Risiko)

**Das schwierigste Stueck.** Die `_build_*_workspace()` Methoden sind tief
mit PBWindow-State gekoppelt (`self.console_text`, `self.status_bar`,
`self.btn_*`, `self.video_pool_table`, etc.).

**Optionen:**
1. **Mediator Pattern:** Ein `AppMediator` Objekt, das UI-Events an Business-Logik weiterleitet
2. **Workspace-Klassen:** Jeder Workspace wird eine eigene QWidget-Subklasse mit
   definierten Signalen/Slots
3. **Controller Pattern:** Separate Controller fuer jeden Workspace

**Empfehlung:** Option 2 (Workspace-Klassen) ist am natuerlichsten fuer Qt.
Aber erst NACH Schritten 1-4, wenn die Worker und Widgets schon raus sind.

**Geschaetzter Gewinn:** ~1500 Zeilen (PBWindow waere dann ~1400 Zeilen)

---

## Abhaengigkeitsgraph

```
Schritt 1 (Workers)        ← Keine Abhaengigkeit, sofort machbar
    ↓
Schritt 2 (TaskManager)    ← Braucht: Workers importieren TaskManager
    ↓
Schritt 3 (Timeline)       ← Unabhaengig von 1+2, aber logisch danach
    ↓
Schritt 4 (Widgets)        ← Unabhaengig, jederzeit machbar
    ↓
Schritt 5 (Workspaces)     ← Braucht: Alles vorher muss stabil sein
```

---

## Risiken & Mitigierung

| Risiko | Mitigierung |
|--------|-------------|
| Circular Imports | Strikte Import-Richtung: workers → services → database. Nie rueckwaerts. |
| Signal/Slot Bruch | Jede Extraktion einzeln committen, danach E2E-Test |
| Modul-Level task_manager | Als Lazy-Singleton implementieren, nicht als Modul-Variable |
| InteractiveTimeline DB-Zugriffe | Akzeptieren fuer jetzt, spaeter durch Service ersetzen |
| PBWindow self.* Referenzen | In Schritt 5 durch Workspace-Signale ersetzen |

---

## Metriken nach Abschluss

| Phase | main.py Zeilen | Neue Dateien |
|-------|---------------|--------------|
| Ist-Zustand | 5.386 | 0 |
| Nach Schritt 1 | ~4.616 | 8 (workers/) |
| Nach Schritt 2 | ~4.276 | 9 |
| Nach Schritt 3 | ~3.676 | 10 |
| Nach Schritt 4 | ~3.098 | 15 |
| Nach Schritt 5 | ~1.400 | 20 |
