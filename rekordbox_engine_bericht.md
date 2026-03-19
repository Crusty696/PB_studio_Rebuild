# Rekordbox-Engine Architektur-Bericht

## Uebersicht

PB Studio implementiert ein Rekordbox/CDJ-inspiriertes Wellenform- und Beatgrid-System
mit 4 Sektoren: Audio-Analyse, Frequenz-Wellenformen, UI-Rendering und Datenbank-Persistenz.

---

## Sektor 1: Praezises Beatgrid (Audio-Analyse)

**Datei:** `services/ai_audio_service.py` — Klasse `FrequencyAnalyzer`

- **Beat-Erkennung:** `librosa.beat.beat_track()` mit `hop_length=512` (~23ms Aufloesung)
- **BPM:** Automatisch erkannt, auf 1 Dezimalstelle gerundet
- **Beat-Positionen:** Frame-genaue Zeitstempel in Sekunden (4 Dezimalstellen)
- **Downbeat-Erkennung:** Jeder 4. Beat wird als Downbeat markiert (staerkere Linie im UI)

**Datenfluss:**
```
Audio-Datei → librosa.load(sr=22050) → beat_track() → frames_to_time()
→ Beatgrid-Tabelle (JSON array von Zeitstempeln)
```

---

## Sektor 2: Frequenz-basierte Wellenformen

**Datei:** `services/ai_audio_service.py` — Klasse `FrequencyAnalyzer`

**Frequenzbaender (wie Rekordbox/CDJ):**

| Band | Frequenzbereich | Farbe   | Typische Inhalte        |
|------|----------------|---------|------------------------|
| Low  | 20 - 250 Hz    | Blau    | Bass, Kicks, Sub-Bass  |
| Mid  | 250 - 4000 Hz  | Rosa    | Vocals, Snare, Melodie |
| High | 4000 - 20000 Hz| Weiss   | HiHats, Cymbals, Air   |

**Algorithmus:**
1. STFT (Short-Time Fourier Transform): `n_fft=2048`, `hop_length=512`
2. Frequenz-Bins werden den 3 Baendern zugeordnet via `librosa.fft_frequencies()`
3. Pro Zeitschritt: Mittlere Magnitude ueber alle Bins im Band
4. Normalisierung: Peak jedes Bandes = 1.0
5. Downsampling auf max. 4000 Samples fuer DB-Effizienz

**Speicherformat:** JSON-Arrays mit float-Werten [0.0 .. 1.0], 4 Dezimalstellen.

---

## Sektor 3: UI — Rekordbox Waveform Graphics Item

**Datei:** `ui/waveform_item.py` — Klasse `WaveformGraphicsItem(QGraphicsItem)`

**Rendering-Strategie:**
- Einmaliges Rendering in `QPixmap` (Cache) — kein Neuzeichnen beim Scrollen
- Pixmap wird nur bei Datenänderung oder Zoom neu gerendert (`_dirty` Flag)
- Max. Pixmap-Breite: 16000px (Speicherschutz)

**Farbschema (Rekordbox-Palette):**
```
Bass (Low):   Blau   #1E5ADC → #3C8CFF (heller bei hoher Amplitude)
Mitten (Mid): Rosa   #DC3278 → #FF50A0 (heller bei hoher Amplitude)
Hoehen (High): Weiss #F0F0FF → #FFFFC8 (gelblich bei hoher Amplitude)
```

**Zeichenreihenfolge (hinten → vorne):**
1. Hoehen (hinterste Schicht — am wenigsten dominant)
2. Mitten (mittlere Schicht)
3. Bass (vorderste Schicht — visuell dominant, wie in Rekordbox)

**Beatgrid-Overlay:**
- Halbtransparente weisse Linien (`alpha=55`) fuer normale Beats
- Staerkere Linien (`alpha=90`, 2px breit) fuer Downbeats (jeder 4. Beat)
- Dezente Mittellinie (`alpha=25`)

**Performance:**
- `QGraphicsItem` mit Pixmap-Cache — O(1) Paint-Operationen
- Kein Anti-Aliasing beim Wellenform-Rendering (Pixel-perfekt, schnell)
- ZValue=1 (ueber Track-Background, unter Clip-Label)

---

## Sektor 4: Datenbank-Sync

**Datei:** `database.py` — Model `WaveformData`

**Schema:**
```sql
CREATE TABLE waveform_data (
    id              INTEGER PRIMARY KEY,
    audio_track_id  INTEGER REFERENCES audio_tracks(id),
    num_samples     INTEGER NOT NULL DEFAULT 0,
    duration        FLOAT NOT NULL DEFAULT 0.0,
    band_low        TEXT NOT NULL,    -- JSON [float]
    band_mid        TEXT NOT NULL,    -- JSON [float]
    band_high       TEXT NOT NULL     -- JSON [float]
);
```

**Beziehungen:**
```
AudioTrack 1:1 WaveformData  (waveform_data relationship)
AudioTrack 1:1 Beatgrid      (beatgrid relationship)
```

**Lade-Performance:**
- Wellenform-Daten werden beim Timeline-Load aus DB gelesen
- JSON-Parsing nur einmal beim Laden, dann im Pixmap gecacht
- Kein Nachladen beim Scrollen/Zoomen

---

## Integration in main.py

**Neuer Worker:** `WaveformAnalysisWorker(QObject)` — Hintergrund-Thread fuer Analyse

**Neuer Button:** "Rekordbox Wellenform" im MEDIA-Workspace (Analyse-Gruppe)

**Timeline-Integration:**
- `InteractiveTimeline.load_from_db()` laedt automatisch Waveforms fuer Audio-Clips
- `InteractiveTimeline.add_clip()` zeigt Waveform sofort an, wenn Daten vorhanden
- Audio-Clips mit Waveform: halbtransparenter Hintergrund (alpha=60), damit Wellenform sichtbar
- Audio-Clips ohne Waveform: solider blauer Hintergrund (alpha=200), wie bisher

---

## Workflow fuer den User

1. Audio-Datei importieren (MEDIA Workspace)
2. "Rekordbox Wellenform" Button klicken
3. Analyse laeuft im Hintergrund (5 Schritte mit Progress)
4. Nach Abschluss: "Zur Timeline hinzufuegen"
5. Timeline zeigt bunte Wellenform mit Beatgrid-Linien
6. Beim naechsten Start: Wellenform wird sofort aus DB geladen (kein Re-Analyse noetig)
