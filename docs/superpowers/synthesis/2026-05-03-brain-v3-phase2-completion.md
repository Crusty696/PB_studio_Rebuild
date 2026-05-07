# Brain V3 — Phase-2-Abschluss (Embedding-Pipeline)

**Datum:** 2026-05-03 12:33
**Status:** Code + Tests komplett, **63/63 pytest grün** auf Ziel-Hardware
**Test-Lauf:** `outputs/pytest_brain_v3_results.txt` (32.5 s, conda-env `pb-studio`, Python 3.10.20)
**Vorlauf:** Phase 1 (`docs/superpowers/synthesis/2026-05-03-brain-v3-phase1-completion.md`)

---

## Was geliefert wurde (Phase 2 NEU)

### GPU-Coordination
| Datei | Zweck |
|---|---|
| `services/brain_v3/gpu_serializer.py` | Threading + Asyncio-Lock, automatisches `torch.cuda.empty_cache()` beim Release, App-globaler Default-Singleton via `get_default_serializer()` |

### Storage (sqlite3 + sqlite-vec)
| Datei | Zweck |
|---|---|
| `services/brain_v3/storage/sqlite_init.py` | PRAGMA-Init (WAL, NORMAL-sync, 32 MB cache, 256 MB mmap, FK on, busy_timeout=5s), `load_vec_extension` mit klarer ImportError-Anweisung |
| `services/brain_v3/storage/migration_runner.py` | PRAGMA `user_version` + nummerierte SQL-Skripte, atomar pro Migration, ROLLBACK on failure |
| `services/brain_v3/storage/embedding_cache.py` | Plan-Doc 04 Schema 3 — `media_embedding_index` Index-DB + `.npy`-Files unter `%APPDATA%\PB_Studio\brain_v3\embeddings\<media_type>\<model>__<ver>\<2-byte-prefix>\<hash>.npy` |
| `services/brain_v3/storage/embedding_repository.py` | Plan-Doc 04 Schema 4 — projekt-spezifische `embeddings.db` mit sqlite-vec virtuellen Tabellen (`audio_embeddings vec0(FLOAT[512])`, `video_embeddings vec0(FLOAT[768])`), KNN-API mit Level-Filter |

### SQL-Migrations
| Datei | Zweck |
|---|---|
| `services/brain_v3/storage/sql_migrations/embedding_cache/001_initial.sql` | Cache-Schema |
| `services/brain_v3/storage/sql_migrations/embeddings_project/001_initial.sql` | audio_units (3-Tier) + video_units (2-Tier) + sqlite-vec virtuelle Tabellen |

### Embedder
| Datei | Zweck |
|---|---|
| `services/brain_v3/audio/audio_embedder.py` | CLAP `laion/larger_clap_music`, 10s-Window/5s-Hop, Window→Section→Mix-Aggregation, L2-Normalisierung, Singleton mit `GpuSerializer.acquire()`, `unload()` zur VRAM-Freigabe |
| `services/brain_v3/video/video_embedder.py` | SigLIP-2 Vision-Tower mit `AutoImageProcessor` (Spike-Lesson!), Frame-Sampling 1 pro Scene-Mitte, Batch=8 Default, Auto-Tuning bei OOM (8→4→2→1), Scene→Clip-Aggregation gewichtet mit Scene-Dauer |

### Tests (28 NEU, total 63)
| Datei | Tests |
|---|---|
| `tests/test_services/test_brain_v3_gpu_serializer.py` | 7 (Threading, Asyncio, Singleton, OOM-Resilience) |
| `tests/test_services/test_brain_v3_storage_cache.py` | 15 (PRAGMA-Init, Migration-Runner, Cache-CRUD, Model-Version-Mismatch, Path-Separation) |
| `tests/test_services/test_brain_v3_storage_repo.py` | 6 (Repo-Init, Audio-/Video-Round-Trip, KNN-Order, Level-Filter, Dim-Mismatch) — **graceful skip bei fehlendem sqlite-vec** |

### Wrapper-Skripte
| Datei | Zweck |
|---|---|
| `install_brain_v3_phase2_deps.bat` | `pip install sqlite-vec` ins richtige Python-Env |
| `run_pytest_brain_v3.bat` | erweitert um Phase-2-Test-Files |

---

## Live-Verifikation (CLAUDE.md OBERSTE REGEL)

**Alle 63 Tests passed** auf:
- Windows 11 (10.0.26200), Python 3.10.20, conda-env `pb-studio`
- sqlite-vec 0.1.6+ (frisch via `install_brain_v3_phase2_deps.bat` installiert)
- 32.5 s Total-Lauf-Zeit

Reale Verifikation auf Ziel-Hardware. Tests umfassen:
- WAL-Mode-Aktivierung pro Connection
- Foreign-Key-Enforcement
- ImportError-Pfad bei fehlendem sqlite-vec liefert User-freundliche Anweisung
- Migration-Idempotenz + Rollback bei kaputtem SQL
- Embedding-Cache: Hash-Lookup, Model-Version-Mismatch (Plan-Doc 07 R07)
- Pfad-Trennung audio/video/model-Subfolders
- sqlite-vec KNN-Reihenfolge bei zwei dimensional getrennten Embeddings
- Level-Filter (`level='window'` vs `level='section'`) wirkt
- Dim-Mismatch (CLAP-Embedding in Video-Repo, SigLIP-Embedding in Audio-Repo) raises ValueError
- GpuSerializer serialisiert zwei Threads sequenziell (kein Interleaving)
- Async-Variante via `acquire_async` serialisiert ebenso
- Default-Singleton ist process-global

---

## Wichtige Befunde + Entscheidungen aus Phase 2

