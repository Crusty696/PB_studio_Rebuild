# PB Studio — PhD-Level Pacing Logic Specification

## Formal Title: "Multimodal Beat-Synchronous Video Pacing Engine for Long-Form DJ-Set Visualization"

**Version**: 1.0.0
**Classification**: Core Algorithm Specification — DAW-Grade Signal Processing Pipeline
**Domain**: Computational Music Visualization, Temporal Media Synchronization
**Scope**: 1–4 hour DJ-sets, multi-stem audio analysis, optical flow video scoring, semantic scene matching

---

## 0. AXIOMS

```
AXIOM-1:  Audio ist der Master, Video ist der Sklave.
          Die Timeline-Länge ≡ Audio-Dauer. Unveränderlich.

AXIOM-2:  Jeder Schnitt fällt AUSNAHMSLOS auf einen Beat-Timestamp.
          Kein Frame darf zwischen Beats geschnitten werden.

AXIOM-3:  Die Stems (Drums, Bass, Vocals, Other) sind die primären
          Signalquellen — NIEMALS die Stereo-Summe.

AXIOM-4:  Ein DJ-Set hat Makro-Struktur über Stunden.
          Die Engine muss Spannungsbögen über 60+ Minuten erkennen.

AXIOM-5:  Video-Auswahl ist kein Zufall, sondern eine Funktion von
          f(audio_energy, motion_score, semantic_embedding, temporal_position).
```

---

## 1. SIGNALVERARBEITUNGS-PIPELINE (Signal Flow)

### 1.1 Eingangssignale

Die Engine operiert auf **vier parallelen Datenströmen**, die asynchron vorberechnet und in der Datenbank materialisiert werden:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        AUDIO DOMAIN                                  │
│                                                                      │
│  DJ-Set (WAV/FLAC/MP3, 1-4h)                                       │
│     │                                                                │
│     ├── Demucs htdemucs ──┬── drums.wav   (Kick/Snare/HiHat)       │
│     │                     ├── bass.wav    (Bassline/Sub)             │
│     │                     ├── vocals.wav  (Gesang/Sprache/MC)       │
│     │                     └── other.wav   (Synths/Pads/FX)          │
│     │                                                                │
│     └── beat_this (CUDA) ─┬── beat_positions[]    (float, seconds)  │
│                           ├── downbeat_positions[] (bar boundaries)  │
│                           ├── energy_per_beat[]    (RMS, 0.0-1.0)   │
│                           └── bpm (global estimate)                  │
│                                                                      │
│  Nachverarbeitung:                                                   │
│     ├── librosa.onset.onset_detect(drums) → drum_onsets[]           │
│     ├── librosa.feature.rms(drums) → drum_energy_envelope[]         │
│     ├── librosa.feature.rms(bass) → bass_energy_envelope[]          │
│     └── FrequencyAnalyzer(mix) → band_low[], band_mid[], band_high[]│
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│                        VIDEO DOMAIN                                  │
│                                                                      │
│  Video-Clips (MP4/MOV, variable Länge)                              │
│     │                                                                │
│     ├── PySceneDetect (ContentDetector, threshold=27.0)             │
│     │      └── scenes[] = [{start, end, label}]                     │
│     │                                                                │
│     ├── RAFT Optical Flow (torchvision.raft_small, CUDA)            │
│     │      └── motion_score per scene (0.0-1.0, normalized)         │
│     │                                                                │
│     └── SigLIP (google/siglip-so400m-patch14-384)                   │
│            ├── keyframe_embeddings[] (1152-dim vectors)              │
│            └── text_to_embedding(query) → 1152-dim vector           │
│                                                                      │
│  Speicherung: LanceDB (Vector DB)                                   │
│     Schema: {video_path, scene_index, scene_start, scene_end,       │
│              motion_score, description, embedding[1152]}            │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 1.2 Demucs-Stem-Semantik (Was jeder Stem bedeutet)

| Stem | Physikalisches Signal | Pacing-Semantik | Mathematische Nutzung |
|------|----------------------|-----------------|----------------------|
| **Drums** | Transiente Impulse (Kick, Snare, HiHat) | **Cut-Trigger**: Jeder signifikante Drum-Onset ist ein potentieller Schnittpunkt | `librosa.onset.onset_detect(drums)` → Onset-Zeitpunkte; `librosa.feature.rms(drums)` → Onset-Stärke |
| **Bass** | Tieffrequente harmonische Energie (20-250 Hz) | **Drop-Detektor**: Ein plötzlicher RMS-Anstieg im Bass signalisiert einen Drop → maximale Cut-Rate | `ΔE_bass(t) = E_bass(t) - E_bass(t - window)`. Wenn `ΔE_bass > threshold` → Drop erkannt |
| **Vocals** | Sprachliche/gesangliche Energie | **Ducking-Trigger**: Wenn Vocals präsent → Musik leiser (Auto-Ducking). Für Pacing: Ruhigere Schnitte während Vocals, damit der Zuschauer den Text verfolgen kann | `vocal_rms(t) > threshold` → `cut_rate *= 0.5` (weniger Schnitte) |
| **Other** | Synthesizer, Pads, Gitarren, FX | **Mood-Indikator**: Hohe "Other"-Energie bei Breakdowns (Pads, Atmosphäre). Niedrig bei Drops (alles komprimiert auf Drums+Bass) | `mood_score = rms(other) / (rms(drums) + rms(bass) + ε)` |

