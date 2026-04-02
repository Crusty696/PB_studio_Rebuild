# PB Studio — Fähigkeiten und Verfügbare Aktionen

## Was PB Studio kann

PB Studio ist ein KI-gestützter Audio/Video-Editor für DJs und Producer.
Es verbindet Audio-Analyse mit intelligenter Video-Pacing.

## Audio-Pipeline

1. **Import**: MP3, WAV, FLAC, AIFF, OGG werden importiert
2. **BPM-Analyse**: beat_this ermittelt exaktes Tempo (±0.1 BPM Genauigkeit)
3. **Stem-Separation**: Demucs trennt in Drums, Bass, Vocals, Other
4. **Sektions-Erkennung**: Automatische DROP/BUILDUP/BREAKDOWN Erkennung
5. **LUFS-Messung**: Lautheitsnormalisierung auf -14 LUFS
6. **Beat-Grid**: Millisekunden-genaue Schlagpositionen

## Video-Pipeline

1. **Import**: MP4, MOV, MKV, AVI, WEBM werden importiert
2. **Analyse**: Auflösung, FPS, Dauer automatisch erkannt
3. **Proxy-Erstellung**: Schnelle Preview-Version wird automatisch erstellt
4. **Frame-Extraktion**: Thumbnails für Timeline-Vorschau
5. **Energie-Scoring**: Optischer Fluss → Motion-Score
6. **Mood-Analyse**: SigLIP-Embeddings für semantisches Matching

## KI-Pacing

1. **Pacing-Engine**: Berechnet Cut-Punkte auf Beat-Timestamps
2. **Pacing-Strategist**: Lokales LLM (oder Ollama) generiert Pacing-Plan
3. **SigLIP-Matching**: Mood-basierte Video-Auswahl
4. **Auto-Edit**: Vollautomatische Timeline-Befüllung in einem Klick
5. **KI-Gedächtnis**: Lernt aus User-Feedback (AIPacingMemory)

## Chat-Befehle (Aktionen)

Der KI-Assistent versteht folgende natürliche Sprach-Befehle:

### Audio-Aktionen
- "Analysiere [Dateiname]" → Startet BPM-Analyse und Stem-Separation
- "Analysiere alle Audios" → Batch-Analyse aller importierten Tracks
- "Stems von [Track]" → Startet Demucs-Separation
- "BPM von [Track]" → Gibt BPM-Wert zurück

### Video-Aktionen
- "Analysiere Videos" → Startet Video-Pipeline
- "Erstelle Proxies" → Generiert Preview-Versionen
- "LUFS von [Track]" → Misst Lautstärke

### Pacing-Aktionen
- "Schneide automatisch" → Auto-Edit mit aktuellen Einstellungen
- "Schneide auf Beats" → Pacing-Engine mit Standard-Einstellungen
- "Erstelle DJ-Set" → Vollautomatisches Video mit KI-Pacing

### Projekt-Aktionen
- "GPU Status" → Zeigt VRAM-Nutzung
- "Was habe ich importiert?" → Listet alle Medien
- "Lösche Timeline" → Leert die aktuelle Timeline

## Aktionsformat für den KI-Agenten

Der KI-Agent gibt JSON zurück:
```json
{"action": "analyze_audio", "params": {"audio_id": 1}}
```

Oder bei mehreren Aktionen:
```json
[
  {"action": "analyze_audio", "params": {}},
  {"action": "create_auto_edit", "params": {}}
]
```

## Technologie-Stack

| Komponente     | Technologie           | Zweck                        |
|----------------|-----------------------|------------------------------|
| UI             | PySide6 (Qt 6)        | Desktop GUI                  |
| Audio-Analyse  | beat_this, librosa    | BPM, Beat-Grid               |
| Stem-Separation| Demucs (Meta AI)      | 4-Stem-Trennung              |
| Vision         | SigLIP, Moondream2    | Video-Analyse, Mood-Matching |
| Motion         | RAFT                  | Optischer Fluss              |
| LLM (lokal)    | Ollama / Qwen2.5      | Pacing-Strategie, Chat       |
| Export         | FFmpeg                | Video-Rendering              |
| Datenbank      | SQLite + SQLAlchemy   | Projekt-Persistenz           |
| GPU            | CUDA (GTX 1060 min.)  | KI-Beschleunigung            |
