# Audio-Analyse — Domain Knowledge

## BPM-Bereiche und Genre-Klassifikation

| BPM-Bereich | Genre/Stil           | Pacing-Implikation                     |
|-------------|----------------------|----------------------------------------|
| 60 – 90     | Hip-Hop, Trap, R&B  | Sehr langsame Schnitte, Flow-orientiert |
| 90 – 110    | House (deep/minimal) | Ruhig, atmosphärisch                   |
| 110 – 128   | House, Nu-Disco      | Standard Tanzfloor, moderate Energie   |
| 128 – 135   | Tech-House, Techno   | Treibend, industrial, präzise          |
| 135 – 145   | Techno, Hard Techno  | Intensiv, repetitiv, hypnotisch        |
| 145 – 160   | Hardstyle, Trance    | Sehr intensiv, euphoric                |
| 160 – 180   | Drum & Bass, Jungle  | Schnell, synkopiert, komplex           |
| 180+        | Hardcore, Gabber      | Maximal, extreme Energie               |

## Stem-Analyse

PB Studio nutzt **Demucs** zur Stem-Separation:

### Drums-Stem
- **Kick-Detection**: Tieffrequenter Impuls (< 200 Hz), kurze Attack
- **Snare-Detection**: Mid-Frequenz (200 – 400 Hz), Rauschanteil
- **HiHat-Detection**: Hochfrequent (> 4 kHz), sehr kurze Dauer
- **Verwendung**: Kick-Positionen sind die primären Cut-Trigger
- **Beat-Grid**: Kick-Timestamps bilden das präzise Beat-Grid

### Bass-Stem
- **RMS-Analyse**: Root Mean Square zur Energiemessung
- **Drop-Trigger**: RMS-Sprung von < 0.2 auf > 0.7 innerhalb von 0.5s
- **Sub-Bass**: < 80 Hz — entscheidend für Drop-Erkennung
- **Verwendung**: Drop-Zeitpunkte + Sektions-Grenzen

### Vocals-Stem
- **Präsenz-Detektion**: RMS > 0.3 = Vocals aktiv
- **Pitch-Analyse**: Melodische Vocals vs. Spoken Word
- **Verwendung**: Ducking-Trigger — Clips werden länger wenn Vocals aktiv

### Other-Stem
- **Synths/Pads/Gitarre**: Atmosphäre und Mood
- **Verwendung**: Mood-Matching mit SigLIP-Embeddings
- **Energie-Analyse**: Bestimmt atmosphärische Dichte

## Audio-Feature-Extraktion

| Feature         | Bibliothek     | Zweck                          |
|-----------------|----------------|--------------------------------|
| BPM             | beat_this      | Exaktes Tempo-Tracking         |
| Beat-Grid       | beat_this      | Millisekunden-genaue Beats     |
| Stems           | Demucs         | 4-Kanal-Separation             |
| LUFS            | intern         | Lautheitsmessung               |
| RMS             | numpy          | Energiemessung pro Stem        |
| Spectral Flux   | librosa        | Onset-Erkennung                |
| Key/Scale       | librosa        | Tonart-Erkennung               |

## Sektions-Erkennung

Die Sektions-Erkennung kombiniert:
1. **RMS-Änderungsrate**: Abrupte Sprünge = Sektions-Grenze
2. **Drum-Dichte**: Mehr Kicks = höhere Energie-Sektion
3. **Bass-Präsenz**: Hohe Sub-Energie = DROP/BUILDUP
4. **Vocal-Aktivität**: Vocals-Pause nach viel Energie = BREAKDOWN

## LUFS-Normalisierung

- **Target**: -14 LUFS (Streaming-Standard)
- **Messung**: Integrated LUFS über gesamten Track
- **Warnung**: Tracks unter -18 LUFS werden als "zu leise" markiert
- **Warnung**: Tracks über -8 LUFS werden als "überkomprimiert" markiert

## Frequenzanalyse-Fenster

- **Short-Time**: 23ms Fenster (44100 Hz Sample-Rate → 1024 Samples)
- **Hop-Length**: 512 Samples (50% Überlappung)
- **FFT-Größe**: 2048 Punkte für spektrale Auflösung