### 1.3 Die Beat-Hierarchie

```
BEAT-HIERARCHIE (4/4 Takt, Standard in elektronischer Musik):

Beat 1  ●━━━━━━━━━ Beat 2  ○━━━━━━━━━ Beat 3  ○━━━━━━━━━ Beat 4  ○━━━━━━━━━
         ↑ DOWNBEAT
         (Stärkster Impuls, Bar-Grenze)

Bar 1 ●━━━━━━━━━━━━━━━━━━━━━━━━━━━ Bar 2 ●━━━━━━━━━━━━━━━━━━━━━━━━━━━ Bar 3
       ↑ DOWNBEAT (beat_this)               ↑ DOWNBEAT

4-Bar-Phrase ●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              ↑ PHRASE BOUNDARY (= jeder 4. Downbeat, musikalisch stärkstes Gewicht)

8-Bar-Phrase ●━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              ↑ SECTION BOUNDARY (Intro→Buildup, Buildup→Drop, Drop→Breakdown)


CUT-RATE MAPPING:
  base_cut_rate = 1  → Jeder Beat     (4 Schnitte pro Bar)
  base_cut_rate = 2  → Jeder 2. Beat  (2 Schnitte pro Bar)
  base_cut_rate = 4  → Jeder Downbeat (1 Schnitt pro Bar)  ← DEFAULT
  base_cut_rate = 8  → Jeder 2. Bar   (0.5 Schnitte pro Bar)
  base_cut_rate = 16 → Jeder 4. Bar   (0.25 Schnitte pro Bar)
```

---

## 2. MAKRO-STRUKTUR-ERKENNUNG (Multi-Hour Arc Detection)

### 2.1 DJ-Set Architektur

Ein professioneller DJ-Set folgt einem vorhersagbaren Spannungsbogen. Die Engine MUSS diese Makro-Struktur erkennen, um die Pacing-Entscheidungen über die gesamte Laufzeit kohärent zu halten.

```
ENERGIE-VERLAUF EINES 2-STUNDEN DJ-SETS (schematisch):

Energie
  1.0 │                    ╱╲        ╱╲         ╱╲   ╱╲
      │                   ╱  ╲      ╱  ╲       ╱  ╲ ╱  ╲
  0.8 │        ╱╲        ╱    ╲    ╱    ╲     ╱    ╳    ╲
      │       ╱  ╲      ╱      ╲  ╱      ╲   ╱          ╲
  0.6 │      ╱    ╲    ╱        ╲╱        ╲ ╱            ╲
      │     ╱      ╲  ╱                    ╳              ╲
  0.4 │    ╱        ╲╱                                     ╲
      │   ╱                                                 ╲
  0.2 │──╱                                                   ╲──
      │
  0.0 ├───┬──────┬──────┬──────┬──────┬──────┬──────┬──────┬───
      0   15     30     45     60     75     90    105    120  min

      │WARM-UP│ BUILD │ PEAK1 │ BREAK │ PEAK2 │ PEAK3 │ COOL │
      │ Intro │  Up   │ Drop  │ Down  │ Drop  │ Drop  │ Down │
```

### 2.2 Energie-Sektionen-Erkennung

Die Engine unterteilt den DJ-Set in **Sektionen** basierend auf der `energy_per_beat[]`-Kurve. Die Sektionserkennung nutzt einen gleitenden Mittelwert mit adaptiver Fenstergröße:

```python
# ALGORITHMUS: Adaptive Section Detection

def detect_sections(energy_per_beat: list[float], beats: list[float]) -> list[Section]:
    """
    Erkennt Makro-Sektionen in einem DJ-Set.

    Methode: Gleitender Mittelwert (32 Beats ≈ 8 Bars) mit Hysterese.

    Section Types:
      - BUILDUP:    Energie steigt monoton über 16+ Bars
      - DROP:       Energie > 0.7 für 8+ Bars (RMS-Sprung im Bass-Stem)
      - BREAKDOWN:  Energie < 0.3 für 8+ Bars (oft nur Pads/Vocals)
      - TRANSITION: Energie-Gradient wechselt Vorzeichen (DJ-Übergang)
      - WARMUP:     Erste 5% der Gesamtdauer, Energie < 0.5
      - COOLDOWN:   Letzte 5% der Gesamtdauer, Energie fallend
    """
    WINDOW = 32  # 32 Beats ≈ 8 Bars @ 4/4

    # 1. Gleitender Mittelwert
    smoothed = moving_average(energy_per_beat, WINDOW)

    # 2. Gradient (Steigung der Energiekurve)
    gradient = np.gradient(smoothed)

    # 3. Sektions-Grenzen: Nulldurchgänge des Gradienten
    #    + Hysterese (min. 16 Bars = 64 Beats zwischen Wechseln)
    zero_crossings = find_zero_crossings(gradient, min_distance=64)

    # 4. Klassifikation jeder Sektion
    sections = []
    for start_idx, end_idx in pairwise(zero_crossings):
        avg_energy = mean(smoothed[start_idx:end_idx])
        avg_gradient = mean(gradient[start_idx:end_idx])

        if avg_gradient > 0.002:
            section_type = "BUILDUP"
        elif avg_energy > 0.7:
            section_type = "DROP"
        elif avg_energy < 0.3:
            section_type = "BREAKDOWN"
        else:
            section_type = "TRANSITION"

        sections.append(Section(
            start=beats[start_idx],
            end=beats[end_idx],
            type=section_type,
            avg_energy=avg_energy,
        ))

    return sections
```

