# LICENSES - PB Studio + Brain V3

Stand: 2026-05-07. Plan-Quelle:
`docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/06_PHASES.md`
und `phase_blueprints/phase_6_haertung.md`.

Diese Datei listet die fuer PB Studio Brain V3 relevanten Modelle,
Python-Pakete und externen Tools. Sie ist Attribution- und
Compliance-Dokumentation im Workspace-Root, keine Rechtsberatung.
Vor Distribution muss der tatsaechlich gebundelte Paket-/Binary-Stand
noch einmal gegen die jeweiligen Lizenzdateien geprueft werden.

## ML-Modelle

### CLAP Audio-Modell
- **ID:** `laion/larger_clap_music`
- **Lizenz:** Apache-2.0
- **Quelle:** https://huggingface.co/laion/larger_clap_music
- **Verwendung:** Audio-Embedding, 10s-Window/5s-Hop
- **Plan-Hinweis:** Die alte AMD-Plan-Behauptung `CC-BY-4.0` ist fuer
  dieses Brain-V3-Modell widerlegt; Plan verlangt keine Splash-Screen-
  Attribution. Diese `LICENSES.md` bleibt Pflicht.

### SigLIP-2 Vision (Brain V3)
- **ID:** `google/siglip2-base-patch16-384`
- **Lizenz:** Apache-2.0
- **Quelle:** https://huggingface.co/google/siglip2-base-patch16-384
- **Verwendung:** Video-Embedding, default batch=8 auf GTX 1060

### SigLIP-1 Vision (Bestand V1/V2)
- **ID:** `google/siglip-so400m-patch14-384`
- **Lizenz:** Apache-2.0
- **Quelle:** https://huggingface.co/google/siglip-so400m-patch14-384
- **Verwendung:** bestehender Vision-Pfad aus V1/V2

### Demucs
- **Komponente:** `demucs` / `htdemucs_ft`
- **Lizenz:** MIT
- **Quelle:** https://github.com/facebookresearch/demucs
- **Verwendung:** Stem-Separation im bestehenden V1/V2-Stack

### beat_this
- **Komponente:** `beat_this`
- **Lizenz:** MIT
- **Quelle:** https://github.com/CPJKU/beat_this
- **Verwendung:** Beat-Detection im bestehenden V1/V2-Stack

### UVR-MDX-NET
- **Komponente:** `UVR-MDX-NET-Inst_HQ_3.onnx`
- **Lizenz:** MIT laut Phase-6-Blueprint
- **Verwendung:** bestehendes ONNX-Audio-Modell

## Python-Dependencies

### torch / torchvision / torchaudio
- **Lizenz:** BSD-3-Clause / MIT laut Phase-6-Blueprint
- **Quellen:**
  - https://github.com/pytorch/pytorch
  - https://github.com/pytorch/vision
  - https://github.com/pytorch/audio
- **Verwendung:** CUDA-Inferenz-Backend, Vision-/Audio-Hilfsfunktionen

### transformers
- **Lizenz:** Apache-2.0
- **Quelle:** https://github.com/huggingface/transformers
- **Verwendung:** `AutoImageProcessor`, Modell-Loader fuer SigLIP/CLAP

### accelerate
- **Lizenz:** Apache-2.0
- **Quelle:** https://github.com/huggingface/accelerate
- **Verwendung:** optionaler Hugging-Face-Inferenz-/Device-Hilfsstack

### librosa
- **Lizenz:** ISC
- **Quelle:** https://github.com/librosa/librosa
- **Verwendung:** Audioanalyse, Tempo-/Feature-Fallback im SubtrackDetector

### scipy / numpy
- **Lizenz:** BSD-3-Clause laut Phase-6-Blueprint
- **Quellen:**
  - https://github.com/scipy/scipy
  - https://github.com/numpy/numpy
- **Verwendung:** numerische Arrays, Signalverarbeitung, Vektoroperationen

### sqlite-vec
- **Lizenz:** Apache-2.0 / MIT (Dual)
- **Quelle:** https://github.com/asg017/sqlite-vec
- **Verwendung:** KNN-Search ueber `vec0`-Tabellen

### sqlite3
- **Lizenz:** Public Domain laut Phase-6-Blueprint
- **Quelle:** https://www.sqlite.org/
- **Verwendung:** lokale Brain-V3-Datenbanken

### opencv-python
- **Lizenz:** Apache-2.0
- **Quelle:** https://github.com/opencv/opencv-python
- **Verwendung:** Frame-/Videoanalyse, Visual-Curves, Testmedien

### Pillow
- **Lizenz:** HPND laut Phase-6-Blueprint
- **Quelle:** https://github.com/python-pillow/Pillow
- **Verwendung:** Bildverarbeitung in Tests und UI-/Vision-Hilfspfaden

### pydantic
- **Lizenz:** MIT
- **Quelle:** https://github.com/pydantic/pydantic
- **Verwendung:** Brain-V3-Schemas

### PySide6
- **Lizenz:** LGPL-3 oder commercial
- **Quelle:** https://wiki.qt.io/Qt_for_Python
- **Verwendung:** Desktop-UI
- **Konsequenz:** dynamisch linken / Qt-Lizenzbedingungen beachten

## Externe Tools

### ffmpeg / ffprobe
- **Lizenz:** LGPL/GPL, abhaengig vom konkreten Build und aktivierten Codecs
- **Quelle:** https://ffmpeg.org/
- **Verwendung:** Medienanalyse, Proxy/Render, NVENC
- **Konsequenz:** externer/dynamischer Tool-Aufruf; vor Distribution Build-
  Lizenz und Codec-Konfiguration pruefen.

### NVIDIA Driver / CUDA Toolkit
- **Lizenz:** proprietaer / NVIDIA EULA
- **Quelle:** https://developer.nvidia.com/cuda-toolkit
- **Verwendung:** GTX-1060-CUDA-Inferenz, NVENC/NVDEC-Stack

## Daten

- App-globaler Brain-V3-Store: `%APPDATA%\PB_Studio\brain_v3\`
- Embedding-Files:
  `<store>/embeddings/<media_type>/<safe_model>__<safe_ver>/<2hex>/<hash>.npy`
- Projekt-spezifische DBs: `<projekt>/brain_v3/`

Keine User-Daten werden an externe Services geschickt. Embeddings werden
lokal berechnet und lokal persistiert.

## Pflege-Regel

Bei jeder neuen Brain-V3-Komponente diese Datei aktualisieren. Bei
Lizenz-Konflikt oder Lizenz-Aenderung: `07_RISKS.md` pruefen und eine
Vault-Decision `D-XXX-<slug>.md` anlegen.
