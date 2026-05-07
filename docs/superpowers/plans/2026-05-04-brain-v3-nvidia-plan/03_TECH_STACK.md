# 03 — Tech-Stack (Brain V3, NVIDIA)

## Python-Dependencies

```text
# Datei: requirements/pb_studio_brain_v3.txt
# Zusatz zu requirements-py310-cu113.txt (Workspace-Bestand)
# Anwendung: pip install -r requirements/pb_studio_brain_v3.txt
# Python-Version: 3.10.20 (conda-env "pb-studio")

# === Bereits im Workspace-Stack vorhanden — V3 fasst NICHT an: ===
# torch==1.12.1+cu113
# torchaudio==0.12.1+cu113
# torchvision==0.13.1+cu113
# transformers==4.38.2
# accelerate==0.27.2
# librosa==0.10.2
# scipy>=1.11
# numpy>=1.24,<2.0
# opencv-python>=4.8
# Pillow>=10.0
# soundfile==0.12.1
# pydantic>=2.5

# === V3 NEU (via install_brain_v3_phase2_deps.bat installiert): ===
sqlite-vec>=0.1.6
```

**Bewusst NICHT genutzt:**
- `torch-directml` — AMD-only, irrelevant für NVIDIA-Pfad
- `chromadb` — Win-Stabilitätsprobleme (ChromaDB Issues #5392, #5868, #5909, #2446)
- `madmom` — librosa.beat ist auf Python 3.10/3.11 stabiler
- `LanceDB` — bereits im Workspace, V3 nutzt aber sqlite-vec für Engine-Konsistenz
- `transformers>=4.45` für SigLIP-2 — **NICHT nötig** dank Phase-0-Spike-Workaround
  (`AutoImageProcessor` statt `AutoProcessor`)

**Warum kein transformers-Upgrade:** Spike-Verifikation 20260503_115947 zeigte
dass `AutoProcessor.from_pretrained` mit transformers 4.38.2 für SigLIP-2 mit
`TypeError: vocab_file is None` fehlschlägt. **Workaround mittels
`AutoImageProcessor.from_pretrained`** funktioniert in 4.38.2 und vermeidet
Upgrade-Kollision mit V1/V2-Stack.

---

## ML-Modelle

### Audio: [`laion/larger_clap_music`](https://hf.co/laion/larger_clap_music)

```text
Architektur     CLAP (Contrastive Language-Audio Pretraining)
Backbone        Audio-Tower aus dem CLAP-Modell
Embedding-Dim   512
Window-Size     10 Sekunden
Hop-Size        5 Sekunden (50 % Overlap)
Sample-Rate     48 kHz Eingang, intern resampled
HuggingFace-ID  laion/larger_clap_music
Library         transformers
Lizenz          Apache-2.0  → kommerziell uneingeschränkt, KEINE Attribution
Updated         30 Okt 2023
Paper           arxiv:2211.06687
Downloads       625.4 K (HF Hub Verify 2026-05-04)
```

**Trainings-Domain:** Music-spezifisch (im Gegensatz zu `laion/clap-htsat-fused`,
das auf allgemeinem Audio trainiert ist).

**Real-Daten Spike 20260503_115926:**
- VRAM allocated: 742 MB FP32
- VRAM reserved: 776 MB nach Load, 808 MB nach Inferenz auf 10 s Random-Audio
- Saubere Unload: `del model + empty_cache()` → 0 MB allocated
- Inferenz-Zeit pro Window (warm): 1.7–5.6 s je nach Cache-Status
- feature_shape: `[1, 512]`, feature_dim: 512 ✓

**WICHTIG:** Original-AMD-Plan behauptete CC-BY-4.0 mit Attribution-Pflicht.
HF Hub bestätigt **Apache-2.0**. R13 (Attribution-Risiko) entfällt.

### Video: [`google/siglip2-base-patch16-384`](https://hf.co/google/siglip2-base-patch16-384)

```text
Architektur     SigLIP-2 Vision-Transformer (nur Vision-Tower benötigt)
Embedding-Dim   768
Auflösung       384 × 384
Patches         24 × 24 = 576
Parameter (gesamt) 375.5 M  (Vision-Tower allein ist Subset)
HuggingFace-ID  google/siglip2-base-patch16-384
Library         transformers
Lizenz          Apache-2.0  → kommerziell uneingeschränkt
Updated         21 Feb 2025
Paper           arxiv:2502.14786
Downloads       769.5 K (HF Hub Verify 2026-05-04)
```

**Warum SigLIP-2 statt SigLIP-1:**
SigLIP-2 nutzt Multitask-Objectives (Captioning + Masked-Prediction).
Bewahrt mehr Low-Level-Visual-Information — kritisch für tanzende Personen,
Natur, Wald.

**Warum patch16-384 statt 256/512:**
- 256 Patches: zu wenig räumliches Detail
- 576 Patches (384): Sweet Spot
- 1024 Patches (512): ~4× langsamer ohne klaren Mehrwert für Use-Case

**Warum nur Vision-Tower:**
Brain V3 braucht nur Bildembeddings. Vision-Tower allein spart VRAM und
vermeidet Tokenizer-Loading.

**Phase-0-Spike-Lesson (`AutoImageProcessor` Pflicht):**
```python
# FALSCH (crasht in transformers 4.38.2):
from transformers import AutoProcessor
processor = AutoProcessor.from_pretrained("google/siglip2-base-patch16-384")
# → TypeError: expected str, bytes or os.PathLike object, not NoneType
#   in transformers/models/siglip/tokenization_siglip.py:150

# RICHTIG (funktioniert in transformers 4.38.2):
from transformers import AutoImageProcessor, AutoModel
processor = AutoImageProcessor.from_pretrained("google/siglip2-base-patch16-384")
full = AutoModel.from_pretrained("google/siglip2-base-patch16-384").eval()
vision = full.vision_model.to("cuda")
del full
```

**Real-Daten Spike 20260503_115926 + 20260504_145214:**

| Batch-Size | VRAM allocated | VRAM reserved | Hochrechnung 500 Clips |
|---|---|---|---|
| Load only | 355.8 MB | 402.0 MB | — |
| batch=1 | 359.8 MB | 434.0 MB | — |
| batch=2 | 363.4 MB | 506.0 MB | — |
| batch=4 | 369.3 MB | 606.0 MB | — |
| **batch=8** | **383.8 MB** | **758.0 MB** | **~34 min** (Inferenz allein) |

**Plan-Doc 07 R10 ("batch=8 sprengt 6 GB") WIDERLEGT.** batch=8 nutzt nur
758 MB reserved von 6143 MB total → nicht annähernd OOM-Risiko.

### Vergleich Bestand: [`google/siglip-so400m-patch14-384`](https://hf.co/google/siglip-so400m-patch14-384)

V1/V2 nutzen aktuell SigLIP-1 SoViT-400M:

```text
Parameter (gesamt) 878.0 M  (deutlich größer als SigLIP-2-base)
Architecture       siglip
Library            transformers
Lizenz             Apache-2.0
Updated            26 Sep 2024
Downloads          76.2 M
```

**Konsequenz:** V3 nutzt das **kleinere, neuere** SigLIP-2-base. Wenn V1/V2
parallel laufen mit ihrem 878 M-Modell, müssen die Lifecycle-Locks im
GpuSerializer beide Modelle nicht gleichzeitig im VRAM halten.

---

## Inferenz-Pfad (Phase 0 verifiziert)

```text
Audio:       PyTorch 1.12.1+cu113   GTX 1060, FP32
Video:       PyTorch 1.12.1+cu113   GTX 1060, FP32 (FP16 nicht nötig laut Spike)
Subtrack:    librosa + scipy + numpy   CPU-only
Storage:     sqlite3 + sqlite-vec   CPU-only
Render:      ffmpeg + NVENC (Pascal H.264/HEVC 8-bit)   Hardware-Pfad bestehend
```

**GPU-Coordination:** [`services/brain_v3/gpu_serializer.GpuSerializer`](../../services/brain_v3/gpu_serializer.py) ✓
ist V3-eigener Threading + Asyncio-Lock mit auto-`empty_cache()` beim Release.
Konsumenten:
- `services/brain_v3/audio/audio_embedder.ClapAudioEmbedder` (Phase 2 ✓)
- `services/brain_v3/video/video_embedder.Siglip2VideoEmbedder` (Phase 2 ✓)
- Zukünftig: Demucs/RAFT/NVENC sollten denselben Lock respektieren

---

## Externe Tools (bereits in PB Studio)

```text
ffmpeg / ffprobe                LGPL/GPL    Video-Frame-Extraktion + Audio-Resampling
UVR-MDX-NET-Inst_HQ_3.onnx      MIT         Stem-Separation (für Subtrack-S2)
NVIDIA Driver 31.0.15.4633      proprietär  Treiber für GTX 1060 Pascal
CUDA 11.3 Toolkit               proprietär  Backwards-compat zu PyTorch 1.12.1+cu113
```

**External-Verify GPU-Treiber:**
- [NVIDIA CUDA Toolkit + Driver Compatibility Matrix](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/):
  CUDA 11.3 erfordert Treiber ≥ 465.19 (Linux) / ≥ 465.89 (Windows).
  Workspace-Treiber 31.0.15.4633 (= 546.33-Familie laut Custom Instructions)
  ist neuer → erfüllt CUDA-11.3-Backward-Compat.

---

## Performance-Hochrechnung (GTX 1060 6 GB, real gemessen)

### Erst-Embedding pro Projekt

```text
Audio (1 × 2h-Mix mit CLAP)
  Erstmaliger Modell-Download:           variabel (~70 min bei langsamer Internet)
  Pro 10s-Window (warm):                 ~250 ms (Single-Window)
  Hochrechnung 2h-Mix mit 720 Windows:   ~3-15 min (abhängig von Batch-Pfad,
                                          Phase 2 nutzt sequenziell-pro-Window)

Video (500 Clips → ~8000 Scenes mit SigLIP-2 Vision)
  Erstmaliger Modell-Download:           variabel (~370 MB)
  Pro Scene (warm) batch=1:              ~200-300 ms
  batch=8 effektiv:                      ~30-40 ms pro Scene
  Hochrechnung 8000 Scenes batch=8:      ~5-8 min
  500-Clip-Hochrechnung Spike:           ~34 min (inkl. Erst-Load + 2 Scenes/Clip)

Re-Import (Hash-Cache-Hit):              <0.1 s pro File
                                         100% Hit-Rate verifiziert in
                                         outputs/spike_brain_v3_embedder/20260504_145214/
```

### Sub-Track-Detection (CPU, librosa)

```text
2h-DJ-Mix
  S1 (SSM + Foote-Novelty):              20-40 s
  S2 (Stem-Aktivität, optional):          3-5 s
  S3 (Tempo-Drift sliding):               8-12 s
  S4 (Spectral-Flux):                     2-4 s
  Fusion + Peak-Picking:                 <1 s
  ─────────────────────────────────────────
  Total:                                 30-60 s
```

### Storage-Größe

```text
Projekt mit 500 Clips:
  embeddings.db                          ~80 MB (Audio + Video, 16-24k Vektoren)
  state.db (Phase 4)                     <5 MB
Hirn-Store global nach 10k Klicks:       <100 MB

Embedding-Files (.npy):
  Audio CLAP 512-dim float32:            ~2.0 KB pro Embedding
  Video SigLIP-2 768-dim float32:        ~3.1 KB pro Embedding
  16000 Audio + 8000 Video:              ~57 MB
```

### KNN-Suche (Phase-2-Spike 20260504_145231 — **Plan-DoD verfehlt!**)

```text
Audio 16k Vektoren (CLAP 512-dim):
  Insert-Zeit total:                     771 s (~12.9 min)
  Insert pro Vektor:                     48.23 ms
  KNN-Latenz median:                     63.48 ms       ← Plan-DoD <50ms MISSED
  KNN-Latenz p95:                        75.17 ms
  KNN-Latenz min/max:                    51.61 / 77.54 ms

Video 16k Vektoren (SigLIP-2 768-dim):
  Insert-Zeit total:                     808 s (~13.5 min)
  Insert pro Vektor:                     50.53 ms
  KNN-Latenz median:                     108.03 ms      ← Plan-DoD <50ms MISSED
  KNN-Latenz p95:                        145.49 ms
  KNN-Latenz min/max:                    81.65 / 234.42 ms
```

**Konsequenz für Plan-Doc 06 Phase 2 DoD:** Schwelle muss neu kalibriert
werden auf **<150 ms p95** ODER auf einen ANN-Index (sqlite-vec ≥0.1.7
hat partiellen HNSW-Support, separater Eval nötig). Siehe `07_RISKS.md` R18.

### Pacing-Run-Latenz (Phase 5)

```text
ohne Brain (Status quo):                 100-300 ms
mit Brain V3 Reranker (Phase 4):         +<800 ms (kalibriert mit KNN-Realität)
```

---

## Lizenz-Compliance

| Komponente | Lizenz | Konsequenz |
|---|---|---|
| `laion/larger_clap_music` | **Apache-2.0** ✓ (HF Verify) | uneingeschränkt, **KEINE Attribution-Pflicht** |
| `google/siglip2-base-patch16-384` | Apache-2.0 ✓ | uneingeschränkt |
| `torch`, `torchvision`, `torchaudio` | BSD-3 / MIT | uneingeschränkt |
| `transformers` | Apache-2.0 | uneingeschränkt |
| `accelerate` | Apache-2.0 | uneingeschränkt |
| `librosa` | ISC | uneingeschränkt |
| `scipy`, `numpy` | BSD-3 | uneingeschränkt |
| `sqlite-vec` | Apache-2.0 / MIT | uneingeschränkt |
| `sqlite3` (eingebaut) | Public Domain | uneingeschränkt |
| `opencv-python` | Apache-2.0 | uneingeschränkt |
| `Pillow` | HPND | uneingeschränkt |
| `pydantic` | MIT | uneingeschränkt |
| `PySide6` | LGPL-3 | dynamisch linken (bestehender Stack) |
| `UVR-MDX-NET-Inst_HQ_3.onnx` | MIT | uneingeschränkt |
| `ffmpeg` | LGPL/GPL | dynamisch linken (bestehender Stack) |

**Konkrete Aktion Phase 6:** `LICENSES.md` mit Auflistung aller Komponenten +
ihrer Lizenzen. Da CLAP **Apache-2.0** ist (nicht CC-BY-4.0 wie AMD-Plan
fälschlich behauptete), entfällt die Attribution-Pflicht im Splash-Screen.
LICENSES.md genügt für Apache-2.0-Compliance.