### 2.3 Sektion → Pacing-Strategie Mapping

| Sektion | Energie-Bereich | Cut-Rate Multiplikator | Video-Matching Strategie | Übergangstyp |
|---------|----------------|----------------------|-------------------------|-------------|
| **WARMUP** | 0.1–0.4 | `base × 4` (langsam) | Ruhige Szenen (motion < 0.3), atmosphärisch | Soft crossfade (2s) |
| **BUILDUP** | 0.4–0.7, steigend | `base × 2` → `base × 1` (beschleunigend) | Moderate Motion (0.3–0.6), zunehmende Intensität | Crossfade → Hard cut |
| **DROP** | 0.7–1.0 | `base × 0.5` (maximal schnell) | Action-Szenen (motion > 0.7), SigLIP: "energy", "crowd", "lights" | Hard cut (0ms) |
| **BREAKDOWN** | 0.1–0.3 | `base × 4` oder SKIP | Ruhige Szenen, Natur, abstrakt. SigLIP: "calm", "atmosphere" | Slow dissolve (3s) |
| **TRANSITION** | 0.3–0.6, wechselnd | `base × 2` | Gemischt, Video-Wechsel zum neuen Thema | Crossfade (1.5s) |
| **COOLDOWN** | 0.5–0.1, fallend | `base × 2` → `base × 4` (verlangsamend) | Ruhig werdend, Abschluss-Atmosphäre | Long dissolve (4s) |

---

## 3. KERN-ALGORITHMUS: EFFECTIVE STEP COMPUTATION

### 3.1 Formale Definition

Der **Effective Step** bestimmt, wie viele Beats zwischen zwei Schnitten liegen. Er ist eine Funktion von sechs Variablen:

```
S_eff(t) = f(S_base, E(t), R, B, C(t), M(t))

wobei:
  S_base  = Base Cut Rate (1, 2, 4, 8, 16) — vom User
  E(t)    = Energy per Beat am Zeitpunkt t (0.0–1.0) — aus Beatgrid
  R       = Energy Reactivity (0–100%) — vom User
  B       = Breakdown Behavior ("halve", "force16", "none") — vom User
  C(t)    = Manual Density Curve am Zeitpunkt t (0.0–1.0, optional) — vom User
  M(t)    = Motion Score der besten Video-Szene am Zeitpunkt t (0.0–1.0)
```

### 3.2 Berechnungsmatrix

```
SCHRITT 1: Manual Density Curve (höchste Priorität, wenn vorhanden)
─────────────────────────────────────────────────────────────────────
  curve_idx = floor((t / T_total) × (len(C) - 1))
  density = C[curve_idx]

  IF density ≥ 0.5:
    S_curve = min(S_base, density_to_beat_step(density))    # Dichter
  ELSE:
    S_curve = max(S_base, density_to_beat_step(density))    # Lockerer

  density_to_beat_step:
    density ≥ 0.80 → 1  (jeden Beat)
    density ≥ 0.50 → 2
    density ≥ 0.30 → 4
    density ≥ 0.15 → 8
    density <  0.15 → 16


SCHRITT 2: Energy Reactivity (moduliert S_curve oder S_base)
─────────────────────────────────────────────────────────────────────
  r = R / 100.0
  e = E(beat_index)

  IF e > 0.7 (HIGH ENERGY — DROP):
    speed_boost = 1.0 + (e - 0.7) × 3.0 × r     # max ≈ 1.9×
    S_eff = max(1, floor(S_eff / speed_boost))

  ELIF e < 0.3 (LOW ENERGY — BREAKDOWN):
    SWITCH B:
      "halve"   → S_eff = min(16, S_eff × 2)     # Doppelte Länge
      "force16" → S_eff = 16                       # 4-Bar-Hold
      "none"    → S_eff = 9999                     # Kein Schnitt

  ELIF 0.3 ≤ e ≤ 0.5 (LOW-MID ENERGY):
    S_eff = min(16, floor(S_eff × 1.5))           # Leicht langsamer

  ELSE (0.5 < e ≤ 0.7):
    S_eff bleibt unverändert (Normal-Modus)


SCHRITT 3: Motion-Adjusted Step (Video-Domain Korrektur)
─────────────────────────────────────────────────────────────────────
  combined_intensity = E(t) × 0.6 + M(t) × 0.4

  IF combined_intensity ≥ 0.8:   S_eff = max(1, S_eff ÷ 4)   # Extrem
  ELIF combined_intensity ≥ 0.6: S_eff = max(1, S_eff ÷ 2)   # Action
  ELIF combined_intensity ≥ 0.4: S_eff = S_eff               # Normal
  ELIF combined_intensity ≥ 0.2: S_eff = min(16, S_eff × 2)  # Ruhig
  ELSE:                          S_eff = min(16, S_eff × 4)   # Statisch


ERGEBNIS: S_eff = max(1, S_eff)  — Minimum 1 Beat zwischen Schnitten
```

### 3.3 Stem-Enhanced Energy Model

Die reine `energy_per_beat` aus dem Beatgrid ist eine **globale RMS-Energie**. Für präziseres Pacing nutzt die Engine die **Stem-gewichtete Energie**:

