# 02 — Recherche Video-Modelle (Verified 2026-05-19)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 1 Foundation
> Status: verified · 2026-05-19 in conda-env `pb-studio`

## Real-Stand (verified via Probe-Skript)

| Komponente | Version | Status | Notes |
|---|---|---|---|
| **PySceneDetect** | `scenedetect 0.7` | installiert | BSD-3-Clause |
| **torch** | `1.12.1+cu113` | installiert | CUDA 11.3 |
| **torchvision** | `0.13.1+cu113` | installiert | RAFT `raft_large` + `raft_small` verfuegbar |
| **transformers** | `4.38.2` | installiert | Apache-2.0 — `AutoModel`/`AutoProcessor` ok |
| **Pillow** | `11.3.0` | installiert | PIL.HPND |
| **numpy** | `1.26.4` | installiert | BSD-3 |
| **ffmpeg** | `8.1-full_build` (gyan.dev) | System-PATH | LGPL/GPL-Build pruefen |
| **PyAV** | — | **FEHLT** | Option offen: installieren ODER subprocess-ffmpeg |
| **imageio-ffmpeg** | — | **FEHLT** | dito |
| **GTX 1060** | cc 6.1, CUDA 11.3 | live verfuegbar | Hartregel D-040 erfuellt |

## Modelle (in LICENSES.md gelistet, in pre_cache_models.py vorgepullt)

| Modell | Lizenz | Status | Verwendung |
|---|---|---|---|
| `google/siglip-so400m-patch14-384` | Apache-2.0 | bereits in PB Studio | bestehender Vision-Pfad V1/V2, **1152-dim** |
| `google/siglip2-base-patch16-384` | Apache-2.0 | bereits in PB Studio (Brain V3) | SigLIP-2, kleiner, **768-dim** |
| `raft_large` (torchvision) | BSD-3 | torchvision-eingebaut | RAFT-Optical-Flow Default |
| `raft_small` (torchvision) | BSD-3 | torchvision-eingebaut | schneller, fuer Balanced-Profile |
| PySceneDetect `ContentDetector` | BSD-3 | scenedetect-Lib | Cut-Detection |

## Empfohlene Default-Modelle (Maximum-Quality auf GTX 1060)

| Rolle | Modell | Bemerkung |
|---|---|---|
| **Vision-Embed** | `google/siglip-so400m-patch14-384` | bestehender Pfad — kein Brain-V3-Konflikt (D-032) |
| **Motion-Flow** | `torchvision.models.optical_flow.raft_large` | best Quality, weights `Raft_Large_Weights.C_T_SKHT_V2` |
| **Scene-Detect** | `scenedetect.detectors.ContentDetector(threshold=27.0)` | bewaehrt |
| **VLM** | siehe Plan B Registry — dynamisch via Auto-Selector | minicpm-v / moondream / llava-phi3 |

## Decoder-Strategie (offene Entscheidung)

Drei Optionen:

| Option | Pro | Contra |
|---|---|---|
| **A — `subprocess.run(['ffmpeg', ...])`** | kein extra dep, system-ffmpeg da | text-parsing, slower per-frame |
| **B — PyAV installieren** | API-native, schneller, NVDEC moeglich | extra dep, build-tools |
| **C — `imageio-ffmpeg`** | py-wheel, einfach | wrapper ueber subprocess |

**Empfehlung:** Option A fuer Tier 1 (sofort verfuegbar, nutzt existierenden FFmpeg). Wenn Performance-Bottleneck: Migration auf PyAV in spaeterer Tier-2-Phase, gepinnte Version.

## Lizenz-Audit zusammengefasst

- **PySceneDetect** BSD-3 ✓
- **torchvision RAFT** BSD-3 ✓
- **SigLIP-1 / SigLIP-2** Apache-2.0 ✓
- **transformers** Apache-2.0 ✓
- **FFmpeg** LGPL/GPL — **Bundling-Variante pruefen** (siehe Plan A `74_DECODER_LICENSE.md`)

Alle bevorzugten Komponenten **distributionstauglich** (sofern FFmpeg LGPL-Build verwendet wird).

## Smoke-Test-Skript (Tier-2-Vorbereitung)

```python
# scripts/spike_video_pipeline_smoke.py (geplant fuer Tier-2-Start)
import torch
import scenedetect
import torchvision
from torchvision.models.optical_flow import raft_large
from transformers import AutoModel, AutoProcessor

assert torch.cuda.is_available()
assert torch.cuda.get_device_capability(0) == (6, 1)

# Scene-Detect Smoke
from scenedetect import detect, ContentDetector
scenes = detect("path/to/Solo_Natur/sample.mp4", ContentDetector())
print(f"Scenes: {len(scenes)}")

# RAFT Smoke
model = raft_large(weights="Raft_Large_Weights.C_T_SKHT_V2").to("cuda:0").eval()
print(f"RAFT loaded: {sum(p.numel() for p in model.parameters())/1e6:.1f}M params")

# SigLIP Smoke
proc = AutoProcessor.from_pretrained("google/siglip-so400m-patch14-384")
mdl = AutoModel.from_pretrained("google/siglip-so400m-patch14-384").to("cuda:0").eval()
print(f"SigLIP loaded: {sum(p.numel() for p in mdl.parameters())/1e6:.1f}M params")
```

## VRAM-Realismus-Messung (Pflicht in Tier-2 Phase 11 vor Pipeline-Aktivierung)

Pro Modell soll der Smoke-Test live messen:
- `nvidia-smi` waehrend Load → exact VRAM-Use
- Inference-Latenz pro Frame
- Ergebnis in `99_OPEN_QUESTIONS.md` eintragen

## Klaerungs-Updates (gegenueber Initial-Entwurf)

- [x] PySceneDetect-Version 0.6.x → tatsaechlich **0.7** in env
- [x] SigLIP-Variant: bestehend `siglip-so400m-patch14-384` (1152-dim) — kein Wechsel noetig
- [x] RAFT in torchvision verfuegbar — kein separates Repo noetig
- [ ] PyAV-Installation: spaeter (Subprocess-FFmpeg reicht Tier 1)
- [ ] FFmpeg-LGPL-vs-GPL-Build fuer Distribution: in Plan A `74_DECODER_LICENSE.md` zu klaeren

## Naechster Schritt

Tier 1 Phase 02 done. Naechste Phase **Tier 1 Phase 03** (Quality-Profiles-Spec konkretisieren) oder direkt Tier 2 Phase 10 (Decoder-Primitive bauen).
