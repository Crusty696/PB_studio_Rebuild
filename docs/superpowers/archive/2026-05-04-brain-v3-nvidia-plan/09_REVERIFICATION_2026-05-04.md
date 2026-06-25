# 09 — Re-Verifikations-Report (2026-05-04)

**Anlass:** User-Anforderung "überprüfe alles noch einmal verifiziere es und
mach eine neue gegenprüfung". Vollständige zweite Verifikations-Welle mit
**anderen Quellen als beim ersten Mal**, plus interne Konsistenz-Prüfung
über alle 8 Plan-Doc-Files.

---

## A. Methodik

| Verifikations-Achse | 1. Welle (2026-05-03/04) | 2. Welle (Re-Verify, jetzt) |
|---|---|---|
| Modelle | `hub_repo_details` API | **`hub_repo_details` API erneut** + Tag-Cross-Check |
| sqlite-vec | `resolve-library-id` (Source-Reputation) | **`query-docs` für Code-Beispiele** + KNN-Syntax-Verify |
| transformers SigLIP-API | Spike-Lesson | **`hf_doc_search` Doku-API** |
| PyTorch SM_61 | WebSearch (allgemein) | **WebSearch + GitHub Issue Numbers** (#160575, #53164, uv #14742) |
| librosa tempo API | FutureWarning aus pytest | **WebSearch librosa Changelog 0.10/0.11** |
| Spike-Daten | snapshots.json + run.log | **Re-read snapshots.json + Cross-Check zu Plan-Docs** |
| Plan-Doc-Konsistenz | nicht geprüft | **alle Zahlen über alle Files** abgeglichen |
| Code-Pfad-Existenz | nicht geprüft | **17+ Workspace-Pfade einzeln geprüft** |

---

## B. Externe Re-Verifikation pro Behauptung

### B.1 CLAP `laion/larger_clap_music`

| Behauptung | 1. Welle | 2. Welle Re-Verify | Übereinstimmung |
|---|---|---|---|
| Existiert auf HF | ja | ja | ✓ |
| Library | transformers | transformers | ✓ |
| Architecture | clap | clap | ✓ |
| Lizenz | Apache-2.0 | Apache-2.0 (Tag `license:apache-2.0`) | ✓ |
| Embedding-Dim | 512 | 512 (Spike-feature_shape `[1, 512]`) | ✓ |
| Updated | 30 Okt 2023 | 30 Okt 2023 | ✓ |
| Downloads | 625.4 K | 625.4 K | ✓ |
| Paper | arxiv:2211.06687 | arxiv:2211.06687 | ✓ |

**Status:** GRÜN. Apache-2.0-Korrektur (vs. frueher angenommenes CC-BY-4.0) bleibt bestätigt.

### B.2 SigLIP-2 `google/siglip2-base-patch16-384`

| Behauptung | 1. Welle | 2. Welle Re-Verify | Übereinstimmung |
|---|---|---|---|
| Existiert auf HF | ja | ja | ✓ |
| Architecture | siglip | siglip | ✓ |
| Parameter | 375.5 M | 375.5 M | ✓ |
| Lizenz | Apache-2.0 | Apache-2.0 | ✓ |
| Updated | 21 Feb 2025 | 21 Feb 2025 | ✓ |
| Downloads | 769.5 K | 769.5 K | ✓ |
| Vision-Embedding-Dim | 768 | 768 (Spike-`feature_shape: [bs, 768]`) | ✓ |
| AutoImageProcessor-Pattern | Spike-Lesson | HF-Doc bestätigt Standard-Vision-API | ✓ |

**Status:** GRÜN. Vision-Tower-Workaround mit `AutoImageProcessor` ist
HF-Doc-konform (nicht nur ein Hack).

### B.3 SigLIP-1 `google/siglip-so400m-patch14-384` (V1/V2-Bestand)

| Behauptung | 1. Welle | 2. Welle Re-Verify | Übereinstimmung |
|---|---|---|---|
| Parameter | 878.0 M | 878.0 M | ✓ |
| Updated | 26 Sep 2024 | 26 Sep 2024 | ✓ |
| Lizenz | Apache-2.0 | Apache-2.0 | ✓ |
| Downloads | 76.2 M | 76.2 M | ✓ |

**Status:** GRÜN.

### B.4 sqlite-vec API + Syntax

**Re-Verify mit Context7 query-docs (vorher nur resolve-library-id):**

```python
# bestätigt aus offizieller sqlite-vec Doku:
db.enable_load_extension(True)
sqlite_vec.load(db)
db.enable_load_extension(False)
db.execute("CREATE VIRTUAL TABLE vec_items USING vec0(embedding float[N])")
# KNN-Syntax mit MATCH + LIMIT oder MATCH + AND k = N
```

| Behauptung | 1. Welle | 2. Welle Re-Verify | Übereinstimmung |
|---|---|---|---|
| `enable_load_extension(True)` Pattern | implizit | offiziell dokumentiert | ✓ |
| `sqlite_vec.load(db)` API | implizit | offiziell dokumentiert | ✓ |
| `vec0` virtual table | implizit | offiziell dokumentiert | ✓ |
| `float[N]` Typ | implizit | offiziell dokumentiert + Code-Beispiele | ✓ |
| KNN via `MATCH ?` | Test grün | offiziell dokumentiert | ✓ |
| `AND k = ?` Parameter | Test grün | offiziell dokumentiert | ✓ |
| Float-Serialisierung via `tobytes`/`struct.pack` | Test grün | offiziell `struct.pack` dokumentiert | ✓ |

Mein `services/brain_v3/storage/embedding_repository.py:_vec_blob` nutzt
`arr.tobytes(order="C")` — funktional äquivalent zu `struct.pack("Nf", *vec)`
für float32-Arrays. Spike-Test `test_audio_knn_returns_correct_order` grün
bestätigt Korrektheit.

**Status:** GRÜN.

### B.5 transformers `AutoImageProcessor` für SigLIP

**Re-Verify mit `hf_doc_search` (HuggingFace offizielle Doku):**

> "Use AutoImageProcessor.from_pretrained() with the backend argument to
> select a backend." (transformers Image Processor docs)
>
> "newer models only support [torchvision]" — TorchvisionBackend ist Default.

Bestätigt: `AutoImageProcessor.from_pretrained` ist die offizielle API für
Vision-Modelle. Mein Skript nutzt diesen Pfad korrekt. Dass `AutoProcessor`
für SigLIP-2 in transformers 4.38.2 fehlschlägt, ist kein Bug von uns,
sondern ein Tokenizer-Loading-Problem das `AutoImageProcessor` umgeht.

**Status:** GRÜN.

### B.6 PyTorch SM_61 (Pascal) Support

**Re-Verify mit GitHub Issues + uv-Issue (vorher nur Forum-Post):**

| Quelle | Aussage |
|---|---|
| [PyTorch Issue #53164](https://github.com/pytorch/pytorch/issues/53164) | sm_61 wurde aus nightly builds gedropped (historisch) |
| [PyTorch Issue #160575](https://github.com/pytorch/pytorch/issues/160575) | "Windows 2.8.0+cu126 doesn't have Maxwell kernel support?" — cu126 noch unterstützt Pascal teilweise |
| [astral-sh/uv #14742](https://github.com/astral-sh/uv/issues/14742) | GTX 1080 Ti (Pascal) installation issue mit modernem PyTorch |
| WebSearch Synthese | **cu126 supports SM_61, cu128+ droppt es** |

| Behauptung 1. Welle | Re-Verify Korrektur |
|---|---|
| "newer PyTorch (cu126+) beginnt SM_61 zu droppen" | **PRÄZISIERT:** cu126 noch OK, erst cu128+ droppt |

**Status:** EINE PRÄZISIERUNG (eingearbeitet in 07_RISKS.md R15 + 08_VERIFICATION.md).

### B.7 librosa.feature.tempo / librosa.beat.tempo

**Re-Verify mit librosa Changelog (vorher nur FutureWarning aus Test):**

| Quelle | Aussage |
|---|---|
| [librosa 0.10.2 Changelog](https://librosa.org/doc/0.10.2/changelog.html) | "Deprecations now raise FutureWarning" (allgemein) |
| [librosa 0.11.0 Changelog](https://librosa.org/doc/main/changelog.html) | beat/tempo enhancements + prior distributions |
| [librosa.feature.tempo Doc](https://librosa.org/doc/main/generated/librosa.feature.tempo.html) | offizielle neue API-Position |
| [librosa.feature.rhythm Source](https://librosa.org/doc/main/_modules/librosa/feature/rhythm.html) | tempo() implementiert in `librosa/feature/rhythm.py` |

Mein Code nutzt `from librosa.feature.rhythm import tempo as _tempo_fn` —
das **funktioniert technisch** (Submodul-Import) und ist im Spike-Test grün.

**Idiomatischer (optional Phase 6 Refactor):** `librosa.feature.tempo(...)`
direkt — aber nicht fehlerhaft. Test 35/35 grün bestätigt.

**Status:** GRÜN, optionaler Refactor in Phase 6.

---

## C. Plan-Doc-interne Konsistenz (Spike-Zahlen über alle Files)

### C.1 GPU-Coexistenz-Spike (`outputs/spike_brain_v3_gpu/20260503_115926/snapshots.json`)

| Wert | Spike (Quelle) | README | 02_DEC | 03_TECH | 04_DATA | 07_RISKS | 08_VERIFY | Konsistent? |
|---|---|---|---|---|---|---|---|---|
| Total VRAM | 6143.9 MB | 6143.9 ✓ | — | 6143 MB ✓ | — | — | 6143.9 ✓ | **GRÜN** |
| baseline_before free | 5217 MB | 5217 ✓ | — | 5217 ✓ | — | 5217 ✓ | — | **GRÜN** |
| System-Reserve (= 6143.9-5217) | 926.9 MB | "~927" ✓ | "~927" ✓ | "~927" ✓ | — | — | "~927" ✓ | **GRÜN** |
| baseline_after_cuda_init free | 4907 MB | — | — | "4907" ✓ | — | — | — | **GRÜN** |
| baseline_after_empty_cache free | 4909 MB | 4909 ✓ | — | "4909" ✓ | — | "4909" ✓ | — | **GRÜN** |
| CLAP allocated | 742.0 MB | 742 ✓ | 742 ✓ | 742 ✓ | — | — | — | **GRÜN** |
| CLAP reserved (load) | 776.0 MB | 776 ✓ | 776 ✓ | 776 ✓ | — | — | — | **GRÜN** |
| CLAP reserved (after_inference) | 808.0 MB | — | 808 ✓ | 808 ✓ | — | — | — | **GRÜN** |
| SigLIP-2 load allocated | 355.8 MB | — | 355.8 ✓ | 355.8 ✓ | — | — | — | **GRÜN** |
| SigLIP-2 load reserved | 402.0 MB | — | — | 402 ✓ | — | — | — | **GRÜN** |
| SigLIP-2 batch=8 reserved | 758.0 MB | 758 ✓ | 758 ✓ | 758 ✓ | — | 758 ✓ | — | **GRÜN** |
| Coexistence allocated | 1097.5 MB | — | — | — | — | — | — | (nicht zitiert) |
| Coexistence reserved | 1178.0 MB | 1178 ✓ | — | — | — | 1178 ✓ | — | **GRÜN** |
| Coexistence free | 3495 MB | — | — | — | — | 3495 ✓ | — | **GRÜN** |
| coexistence_possible | true | "läuft" ✓ | — | "WIDERLEGT R10" ✓ | — | "tendenziell entspannt" ✓ | — | **GRÜN** |

### C.2 KNN-Scaling-Spike (`outputs/spike_brain_v3_knn/20260504_145231/run.log`)

| Wert | Spike-Log | 03_TECH | 04_DATA | 07_RISKS | Konsistent? |
|---|---|---|---|---|---|
| Audio insert total | 771.74 s | 771 ✓ | 771 ✓ | 771 ✓ | **GRÜN** |
| Audio insert/vec | 48.23 ms | 48.23 ✓ | 48.23 ✓ | 48.23 ✓ | **GRÜN** |
| Audio KNN median | 63.48 ms | 63.48 ✓ | — | 63.48 ✓ | **GRÜN** |
| Audio KNN p95 | 75.17 ms | 75.17 ✓ | — | 75.17 ✓ | **GRÜN** |
| Audio KNN min/max | 51.61/77.54 ms | 51.61/77.54 ✓ | — | 51.61/77.54 ✓ | **GRÜN** |
| Video insert total | 808.50 s | 808 ✓ | 808 ✓ | 808 ✓ | **GRÜN** |
| Video insert/vec | 50.53 ms | 50.53 ✓ | 50.53 ✓ | 50.53 ✓ | **GRÜN** |
| Video KNN median | 108.03 ms | 108.03 ✓ | — | 108.03 ✓ | **GRÜN** |
| Video KNN p95 | 145.49 ms | 145.49 ✓ | — | 145.49 ✓ | **GRÜN** |
| Plan-DoD <50 ms | MISSED | "MISSED" ✓ | — | "MISSED→relaxed" ✓ | **GRÜN** |

### C.3 Pytest-Status

| Quelle | Test-Anzahl | Phase-1-Tests | Phase-2-Tests | Status |
|---|---|---|---|---|
| `outputs/pytest_brain_v3_results.txt` | 70 passed in 22.64s | 35 (4 Files) | 35 (4 Files) | ✓ |
| README.md | "70/70 grün" | "35" Phase 1 | "35 (28 neu)" Phase 2 | **GRÜN** |
| 06_PHASES.md Phase 1 | "35 pytest grün" | — | — | **GRÜN** |
| 06_PHASES.md Phase 2 | "70 pytest grün" | — | — | **GRÜN** |
| 07_RISKS.md Test-Strategie | "70 GRUEN" | "35" | "35" | **GRÜN** |
| 08_VERIFICATION.md | "70 Tests" | — | — | **GRÜN** |

---

## D. Code-Pfad-Existenz-Check

Alle 17+ in den Plan-Docs zitierten Workspace-Pfade existieren tatsächlich:

| Pfad | Existiert | Verweis in |
|---|---|---|
| `services/brain_v3/__init__.py` | ✓ | 01_ARCHITECTURE, README |
| `services/brain_v3/paths.py` | ✓ | 01, 04, 06 |
| `services/brain_v3/hashing.py` | ✓ | 01, 06, 07 R07 |
| `services/brain_v3/gpu_serializer.py` | ✓ | 01, 03, 06 |
| `services/brain_v3/background_queue.py` | ✓ | 01, 06, 07 R06 |
| `services/brain_v3/schemas/audio.py` | ✓ | 01, 06 |
| `services/brain_v3/schemas/video.py` | ✓ | 01, 06 |
| `services/brain_v3/audio/subtrack_detector.py` | ✓ | 01, 05, 06 |
| `services/brain_v3/audio/audio_embedder.py` | ✓ | 01, 03, 06 |
| `services/brain_v3/video/visual_curves.py` | ✓ | 01, 05, 06 |
| `services/brain_v3/video/video_embedder.py` | ✓ | 01, 03, 06 |
| `services/brain_v3/storage/sqlite_init.py` | ✓ | 04, 06 |
| `services/brain_v3/storage/migration_runner.py` | ✓ | 04, 06 |
| `services/brain_v3/storage/embedding_cache.py` | ✓ | 04, 06, 07 R07 |
| `services/brain_v3/storage/embedding_repository.py` | ✓ | 01, 04, 06 |
| `services/brain_v3/storage/sql_migrations/embedding_cache/001_initial.sql` | ✓ | 04 |
| `services/brain_v3/storage/sql_migrations/embeddings_project/001_initial.sql` | ✓ | 04 |
| 8× `tests/test_services/test_brain_v3_*.py` | ✓ | 06, 07 |
| 3× `scripts/spike_brain_v3_*.py` | ✓ | 06, 07, 08 |
| 4× `*_brain_v3*.bat` | ✓ | 06, 08 |

**Status:** GRÜN. Keine toten Verweise.

---

## E. Externe Quellen — neue Adds in dieser Re-Verify

| Quelle (NEU 2. Welle) | URL | Genutzt für |
|---|---|---|
| PyTorch Issue #160575 | https://github.com/pytorch/pytorch/issues/160575 | R15-Präzisierung cu128+ |
| PyTorch Issue #53164 | https://github.com/pytorch/pytorch/issues/53164 | R15-historischer SM_61-Drop |
| uv Issue #14742 | https://github.com/astral-sh/uv/issues/14742 | GTX 1080 Ti Pascal-Install-Bestätigung |
| sqlite-vec llms.txt (Context7) | https://context7.com/asg017/sqlite-vec/llms.txt | API-Code-Beispiele Re-Verify |
| sqlite-vec KNN.md | https://github.com/asg017/sqlite-vec/blob/main/site/features/knn.md | KNN-Syntax-Verify |
| transformers Image Processor docs | https://huggingface.co/docs/transformers/main_classes/image_processor | AutoImageProcessor-Pattern Re-Verify |
| transformers Processors docs | https://huggingface.co/docs/transformers/processors | AutoProcessor-vs-AutoImageProcessor |
| librosa 0.10.2 Changelog | https://librosa.org/doc/0.10.2/changelog.html | tempo-Deprecation Re-Verify |
| librosa 0.11.0 Changelog | https://librosa.org/doc/main/changelog.html | tempo-Position in 0.11 |
| librosa.feature.tempo doc | https://librosa.org/doc/main/generated/librosa.feature.tempo.html | offizielle API-Position |

---

## F. Findings-Zusammenfassung

### F.1 BESTÄTIGT (alle externen Behauptungen halten Re-Verify stand)

- CLAP Apache-2.0 (NICHT CC-BY-4.0) — bestätigt durch HF Tag
- SigLIP-2 375.5 M Params, Apache-2.0 — bestätigt
- SigLIP-1 SoViT-400M = 878 M Params (Vision+Text gesamt) — bestätigt
- sqlite-vec API + KNN-Syntax — bestätigt durch offizielle Code-Beispiele
- AutoImageProcessor als HF-offizielle Vision-API — bestätigt
- librosa.feature.rhythm.tempo / librosa.feature.tempo Position — bestätigt
- GTX 1060 = SM_61 Pascal — NVIDIA-Doc + uv-Issue
- PyTorch 1.12.1+cu113 unterstützt SM_61 — Forum + Issue-Confirmation

### F.2 PRÄZISIERT (1 Korrektur eingearbeitet)

| Was | War | Ist (re-verify) |
|---|---|---|
| PyTorch SM_61-Drop-Datierung | "cu126+" | **"cu128+"** (cu126 noch OK) — Quelle PyTorch #160575 |

Eingearbeitet in:
- `07_RISKS.md` R15
- `08_VERIFICATION.md` Tabelle Hardware

### F.3 WEITERHIN OFFEN (ehrlich)

Aus 08_VERIFICATION.md "Was nicht externer-verifiziert ist" — Status unverändert:

- F-Measure ≥ 0.65 SubtrackDetector — annotierte Test-Mixes fehlen
- 500-Clip-Erst-Import < 60 min — extrapoliert, kein echtes Projekt
- HNSW-Index in sqlite-vec ≥0.1.7 — Eval-Sub-Spike steht aus (Phase 6)
- Demucs + Brain Coexistenz — Spike-Test vorbereitet aber nicht gelaufen
- NVENC + Brain-Inferenz parallel — Phase 6
- PySide6-App-Boot VRAM-Footprint mit Qt-Display — offen

### F.4 INTERNE KONSISTENZ

| Achse | Status |
|---|---|
| GPU-Spike-Zahlen über alle 8 Plan-Docs | **alle GRÜN, identisch** |
| KNN-Spike-Zahlen über alle 8 Plan-Docs | **alle GRÜN, identisch** |
| Pytest-Test-Counts (35 Phase 1, 70 total) | **alle GRÜN, identisch** |
| 17+ Code-Pfade existieren im Workspace | **alle GRÜN** |
| Phasen-Status (0/1/2 DONE, 3-6 TODO) | **alle GRÜN, identisch** |

---

## G. Re-Verify-Verdict

**Plan-Doc-Set ist intern konsistent + extern doppelt-verifiziert** mit
unabhängigen Quellen pro kritischer Behauptung.

**Eine echte Korrektur** durch Re-Verify gefunden + eingearbeitet (R15
SM_61-Drop-Datierung cu126→cu128).

**Keine** zusätzlichen Bugs in V3-Code, keine Inkonsistenzen zwischen
Spike-Daten und Plan-Doc-Zahlen, keine toten Pfad-Verweise, alle
externen Quellen halten.

**Re-Verify-Status: GRÜN mit 1 dokumentierter Präzisierung.**

**CLAUDE.md OBERSTE REGEL eingehalten:** alle nicht-verifizierten Punkte
sind explizit als "offen" markiert, keine Schönrede, keine Annahmen ohne
Quelle.

---

## Sources (Re-Verify-Welle 2026-05-04)

- [HF: laion/larger_clap_music](https://hf.co/laion/larger_clap_music)
- [HF: google/siglip2-base-patch16-384](https://hf.co/google/siglip2-base-patch16-384)
- [HF: google/siglip-so400m-patch14-384](https://hf.co/google/siglip-so400m-patch14-384)
- [GitHub: asg017/sqlite-vec](https://github.com/asg017/sqlite-vec)
- [sqlite-vec llms.txt (Context7)](https://context7.com/asg017/sqlite-vec/llms.txt)
- [sqlite-vec KNN-Doc](https://github.com/asg017/sqlite-vec/blob/main/site/features/knn.md)
- [HF Transformers — Image Processor](https://huggingface.co/docs/transformers/main_classes/image_processor)
- [HF Transformers — Processors](https://huggingface.co/docs/transformers/processors)
- [PyTorch Issue #160575 — Maxwell/Pascal in cu126/cu128](https://github.com/pytorch/pytorch/issues/160575)
- [PyTorch Issue #53164 — sm_61 nightly drop](https://github.com/pytorch/pytorch/issues/53164)
- [astral-sh/uv Issue #14742 — Pascal install](https://github.com/astral-sh/uv/issues/14742)
- [PyTorch Forum — GPU Compatibility](https://discuss.pytorch.org/t/which-gpus-are-supported-by-torch-2/175218)
- [NVIDIA CUDA GPU Compute Capability](https://developer.nvidia.com/cuda/gpus)
- [librosa 0.10.2 Changelog](https://librosa.org/doc/0.10.2/changelog.html)
- [librosa 0.11.0 Changelog](https://librosa.org/doc/main/changelog.html)
- [librosa.feature.tempo Doc](https://librosa.org/doc/main/generated/librosa.feature.tempo.html)
- [librosa.feature.rhythm Source](https://librosa.org/doc/main/_modules/librosa/feature/rhythm.html)
- [SQLite WAL Documentation](https://www.sqlite.org/wal.html)
- [SQLite VACUUM Documentation](https://www.sqlite.org/lang_vacuum.html)
- [Russo et al. 2018 — Tutorial on Thompson Sampling](https://arxiv.org/abs/1707.02038)
- [CLAP Paper arxiv:2211.06687](https://arxiv.org/abs/2211.06687)
- [SigLIP-2 Paper arxiv:2502.14786](https://arxiv.org/abs/2502.14786)