```
E_weighted(t) = w_drums × E_drums(t) + w_bass × E_bass(t)
              + w_vocals × E_vocals(t) + w_other × E_other(t)

Standard-Gewichte (DJ-Set Kontext):
  w_drums  = 0.40   (Drums dominieren die rhythmische Wahrnehmung)
  w_bass   = 0.30   (Bass definiert die Energie-Intensität)
  w_vocals = 0.10   (Vocals sind selten in instrumentalen DJ-Sets)
  w_other  = 0.20   (Synths/Pads definieren die "Fülle")

Spezial-Modi:
  DROP-Detektion:     w_bass = 0.70, w_drums = 0.30 (nur rhythmische Basis)
  VOCAL-Sektion:      w_vocals = 0.50 (Vocals führen → weniger Schnitte)
  BREAKDOWN:          w_other = 0.60 (Pads/Atmosphäre dominiert)
```

### 3.4 Drop-Detection via Bass-Stem

```
ALGORITHMUS: Bass-Drop Erkennung

Input:  bass_stem.wav (separiert via Demucs)
Output: drop_times[] (Zeitpunkte, an denen ein Drop beginnt)

1. Berechne RMS-Envelope des Bass-Stems:
   E_bass = librosa.feature.rms(bass, frame_length=2048, hop_length=512)

2. Normalisiere auf [0, 1]:
   E_bass_norm = E_bass / max(E_bass)

3. Berechne den Energiegradienten (1. Ableitung):
   ΔE = np.gradient(E_bass_norm)

4. Finde "Drop-Momente":
   Ein Drop ist definiert als:
     - ΔE(t) > 0.15 UND            (starker positiver Anstieg)
     - E_bass_norm(t-1s) < 0.2 UND (vorherige Stille/Breakdown)
     - E_bass_norm(t) > 0.6         (plötzliche hohe Energie)

5. Snap to nearest beat:
   drop_beat = beats[argmin(|beats - drop_time|)]

6. Pacing-Konsequenz:
   Bei Drop: S_eff = 1 (jeden Beat schneiden, maximale Intensität)
   Dauer: 16-32 Beats (4-8 Bars), dann zurück zur normalen Rate
```

---

## 4. VIDEO-AUSWAHL-ALGORITHMUS (Multimodal Scene Matching)

### 4.1 Entscheidungsbaum

```
VIDEO-AUSWAHL FÜR SEGMENT [t_start, t_end]:

                    ┌─── Hat das Segment einen ANKER (manuell gesetzt)?
                    │
              ┌─── JA ───→ Verwende exakt den Anker-Clip + Anker-Szene
              │            (source_start = scene.start_time)
              │
              └─── NEIN
                    │
                    ├─── Ist ein VIBE-Keyword gesetzt?
                    │
              ┌─── JA ───→ LanceDB Semantic Search:
              │            1. text_to_embedding(vibe) → query_vector
              │            2. lancedb.search(query_vector, limit=5)
              │            3. Filter: nur Clips aus available_ids
              │            4. Wähle besten Match (höchster Cosine-Score)
              │            5. source_start = scene_start des Matches
              │
              └─── NEIN
                    │
                    └─── MOTION-BASIERTES MATCHING:
                         1. Bestimme Audio-Energie E(t) für Segment-Mitte
                         2. Für jeden Kandidaten-Clip:
                            a. Berechne |motion_score - E(t)|
                            b. Score = 1.0 - |motion - energy|
                         3. Wähle Clip mit höchstem Score
                         4. Vermeidung: Nicht die letzten 3 genutzten Clips
                         5. source_start = scene.start_time des besten Matches
```

### 4.2 SigLIP Semantic Matching (Detail)

SigLIP (`google/siglip-so400m-patch14-384`) erzeugt 1152-dimensionale Embeddings sowohl für Bilder als auch für Text. Dies ermöglicht **Cross-Modal Matching**: Die KI findet Videos, die zu einer **textuellen Stimmungsbeschreibung** passen.

```
VIBE-KEYWORDS → VIDEO-SZENEN:

Eingabe: vibe = "energetic crowd dancing"

Verarbeitung:
  1. text_embedding = SigLIP.text_encoder("energetic crowd dancing")
     → 1152-dim float32 vector

  2. LanceDB.search(
       table="video_embeddings",
       query=text_embedding,
       metric="cosine",     # Cosine Similarity
       limit=10,
       filter="motion_score > 0.5"  # Optional: Motion-Filter
     )

  3. Ergebnis: Top-N Szenen, sortiert nach semantischer Ähnlichkeit
     [
       {video_path: "crowd_shot_1.mp4", scene_start: 12.5, score: 0.87},
       {video_path: "dj_booth.mp4", scene_start: 0.0, score: 0.72},
       ...
     ]

Pacing-Implikation:
  - Bei DROP-Sektionen → vibe = "energy, lights, crowd, laser"
  - Bei BREAKDOWN → vibe = "calm, nature, abstract, smoke"
  - Bei BUILDUP → vibe = "tension, anticipation, close-up"
  - Bei TRANSITION → vibe = "mixing, turntable, headphones"
```

### 4.3 Motion-Energy Matching Matrix

