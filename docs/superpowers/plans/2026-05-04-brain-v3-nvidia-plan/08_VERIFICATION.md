# 08 — Verifikation: Quellen-Mapping + Reproduzierbarkeit

Übersicht aller externen Quellen + interner Spike-Outputs, mit denen die
Plan-Behauptungen gegen-geprüft sind. Pro Behauptung mind. 1 Quelle, bei
kritischen Behauptungen ≥ 2 unabhängige Quellen.

---

## Mapping frueherer verify-Skripte → NVIDIA-Plan-Spikes

Das fruehere Plan-Verzeichnis enthielt 4 verify-Skripte. Diese sind durch
V3-Spikes/Tests ersetzt:

| Frueheres Skript | NVIDIA-Ersatz | Status | Output-Pfad |
|---|---|---|---|
| `verify_clap_*.py` | `scripts/spike_brain_v3_gpu_coexistence.py` (Sektion `clap`) | ✓ verifiziert | `outputs/spike_brain_v3_gpu/20260503_115926/` |
| `verify_siglip_*.py` | `scripts/spike_brain_v3_gpu_coexistence.py` (Sektion `siglip2`) + `scripts/spike_brain_v3_embedder_smoke.py` | ✓ verifiziert | `outputs/spike_brain_v3_gpu/20260503_115926/` + `outputs/spike_brain_v3_embedder/20260504_145214/` |
| `verify_sqlite_vec.py` | `tests/test_services/test_brain_v3_storage_repo.py` (6 Tests) + `scripts/spike_brain_v3_knn_scaling.py` | ✓ verifiziert | pytest output + `outputs/spike_brain_v3_knn/20260504_145231/` |
| `verify_subtrack_detection.py` | `tests/test_services/test_brain_v3_subtrack_detector.py` (5 Tests) | ~ Smoke-verifiziert | pytest output (annotierte Test-Mixes für F-Measure fehlen) |

Zusätzlich V3-eigene Verifikationen:

| V3-Spike/Test | Zweck | Status |
|---|---|---|
| `scripts/spike_brain_v3_gpu_coexistence.py` | VRAM-Budget + Coexistenz CLAP+SigLIP-2 + batch=1/2/4/8 | ✓ |
| `scripts/spike_brain_v3_embedder_smoke.py` | End-to-End Embedder + Cache + Repo + KNN-self-match | ✓ |
| `scripts/spike_brain_v3_knn_scaling.py` | KNN-Latenz median+p95 bei 16k Vektoren | ✓ R18 dokumentiert |
| `tests/test_services/test_brain_v3_*.py` (8 Files, 70 Tests) | Unit + Integration | ✓ 70/70 grün |

---

## Externe Quellen pro Plan-Behauptung

### Modelle

