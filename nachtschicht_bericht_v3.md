# Nachtschicht-Bericht v3: Bugfix & Director's Desk

**Datum:** 2026-03-19
**Mission:** 3 — Bugfix, Director's Desk (Timeline-System), Pacing-Service

---

## 1. BUGFIX: Audio-Analyse Scalar Conversion (ERLEDIGT)

**Problem:** `librosa.beat.beat_track()` gibt ab Version 0.10+ `tempo` als numpy-Array zurück,
nicht als Skalar. Die Zeile `float(np.round(tempo, 1))` crashte mit:
```
TypeError: only size-1 arrays can be converted to Python scalars
```

**Fix in `services/audio_service.py` (Zeile 21-23):**
```python
# Vorher (kaputt):
tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
bpm = float(np.round(tempo, 1))

# Nachher (fix):
tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
tempo_val = tempo.item() if hasattr(tempo, 'item') else float(tempo)
bpm = round(tempo_val, 1)
```
- `tempo.item()` extrahiert sicher den Skalar aus einem 0-d oder 1-Element numpy-Array
- Fallback `float(tempo)` für ältere librosa-Versionen

**Verifizierung:**
- Synthetische Test-Audio (120 BPM Kick-Drum, 10s) erstellt
- Analyse lief fehlerfrei durch
- DB-Check: `bpm=117.5, duration=10.0` korrekt gespeichert
- librosa 0.11.0 / numpy 2.4.3 bestätigt kompatibel

---

## 2. DIRECTOR'S DESK TAB (ERLEDIGT)

Neuer Tab in `main.py` — vorher war nur ein leeres `QWidget()`.

### Layout-Aufbau:

```
┌─────────────────────────────────────────────────┐
│  Pacing-Steuerung (GroupBox)                    │
│  ┌───────────────────────────────────────────┐  │
│  │ Stimmung/Vibe: [___Eingabefeld___________]│  │
│  ├───────────────────────────────────────────┤  │
│  │ Audio: [Combo▾]  │Tempo│Energie│Dichte│ ┌──┐│
│  │ Video: [Combo▾]  │ 50  │  50  │  50  │ │TL││
│  │                   │  ▒  │  ▒   │  ▒   │ │GN││
│  │                   │  ▒  │  ▒   │  ▒   │ └──┘│
│  └───────────────────────────────────────────┘  │
├─────────────────────────────────────────────────┤
│  Timeline-Vorschau (GroupBox)                   │
│  ┌───────────────────────────────────────────┐  │
│  │ Audio  ████████████████░░░░░░░░  (blau)   │  │
│  │ Video  █████████████████████████ (orange)  │  │
│  │ Cuts   | | || |  | || | |  ||  | (farbig) │  │
│  │ ──────┼────┼────┼────┼────┼──── (Achse)   │  │
│  │ 0s    6s   12s  18s  24s  30s              │  │
│  ├───────────────────────────────────────────┤  │
│  │ 19 Schnittpunkte | Beat: 19 | Szene: 0   │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Komponenten:
- **Vibe-Eingabe:** QLineEdit mit Placeholder
- **Audio/Video-Combos:** QComboBox mit DB-Einträgen (auto-refresh nach Import/Analyse)
- **3 Slider:** Tempo, Energie, Schnitt-Dichte (je 0-100, vertical, mit Live-Wert-Anzeige)
- **Timeline generieren Button:** Startet Pacing-Berechnung
- **TimelineWidget:** Custom QPainter-Widget mit:
  - Blauer Audio-Balken (proportional zur Dauer)
  - Oranger Video-Balken (proportional zur Dauer)
  - Farbige Cut-Marker (Grün=Beat, Gelb=Szene, Lila=Energie)
  - Zeitachse mit Sekunden-Markierung
- **Cut-Info-Label:** Zeigt Anzahl und Art der Cuts

### Signal-Verdrahtung:
- Import → `_refresh_director_combos()`
- Audio-Analyse fertig → `_refresh_director_combos()` (BPM wird in Combo angezeigt)
- Video-Analyse fertig → `_refresh_director_combos()`
- Button "Timeline generieren" → `_generate_timeline()` → Pacing-Service → Timeline-Update

---

## 3. PACING-SERVICE (ERLEDIGT)

Neue Datei: `services/pacing_service.py`

### Architektur:
```
PacingSettings (dataclass)
  ├── tempo: int (0-100)
  ├── energy: int (0-100)
  ├── cut_density: int (0-100)
  └── vibe: str

CutPoint (dataclass)
  ├── time: float (Sekunden)
  ├── source: str ("beat" | "scene" | "energy")
  └── strength: float (0.0-1.0)

calculate_cut_points(audio_id, video_id, settings, duration) → list[CutPoint]
```

### Logik:
1. **Beat-Cuts:** BPM aus DB → Beat-Interval → Tempo-Slider bestimmt Divisor:
   - 0-25: jeder 4. Beat | 25-50: jeder 2. Beat | 50-75: jeder Beat | 75-100: halbe Beats
2. **Szenen-Cuts:** Szenenübergänge aus Video-Analyse (DB: scenes-Tabelle)
3. **Fallback:** Ohne BPM → gleichmäßige Cuts basierend auf Tempo-Slider
4. **Density-Filter:** Cut-Density-Slider setzt Schwelle → schwache Cuts werden entfernt
5. **Deduplizierung:** Cuts < 0.1s Abstand werden zusammengeführt

### Test-Ergebnisse:
| Test | Einstellungen | Ergebnis |
|------|--------------|----------|
| Mit BPM (117.5) | Tempo=50, Energie=60, Dichte=50 | 19 Cuts |
| Ohne BPM (Fallback) | Tempo=75, Energie=80, Dichte=30 | 21 Cuts |
| High Energy | Tempo=90, Energie=90, Dichte=90 | 234 Cuts |

---

## 4. VERIFIKATION

| Check | Status |
|-------|--------|
| `audio_service.py` — Syntax | OK |
| `audio_service.py` — BPM-Analyse | OK (117.5 BPM erkannt) |
| `audio_service.py` — DB-Speicherung | OK (bpm, duration, energy_curve) |
| `pacing_service.py` — Syntax | OK |
| `pacing_service.py` — Cut-Berechnung | OK (3 Szenarien getestet) |
| `main.py` — Syntax | OK |
| `main.py` — Kompilierung | OK |
| Signal-Verdrahtung | Combos refresh nach Import/Analyse |

---

## Geänderte/Neue Dateien

| Datei | Aktion | Zeilen |
|-------|--------|--------|
| `services/audio_service.py` | Bugfix BPM scalar | ~3 Zeilen |
| `services/pacing_service.py` | NEU — Pacing-Engine | ~100 Zeilen |
| `main.py` | Director's Desk Tab + TimelineWidget | ~200 Zeilen neu |
| `tests/create_test_audio.py` | NEU — Audio-Analyse-Test | ~50 Zeilen |
| `tests/test_pacing.py` | NEU — Pacing-Service-Test | ~25 Zeilen |

---

## Bekannte Limitierungen / Nächste Schritte

1. **Video-Duration** wird noch nicht von `video_service.py` gespeichert → Video-Balken in Timeline zeigt 0
2. **Szenen-Erkennung** fehlt noch → `scenes`-Tabelle ist leer → keine Szenen-Cuts
3. **Vibe-Eingabe** wird an PacingSettings übergeben, aber noch nicht ausgewertet (KI-Feature geplant)
4. **Production-Tab** ist noch leer (nächste Mission)