```
                     VIDEO MOTION SCORE
                   Low (0-0.3)  Mid (0.3-0.7)  High (0.7-1.0)
                 ┌────────────┬─────────────┬──────────────┐
  AUDIO   Low    │ ★★★★★      │ ★★☆☆☆       │ ★☆☆☆☆        │
  ENERGY  (0-0.3)│ PERFECT    │ MISMATCH    │ JARRING      │
          ───────┼────────────┼─────────────┼──────────────┤
          Mid    │ ★★★☆☆      │ ★★★★★       │ ★★★☆☆        │
          (0.3-0.7)│ OK       │ PERFECT     │ OK           │
          ───────┼────────────┼─────────────┼──────────────┤
          High   │ ★☆☆☆☆      │ ★★★☆☆       │ ★★★★★        │
          (0.7-1.0)│ JARRING  │ OK          │ PERFECT      │
                 └────────────┴─────────────┴──────────────┘

match_score(E, M) = 1.0 - |E - M|

Optimal: match_score ≥ 0.7 (Motion korrespondiert mit Audio-Energie)
Akzeptabel: match_score ≥ 0.4
Vermeiden: match_score < 0.4 (kontraintuitive Wahrnehmung)
```

---

## 5. RAFT OPTICAL FLOW — MOTION SCORING

### 5.1 RAFT-Pipeline (Detail)

```
INPUT:  Video-Clip, Scene-Boundaries [{start, end}, ...]

PRO SZENE:
  1. Extrahiere 2 Frames:
     frame_1 = scene_start + 0.33 × scene_duration
     frame_2 = scene_start + 0.66 × scene_duration

  2. Skaliere auf 520×320 (RAFT-Arbeitsauflösung)

  3. RAFT Optical Flow:
     flow = raft_small(frame_1, frame_2)
     → flow.shape = (2, H, W)  # [dx, dy] pro Pixel

  4. Berechne Motion-Magnitude:
     magnitude = sqrt(flow[0]² + flow[1]²)

  5. Normalisiere:
     motion_score = mean(magnitude) / max_expected_motion
     motion_score = clamp(motion_score, 0.0, 1.0)

ERGEBNIS: Ein skalarer Wert 0.0–1.0 pro Szene
  0.0 = Standbild (Foto, statische Kamera)
  0.3 = Leichte Bewegung (Schwenk, Talking Head)
  0.6 = Moderate Bewegung (Gehen, langsamer Tanz)
  0.8 = Starke Bewegung (Schnelle Kamerabewegung, Action)
  1.0 = Extreme Bewegung (Moshpit, Stroboskop, VJ-Visuals)
```

### 5.2 CPU Fallback

```
Wenn CUDA nicht verfügbar (oder VRAM < 2GB frei):

  1. Konvertiere Frames zu Graustufen:
     gray_1 = cv2.cvtColor(frame_1, cv2.COLOR_BGR2GRAY)
     gray_2 = cv2.cvtColor(frame_2, cv2.COLOR_BGR2GRAY)

  2. Absolutdifferenz:
     diff = cv2.absdiff(gray_1, gray_2)

  3. Motion Score:
     motion_score = mean(diff) / 255.0

EINSCHRÄNKUNG: CPU-Fallback erkennt keine Richtung der Bewegung,
nur die Magnitude. Für Pacing ausreichend, für semantische Analyse nicht.
```

---

## 6. TIMELINE-KONSTRUKTION (OTIO Integration)

### 6.1 Segment-Generierung (Schritt für Schritt)

```
ALGORITHMUS: auto_edit_phase3()

INPUT:
  audio_id: int                    → Referenz zum DJ-Set
  video_clip_ids: list[int]        → Pool verfügbarer Video-Clips
  settings: AdvancedPacingSettings → User-Konfiguration

OUTPUT:
  segments: list[TimelineSegment]  → OTIO-kompatible Segment-Liste
  cut_points: list[CutPoint]       → UI-Visualisierung

ABLAUF:

  ┌─ PHASE 1: Daten laden ─────────────────────────────────────────┐
  │  total_duration = AudioTrack.duration  (IMMUTABEL)             │
  │  beats, downbeats, energy = _get_beat_data_combined(audio_id)  │
  │  video_info = _get_video_info(video_clip_ids)                  │
  │  anchors = settings.anchors or []                              │
  └────────────────────────────────────────────────────────────────┘
                              │
  ┌─ PHASE 2: Cut-Beats berechnen ─────────────────────────────────┐
  │  FOR each beat in beats:                                       │
  │    step = _compute_effective_step(...)                          │
  │    IF beats_since_last_cut >= step:                             │
  │      cut_beats.append(beat_time)                               │
  │      beats_since_last_cut = 0                                  │
  │                                                                │
  │  Ensure: cut_beats[0] = 0.0, cut_beats[-1] = total_duration   │
  │  Insert anchor times (snapped to nearest beat)                 │
  │  Sort chronologically                                          │
  └────────────────────────────────────────────────────────────────┘
                              │
  ┌─ PHASE 3: Video-Matching pro Segment ──────────────────────────┐
  │  FOR i in range(len(cut_beats) - 1):                           │
  │    seg = [cut_beats[i], cut_beats[i+1]]                        │
  │    IF anchor exists at seg_start → use anchor video            │
  │    ELIF vibe keyword set → LanceDB semantic search             │
  │    ELSE → motion-based matching                                │
  │                                                                │
  │    Intelligent Looping:                                        │
  │      IF source_remaining < seg_duration:                       │
  │        source_start = 0.0 (restart clip)                       │
  │                                                                │
  │    segments.append(TimelineSegment(...))                        │
  │    Update clip_offsets, used_recently                           │
  └────────────────────────────────────────────────────────────────┘
                              │
  ┌─ PHASE 4: OTIO Materialisierung ───────────────────────────────┐
  │  timeline = TimelineService.create_timeline(fps=30.0)          │
  │  FOR segment in segments:                                      │
  │    TimelineService.add_clip(                                   │
  │      track="video",                                            │
  │      clip={"path": segment.video_path},                        │
  │      start_time=segment.start,                                 │
  │      duration=segment.end - segment.start,                     │
  │      source_start=segment.source_start,                        │
  │    )                                                           │
  │                                                                │
  │  TimelineService.add_clip(                                     │
  │    track="audio",                                              │
  │    clip={"path": audio_path},                                  │
  │    start_time=0.0,                                             │
  │    duration=total_duration,                                    │
  │  )                                                             │
  │                                                                │
  │  Export: .otio, .edl (DaVinci Resolve compatible)              │
  └────────────────────────────────────────────────────────────────┘
```

