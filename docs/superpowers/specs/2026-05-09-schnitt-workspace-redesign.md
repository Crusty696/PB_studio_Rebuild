---
title: SCHNITT Workspace Redesign Design
date: 2026-05-09
status: draft-approved-for-planning
scope: nav-bar SCHNITT-tab edit-workspace timeline pacing anchors stems rl notes
related: ["D-018", "D-021", "D-033"]
vault_anchor: projects/pb-studio/wiki/synthesis/schnitt-workspace-redesign-2026-05-09.md
---

# SCHNITT Workspace Redesign Design

## Ziel

Der bisherige zweigeteilte Workflow `AUTO-SCHNITT` + `REVIEW` wird zu **einem** Top-Tab `SCHNITT` zusammengeführt. Die Hauptnavigation reduziert sich von 5 auf 4 Tabs. Innerhalb von `SCHNITT` führt ein klarer Drei-Zustands-Flow (`Empty → Loading → Editor`) den Nutzer von „leerer Timeline" über „KI rechnet" zu „fertige Timeline mit Feinarbeit". Der Editor bündelt vier semantisch getrennte Sub-Tabs, einen persistenten Inspector als rechte Spalte und respektiert „gelockte" Clips bei Re-Generierung.

User-Befund 2026-05-09: Der bisherige Review-Bereich ist „Katastrophe / nicht nutzbar / keine Struktur / vieles nicht angezeigt / unklarer Zweck". Dieses Design adressiert die Hauptursachen: keine durchgängige Sichtbarkeit von Pacing/Anker im Review, destruktiver Stage-Switch, doppelte Pacing-Curve-UIs, Tab-Pingpong zwischen Auto-Schnitt und Review, fehlendes Locking, fehlende Loading-Stage, fehlende Notes/RL-Integration, empfindliche Combos/Slider durch ungeschützte Wheel-Events.

## Kontext aus Code

### Heutige Hauptnavigation

- `ui/widgets/nav_bar.py:40-46` definiert `WorkspaceNavBar.WORKSPACE_NAMES = ["PROJEKT", "MATERIAL & ANALYSE", "AUTO-SCHNITT", "REVIEW", "EXPORT"]`. Tabs 2 und 3 zeigen heute beide auf `EditWorkspace` per `set_workflow_stage("auto"|"review")`.
- `ui/controllers/workspace_setup.py:154-411` baut den Stack mit vier Widgets (`_project_dashboard`, `_material_analysis_ws`, `_edit_ws`, `_deliver_ws`). Die fünf Nav-Tabs werden via `_on_workspace_changed` auf vier Stack-Indizes gemappt — Index 2 wird von beiden geteilt.
- `ui/controllers/workspace_setup.py:413-442` `_handle_cockpit_action` mappt Cockpit-Action-Keys auf Nav-Indizes 0..4 inklusive `open_auto_edit` und `open_review`.

### Heutiger EditWorkspace

- `ui/workspaces/edit_workspace.py:21-485` definiert `EditWorkspace`. Wesentliche Methoden:
  - `set_workflow_stage(stage)` (Zeile 88) — destruktiver Tab-Austausch via `removeTab(0)` Schleife.
  - `_build_auto_page()` (Zeile 99) — zeigt Pacing-Tab voll.
  - `_build_review_page()` (Zeile 109) — HBox mit Timeline-Tab (stretch 3) + Inspector-Tab (stretch 1).
  - `_build_pacing_tab()` (Zeile 193) — Pacing-Curve, Cut-Rate, Style-Preset, Reactivity, Breakdown, Generate/Auto-Edit, RL-Buttons.
  - `_build_timeline_tab()` (Zeile 121) — Video-Preview 640×360 fix, Transport, `InteractiveTimeline`, Cut-Info-Label.
  - `_build_inspector_tab()` (Zeile 381) — `ClipInspectorPanel`, Keyframe-Read-only.
  - `_build_anker_tab()` (Zeile 424) — gehört zu `expert_tools`/`expert_tabs` und wird in keinem der beiden Stages sichtbar.
- `ui/controllers/edit_workspace.py:68-197` `_generate_timeline` debounced 250 ms → `_generate_timeline_impl` startet `_CutsWorker` im QThread. Worker liefert `done(cuts, total_dur, seq)` und `failed(err, seq)` — keine Stage-Progress-Signale.
- `ui/controllers/edit_workspace.py:199-264` `_auto_edit_to_beat` startet `AutoEditWorker` via `worker_dispatcher`. Buttons werden disabled, kein Vollbild-Loader.

### Timeline / Clips / Auto-Edit

