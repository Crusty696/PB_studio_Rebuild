# Glossar

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19`
> Status: living document

| Begriff | Bedeutung |
|---|---|
| **Scene** | Video-Abschnitt ohne harten Schnitt. Detected via Histogramm-/Edge-Diff. |
| **Keyframe** | Repraesentativer Frame pro Szene (z. B. Mitte oder I-Frame). |
| **Sparse-Sample** | Frame-Sampling mit fester Rate (z. B. 1 Frame/2 s). |
| **Dense-Sample** | Jeder Frame oder hohe Frequenz. Nur fuer kurze Clips. |
| **Coverage** | Anteil der Video-Sekunden die abgedeckt sind. Ziel ≥ 99.5 %, max-Luecke 2 s. |
| **Proxy** | Niedrig aufgeloeste/-bitrate Kopie fuer UI-Playback. Analyse weiter auf Original. |
| **SigLIP** | Vision-Language-Embedding-Modell (Brain-V3 nutzt es auch). |
| **RAFT** | Optical-Flow-Modell (Pixel-Bewegung Frame-zu-Frame). |
| **VLM** | Vision-Language-Modell (LLaVA, MiniCPM-V, Qwen2.5-VL). Via Plan B Backend. |
| **Stream-SHA** | Hash des dekodierten Audio-/Video-Streams (Container-uebergreifend). |
| **Resume-Checkpoint** | JSON pro Job; bei Crash naechster Lauf ueberspringt fertige Stages. |
| **Cross-Modal** | Audio-Outputs (Beats, Sections, Drops von V2) + Video-Outputs → Cut-Vorschlaege. |
| **GPU-Lock-Aware** | Vor GPU-Use pynvml-Probe; respektiert V2 `GPU_EXECUTION_LOCK` ohne ihn anzufassen. |
| **`status: fixed`** | Setzt nur User. |
