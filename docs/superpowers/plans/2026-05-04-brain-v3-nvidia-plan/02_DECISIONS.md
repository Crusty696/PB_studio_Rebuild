# 02 — Designentscheidungen (Brain V3, NVIDIA)

24 finale Entscheidungen — Original 20 (aus frueherem Plan) plus 4 NVIDIA-spezifisch
(#21–#24). Alle mit externer Quellen-Verifikation oder Spike-Daten belegt.

| # | Punkt | Beschluss | Quelle/Verifikation |
|---|---|---|---|
| 1 | Use-Case | A–E parallel + lernfähig durch User-Klicks | F1 (User-Brainstorming) |
| 2 | Lern-Mechanismus | Online ohne Training/Setup | F1 |
| 3 | Audio-Granularität | 3-Tier: window (1 s hop pro CLAP-Window) / section / mix | F11 |
| 4 | Video-Granularität | 2-Tier: scene / clip (frame-level opt-in) | F14 |
| 5 | Vector-DB | **SQLite + sqlite-vec** (Engine-Konsistenz, [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) High-Reputation) | F28 + Context7 |
| 6 | Daten-Schichtung | Projekt-Store ≠ Hirn-Store | F18 |
| 7 | Lern-Algorithmus | Beta-Bernoulli mit Hierarchical Backoff | F19 |
| 8 | Kontext-Konditionierung | Fein, 6 Slots, 5 Backoff-Levels | F20 |
| 9 | Cold-Start | Heuristik-Defaults aus `TriggerSettings`-Dataclass | F17 |
| 10 | Bridge-Achsen | 10 Audio + 7 Video = 17 | F20 |
| 11 | 4-Klick-Mapping | α+2.0 / α+1.0 / β+1.0 / β+2.0 | F20 |
| 12 | Sub-Track-Detection | Heuristisch (4 Signale Fusion), Pflicht synchron, Fallback = 1 Track | F21, F29 |
| 13 | UI-Feedback | Hybrid: On-Demand + optionaler Lern-Session-Dialog | F22 |
| 14 | Embedding-Cache | sha256 Hash, projektübergreifend | F18 |
| 15 | Audio-Modell | [`laion/larger_clap_music`](https://hf.co/laion/larger_clap_music) (512-dim, 10 s Window, 5 s Hop, **Apache-2.0**) | HF Hub Verify 2026-05-04 |
| 16 | Video-Modell | [`google/siglip2-base-patch16-384`](https://hf.co/google/siglip2-base-patch16-384) (Vision-Tower only, 768-dim, **Apache-2.0**, 375.5 M Params) | HF Hub Verify 2026-05-04 |
| 17 | **Inferenz-Pfad** | **PyTorch 1.12.1+cu113**, kein ONNX in Phase 1 | Workspace `requirements-py310-cu113.txt` + Phase-0-Spike |
| 18 | Storage-Concurrency | WAL + busy_timeout=5000 | F28 + sqlite-vec docs |
| 19 | Schema-Migrations | PRAGMA `user_version` + nummerierte SQL-Skripte | F28 |
| 20 | Backup | `VACUUM INTO` atomar, wöchentlich | F28 + SQLite-Doc |
| **21** | **VRAM-Budget** | **Brain-Inferenz max 4.0 GB gleichzeitig (real verbleibend nach System-Reserve)** | Spike 20260503_115926: total 6143.9 MB, frei 5217 MB nach Boot, 4909 MB nach CUDA-init |
| **22** | **Precision** | **FP32 Default. Kein BF16 (Pascal kann es nicht). FP16 NICHT nötig (Spike: CLAP+SigLIP zusammen <1.2 GB FP32)** | Spike-Daten + NVIDIA Pascal Compute-Capability-Doc |
| **23** | **NVENC-Koexistenz** | **Render-Pfad nutzt NVENC (Pascal H.264/HEVC 8-bit, kein AV1). GpuSerializer serialisiert mit Brain-Inferenz** | NVIDIA Video-Codec-SDK-Matrix für Pascal |
| **24** | **V1/V2-Trennung** | **V3 separater Code-Namespace (`services/brain_v3/`), eigene DBs (`%APPDATA%\PB_Studio\brain_v3\`), eigener UI-Tab. V1 und V2 duerfen umgebaut werden, ABER pro Refactor ist eine Live-Verifikation der V1/V2-Funktion erforderlich (Regression-Test, kein bytewise-Identitaet erforderlich aber funktional unveraendert)** | User-Direktive 2026-05-03 (Original) + User-Direktive 2026-05-05 F2 (V1/V2-Refactor freigegeben) |

---

## Begründungen — Schlüsselentscheidungen

### #5: SQLite + sqlite-vec statt ChromaDB

ChromaDB hat 2025–2026 mehrere kritische Bugs auf Windows 11 (Issues #5392,
#5868, #5909, #2446) — File-Locking, Rust-Panics, Persistenz-Korruption.

SQLite + sqlite-vec ist auf Windows rock-solid, hat WAL-Concurrency,
atomare `VACUUM INTO`-Backups und ist zur Hirn-Store-Engine identisch.

**External-Verify:**
- [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) — pure-C extension,
  unterstützt float/int8/binary Vektoren, Source Reputation: High
- Im Workspace bereits via `install_brain_v3_phase2_deps.bat` installiert
  und durch `test_brain_v3_storage_repo.py` (6 Tests) verifiziert.

### #7+#8: Beta-Bernoulli mit Hierarchical Backoff

Pro Achse + Kontext werden α (positive Erfahrungen) und β (negative)
gezählt. Posterior Mean = `(α+1)/(α+β+2)` ergibt eine geglättete
Wahrscheinlichkeit zwischen 0 und 1.

Hierarchischer Backoff über 5 Levels: bei zu wenig Daten in spezifischem
Kontext fällt der Lookup auf allgemeineren Kontext zurück. Threshold
`MIN_CONFIDENT = 10 Samples` pro Level.

**Quelle:** Standard-Bayes-Bandit-Literatur. Implementation in Phase 3.

### #11: 4-Klick-Mapping

| Klick | α-Inkrement | β-Inkrement | Bedeutung |
|---|---|---|---|
| Passt perfekt | +2.0 | 0 | starkes positives Signal |
| Passt | +1.0 | 0 | schwaches positives Signal |
| Passt nicht ganz | 0 | +1.0 | schwaches negatives Signal |
| Passt gar nicht | 0 | +2.0 | starkes negatives Signal |

Update auf **allen 5 Backoff-Levels gleichzeitig** in einer Transaktion.
17 Achsen × 6 Levels (0..5) = **102 Bucket-Updates pro Klick** (Code-Wahrheit; ursprünglicher Plan-Wert "85" war Schreibfehler — Level 0 muss mit-geschrieben werden damit Backoff-Lookup einen globalen Confidence-Anker hat).

### #15: CLAP Audio-Modell

**[`laion/larger_clap_music`](https://hf.co/laion/larger_clap_music)** —
HuggingFace-Verifikation 2026-05-04:

| Eigenschaft | Wert |
|---|---|
| Embedding-Dim | 512 |
| Window-Size | 10 s |
| Hop-Size | 5 s (50 % Overlap) |
| Sample-Rate | 48 kHz Eingang |
| Architecture | clap |
| Library | transformers |
| Downloads | 625.4 K |
| **Lizenz** | **Apache-2.0** |
| Updated | 30 Okt 2023 |
| Paper | [arxiv:2211.06687](https://arxiv.org/abs/2211.06687) |

**WICHTIG — Korrektur gegenüber frueherem Plan:** Der ursprueng­liche Plan
behauptete CC-BY-4.0 mit Attribution-Pflicht. **Das ist falsch.** HF Hub
zeigt Apache-2.0 → kommerziell uneingeschränkt, **keine Attribution-Pflicht**.
Plan-Doc 07 R13 entfällt entsprechend.

**Trainings-Domain:** Music-spezifisch (im Gegensatz zu `laion/clap-htsat-fused`,
das auf allgemeinem Audio trainiert ist). Geeignet für DJ-Mix-Charakterisierung.

**Spike-Verifikation 20260503_115926:**
VRAM-Footprint: 742 MB allocated, 776 MB reserved, ~810 MB inkl. Inferenz.
Sauberer Unload via `del model + torch.cuda.empty_cache()` setzt zurück auf 0 MB.

### #16: SigLIP-2 Video-Modell

**[`google/siglip2-base-patch16-384`](https://hf.co/google/siglip2-base-patch16-384)** —
HuggingFace-Verifikation 2026-05-04:

| Eigenschaft | Wert |
|---|---|
| Embedding-Dim (Vision) | 768 |
| Auflösung | 384 × 384 |
| Patch-Größe | 16 → 576 Patches |
| Parameter (gesamt) | 375.5 M |
| Architecture | siglip |
| Library | transformers |
| Downloads | 769.5 K |
| **Lizenz** | **Apache-2.0** |
| Updated | 21 Feb 2025 |
| Paper | [arxiv:2502.14786](https://arxiv.org/abs/2502.14786) |

**Warum SigLIP-2 statt SigLIP-1:** SigLIP-2 wurde mit Multitask-Objectives
trainiert (Captioning + Masked-Prediction). Bewahrt mehr Low-Level-Visual-
Information — kritisch für photorealistisches Material wie tanzende Personen,
Natur, Wald.

**Warum patch16-384:** 576 Patches → Sweet Spot für Personen + Natur.
- 256 Patches: zu wenig räumliches Detail
- 1024 Patches (512px): ~4× langsamer ohne klaren Mehrwert

**Warum nur Vision-Tower:** Wir brauchen nur Bildembeddings, kein Text-Encoder.
Plan-Doc 03 #16 macht klar: `AutoModel.from_pretrained(...).vision_model`
extrahieren, Text-Tower löschen.

**WICHTIG — Phase-0-Spike-Lesson:**
- `AutoProcessor.from_pretrained` schlägt mit transformers 4.38.2 fehl
  (`TypeError: vocab_file is None` — Tokenizer-Loader-Bug bei SigLIP-2).
- Workaround: **`AutoImageProcessor.from_pretrained`** (lädt nur die
  Bild-Seite, kein Tokenizer). Funktioniert ohne transformers-Upgrade.
- Spike-Verifikation: 355 MB load, 758 MB reserved bei batch=8 — **Plan-Doc 07 R10
  WIDERLEGT** ("batch=8 sprengt 6 GB" war falsch).

### #16-Vergleich: Bestand-SigLIP-1

Workspace V1/V2 nutzt [`google/siglip-so400m-patch14-384`](https://hf.co/google/siglip-so400m-patch14-384):

| Eigenschaft | Wert |
|---|---|
| Parameter (gesamt) | **878.0 M** (deutlich größer als SigLIP-2-base) |
| Architecture | siglip (V1) |
| Lizenz | Apache-2.0 |
| Updated | 26 Sep 2024 |

V3 nutzt das **kleinere** SigLIP-2-base-patch16-384 statt das große SigLIP-1
SoViT-400M. Spike-Coexistenz-Test bestätigt: V3-CLAP+SigLIP-2 zusammen 1178 MB
reserved (passt locker neben V1/V2 falls die separat geladen wären).

### #17: PyTorch 1.12.1+cu113

PyTorch+CUDA ist nativ unterstützter Pfad. Workspace nutzt cu113 wegen
Surface-Book-2-Treiber-Reihenfolge (siehe `requirements-py310-cu113.txt`):

```text
torch==1.12.1+cu113
torchaudio==0.12.1+cu113
torchvision==0.13.1+cu113
transformers==4.38.2
```

**External-Verify:**
- [PyTorch GPU Compatibility Forum](https://discuss.pytorch.org/t/which-gpus-are-supported-by-torch-2/175218):
  PyTorch 1.12 unterstützt SM_61 (Pascal) — newer PyTorch builds (cu126+)
  beginnen SM_61 zu droppen, **wir bleiben sicher auf 1.12.1**.
- [NVIDIA CUDA GPU Compute Capability](https://developer.nvidia.com/cuda/gpus):
  GTX 1060 = Compute Capability 6.1 (Pascal GP106).

ONNX/TensorRT optional in Phase 6 — **Pascal hat keine FP16-Tensor-Cores**,
deshalb Optimierungs-Headroom kleiner als auf Ampere/Ada.

### #19: Migrations ohne Alembic

Für 5 SQLite-Files mit überschaubarer Schema-Evolution ist Alembic
Overkill. PRAGMA `user_version` + nummerierte SQL-Skripte sind ~70 Zeilen
Code (siehe `services/brain_v3/storage/migration_runner.py`).

V3-Migrations leben in
`services/brain_v3/storage/sql_migrations/<scope>/NNN_<slug>.sql`.
Alembic bleibt für App-Bestand zuständig (`database/alembic/`) — V3
fasst es nicht an.

### #20: VACUUM INTO statt File-Copy

Bei aktiven WAL-Writes kann File-Copy inkonsistente Zustände einfangen.
`VACUUM INTO 'backup.db'` ist atomar, online, konsistent — die offiziell
empfohlene Methode für SQLite-Online-Backups
([SQLite docs](https://www.sqlite.org/lang_vacuum.html)).

### #21: VRAM-Budget — Realdaten aus Spike

Plan-Doc 02-Korrektur basierend auf Spike-Messung:

| Was | Was-tatsächlich-frei (gemessen) |
|---|---|
| Total VRAM | 6143.9 MB |
| Nach Boot vor torch-Init | 5217 MB frei (= ~927 MB System-Reserve) |
| Nach CUDA-Init (1 Tensor) | 4907 MB frei (=~310 MB CUDA-Kontext) |
| Nach `empty_cache()` | 4909 MB frei |
| **Brain-nutzbarer Spielraum** | **~4.0 GB als Pflicht-Limit (mit Reserve für Demucs/RAFT/NVENC)** |

CLAP 742 MB + SigLIP-2 355 MB = ~1.1 GB Coexistenz, plus weitere Workloads
serialisiert via GpuSerializer.

### #22: FP32 Default — Spike-Bestätigung

Pascal hat KEINE Tensor Cores → kein FP16-Speedup über Memory-Bandwidth-
Reduktion hinaus. CLAP+SigLIP zusammen brauchen <1.2 GB FP32 → FP16-Halbierung
unnötig.

**External-Verify:**
- [NVIDIA Pascal Architecture Whitepaper](https://www.nvidia.com/en-us/data-center/resources/pascal-architecture-whitepaper/):
  GP106 hat 1280 CUDA-Cores, **keine Tensor Cores** (erst ab Volta GV100).
- BF16 nativ erst ab Ampere SM_80 → für Pascal nicht möglich.

### #23: NVENC-Koexistenz

GTX 1060 hat 6th-Gen NVENC: H.264 (mit B-Frames), HEVC 8-bit, **kein AV1**
(AV1 erst ab Ada Lovelace SM_89, Hopper SM_90).

NVENC-Encode + GPU-Inferenz konkurrieren um VRAM (NVENC reserviert ~150 MB
für seine Encoder-Pipeline). `GpuSerializer.acquire("render")` muss NVENC
mit CLAP/SigLIP/Demucs/RAFT serialisieren.

**External-Verify:**
- [NVIDIA Video Codec SDK Support Matrix](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new):
  Pascal GP106 = NVENC-Gen 6, H.264 + HEVC 8-bit, kein AV1.

### #24: V1/V2-Trennung

User-Direktive 2026-05-03: V1 (`services/brain_service.py`) und V2
(`services/brain_v2/`) waren urspruenglich **hands-off bis explizite
Freigabe**.

User-Direktive 2026-05-05 (F2): **Refactor von V1/V2 ist freigegeben.**
V1 + V2 duerfen angefasst werden, aber pro Refactor ist eine
Live-Verifikation der V1/V2-Funktion erforderlich (Regression-Test,
funktional unveraendert).

V3 ist parallel:
- Code: `services/brain_v3/*`
- Tests: `tests/test_services/test_brain_v3_*.py`
- DBs: `%APPDATA%\PB_Studio\brain_v3\` (separater Subfolder von V1/V2)
- UI: neuer Tab/Window in Phase 5 (NICHT `studio_brain_window.py` umbauen)
- API: neuer in-process Fassaden-Wrapper `services/brain_v3/brain_v3_service.py` mit Klasse `BrainV3Service` (Phase 4) — **kein REST**, kein FastAPI-Server (User-Direktive 2026-05-05, F1)

CI-Check empfohlen: pytest assert dass `services/brain_v3/*` keine V1/V2-DBs
schreibt (per Pfad-Inspection der `brain_v3.paths`-Helpers).