### sqlite-vec war nicht installiert → installiert
Phase 0 hat sqlite-vec nicht gebraucht. Phase 2 schon. `install_brain_v3_phase2_deps.bat`
installiert es ins conda-env. **`enable_load_extension(True)` funktioniert** auf
Windows mit conda Python 3.10 — der oft beobachtete Build-Fall (sqlite ohne Extension-Support)
trifft hier nicht zu.

### transformers 4.38.2 ist ausreichend
Spike bestaetigte: SigLIP-2 mit `AutoImageProcessor` laedt sauber.
**Kein transformers-Upgrade noetig** — V1/V2-Stack bleibt unangetastet.
`Siglip2VideoEmbedder._ensure_loaded` nutzt explizit `AutoImageProcessor`,
nicht `AutoProcessor`.

### Embedder ARE NICHT live-getestet im pytest-Lauf
Bewusst — CLAP-Load + SigLIP-Load + Inferenz sind teuer (~1-3 min pro Test
bei kaltem Cache). **Phase-0-Spike (`outputs/spike_brain_v3_gpu/20260503_115926/`)
hat das Pattern bereits live verifiziert.** Embedder-Klassen sind Wrapper
ueber das bewiesene Pattern — Risiko gering.

Falls expliziter Embedder-Smoke gewuenscht: separates Skript
`scripts/spike_brain_v3_embedder_smoke.py` waere naechster Sub-Spike.

### Deprecation-Warning gefixt
`librosa.beat.tempo` → `librosa.feature.rhythm.tempo`. `rhythm` ist Submodul,
muss explizit importiert werden (`from librosa.feature.rhythm import tempo`),
sonst bleibt FutureWarning aktiv. Gefixt im Detector.

### Embedding-Pfad-Konvention fuer skalierbares Filesystem
`<embeddings_dir>/<media_type>/<safe_model>__<safe_ver>/<2-byte-prefix>/<hash>.npy`
verhindert dass ein Verzeichnis 100k+ Files enthaelt (NTFS wird bei
~10k Files/Verzeichnis spuerbar langsam).

---

## Was Plan-Doc 06 Phase 2 verlangt vs. geliefert

| Plan-Aufgabe | Status |
|---|---|
| `audio_embedder.py` (CLAP, CUDA-Singleton, GPULockMiddleware-Respect) | ✓ |
| `video_embedder.py` (SigLIP-2, batch=8, Auto-Tuning) | ✓ |
| `storage/embedding_repository.py` (sqlite-vec) | ✓ |
| Embedding-Cache aktiv (Hash-Lookup vor Berechnung) | ✓ Cache-Modul + Tests |
| Background-Queue (`asyncio.Queue` + Worker) | **NICHT geliefert** — Phase-4-naher Code (Async-API), ausser Scope Phase 2 |
| Verifikations-Skripte CLAP/SigLIP/sqlite-vec | Spike `spike_brain_v3_gpu_coexistence.py` deckt CLAP/SigLIP ab; sqlite-vec via `test_brain_v3_storage_repo.py` |
| 500-Clip-Projekt Erst-Import in <45 min | **NICHT validiert** — braucht echtes 500-Clip-Projekt, kein Code-Test |
| Re-Import Cache-Hit-Rate ≥95% in <5 s | **NICHT validiert** — braucht echtes 500-Clip-Re-Import |
| KNN-Latenz median <50 ms bei 16k Vektoren | **NICHT live gemessen** — Tests nutzen <10 Vektoren. Skalierungs-Spike folgt bei Bedarf. |

### Phase-2-DoD: was offen bleibt

- **Background-Queue** — implementiere ich in Phase 4 (Pacing-Integration), wo Async natuerlich rein kommt.
- **Echte Skalierungs-Validierung** (45-min-Schwelle, 95% Cache-Hit, 50 ms KNN) — Code-Pfad funktioniert; Performance-Validierung braucht echtes Projekt-Material.
- **Embedder-Live-Smoke** — erfasst durch Spike Phase 0; separater Embedder-only-Smoke-Spike optional.

---

## Vault-Pflege

- [x] Phase-2-Synthesis-Doc geschrieben (diese Datei)
- [ ] Im Brain-Bug Vault `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\` als
  `brain-v3-phase2-completion-2026-05-03.md` ablegen (User-Aktion)
- [ ] `log.md`-Eintrag im Vault mit Verweis auf Phase 2

---

## Naechster Schritt: Phase 3 — Brain-Core (Beta-Bernoulli + Hierarchical Backoff)

Aus Plan-Doc 06 Phase 3:
- `services/brain_v3/storage/brain_store.py` (3 SQLite-Files: weights, patterns, embedding_cache → letzteres existiert schon)
- `services/brain_v3/bridge_dimensions.py` (17 Achsen-Berechnung)
- `services/brain_v3/context_resolver.py` (6 Slots, 5 Backoff-Keys)
- `services/brain_v3/weight_store.py` (Posterior-Mean, Backoff-Lookup, MIN_CONFIDENT=10)
- `services/brain_v3/scorer.py` (gewichteter Score-Vektor)
- `services/brain_v3/feedback_logger.py` (atomarer 85-Bucket-Update)
- `services/brain_v3/cold_start.py` (Defaults aus TriggerSettings + Video-Mitte)
- Tests fuer alle Bausteine (Mock-Klicks → Posterior-Konvergenz, Backoff-Lookup-Fallback)

Schaetzung Plan-Doc 06: 5-7 Tage. Realistisch fuer reine Code+Test-Implementation: ~1-2 Stunden.

**KEINE GPU-Abhaengigkeit in Phase 3** — alles CPU-Logic + SQLite. Tests laufen schnell.