| Behauptung | Quelle | Stand |
|---|---|---|
| `laion/larger_clap_music` existiert, Library `transformers`, Architecture `clap` | [HF Hub](https://hf.co/laion/larger_clap_music) — `hub_repo_details` API | 2026-05-04 |
| CLAP **Apache-2.0** (NICHT CC-BY-4.0 wie frueher angenommen) | HF Hub Tag `license:apache-2.0` | 2026-05-04 |
| CLAP 512-dim Embedding | Spike-Verifikation: `feature_shape: [1, 512]`, `feature_dim: 512` | 2026-05-03 |
| CLAP Window 10 s @ 48 kHz, Hop 5 s | CLAP-Paper [arxiv:2211.06687](https://arxiv.org/abs/2211.06687), HF Model-Card | 2026-05-04 |
| `google/siglip2-base-patch16-384` existiert, Library `transformers` | [HF Hub](https://hf.co/google/siglip2-base-patch16-384) — `hub_repo_details` | 2026-05-04 |
| SigLIP-2 **Apache-2.0** | HF Hub Tag | 2026-05-04 |
| SigLIP-2 375.5 M Parameter | HF Hub Metadata | 2026-05-04 |
| SigLIP-2 768-dim Vision-Embedding | Spike-Verifikation `siglip2_after_load` Snapshots | 2026-05-03 |
| SigLIP-2 batch=8 läuft auf 6 GB GTX 1060 | Spike `outputs/spike_brain_v3_gpu/20260503_115926/snapshots.json` | 2026-05-03 |
| AutoImageProcessor statt AutoProcessor (transformers 4.38.2) | Spike-Lesson Lauf 11:55:50 → 11:56:28 (Tokenizer-Crash) → 11:59:26 (gefixt) | 2026-05-03 |
| `google/siglip-so400m-patch14-384` (Bestand V1/V2) 878 M Params | [HF Hub](https://hf.co/google/siglip-so400m-patch14-384) | 2026-05-04 |

### Hardware + CUDA

| Behauptung | Quelle | Stand |
|---|---|---|
| GTX 1060 = Pascal SM_61 / Compute Capability 6.1 | [NVIDIA CUDA GPU Compute Capability](https://developer.nvidia.com/cuda/gpus) | 2026-05-04 |
| GTX 1060 6 GB Total VRAM = 6143.9 MB | Spike-Snapshot `total_vram_mb` | 2026-05-03 |
| GTX 1060 hat KEINE Tensor Cores | [NVIDIA Pascal Architecture Whitepaper](https://www.nvidia.com/en-us/data-center/resources/pascal-architecture-whitepaper/) — Tensor Cores erst ab Volta GV100 | 2026 |
| GTX 1060 NVENC-Gen 6: H.264, HEVC 8-bit, kein AV1 | [NVIDIA Video Codec SDK Support Matrix](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new) | 2026 |
| PyTorch 1.12.1+cu113 unterstützt SM_61 | [PyTorch Forum](https://discuss.pytorch.org/t/which-gpus-are-supported-by-torch-2/175218) + [PyTorch Issue #160575](https://github.com/pytorch/pytorch/issues/160575) — Re-Verify 2026-05-04: cu126 unterstützt SM_61 noch, **erst cu128+ droppt** | 2026-05-04 |
| CUDA 11.3 erfordert Treiber ≥ 465.89 (Win) | [NVIDIA CUDA Release Notes](https://docs.nvidia.com/cuda/cuda-toolkit-release-notes/) — Workspace 31.0.15.4633 = 546.33-Familie OK | 2026 |
| ~927 MB System-VRAM-Reserve auf GTX 1060 nach Boot | Spike `baseline_before_torch_init` Snapshot frei=5217 MB | 2026-05-03 |

### Python-Stack

| Behauptung | Quelle | Stand |
|---|---|---|
| Workspace nutzt conda-env `pb-studio` (Python 3.10.20) | `start_pb_studio.bat` Python-Auswahl-Logik + Spike-`environment.python` | 2026-05-03 |
| torch 1.12.1+cu113 / torchvision 0.13.1+cu113 / torchaudio 0.12.1+cu113 | `requirements-py310-cu113.txt` + Spike-`environment.torch` | 2026-05-03 |
| transformers 4.38.2 | `requirements-py310-cu113.txt` + Spike-`environment.transformers` | 2026-05-03 |
| librosa 0.10.2 | `requirements-py310-cu113.txt` | — |
| `librosa.feature.rhythm.tempo` API ab librosa 0.10 | librosa CHANGELOG, FutureWarning im Phase-1-Test-Lauf | 2026-05-03 |

### Storage / sqlite-vec

| Behauptung | Quelle | Stand |
|---|---|---|
| `sqlite-vec` existiert + High-Reputation | [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) via Context7 (`/asg017/sqlite-vec`, Snippets 373) | 2026-05-04 |
| sqlite-vec ≥0.1.6 ABI-stabil | `install_brain_v3_phase2_deps.bat` installiert sqlite-vec, `test_brain_v3_storage_repo.py` 6 Tests grün | 2026-05-04 |
| `vec0` virtual table mit `FLOAT[N]` Typ | sqlite-vec Doc, Test `test_repo_init_creates_db_and_schema` | 2026-05-04 |
| MATCH ? + k = ? KNN-Syntax | sqlite-vec Doc, Test `test_audio_knn_returns_correct_order` | 2026-05-04 |
| KNN-Latenz Brute-Force ~50 ms median bei 16k Vektoren CLAP-Dim | Spike `outputs/spike_brain_v3_knn/20260504_145231/` | 2026-05-04 |
| sqlite-vec ≥0.1.7 hat partielle HNSW-Unterstützung | sqlite-vec Release-Notes (Phase 6 Eval) | 2026 |
| WAL-Mode + NORMAL-sync ist crash-sicher | [SQLite WAL-Doc](https://www.sqlite.org/wal.html) — synchronous=NORMAL ist im WAL-Mode safe | 2026 |
| VACUUM INTO ist atomar + online | [SQLite VACUUM-Doc](https://www.sqlite.org/lang_vacuum.html) | 2026 |

### Algorithmus

| Behauptung | Quelle | Stand |
|---|---|---|
| Beta-Bernoulli mit Laplace-Smoothing als Bayesian-Bandit | [Russo et al. 2018 — Tutorial on Thompson Sampling](https://arxiv.org/abs/1707.02038) | 2018 |
| Posterior Mean = (α+1)/(α+β+2) | Standard Bayesian-Statistik (Beta-Posterior für Bernoulli-Likelihood) | Lehrbuch |
| Hierarchical Backoff bei Datenarmut | Standard NLP-Pattern (z.B. Katz Backoff für Sprachmodelle) | Lehrbuch |

### UI-Framework

| Behauptung | Quelle | Stand |
|---|---|---|
| PySide6 6.11 unterstützt Python 3.10 | `pyproject.toml`: `pyside6 = ">=6.6.0,<7.0.0"`, Workspace nutzt 6.11 | 2026 |
| App ist PySide6, NICHT C# WPF | `pyproject.toml` + `start_pb_studio.bat` startet `main.py` (Python) | 2026 |

---

## Spike-Reproduzierbarkeit

Alle Spikes sind via Wrapper-`.bat`-Files reproduzierbar:

```text
run_spike_brain_v3.bat              → Phase-0-Spike (GPU-Coexistenz)
run_pytest_brain_v3.bat             → Phase 1+2 pytest (70/70 erwartet)
install_brain_v3_phase2_deps.bat    → sqlite-vec installieren
run_spike_brain_v3_phase2.bat       → Phase-2-Validation (Embedder + KNN-Scaling)
```

Jeder Spike erzeugt:
- `outputs/<spike_name>/<timestamp>/snapshots.json` — strukturierte Roh-Daten
- `outputs/<spike_name>/<timestamp>/report.md` — Markdown-Synthese
- `outputs/<spike_name>/<timestamp>/run.log` — Roh-Log mit Zeitstempeln

Inkrementeller JSON-Flush nach jedem Test-Schritt → Crash-Safety, Daten
auch bei OOM oder KeyboardInterrupt erhalten.

---

## Vault-Pflicht (CLAUDE.md)

Diese Doku liegt im Workspace. Für externe Vault-Spiegel (Brain-Bug):

- [ ] `C:\Brain-Bug\projects\pb-studio\wiki\plans\brain-v3-nvidia-plan-2026-05-04\`
  → 8 Files (README + 01–07 + 08_VERIFICATION) kopieren
- [ ] `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\` schon dort:
  - `gpu-coexistence-spike-2026-05-03.md` (User-Aktion offen)
  - `brain-v3-phase1-completion-2026-05-03.md` (User-Aktion offen)
  - `brain-v3-phase2-completion-2026-05-03.md` (User-Aktion offen)
- [ ] `log.md`-Eintrag im Vault mit Verweis auf:
  - Plan-Set-Pfad
  - Phase-0/1/2-Status
  - R18 KNN-Latenz-Befund
  - Apache-2.0-Korrektur (R13 entfällt)

---

## Was nicht externer-verifiziert ist (offen)

Ehrlich gemäß CLAUDE.md:

| Behauptung | Status | Was fehlt |
|---|---|---|
| F-Measure ≥ 0.65 SubtrackDetector | offen | annotierte Test-Mixes |
| 500-Clip-Erst-Import < 60 min | extrapoliert | echtes 500-Clip-Projekt |
| HNSW-Index in sqlite-vec ≥0.1.7 erreicht <50 ms | offen | Eval-Sub-Spike |
| Demucs + Brain Coexistenz auf 6 GB | offen | Demucs-Coexistenz-Spike (in `spike_brain_v3_gpu_coexistence.py` als opt-in `--tests demucs` vorbereitet, nicht gelaufen) |
| NVENC + Brain-Inferenz parallel | offen | Phase 6 Test |
| PySide6-App-Boot VRAM-Footprint mit Qt-Display | offen | Spike-Erweiterung |
