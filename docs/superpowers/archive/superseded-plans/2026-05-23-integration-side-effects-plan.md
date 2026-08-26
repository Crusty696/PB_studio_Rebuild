# Phase 2: Lückenlose KI-Chat-Steuerung — Tiefe UI-Kontrolle

Phase 1 (abgeschlossen) hat administrative Aktionen hinzugefügt: `create_project`, `open_project`, `delete_media`, `clear_timeline`, `save_project`.

Phase 2 schließt **alle verbleibenden UI-Funktionen**, die der Benutzer manuell per Button/Menü ausführen kann, als Chat-Aktionen an.

## Vorgeschlagene Änderungen

Insgesamt **13 neue Chat-Aktionen** in 5 Kategorien:

---

### Kategorie 1: Medien-Info & Navigation (3 Aktionen)

Diese Aktionen geben dem Chat-KI **Sichtbarkeit** über den aktuellen Zustand, damit sie intelligent reagieren kann.

#### `list_media` — Alle Medien im Projekt auflisten
- **Beschreibung**: Listet alle importierten Audio-Tracks und Video-Clips mit ID, Titel, Dauer, BPM, Analyse-Status auf.
- **Parameter**: keine
- **Logik**: Ruft `get_all_audio()` und `get_all_video()` auf und gibt eine strukturierte Liste zurück.

#### `list_timeline` — Alle Timeline-Einträge auflisten
- **Beschreibung**: Zeigt den aktuellen Inhalt der Timeline mit Clip-Reihenfolge, Timecodes und Effekten.
- **Parameter**: keine
- **Logik**: Abfrage von `TimelineEntry` für das aktive Projekt, sortiert nach `start_time`.

#### `get_project_info` — Projektdetails abrufen
- **Beschreibung**: Gibt Name, Pfad, Auflösung, FPS, Anzahl Medien und Timeline-Status zurück.
- **Parameter**: keine
- **Logik**: Abfrage von `get_active_project_id()` und Projekt-Metadaten.

---

### Kategorie 2: Timeline-Manipulation (4 Aktionen)

#### `add_to_timeline` — Medium zur Timeline hinzufügen
- **Beschreibung**: Fügt ein importiertes Medium (Audio oder Video) per ID an das Ende der Timeline hinzu.
- **Parameter**:
  - `media_id` (integer, required) — ID des Mediums
  - `media_type` (string, required, enum: `["audio", "video"]`) — Typ