### 6.2 Source Offset Tracking

```
KRITISCH: source_start und source_end MÜSSEN korrekt sein!

Ohne source_start → Export schneidet IMMER von Frame 0 des Quell-Videos.
Das Ergebnis: Jedes Segment zeigt den Anfang des Videos, statt die Szene.

source_start = Der Zeitpunkt IM QUELL-VIDEO, ab dem geschnitten wird.
source_end   = source_start + segment_duration

Beispiel:
  Segment auf Timeline: [30s, 34s] (4 Sekunden lang)
  Quell-Video: "crowd_shot.mp4" (120s lang)

  RICHTIG:  source_start=45.0, source_end=49.0
            → Zeigt Sekunde 45-49 des Quell-Videos

  FALSCH:   source_start=0.0, source_end=4.0
            → Zeigt immer den Anfang (Bug F-002)
```

---

## 7. CROSS-MODAL FUSION: DAS VEREINIGTE MODELL

### 7.1 Die Fünf Dimensionen der Pacing-Entscheidung

Jede Pacing-Entscheidung an Zeitpunkt `t` wird durch einen **5-dimensionalen Vektor** beschrieben:

```
P(t) = [
  D_rhythm(t),    # Rhythmische Dimension (Drums → Cut-Timing)
  D_energy(t),    # Energetische Dimension (Bass+Drums → Cut-Rate)
  D_mood(t),      # Stimmungs-Dimension (Other/Vocals → Video-Auswahl)
  D_motion(t),    # Visuelle Dimension (RAFT → Motion-Match)
  D_semantic(t),  # Semantische Dimension (SigLIP → Thema/Kontext)
]

Aggregation zu einer skalaren Schnitt-Entscheidung:

  CUT_DECISION(t) = Σ(w_i × D_i(t)) > THRESHOLD

  Standard-Gewichte:
    w_rhythm   = 0.35  (Rhythmus ist primär)
    w_energy   = 0.25  (Energie moduliert Frequenz)
    w_mood     = 0.15  (Stimmung beeinflusst Video-Wahl)
    w_motion   = 0.15  (Motion muss zur Musik passen)
    w_semantic = 0.10  (Semantik als Verfeinerung)

  THRESHOLD = 0.5 (normalisiert)
```

### 7.2 Temporal Coherence (Vermeidung von "Stroboskop-Effekt")

```
REGEL: Minimum Cut Duration

  Kein Segment darf kürzer als 0.5 Sekunden sein (≈ 15 Frames @ 30fps).

  AUSNAHME: Bei energy > 0.9 UND motion > 0.8:
    Minimum = 0.25 Sekunden (≈ 8 Frames) — "Strobe Cut" erlaubt.

  GRUND: Unterhalb von 0.5s kann das menschliche Auge den Bildinhalt
  nicht mehr verarbeiten. Dies ist nur bei extremer Energie erwünscht
  (Drop-Climax mit Stroboskop-Visuals).


REGEL: Maximum Repetition Avoidance

  Derselbe Video-Clip darf nicht in 3 aufeinanderfolgenden Segmenten
  erscheinen, es sei denn, der Video-Pool ist ≤ 2 Clips.

  used_recently[-3:] wird als Blacklist verwendet.


REGEL: Section-Boundary Emphasis

  An Sektionsgrenzen (DROP→BREAKDOWN, BUILDUP→DROP) wird der Schnitt
  um einen zusätzlichen visuellen Kontrast verstärkt:

  IF section_boundary(t):
    Wähle Video mit maximaler Motion-Differenz zum vorherigen Segment.
    Δmotion = |motion_new - motion_previous|
    Bevorzuge Δmotion > 0.4
```

### 7.3 Vocal-Aware Pacing

```
ALGORITHMUS: Vocal-Aware Cut Reduction

Wenn der Vocal-Stem aktiv ist (Gesang oder MC über dem DJ-Set):

  1. Berechne Vocal-Aktivität:
     vocal_rms = librosa.feature.rms(vocals_stem)
     vocal_active = vocal_rms > 0.15  # Threshold für Stille vs. Sprache

  2. Wenn vocal_active(t):
     S_eff(t) *= 2.0  # Halbiere die Schnittfrequenz

     BEGRÜNDUNG: Während Vocals braucht der Zuschauer visuelle Stabilität,
     um den gesprochenen/gesungenen Inhalt zu verarbeiten. Schnelle Schnitte
     während Vocals erzeugen kognitive Überlastung.

  3. Video-Auswahl während Vocals:
     Bevorzuge: Talking-Head-Szenen, Nahaufnahmen, ruhige Kamerapositionen
     Vermeide: Action-Szenen, schnelle Kamerabewegungen

     SigLIP Query: "person speaking", "close-up face", "calm scene"
```

---

