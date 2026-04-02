# Video-Matching — Domain Knowledge

## Energie-zu-Video Mapping

Das Video-Matching-System ordnet Video-Clips anhand ihrer visuellen Energie
der aktuellen Audio-Energie zu.

### Visuelle Energie-Messung

| Clip-Typ                    | Energie-Score | Geeignet für Sektion |
|-----------------------------|--------------|----------------------|
| Statische Kamera, ruhige Szene | 0.0 – 0.2  | INTRO, COOLDOWN      |
| Langsame Schwenks, Crowd     | 0.2 – 0.4   | WARMUP, BREAKDOWN    |
| Moderate Bewegung, Tanz      | 0.4 – 0.6   | WARMUP, TRANSITION   |
| Schnelle Bewegung, Lights    | 0.6 – 0.8   | BUILDUP, DROP        |
| Extreme Bewegung, Strobe     | 0.8 – 1.0   | DROP, Climax         |

### Motion-Score-Berechnung

```
M = mean(optical_flow_magnitude) / max_expected_flow
```

- **Optical Flow**: Berechnet mit RAFT-Modell (Frame-Differenz-basiert)
- **Normalisierung**: Relativ zum Maximum des Clips
- **Kombination mit Audio**: `combined = E_audio × 0.6 + M_visual × 0.4`

## SigLIP Mood-Matching

PB Studio nutzt SigLIP (Vision+Text-Encoder) für semantisches Matching:

### Audio-Mood → Text-Query Mapping

| Audio-Sektionstyp | Text-Query für SigLIP                                    |
|-------------------|----------------------------------------------------------|
| DROP              | "explosive energy, crowd euphoria, light show, festival" |
| BUILDUP           | "tension, anticipation, rising energy, crowd gathering"  |
| BREAKDOWN         | "emotional, melancholic, atmospheric, beauty"            |
| WARMUP            | "dancing, fun, party, groove, relaxed crowd"             |
| INTRO/COOLDOWN    | "landscape, abstract, peaceful, artistic, minimal"       |

### Embedding-Vergleich

1. SigLIP generiert 1152-dim Embeddings für jeden Video-Frame
2. Text-Queries werden ebenfalls in 1152-dim projiziert
3. Cosinus-Ähnlichkeit bestimmt den Mood-Match-Score
4. Clips mit Score > 0.7 werden bevorzugt für die jeweilige Sektion

## Clip-Auswahl-Algorithmus

```
fitness = (mood_match × 0.4) + (energy_match × 0.4) + (variety × 0.2)
```

### Variety-Penalty

- Clip wurde noch nie gezeigt: +0.2 Bonus
- Clip wurde 1-2× gezeigt: Keine Änderung
- Clip wurde 3-5× gezeigt: -0.1 Penalty
- Clip wurde > 5× gezeigt: -0.3 Penalty (bei Variety > 0.5)

### Clip-Länge-Anpassung

```python
# Maximale Clip-Länge berechnen
max_duration = section_remaining_beats × (60.0 / bpm) × max_beats_per_clip

# Mindestdauer sicherstellen
if clip_available_duration < min_duration:
    skip_clip()  # Nicht genug Material
```

## Proxy-Clips

- **Zweck**: Schnelle Preview-Generierung (1/4 Auflösung, 30fps)
- **Format**: MP4 H.264 mit niedrigem Bitrate
- **Verwendung**: In der Timeline-Vorschau
- **Original-Qualität**: Nur beim finalen Export

## Unterstützte Video-Formate

| Format | Extension    | Kommentar                    |
|--------|--------------|------------------------------|
| H.264  | .mp4, .mov   | Standard, breite Kompatibilität |
| H.265  | .mp4, .mkv   | Bessere Kompression           |
| ProRes | .mov         | Professionelle Qualität       |
| DNxHD  | .mxf, .mov   | Avid-kompatibel               |
| VP9    | .webm        | Web-optimiert                 |

## Auflösungs-Standards

| Auflösung | Name   | Empfehlung                   |
|-----------|--------|------------------------------|
| 1920×1080 | Full HD | Standard für Ausgabe         |
| 3840×2160 | 4K UHD | Wenn Quelldateien 4K sind     |
| 1280×720  | HD     | Für Web/Social Media          |
| 2560×1440 | QHD    | YouTube-Premium               |

## Export-Framerate-Regeln

- **24 fps**: Cinematic Look
- **25 fps**: PAL/European Standard
- **30 fps**: NTSC/US Standard, YouTube Standard
- **60 fps**: Smooth Motion, Gaming
- **Matching**: Export-FPS sollte Source-FPS entsprechen wenn möglich
