# PB Studio - Kern-Workflow & Zweck

## Zweck
PB Studio ist ein KI-gestützter Video-Editor für DJs und Musikproduzenten. Er automatisiert den Schnitt von Videoclips passend zur Musik-Energie und zum Beat.

## Der Workflow (End-to-End)
1. **Ingest**: Import von Audio (WAV/MP3) und Video (MP4).
2. **Audio-Analyse**: 
   - 'beat_this' für ±0.1 BPM Präzision.
   - 'Demucs' für die Trennung von Drums, Bass, Vocals.
3. **Video-Analyse**:
   - Szenenerkennung (PySceneDetect).
   - 'SigLIP' für semantische Mood-Embeddings.
   - 'RAFT' für Bewegungs-Energie (Motion Score).
4. **KI-Pacing**: 
   - Das System berechnet Schnittpunkte exakt auf den Beats.
   - Mood-Matching: Wählt Clips aus, die zur Audio-Energie passen.
5. **Auto-Edit**: Erstellt automatisch eine fertige Timeline.
6. **Export**: Finales Rendering via FFmpeg (NVENC Hardware-Beschleunigung).

## Hardware-Limit (Kritisch)
- Ziel-Hardware: GTX 1060 (6GB VRAM).
- Striktes VRAM-Management erforderlich (nur ein Modell zur Zeit).