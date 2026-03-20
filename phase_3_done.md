# Phase 3: Intelligence — Abgeschlossen

**Datum:** 2026-03-20
**Status:** FERTIG

---

## Sektor 1: Advanced Pacing UI (DJ-Regler)

Im EDIT-Workspace wurden die alten Tempo/Energie/Dichte-Slider durch praezise DJ-Regler ersetzt:

| Regler | Typ | Funktion |
|--------|-----|----------|
| **Base Cut Rate** | ComboBox | 1, 2, 4, 8, 16 Beats — Basis-Schnittintervall |
| **Energy Reactivity** | Slider + SpinBox (0-100%) | Erhoeht Cut-Rate bei hohem Audio-RMS |
| **Breakdown Behavior** | ComboBox | "Cuts halbieren", "16-Beat erzwingen", "Keine Cuts" |

Alle Regler steuern die Phase 3 Pacing-Engine direkt.

## Sektor 2: Pacing Engine & OTIO

### Neue Datei: `services/pacing_service.py` (komplett ueberarbeitet)

**Algorithmus:**
1. Audio-Dauer diktiert die OTIO-Timeline-Laenge (ZWINGENDE REGEL).
2. Beats + Downbeats aus SQLite (beat_this-Ergebnisse) laden.
3. Per-Beat RMS-Energie fuer Energy Reactivity nutzen.
4. `_compute_effective_step()`: Kombiniert Base Cut Rate + Energy Reactivity + Breakdown Behavior + Manual Pacing Curve.
5. `_select_cut_beats_advanced()`: Waehlt Cut-Beats mit dem effektiven Schritt aus.
6. `_match_video_for_segment()`: LanceDB Semantic Search bei Vibe-Keyword, sonst Motion-Score/Round-Robin.
7. Intelligentes Looping bei zu wenig Video-Material.

**Neue Datentypen:**
- `AdvancedPacingSettings` — DJ-Regler Einstellungen
- `TimelineSegment` — OTIO-konformes Segment mit Video-Pfad und Anker-Info

### DB-Schema-Erweiterungen (`database.py`)
- `Beatgrid.downbeat_positions` (Text, JSON) — Downbeat-Timestamps
- `Beatgrid.energy_per_beat` (Text, JSON) — Normalisierte RMS-Energie pro Beat [0.0-1.0]
- Auto-Migration in `init_db()` fuer bestehende Datenbanken

### `beat_analysis_service.py` Update
- `analyze_and_store()` speichert jetzt Downbeats + Per-Beat-Energie
- `_compute_energy_per_beat()` — RMS pro Beat-Intervall (librosa)

## Sektor 3: Anchor System (OTIO Marker)

### UI (im EDIT-Workspace Inspector)
- **Anchor-Liste** (QTreeWidget): Zeigt alle Anker mit Zeitpunkt und Video/Szene
- **"+ Anker" Button**: Oeffnet Dialog mit Zeitpunkt-SpinBox und Szenen-Auswahl
- **"- Anker" Button**: Entfernt ausgewaehlten Anker
- **"Sync" Button**: Synchronisiert Timeline-Clips an Ankern

### OTIO-Integration
- Anker werden als `otio.schema.Marker` gespeichert mit Metadata:
  ```python
  {"pb_studio": {"scene_id": "42", "type": "anchor"}}
  ```
- Farbe: MAGENTA (sichtbar in DaVinci Resolve / Premiere)
- Pacing-Engine respektiert Anker: Erzwingt die zugewiesenen Videos an den Marker-Positionen.

### Auto-Edit Flow
1. User klickt "Auto-Edit"
2. `AutoEditWorker` laeuft im Hintergrund (QThread)
3. `auto_edit_phase3()` berechnet Segmente + CutPoints
4. SQLite TimelineEntries werden aktualisiert
5. OTIO-Timeline wird generiert und als `.otio` gespeichert
6. InteractiveTimeline zeigt die Ergebnisse mit farbigen Cut-Markern
7. CutPoint-Info zeigt Beat/Anker-Statistik

## Verifizierung

- Syntax-Check: Alle 4 geaenderten Dateien parsen fehlerfrei
- Import-Check: Alle neuen Module laden korrekt
- Pacing-Engine-Test: 128 BPM, 120s, rate=4 → 69 Cuts (korrekt moduliert)
- OTIO-Test: Timeline mit Audio + Video + Marker generiert und gespeichert

## Geaenderte Dateien

| Datei | Aenderung |
|-------|-----------|
| `database.py` | +2 Spalten (downbeat_positions, energy_per_beat), Auto-Migration |
| `services/beat_analysis_service.py` | Downbeats + Energy speichern |
| `services/pacing_service.py` | Komplett neu: Phase 3 DJ-Engine + Legacy-Compat |
| `main.py` | Advanced Pacing UI, Anchor System UI, OTIO-Wiring |