- `ui/timeline.py:84-444` `TimelineClipItem(QGraphicsRectItem)` — kein `locked`-Feld, kein Lock-Icon.
- `ui/timeline.py:448` `InteractiveTimeline(QGraphicsView)` — `QUndoStack` (Zeile 476) ist aktiv und hält bestehende Move/Add/Remove/Trim-Commands.
- `ui/undo_commands.py:24-275` `MoveClipCommand`, `AddClipCommand`, `RemoveClipCommand`, `TrimClipCommand`.
- `ui/undo_commands.py:276-331` `ApplyAutoEditCommand` — der `redo` löscht heute alle `TimelineEntry` mit `track="video"` und schreibt neue. Es gibt keine Berücksichtigung eines Lock-Flags.
- `services/timeline_service.py` `apply_auto_edit_segments(...)` — Backend-Funktion für den Bulk-Replace; muss um Lock-Filter erweitert werden.
- `database/models.py:434-470` `TimelineEntry` — kein `locked`-Feld; vorhanden sind `track`, `media_id`, `start_time`, `end_time`, `lane`, `crossfade_duration`, `source_start/end`, `brightness`, `contrast`. Anker-Beziehung über `ClipAnchor`.

### Cockpit / Recent Projects

- `services/cockpit_orchestrator.py:24,97-104,210-275` definiert `CockpitAction` mit den Keys `open_auto_edit` und `open_review`.
- `ui/controllers/workspace_setup.py:417-441` `_handle_cockpit_action` mappt diese auf `nav_bar.set_workspace(2)` bzw. `(3)`.

### QSettings / Persistenz

- `ui/controllers/workspace_setup.py:590-618` speichert/restoriert `workflowStageIndex` (Tab-Index 0..4) und `rightTabIndex`.

### Tests, die heute auf 5 Tabs / Stage-Wechsel pinnen

- `tests/ui/test_frontend_rebuild_contract.py:24-34` `test_workflow_navigation_names_are_final` prüft hart die fünf Top-Tab-Namen.
- `tests/ui/test_workspaces_smoke.py:137,142` prüft `_tabs.tabText(0) == "AUTO-SCHNITT"` / `"REVIEW"` nach `set_workflow_stage()`.
- `e2e_render_test.py:141` ruft `workspace_stack.setCurrentIndex(4)` — Stack hat aktuell nur vier Widgets (Index 0..3); bestehender Off-by-One/Bug.

### Aktueller Sub-Tab-Stand im Review

- Sub-Tab-Texte „TIMELINE", „PACING", „INSPECTOR", „ANKER" werden in `EditWorkspace` ausgespart oder im `expert_tools` versteckt. Der Tooltip „Timeline, Vorschau, Inspector und Anker pruefen" (`ui/widgets/nav_bar.py:67`) verspricht die Anker-Sicht, die im Review-Page gar nicht eingebunden ist.
- `btn_toggle_inspector` (`ui/workspaces/edit_workspace.py:168-174` + `ui/controllers/workspace_setup.py:620-626`) ist Tot-Code: hide/show auf einem Tab-Inhalt hat keine Wirkung.

## Externe Vergleichsmuster

Mindestens fünf Ansätze wurden verglichen:

- DaVinci Resolve „Cut Page" — eine einzige Cut-Surface mit Source/Timeline-Stack, Auto-Edit per Klick, persistenter Inspector. Quelle: https://www.blackmagicdesign.com/products/davinciresolve/cut
- Final Cut Pro Magnetic Timeline mit Locked Roles — Rollen/Spuren lassen sich gegen Veränderung sperren; Re-Edits respektieren Sperren. Quelle: https://support.apple.com/guide/final-cut-pro/locking-roles-vera60734a4/mac
- Premiere Pro — „Track Lock" (Vorhängeschloss-Icon pro Spur) verhindert Schreibzugriffe von Trim/Re-Generate. Quelle: https://helpx.adobe.com/premiere-pro/using/working-with-tracks.html
- Adobe Express / Captions Auto-Edit — Empty-State mit „Wähle Stil" als großer Hero-Button, danach Loader mit Status-Texten, danach Editor. Quelle: https://www.adobe.com/express/feature/video/auto-edit
- Figma / VSCode — Notes/Comments als persistente Side-Panel-Tabs neben dem Hauptarbeitsbereich. Quelle: https://help.figma.com/hc/en-us/articles/360050818354

Übernommene Prinzipien: ein einziger primärer Schnitt-Workspace mit klaren Modi (Empty/Loading/Editor); Lock-Konzept pro Clip statt nur pro Spur, weil PB Studio mit beat-synchronen Einzel-Clips arbeitet; Auto-Edit-Run mit explizitem Confirm vor destruktivem Re-Write.

## Zielbild UI

### Hauptnavigation

Vier Top-Tabs:

| Index | Name | View-Klasse | Datei |
|---|---|---|---|
| 0 | PROJEKT | `ProjectDashboard` | `ui/workspaces/workflow_pages.py:43` |
| 1 | MATERIAL & ANALYSE | `MaterialAnalysisWorkspace` | `ui/workspaces/workflow_pages.py:284` |
| 2 | SCHNITT | `SchnittWorkspace` (NEU, ersetzt `EditWorkspace`) | `ui/workspaces/schnitt_workspace.py` (NEU) |
| 3 | EXPORT | `DeliverWorkspace` | `ui/workspaces/deliver_workspace.py:16` |

`WorkspaceNavBar.WORKSPACE_NAMES` und alle Tooltips/Accessible-Names/Status-Tips werden auf vier reduziert. Die Reihenfolge bleibt natürlich nach Workflow.

### SCHNITT — Drei-Zustands-Architektur

Der `SchnittWorkspace` hält ein internes `QStackedWidget` mit drei States. Wechsel werden ausschließlich vom State-Manager getrieben (siehe Datenmodell), nicht direkt aus UI-Events.

```
SchnittWorkspace (QWidget)
└── QStackedWidget (self._stack)
    ├── 0: SchnittEmptyView      (QWidget)   — Quick-Lane Presets
    ├── 1: SchnittLoadingView    (QWidget)   — Vollbild-Loader, rotierender Status-Text
    └── 2: SchnittEditorView     (QWidget)   — HBox mit Sub-Tabs + persistenter Inspector
```

#### State 0 — SchnittEmptyView

Aktiv wenn keine Timeline für das aktive Projekt existiert. Detection: `count(TimelineEntry where project_id=active_project_id and track="video") == 0`.

Inhalt zentriert:

- `QLabel` Titel: „Noch keine Timeline vorhanden."
- `QLabel` Subtitle: „Wähle einen Auto-Edit Stil, um zu starten."
- Vier Preset-Karten als große Buttons in einem horizontalen Layout (FlowLayout-fähig bei zu schmalem Fenster):
  - „Techno"  — Cut-Rate 4 Beats, Reactivity 70 %, Breakdown halve.
  - „Cinematic" — Cut-Rate 16 Beats, Reactivity 30 %, Breakdown none.
  - „House" — Cut-Rate 8 Beats, Reactivity 50 %, Breakdown halve.
  - „Festival" — Cut-Rate 2 Beats, Reactivity 90 %, Breakdown halve.
- Sekundärer Button „Eigene Einstellungen…" — wechselt direkt zu State 2 in den Sub-Tab `Pacing & Anker`, ohne Auto-Edit zu starten.

Klick auf eine Preset-Karte ruft `SchnittController.start_auto_edit_with_preset(preset_key)` auf:

1. Daten-Validation: Audio-Track + mindestens ein Video-Clip importiert? Sonst Inline-Hinweis und Sprung zu MATERIAL & ANALYSE.
2. State-Switch zu 1 (Loading).
3. `AutoEditWorker` starten mit `PacingProfile.from_preset(preset_key)`.

#### State 1 — SchnittLoadingView

Aktiv während laufender Auto-Edit- oder Re-Generate-Operation. Inhalt:

- Großer Spinner (Qt-`QProgressIndicator` als Custom-Widget oder animiertes `QMovie`).
- `QLabel` rotierender Status-Text. Mögliche Texte:
  - „Analysiere Audio…"
  - „Bestimme Beatgrid…"
  - „Setze Schnitte…"
  - „Wähle Clips aus…"
  - „Synchronisiere mit Anker…"
- Kleiner sekundärer Button „Abbrechen" → ruft `AutoEditWorker.cancel()` auf, wechselt zurück zu State 0 oder 2 (je nach vorherigem State).

Worker müssen ein `progress(stage_key: str, fraction: float)`-Signal emittieren — siehe Datenmodell. Der State-Manager mappt `stage_key` auf den menschenlesbaren Text. Wechsel zu State 2 erfolgt im `done`-Handler.

#### State 2 — SchnittEditorView

Aktiv nach erfolgreicher Generierung oder bei vorhandener Timeline.

Layout: `QHBoxLayout`

```
SchnittEditorView (QHBoxLayout)
├── QTabWidget (self._sub_tabs, stretch=3)
│   ├── Sub-Tab "Schnitt"          → SchnittTabSchnitt
│   ├── Sub-Tab "Pacing & Anker"   → SchnittTabPacingAnker
│   ├── Sub-Tab "Audio"            → SchnittTabAudio
│   └── Sub-Tab "RL & Notes"       → SchnittTabRlNotes
└── ClipInspectorPanel (persistent, stretch=1)
```