- **Logik**: Analog zu [_add_selected_to_timeline](file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/ui/controllers/edit_workspace.py#L913-L1023), erstellt einen `TimelineEntry` direkt in der DB am Ende der Timeline. Emittiert Signal → UI-Refresh.

#### `set_clip_effects` — Effekte auf Timeline-Clip setzen
- **Beschreibung**: Setzt Helligkeit, Kontrast und Crossfade-Dauer für einen Clip auf der Timeline.
- **Parameter**:
  - `entry_id` (integer, required) — ID des Timeline-Eintrags
  - `brightness` (number, optional, -1.0 bis 1.0, default: 0.0)
  - `contrast` (number, optional, 0.0 bis 3.0, default: 1.0)
  - `crossfade` (number, optional, 0.0 bis 5.0s, default: 0.0)
- **Logik**: Analog zu [_apply_effects](file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/ui/controllers/convert.py#L116-L143), DB-Update auf dem TimelineEntry.

#### `move_clip` — Clip auf der Timeline verschieben
- **Beschreibung**: Verschiebt einen Timeline-Clip an eine neue Startzeit.
- **Parameter**:
  - `entry_id` (integer, required) — ID des Timeline-Eintrags
  - `new_start_time` (number, required) — Neue Startzeit in Sekunden
- **Logik**: DB-Update auf `TimelineEntry.start_time` und Neuberechnung von `end_time`.

#### `remove_clip` — Einzelnen Clip von der Timeline entfernen
- **Beschreibung**: Entfernt einen bestimmten Clip von der Timeline (ohne das Medium aus dem Pool zu löschen).
- **Parameter**:
  - `entry_id` (integer, required) — ID des Timeline-Eintrags
- **Logik**: Löscht den `TimelineEntry` und zugehörige `ClipAnchor`-Einträge.

---

### Kategorie 3: Konvertierung & Export (2 Aktionen)

#### `convert_videos` — Batch-Video-Konvertierung starten
- **Beschreibung**: Konvertiert alle Videos im Pool in ein einheitliches Format.
- **Parameter**:
  - `resolution` (string, optional, default: "1920x1080")
  - `fps` (string, optional, default: "30")
  - `codec` (string, optional, enum: `["h264", "h265", "prores"]`, default: "h264")
- **Logik**: Analog zu [_standardize_all_videos](file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/ui/controllers/convert.py#L182-L228). Emittiert Signal → Worker.

#### `preview_export` — Quick-Preview der Timeline rendern
- **Beschreibung**: Rendert die ersten 10 Sekunden der Timeline als Vorschau-Video.
- **Parameter**: keine
- **Logik**: Analog zu [_start_preview_export](file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/ui/controllers/export.py#L108-L135). Emittiert Signal → Worker.

---

### Kategorie 4: Stems & Ducking (1 Aktion)

#### `auto_ducking` — Auto-Ducking starten
- **Beschreibung**: Startet automatisches Audio-Ducking (Musik leiser unter Vocals).
- **Parameter**:
  - `audio_track_id` (integer, required) — ID des Audio-Tracks (muss Stems haben)
- **Logik**: Analog zu [_start_auto_ducking](file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/ui/controllers/stems.py#L175-L209). Validiert Stem-Voraussetzungen und emittiert Signal → Worker.

---

### Kategorie 5: Pacing, Presets & Feedback (3 Aktionen)

#### `apply_style_preset` — Style-Preset auf Pacing anwenden
- **Beschreibung**: Wendet ein gespeichertes Style-Preset (Cut-Rate, Breakdown, Reaktivität) an.
- **Parameter**:
  - `preset_name` (string, required) — Name des Style-Presets
- **Logik**: Analog zu [_apply_style_preset](file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/ui/controllers/edit_workspace.py#L688-L711). DB-Abfrage + Preset-Anwendung.

#### `add_anchor` — Sync-Anker programmatisch hinzufügen
- **Beschreibung**: Fügt einen Sync-Anker an einer bestimmten Zeit für eine bestimmte Szene hinzu.
- **Parameter**:
  - `time_seconds` (number, required) — Zeitpunkt in Sekunden
  - `scene_id` (string, optional) — ID der zu synchronisierenden Szene
- **Logik**: DB-Insert eines `ClipAnchor` oder Anker-Eintrag im Anchor-Widget. Emittiert Signal → UI-Refresh.

#### `rl_feedback` — RL-Feedback auf aktuelle Timeline geben
- **Beschreibung**: Gibt positives oder negatives Reinforcement-Learning-Feedback auf den aktuellen Auto-Edit.
- **Parameter**:
  - `sentiment` (string, required, enum: `["positive", "negative"]`) — Bewertung
- **Logik**: Analog zu [_save_rl_feedback](file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/ui/controllers/edit_workspace.py#L674-L686). Ruft `record_rl_feedback()` auf.

---

## Dateien

### [MODIFY] [edit_actions.py](file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/services/actions/edit_actions.py)
Die 13 neuen Aktionen werden am Ende der Datei hinzugefügt. Alle folgen dem bestehenden Muster: `@action_registry.register()` Decorator mit `param_schema`.

Aktionen, die Worker starten müssen (convert_videos, preview_export, auto_ducking), verwenden das `agent_command_signal.emit()`-Pattern.

Reine DB-Aktionen (list_media, list_timeline, get_project_info, set_clip_effects, move_clip, remove_clip, add_anchor, apply_style_preset, rl_feedback, add_to_timeline) werden direkt ausgeführt.

### [MODIFY] [chat_dock.py](file:///C:/Users/David%20Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/ui/chat_dock.py)
UI-Refresh-Hooks in `_on_agent_finished` für die neuen Aktionen:
- `add_to_timeline` → Timeline + Media-Tabelle neu laden
- `set_clip_effects` → Timeline neu laden
- `move_clip` → Timeline neu laden
- `remove_clip` → Timeline neu laden
- `convert_videos` → Media-Tabelle neu laden (nach Finish)
- `add_anchor` → Anchor-Liste im UI aktualisieren (wenn möglich)

---

## Verifikationsplan

### Automatisierte Tests
```bash
python -m pytest tests/test_phase2_chat_actions.py -v
```
- Testskript für alle 13 neuen Aktionen mit Mocked-DB oder Temp-DB
- Prüfung von Input-Validierung, korrekter Rückgabe und Fehlerbehandlung

### Manuelle Verifikation
- Chat-Befehle wie `"Zeige mir alle importierten Medien"`, `"Füge Video 3 zur Timeline hinzu"`, `"Setze die Helligkeit von Clip 1 auf 0.5"` im Chat testen

## Superseded / Task Transfer

Transferred to `PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09` / `OTK-015` on 2026-06-09.

- Original plan: `PB-STUDIO-INTEGRATION-SIDE-EFFECTS-2026-05-23`
- Original open work: Task 2: Export-NVENC absichern (Befund 1).
- Transfer status: `transferred`
- Archive rule: source remains evidence only; do not use this plan as active work authority.
- Honesty guard: no `fixed` marker was set by this transfer.

