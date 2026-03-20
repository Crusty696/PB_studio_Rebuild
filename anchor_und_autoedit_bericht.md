# Anchor-System & Intelligent Auto-Edit — Architektur-Bericht

## Datum: 2026-03-20

---

## SEKTOR 1: Anchor-System (Manuelle Synchronisation)

### Datenmodell

**Neue Tabelle: `clip_anchors`** (database.py)

| Feld | Typ | Beschreibung |
|------|-----|-------------|
| `id` | Integer PK | Auto-increment |
| `timeline_entry_id` | FK -> timeline_entries | Referenz zum Clip |
| `time_offset` | Float | Offset in Sekunden relativ zum Clip-Start |
| `label` | String | Optionaler Name |
| `color` | String | Hex-Farbe (default: #FF3333) |

### UI-Komponenten

**AnchorMarkerItem** (main.py)
- Visuell: Rotes Dreieck (Pfeil nach unten) + gestrichelte rote Vertikallinie
- Gerendert als `QGraphicsPolygonItem` mit Child `QGraphicsLineItem`
- ZValue 9-10 (ueber allen anderen Clip-Elementen)

**Anker setzen — 3 Wege:**
1. **Rechtsklick** auf einen Clip -> Kontextmenue "Anker setzen (X.XXs)"
   - Setzt den Anker exakt an der Mausposition
2. **Taste M** — setzt Anker in der Mitte des selektierten Clips
3. Beide Methoden speichern sofort in die DB

**Anker synchronisieren:**
- Button "Anker synchronisieren" im Inspector Panel
- Methode `InteractiveTimeline.sync_anchors()`
- Algorithmus:
  1. Finde alle Audio-Clips mit Ankern
  2. Finde alle Video-Clips mit Ankern
  3. Berechne: `neuer_video_start = audio_anker_absolut - video_anker_offset`
  4. Verschiebe den Video-Clip, sodass beide Anker exakt uebereinander liegen
  5. Aktualisiere die DB

### Kontextmenue (Rechtsklick auf Clip)
- "Anker setzen (X.XXs)" — Neuen Anker an Mausposition
- "Alle Anker entfernen" — Loescht alle Anker dieses Clips
- Info-Zeile: Clip-Typ und Media-ID

---

## SEKTOR 2: Intelligent Auto-Edit Engine

### Kernprinzip
**Jeder Schnitt faellt AUSNAHMSLOS auf einen Beat-Timestamp aus dem Beatgrid.**

### Beat-Quellen (Prioritaet)
1. **Beatgrid aus der DB** (`beatgrids.beat_positions` JSON)
2. **BPM-generierte Beats** (Fallback: `60.0 / bpm` Intervall ab offset)
3. **Feste Intervalle** (letzter Fallback ohne Audio)

### Algorithmus: `auto_edit_to_beats()` (pacing_service.py)

```
1. Lade Beat-Positionen aus dem Beatgrid
2. Filtere Beats anhand der Pacing-Kurve (_select_cut_beats)
3. Fuege Start (0.0) und Ende (total_duration) hinzu
4. Fuer jedes Beat-Segment:
   a. Waehle naechsten Video-Clip (Round-Robin)
   b. Berechne source_start (interner Clip-Offset)
   c. Bei zu kurzem Material: Loop (Clip von vorne)
   d. Erzeuge Segment-Dict
```

### Drum-Cut Snapping
`calculate_drum_cuts()` snapped Drum-Onsets auf den naechsten Beat:
- Librosa Onset-Detection auf dem Drums-Stem
- `np.argmin(np.abs(beats - onset_time))` findet den naechsten Beat
- Max. Snap-Distanz: 0.15 Sekunden
- Deduplizierung: Jeder Beat wird nur einmal verwendet

---

## SEKTOR 3: Pacing-Kurve x Beatgrid

### Dichtemapping

| Kurven-Wert | Beat-Step | Beschreibung |
|-------------|-----------|-------------|
| >= 0.80 | 1 | Jeden Beat (schnell) |
| 0.50 - 0.79 | 2 | Jeden 2. Beat |
| 0.30 - 0.49 | 4 | Jeden 4. Beat (Downbeats) |
| 0.15 - 0.29 | 8 | Jeden 8. Beat |
| < 0.15 | 16 | Jeden 16. Beat (ruhig) |

### Kombination Tempo-Slider + Pacing-Kurve

```python
if density >= 0.5:
    effective_step = min(base_step, curve_step)  # Mehr Cuts
else:
    effective_step = max(base_step, curve_step)  # Weniger Cuts
```

- **Hohe Kurve + hoher Tempo**: Maximale Schnittdichte (jeden Beat)
- **Hohe Kurve + niedriger Tempo**: Kurve dominiert (mehr Cuts als Slider)
- **Niedrige Kurve + hoher Tempo**: Kurve bremst (weniger Cuts als Slider)
- **Niedrige Kurve + niedriger Tempo**: Minimale Schnittdichte (jeden 16. Beat)

### Szenen-Snapping
Video-Szenen-Wechsel werden auf den naechsten Beat gesnappt:
```python
idx = np.searchsorted(beats_arr, scene.start_time)
snapped = beats_arr[idx]
```

### Downbeat-Betonung
Jeder 4. Beat erhaelt automatisch +0.15 Staerke (Downbeat = Taktanfang).

---

## Datenfluesse

### Auto-Edit Workflow
```
User zeichnet Pacing-Kurve
        |
User klickt "Auto-Edit to Beat"
        |
AutoEditWorker (Background Thread)
        |
auto_edit_to_beats(audio_id, video_ids, duration, pacing_curve, tempo)
        |
_get_beat_positions() --> Beatgrid aus DB
        |
_select_cut_beats() --> Pacing-Kurve filtert Beats
        |
Segmente erzeugen (Round-Robin, Loop bei zu kurzen Clips)
        |
TimelineEntry-Records in DB schreiben
        |
Timeline-View aktualisieren
```

### Anchor Sync Workflow
```
User setzt Anker auf Audio-Clip (Rechtsklick / M)
User setzt Anker auf Video-Clip (Rechtsklick / M)
User klickt "Anker synchronisieren"
        |
sync_anchors()
        |
audio_anchor_abs = audio_clip_start + audio_anchor_offset
new_video_start = audio_anchor_abs - video_anchor_offset
        |
Video-Clip verschieben + DB update
```

---

## Geaenderte Dateien

| Datei | Aenderung |
|-------|----------|
| `database.py` | Neue Klasse `ClipAnchor` (Tabelle `clip_anchors`) |
| `services/pacing_service.py` | Komplett neu: Beatgrid-basierte Cuts, Pacing-Kurve, Beat-Snapping |
| `main.py` | `AnchorMarkerItem`, `TimelineClipItem` mit Anker-Support, `sync_anchors()`, aktualisierter Auto-Edit |

## Test-Ergebnisse

- Syntax-Check: Alle 3 Dateien kompilieren fehlerfrei
- Density-Mapping: 5/5 Tests bestanden
- Pacing-Kurve Filterung: High density (100 Cuts) vs. Low density (7 Cuts) korrekt
- Fallback-Pfade: Ohne Audio/Video werden 6 Fallback-Cuts generiert