Der `ClipInspectorPanel` lebt als rechte Spalte und reagiert auf das `selection_changed`-Signal der `InteractiveTimeline` unabhängig vom aktiven Sub-Tab.

##### Sub-Tab „Schnitt"

Vertikales Layout:

- Video-Preview-Widget (`VideoPreviewWidget`, fix 640×360, zentriert).
- Transport-Row: ▶/⏸, ⏹, Frame-Step −/+, A-B-Loop, Zeitanzeige `MM:SS / MM:SS`.
- `InteractiveTimeline` (vergrößert gegenüber heute; `stretch=1`).
- Cut-Info-Label am unteren Rand: „47 Cuts · 03:45 · 4 Anker · BPM 128".

**Clip-Locking:** Jeder `TimelineClipItem` zeichnet rechts oben ein Lock-Icon (`AnchorMarkerItem`-ähnliche Sub-Item-Klasse `LockIconItem`). Default: ungesperrt (offenes Schloss, semitransparent). Klick auf das Icon togglet das `locked`-Flag, sendet einen neuen `ToggleClipLockCommand` in den `QUndoStack`, persistiert via `apply_lock_change(entry_id, locked)` in `services/timeline_service.py`. Visueller State: gesperrte Clips bekommen einen Goldrand und ein gefülltes Schloss-Icon.

##### Sub-Tab „Pacing & Anker"

Zwei Spalten (Splitter, default 50:50):

Linke Spalte „Pacing":
- `PacingCurveWidget` groß (Mindesthöhe 280 px).
- Cut-Rate-Combo, Style-Preset-Combo, Breakdown-Combo.
- Reactivity-Slider gekoppelt mit Spinbox.
- Vibe-Eingabe.
- Action-Row mit primärem Button **„Mit neuem Pacing generieren"** (orange, betont). Klick triggert `SchnittController.regenerate_with_pacing()`:
  1. `QMessageBox.warning(self, "Re-Generate?", "Achtung: Dies überschreibt aktuelle ungelockte Schnitte. Fortfahren?")` mit Yes/No.
  2. Bei Yes: Aktuellen Timeline-State als `TimelineSnapshot(label="Vor Re-Generate")` persistieren; State-Switch zu 1; Worker mit aktuellem `PacingProfile` starten; Worker respektiert `locked=True`-Entries (siehe Service-Refactor).
  3. Bei No: nichts passiert.

Rechte Spalte „Anker":
- `QTreeWidget` mit Spalten Zeit / Video / Label / Gewicht; sortierbar.
- Toolbar darunter: `+ Anker`, `− Anker`, `Sync`, `Als KI-Lernregel speichern`.
- Doppelklick auf einen Anker springt im Sub-Tab „Schnitt" zur entsprechenden Timeline-Position.

##### Sub-Tab „Audio"

Vertikales Layout:

- Audio-Waveform-Widget (`WaveformItem` aus `ui/waveform_item.py`, MinHöhe 100 px) mit Beatgrid-Overlay und Strukturmarkern (Intro / Drop / Outro / Buildup / Breakdown).
- Stems-Mixer-Section: vier Reihen `StemTrackWidget` für Vocals / Drums / Bass / Other mit Vol-Slider, Mute, Solo.
- Stem-Player-Transport (`StemTransport`).
- LUFS-Meter-Widget rechts oben.
- Tonart-Display („Cm — 7A").

##### Sub-Tab „RL & Notes"

Zwei Spalten:

Linke Spalte „RL Feedback":
- Header „Wie beurteilst du den letzten Auto-Edit?".
- Zwei große Buttons 👍 / 👎 (verbindet die heutigen `btn_thumbs_up` / `btn_thumbs_down`).
- Liste der jüngsten RL-Events (Brain V3, aus `_brain_v3_feedback_service`): Datum, Confidence, gespeicherter Anker.

Rechte Spalte „Notes":
- `QTextEdit` mit Markdown-Highlighting; Auto-Save bei `textChanged` (Debounce 1000 ms) → `update_project_notes(project_id, content_md)`.
- Footer-Label „Zuletzt gespeichert: HH:MM:SS".

### Persistenter Inspector

`ClipInspectorPanel` (rechte Spalte) zeigt:
- Datei + In/Out + Dauer.
- Beat-Sync-Status (✓ Beat N / Off-Beat).
- Motion-Score, SigLIP-Tags.
- Keyframe-Kontext (read-only, aus MATERIAL & ANALYSE).
- Brain-V3-Confidence-Bar.

Beim Wechsel zwischen Sub-Tabs bleibt der Inspector sichtbar und gefüllt — kein Tab-Wechsel-Flicker.

### Maus-Schutz

Damit Combos/Slider/Spinbox nicht durch versehentliches Mausrad-Drüberscrollen verstellt werden:

- Globaler `EventFilter` `WheelGuard` für `QComboBox`, `QSlider`, `QSpinBox`, `QDoubleSpinBox`:
  - `QEvent.Wheel` wird nur durchgereicht, wenn das Widget den Fokus hat.
  - Sonst `event.ignore()` — das Wheel-Event scrollt das umgebende Scroll-Area weiter.
- `setFocusPolicy(Qt.StrongFocus)` für alle betroffenen Widgets statt `Qt.WheelFocus`.
- `PacingCurveWidget`: Drag-Threshold von 4 px für Knot-Movements, damit ein versehentliches Klicken keine Kurve verschiebt.
- `QTreeWidget` (Anker-Liste): kein Auto-Sort-Wechsel beim Hover; Sort-Klick muss bewusst sein.

Implementierungsort: `ui/widgets/wheel_guard.py` (NEU). Application-weit installieren in `main.py` über `app.installEventFilter(WheelGuard(app))`.

## Datenarchitektur

### `PacingProfile` (Dataclass)

`services/pacing_profile.py` (NEU):

```python
@dataclass(slots=True)
class PacingProfile:
    audio_id: int | None = None
    video_id: int | None = None
    vibe: str = ""
    cut_rate_index: int = 2          # 0..4 → 1/2/4/8/16 Beats
    style_preset: str = "Standard"   # eines der bekannten Presets
    energy_reactivity: int = 50      # 0..100
    breakdown: str = "halve"         # halve | force16 | none
    manual_density_curve: list[float] | None = None
    anchors: list[ClipAnchorRef] = field(default_factory=list)

    @classmethod
    def from_preset(cls, key: str) -> "PacingProfile":
        ...

    def to_advanced_settings(self) -> AdvancedPacingSettings:
        ...
```

UI-Widgets binden bidirektional an dieses Objekt über einen kleinen `Binder` (`services/ui_binder.py` NEU). Alle Worker bekommen das Profil als Argument; sie lesen NICHT direkt aus Widgets.

### `TimelineState` (Dataclass)

`services/timeline_state.py` (NEU):

```python
@dataclass(slots=True)
class ClipEntry:
    entry_id: int
    media_id: int
    track: str          # "audio" | "video"
    start: float
    end: float
    lane: int
    locked: bool = False
    source_start: float = 0.0
    source_end: float | None = None

@dataclass(slots=True)
class TimelineState:
    project_id: int
    version: int
    clips: list[ClipEntry]
    snapshot_label: str | None = None

    def lock_count(self) -> int:
        return sum(1 for c in self.clips if c.locked)

    @classmethod
    def load(cls, project_id: int) -> "TimelineState":
        ...

    def save_snapshot(self, label: str) -> int:
        ...
```

`InteractiveTimeline` hält weiterhin die Live-`QGraphicsScene`, aber synchronisiert über `TimelineState.load/save_snapshot` mit der DB.

### Hybrid Undo

- Live-Undo: bestehender `QUndoStack` pro `InteractiveTimeline`. Neue Commands:
  - `ToggleClipLockCommand(entry_id, new_locked)`.
  - `ApplyAutoEditCommand` wird angepasst: respektiert `locked=True`-Entries; `redo` schreibt nur ungesperrte Clips.
  - `RestoreSnapshotCommand(snapshot_id)` für Versions-History.
- Persistente Snapshots: bei jedem Auto-Edit-Run und jedem Re-Generate ein Snapshot in `timeline_snapshots`. UI: Versions-History-Panel (Toolbar-Button im Sub-Tab „Schnitt", öffnet Side-Drawer mit Liste).

## DB-Migrationen

### `TimelineEntry.locked` (neue Column)

`database/models.py` ergänzt:

```python
locked = Column(Boolean, nullable=False, default=False, server_default="0")
```

Migration in `database/migrations.py`:

```sql
ALTER TABLE timeline_entries ADD COLUMN locked BOOLEAN NOT NULL DEFAULT 0;
```

Konsumenten:
- `services/timeline_service.apply_auto_edit_segments` filtert vor Bulk-Replace: `session.query(TimelineEntry).filter_by(project_id=p, track="video", locked=False).delete()`. Gesperrte Clips bleiben unangetastet; neue Segmente werden danach addiert mit Range-Konflikt-Detection (Locked-Range darf nicht durch neue Segmente überlappt werden — bei Konflikt: neuer Segment-Boundary auf Lock-Range klemmen).

### `TimelineSnapshot` (neue Tabelle)

```python
class TimelineSnapshot(Base):
    __tablename__ = "timeline_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    label = Column(String, nullable=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (Index("idx_snapshot_project_version", "project_id", "version"),)
```

Migration:

```sql
CREATE TABLE timeline_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    label TEXT,
    payload_json TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_snapshot_project_version ON timeline_snapshots(project_id, version);
```

Service: `services/timeline_snapshot_service.py` mit `create_snapshot(project_id, label) -> int`, `list_snapshots(project_id) -> list[Snapshot]`, `restore_snapshot(snapshot_id)`.

### `ProjectNotes` (neue Tabelle)

```python
class ProjectNote(Base):
    __tablename__ = "project_notes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    content_md = Column(Text, nullable=False, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

Migration:

```sql
CREATE TABLE project_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    content_md TEXT NOT NULL DEFAULT '',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Service: `services/project_notes_service.py` mit `get_notes(project_id) -> str`, `update_notes(project_id, content_md)`.

## Worker-Refactor

`AutoEditWorker` und `_CutsWorker` bekommen ein `progress(stage_key: str, fraction: float)`-Signal. Mögliche `stage_key`-Werte und ihre Mapping-Texte:

| stage_key | Anzeige |
|---|---|
| `audio_load` | „Lade Audio…" |
| `beat_grid` | „Bestimme Beatgrid…" |
| `structure` | „Erkenne Songstruktur…" |
| `cut_calc` | „Setze Schnitte…" |
| `clip_select` | „Wähle Clips aus…" |
| `anchor_sync` | „Synchronisiere Anker…" |
| `db_write` | „Speichere Timeline…" |

`SchnittLoadingView` zeigt den Text des letzten empfangenen `stage_key`. Fraction wird in einem dünnen Bottom-Progress-Bar visualisiert.

`AutoEditWorker.cancel()` muss kooperativ sein (Cancel-Flag pro Stage, Check zwischen Stages). Bei Cancel: Worker bricht ab, `SchnittController` wechselt State zu 0 (wenn keine Timeline) oder 2 (wenn Timeline existiert).

## Konsumenten-Re-Map

### `ui/widgets/nav_bar.py`

Reduziere `WORKSPACE_NAMES`, `tooltips`, `accessible_names`, `status_tips` jeweils auf vier Einträge:

```python
WORKSPACE_NAMES = ["PROJEKT", "MATERIAL & ANALYSE", "SCHNITT", "EXPORT"]
```

Tooltip für SCHNITT: „Schnitt: Auto-Edit, Pacing, Anker, Audio-Mixer und Notes — alles in einem Workspace."

### `ui/controllers/workspace_setup.py`

- `_create_workspaces` baut vier Stack-Widgets: `_project_dashboard`, `_material_analysis_ws`, `_schnitt_ws` (NEU), `_deliver_ws`. `_edit_ws` entfällt.
- `_handle_cockpit_action`: `open_auto_edit` und `open_review` werden zu `open_schnitt` zusammengeführt. Backward-Compat: Cockpit-Action-Service kann beide alten Keys auf `open_schnitt` weiterleiten.
- `_on_workspace_changed(index)` reduziert von 5 auf 4 Branches; jeder Branch setzt nur noch den Stack-Index. Kein `set_workflow_stage` mehr.

### `services/cockpit_orchestrator.py`

- Neue `ACTIONS["open_schnitt"]` mit Label „SCHNITT öffnen".
- `ACTIONS["open_auto_edit"]` und `ACTIONS["open_review"]` werden zu Aliassen für `open_schnitt` (Soft-Deprecation für externe Konsumenten).
- `compute_next_action(...)` (sinngemäß `cockpit_orchestrator.py:275`) gibt bei „Timeline existiert nicht" die `open_schnitt`-Action mit `description="Auto-Edit starten"` zurück; bei „Timeline existiert" mit `description="Timeline prüfen und feinjustieren"`. Empty/Editor-State steuert SchnittController automatisch.

### QSettings-Migration

`workspace_setup.py:603` `_restore_window_state` lädt `workflowStageIndex`. Wenn Wert `3` oder `4` gespeichert ist (alter REVIEW oder EXPORT), wird er in einen Migrationsschritt umgemappt: `3 → 2` (REVIEW → SCHNITT), `4 → 3` (EXPORT bleibt am Ende). Migration einmalig pro Nutzer; danach `workflowStageMigratedV2 = true` setzen, damit kein Re-Map.

```python
def _migrate_workflow_stage_index(settings: QSettings) -> None:
    if settings.value("window/workflowStageMigratedV2", False, type=bool):
        return
    raw = settings.value("window/workflowStageIndex")
    if raw is None:
        settings.setValue("window/workflowStageMigratedV2", True)
        return
    try:
        old = int(raw)
    except (TypeError, ValueError):
        old = 0
    new = {0: 0, 1: 1, 2: 2, 3: 2, 4: 3}.get(old, 0)
    settings.setValue("window/workflowStageIndex", new)
    settings.setValue("window/workflowStageMigratedV2", True)
```

## Empty-State-Detection

`SchnittController` registriert sich beim Projekt-Wechsel und beim Tab-Eintritt:

```python
def detect_state(self, project_id: int) -> int:
    if self._is_worker_running():
        return 1
    if project_id is None:
        return 0
    with nullpool_session() as s:
        n = s.query(TimelineEntry).filter_by(
            project_id=project_id, track="video"
        ).count()
    return 2 if n > 0 else 0
```

Auslöser für Re-Detection:
- `project_manager._on_project_changed`.
- `nav_bar.workspace_changed` mit Ziel-Index 2.
- `ApplyAutoEditCommand.redo` finished.
- `RestoreSnapshotCommand.redo` finished.
- Manueller Button „Timeline leeren" im Sub-Tab „Schnitt" (löscht alle ungesperrten Clips, danach Re-Detection).

## Test-Plan

### Bestehende Tests, die angepasst werden

- `tests/ui/test_frontend_rebuild_contract.py` — neuer Soll-Wert:
  ```python
  assert WorkspaceNavBar.WORKSPACE_NAMES == ["PROJEKT", "MATERIAL & ANALYSE", "SCHNITT", "EXPORT"]
  ```
- `tests/ui/test_workspaces_smoke.py` — die `set_workflow_stage`-Asserts entfallen; statt dessen prüfe:
  - State 0 sichtbar nach Projekt-Open ohne Timeline.
  - Sub-Tab-Texte im Editor-State `["Schnitt", "Pacing & Anker", "Audio", "RL & Notes"]`.
- `e2e_render_test.py:141` — Off-by-One fixen: `setCurrentIndex(3)` statt `(4)`.

### Neue Tests

- `tests/ui/test_schnitt_workspace_states.py` — Empty/Loading/Editor-Switch, Worker-cancel-Path, Re-Detection bei Projektwechsel.
- `tests/ui/test_schnitt_clip_locking.py` — Lock-Toggle persistiert in DB, `ApplyAutoEditCommand.redo` lässt gesperrte Clips unverändert, Range-Konflikt-Klemmung.
- `tests/ui/test_schnitt_safety_dialog.py` — QMessageBox erscheint bei Re-Generate, „No" wechselt nicht in Loading.
- `tests/ui/test_schnitt_wheel_guard.py` — `WheelGuard` blockiert Wheel auf unfokussiertem Combo/Slider/Spinbox.
- `tests/test_services/test_timeline_snapshot_persistence.py` — Snapshot-Create, List, Restore.
- `tests/test_services/test_project_notes.py` — CRUD inklusive Auto-Save-Idempotenz.
- `tests/test_services/test_pacing_profile_binding.py` — Bidirektionales Binding zwischen `PacingProfile` und Widgets.

## Risiko-Mitigation (vollständig durchgegangen)

| # | Punkt | Mitigation |
|---|---|---|
| 1 | `TimelineEntry.locked` Column + Migration | Schema oben; Default `False`; Backfill nicht nötig (alle Bestandsclips ungesperrt). |
| 2 | `TimelineClipItem` lockable | Neue `LockIconItem`-Sub-Klasse; State + Visualisierung; Toggle-Click via `mousePressEvent` mit Hit-Test auf das Icon. |
| 3 | `ApplyAutoEditCommand` respektiert Lock | Service-Filter `locked=False` vor Bulk-Delete; Range-Klemmung neuer Segmente an Lock-Boundaries. |
| 4 | `test_frontend_rebuild_contract.py` Anpassung | siehe Test-Plan. |
| 5 | `test_workspaces_smoke.py` Anpassung | siehe Test-Plan. |
| 6 | `e2e_render_test.py:141` Index-Bug | `setCurrentIndex(3)`. |
| 7 | `cockpit_orchestrator` `open_schnitt` | Aliassieren der alten Keys, Soft-Deprecation; siehe oben. |
| 8 | `workspace_setup` Re-Map | siehe oben; nur noch vier Branches. |
| 9 | `_on_workspace_changed` reduziert | siehe oben. |
| 10 | `QSettings workflowStageIndex` Migration | siehe `_migrate_workflow_stage_index`. |
| 11 | `nav_bar` reduziert | `WORKSPACE_NAMES` + Tooltips + Accessible-Names + Status-Tips. |
| 12 | `PacingProfile`-Dataclass | Neuer Service; `Binder` für UI; Worker bekommen Profil. |
| 13 | `TimelineState`-Dataclass + Versionierung | Neuer Service; Snapshot-DB-Schema; Versions-History-Panel. |
| 14 | Undo Hybrid | `QUndoStack` + persistente Snapshots; neue Commands `ToggleClipLockCommand`, `RestoreSnapshotCommand`. |
| 15 | Worker-Stage-Progress | Worker-Refactor mit `progress(stage_key, fraction)`-Signal. |
| 16 | Empty-State-Detection | siehe `SchnittController.detect_state`. |
| 17 | Persistenter Inspector | rechte Spalte, außerhalb der Sub-Tabs. |
| 18 | Sub-Tab Notes | DB-Tabelle `project_notes` + Service + UI. |
| 19 | Maus-Schutz | `WheelGuard`-EventFilter; `Qt.StrongFocus`. |
| 20 | Legacy `btn_toggle_inspector` entfernen | Tot-Code in `workspace_setup.py:620-626` und `edit_workspace.py:168-174` löschen. |
| 21 | Brain-V3-Confidence bei gelockten Clips | gesperrte Clips überspringen Re-Inferenz, Confidence bleibt auf zuletzt persistiertem Wert. |
| 22 | `style_preset_combo` | aus Risiko-Liste gestrichen — Combo existiert in `_build_pacing_tab`. |

## Datei-Layout (Soll-Zustand)

```
ui/workspaces/schnitt_workspace.py            (NEU, ersetzt edit_workspace.py)
ui/workspaces/schnitt/
    __init__.py
    empty_view.py                              (NEU)
    loading_view.py                            (NEU)
    editor_view.py                             (NEU)
    tab_schnitt.py                             (NEU)
    tab_pacing_anker.py                        (NEU)
    tab_audio.py                               (NEU)
    tab_rl_notes.py                            (NEU)
ui/widgets/wheel_guard.py                      (NEU)
ui/widgets/lock_icon_item.py                   (NEU)
services/pacing_profile.py                     (NEU)
services/timeline_state.py                     (NEU)
services/timeline_snapshot_service.py          (NEU)
services/project_notes_service.py              (NEU)
services/ui_binder.py                          (NEU)
services/timeline_service.py                   (PATCH: lock-aware apply_auto_edit_segments)
ui/undo_commands.py                            (PATCH: ToggleClipLockCommand, RestoreSnapshotCommand)
database/models.py                             (PATCH: TimelineEntry.locked, TimelineSnapshot, ProjectNote)
database/migrations.py                         (PATCH: drei neue Migrationsschritte)
ui/widgets/nav_bar.py                          (PATCH: 4 Tabs)
ui/controllers/workspace_setup.py              (PATCH: vier Stack-Widgets, neuer Mapping)
ui/controllers/edit_workspace.py               (REPLACE → SchnittController)
services/cockpit_orchestrator.py               (PATCH: open_schnitt + Aliasse)
main.py                                        (PATCH: WheelGuard, settings-migration call)
ui/workspaces/edit_workspace.py                (DELETE nach Migration aller Imports)
```

## Migrations-Strategie / Rollout

Schrittfolge für Implementation (greift in `writing-plans`-Skill als Implementations-Plan):

1. DB-Migrationen + Modelle (`TimelineEntry.locked`, `TimelineSnapshot`, `ProjectNote`).
2. Datenklassen + Services (`PacingProfile`, `TimelineState`, `TimelineSnapshotService`, `ProjectNotesService`).
3. `WheelGuard` + `LockIconItem` als Building Blocks.
4. `SchnittWorkspace` Skeleton (drei Views) ohne Sub-Tab-Inhalt.
5. Sub-Tab `Schnitt` (Preview + Timeline + Locking).
6. Sub-Tab `Pacing & Anker` inklusive Re-Generate-Confirm-Dialog und Lock-aware `apply_auto_edit_segments`.
7. Sub-Tab `Audio`.
8. Sub-Tab `RL & Notes` mit Notes-Auto-Save.
9. Worker-Refactor (Stage-Progress) + Loading-View-Hook.
10. `nav_bar` reduzieren + Stack-Aufbau anpassen + QSettings-Migration.
11. `cockpit_orchestrator` `open_schnitt`.
12. Tests anpassen + neue Tests ergänzen.
13. Legacy-Code entfernen (`btn_toggle_inspector`, `EditWorkspace`).
14. Live-Verifikation mit Test-Datensatz Solo_Natur + Crusty Progressive Psy Set2.

Status `fixed` setzt nur der User nach Live-Verifikation.

## Offene Punkte

Keine. Alle Klärungsfragen wurden 2026-05-09 beantwortet (siehe Vault-Anker oben).

## Vault-Anker

Living Plan: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-workspace-redesign-2026-05-09.md`. Diese Spec und der Vault-Plan müssen bei jeder Folge-Iteration synchron gehalten werden.