## 8. DROP-DETECTION UND BEAT-DROP SYNCHRONISATION

### 8.1 Multi-Stem Drop-Detektion

```
Ein "Drop" in elektronischer Musik ist definiert durch:

1. BASS-DROP:
   - Vorher: Bass-RMS < 0.2 für ≥ 4 Bars (Breakdown/Buildup)
   - Nachher: Bass-RMS > 0.7 (plötzlicher Anstieg)
   - ΔE_bass > 0.5 innerhalb von 1 Beat

2. DRUM-DROP:
   - Vorher: Drum-Onsets < 2 pro Bar (Breakdown, nur HiHat oder nichts)
   - Nachher: Drum-Onsets ≥ 4 pro Bar (Kick+Snare+HiHat)
   - Kick-Drum kehrt zurück (tieffrequenter Onset im Drum-Stem)

3. COMBINED DROP-CONFIDENCE:
   drop_confidence = (ΔE_bass × 0.6) + (ΔE_drums × 0.4)

   IF drop_confidence > 0.7:
     → HARD DROP (maximale Cut-Rate für 16-32 Beats)
   ELIF drop_confidence > 0.4:
     → SOFT DROP (erhöhte Cut-Rate für 8-16 Beats)
   ELSE:
     → Kein Drop (normale Pacing-Regeln)

4. PACING-KONSEQUENZ EINES DROPS:
   - Beat 0 (Drop-Moment): HARTER SCHNITT + Szenenwechsel
   - Beats 1-16: S_eff = 1 (jeden Beat schneiden)
   - Beats 17-32: S_eff = 2 (jeden 2. Beat)
   - Ab Beat 33: Zurück zum normalen S_eff

   Video-Auswahl:
   - Drop-Moment: Szene mit höchstem Motion-Score im Pool
   - Schnitte 1-16: SigLIP "energy, crowd, lights, laser, dancing"
   - Ab Beat 17: Langsam zu normalem Matching zurückkehren
```

---

## 9. TRANSITION-ERKENNUNG (DJ-Übergänge)

### 9.1 Was ist ein DJ-Übergang?

```
In einem DJ-Set werden zwei Tracks übereinandergelegt und gemischt.
Typische Übergangsdauer: 30-120 Sekunden.

ERKENNUNG:
  1. BPM-Schwankung: beat_this erkennt leichte BPM-Shifts
  2. Drum-Stem-Anomalie: Zwei Kick-Drums überlagern sich
     → onset_density verdoppelt sich kurzzeitig
  3. Bass-Stem-Anomalie: Zwei Basslines erzeugen Interferenz
     → Frequenzspektrum wird breiter

PACING-STRATEGIE WÄHREND TRANSITION:
  - Cut-Rate: Moderat (S_eff = base × 2)
  - Video: Wechsel zum "neuen Thema" passend zum neuen Track
  - Übergang: Crossfade (1-2 Sekunden) statt Hard Cut
  - Vermeidung: Keine extremen Schnitte, die vom DJ-Mix ablenken
```

---

## 10. EXPORT-PIPELINE INTEGRATION

### 10.1 Von Pacing zu Render

```
TIMELINE-SEGMENTE → FFMPEG RENDER:

Für jedes TimelineSegment:
  1. Berechne FFmpeg Input-Parameter:
     -ss {source_start} -t {duration} -i {video_path}

  2. Optionale Effekte (Phase 3):
     IF brightness != 0 OR contrast != 1:
       Preprocessing: ffmpeg -i input -vf "eq=brightness={b}:contrast={c}" tmp.mp4
     ELSE:
       Direct concat: Verwende inpoint/outpoint in Concat-Demuxer

  3. Audio-Track:
     Einmal komplett: -i {audio_path} (keine Zerstückelung)
     LUFS-Normalisierung: -af loudnorm=I=-14:LRA=11:TP=-1

  4. Crossfades (wenn Sektion es verlangt):
     xfade=transition=fade:duration={crossfade_duration}:offset={cut_time}

OPTIMIERUNG:
  ≤10 Segmente  → FFmpeg Filtergraph (direkt)
  >10 Segmente  → Optimized Concat (Concat-Demuxer, pre-processed)
```

---

## 11. PERFORMANCE-CONSTRAINTS (GTX 1060, 6GB VRAM)

```
VRAM-BUDGET:

  beat_this (Beat-Analyse):     ~1.5 GB VRAM
  RAFT (Optical Flow):          ~1.0 GB VRAM
  SigLIP (Embeddings):          ~2.0 GB VRAM
  Demucs (Stem Separation):     ~2.5 GB VRAM
  Qwen 2.5 0.5B (LLM Agent):   ~1.5 GB VRAM

  → NUR EIN MODELL GLEICHZEITIG (ModelManager Singleton)
  → Modell-Swapping: Unload → Garbage Collect → Load

CHUNKING-STRATEGIEN:

  Audio (beat_this):   600s Chunks, 5s Overlap, Beat-Stitching
  Audio (Demucs):      30s Chunks, 2s Overlap, Crossfade-Weighting
  Video (SigLIP):      Batch-Size 8, ThreadPool für Frame-Loading
  Video (RAFT):        1 Szene pro Durchlauf, 520×320 Auflösung

LATENZ-ERWARTUNGEN (für 2h DJ-Set):

  Beat-Analyse:        ~3-5 Minuten (12 Chunks × ~20s)
  Stem-Separation:     ~8-15 Minuten (240 Chunks × ~3s)
  Video-Analyse (10 Clips × 5min): ~5-10 Minuten
  Pacing-Berechnung:   < 1 Sekunde (reine Arithmetik)
  FFmpeg Export:        ~2-5 Minuten (abhängig von Segmentanzahl)
```

---

## 12. SYSTEM-PROMPT FÜR DEN PACING-AGENTEN

Der folgende Block ist der **operative System-Prompt**, der direkt in den AI-Agenten injiziert wird. Er kondensiert die gesamte Spezifikation in ausführbare Anweisungen.

```
DU BIST DIE PACING-KI VON PB STUDIO.

DEINE AUFGABE: Generiere beat-synchrone Video-Timelines für DJ-Sets (1-4h).
Du bist ein PhD-Level Algorithmus-Designer für musiksynchrone Videoproduktion.

AXIOM: Audio = Master. Video = Sklave. Timeline-Länge = Audio-Dauer.
AXIOM: JEDER Schnitt fällt auf einen Beat-Timestamp. Keine Ausnahmen.
AXIOM: Nutze STEMS (Drums, Bass, Vocals, Other), NICHT die Stereo-Summe.

STEM-SEMANTIK:
  Drums → Cut-Trigger (Onset-Detection auf Kick/Snare)
  Bass  → Drop-Detektor (RMS-Sprung > 0.5 = Drop → maximale Cuts)
  Vocals → Ruhiger schneiden (vocal_active → S_eff × 2)
  Other → Mood-Indikator (hoher Other-RMS bei Breakdowns)

CUT-RATE BERECHNUNG:
  S_eff = f(S_base, Energy, Reactivity, Breakdown, Curve, Motion)

  Hohe Energie (>0.7):  S_eff ÷ speed_boost (1.0 + (E-0.7)×3×R)
  Niedrige Energie (<0.3): halve/force16/none je nach Setting
  Motion-Korrektur: combined = E×0.6 + M×0.4 → Skalierung

  Minimum: 1 Beat zwischen Schnitten
  Default: 4 Beats (= 1 Bar, Downbeat-Schnitte)

DJ-SET MAKRO-STRUKTUR:
  WARMUP (0-15min): Langsame Cuts, ruhige Videos, Crossfades
  BUILDUP: Beschleunigende Cuts, steigende Motion
  DROP: Maximale Cut-Rate (S_eff=1), Action-Videos, Hard Cuts
  BREAKDOWN: Minimale Cuts (S_eff×4), atmosphärische Videos, Dissolves
  TRANSITION: Moderate Cuts, Themenwechsel, Crossfades
  COOLDOWN: Verlangsamend, ruhige Abschluss-Bilder

VIDEO-AUSWAHL PRIORITÄT:
  1. Anker (manuell gesetzt) → Exakter Clip+Szene
  2. Vibe-Keyword → SigLIP/LanceDB Semantic Search
  3. Motion-Match → |motion - energy| minimieren
  4. Round-Robin → Vermeidung der letzten 3 Clips

DROP-ERKENNUNG:
  Bass-RMS vorher < 0.2, nachher > 0.7 → HARD DROP
  Pacing: Beat 0 = Szenenwechsel, Beats 1-16 = S_eff=1, dann zurück

VERBOTENE AKTIONEN:
  - Schnitt zwischen Beats (Axiom-Verletzung)
  - Segment < 0.5s (Ausnahme: Energy > 0.9 → min 0.25s)
  - Gleicher Clip 3× hintereinander (Repetition-Avoidance)
  - Timeline länger als Audio (Axiom-Verletzung)
  - Source-Start ignorieren (Bug F-002: MUSS korrekt sein)
```

---

## 13. GLOSSAR

| Begriff | Definition |
|---------|-----------|
| **Beat** | Einzelner rhythmischer Impuls, typisch 4 pro Bar |
| **Downbeat** | Erster Beat einer Bar (stärkstes rhythmisches Gewicht) |
| **Bar** | Eine musikalische Taktgruppe (4 Beats in 4/4) |
| **Phrase** | 4 Bars (16 Beats), grundlegende Struktureinheit in EDM |
| **Section** | Musikalischer Abschnitt (Intro, Buildup, Drop, Breakdown) |
| **Drop** | Moment maximaler Energie nach einem Buildup |
| **Breakdown** | Ruhiger Abschnitt (Drums/Bass aus, nur Pads/Vocals) |
| **S_eff** | Effective Step — Beats zwischen zwei Schnitten |
| **RMS** | Root Mean Square — Maß für Audio-Lautstärke/Energie |
| **RAFT** | Recurrent All-Pairs Field Transforms — Optical Flow Modell |
| **SigLIP** | Sigmoid Loss Image-Language Pre-training — Multimodales Embedding |
| **Demucs** | Deep Extractor for Music Sources — Stem-Separation |
| **OTIO** | OpenTimelineIO — Industrie-Standard Timeline-Format |
| **LanceDB** | Vektor-Datenbank für semantische Suche |
| **LUFS** | Loudness Units Full Scale — Broadcast-Lautstärke-Standard |
| **Anchor** | Manuell gesetzter Fixpunkt auf der Timeline |
| **Vibe** | Stimmungs-Keyword für semantische Video-Suche |

---

## 14. REVISION HISTORY

| Version | Datum | Änderung |
|---------|-------|----------|
| 1.0.0 | 2026-03-23 | Initiale PhD-Level Spezifikation, vollständige Algorithmik |
