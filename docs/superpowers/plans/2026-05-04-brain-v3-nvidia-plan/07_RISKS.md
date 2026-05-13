# 07 — Risiken, Mitigationen, Test-Strategie (Brain V3, NVIDIA)

## Risiko-Matrix (kalibriert mit Spike-Realdaten)

| # | Risiko | Wahrsch. | Impact | Status | Mitigation |
|---|---|---|---|---|---|
| R01 | torch+CUDA-Wheel-Mismatch (cu113 vs Treiber) | niedrig | hoch | aktiv | Pin `torch==1.12.1+cu113`, Treiber-Mindestversion ≥ 465.89 (Win) — Workspace 31.0.15.4633 OK |
| R02 | sqlite-vec ABI-Inkompatibilität nach Update | niedrig | mittel | aktiv | Version-Pin ≥0.1.6, ABI seit 0.1 stabil, Tests in `test_brain_v3_storage_repo.py` |
| R03 | WAL-File wächst unbegrenzt bei nicht-beendeten Read-Tx | niedrig | mittel | aktiv | Connection-Lifecycle strikt im Repository-Pattern, automatisches `close()`, wöchentliches `wal_checkpoint(TRUNCATE)` (Phase 6) |
| R04 | Sub-Track-Detection versagt bei seamless mixes | mittel | niedrig | aktiv | Hierarchical Backoff kompensiert; Fallback = 1 Sub-Track in `SubtrackDetector` ✓ |
| R05 | User klickt zu wenig → Hirn lernt nicht | mittel | hoch | aktiv | Smart-Sampling-Dialog macht Klicks maximal effektiv (102 Buckets/Klick, 1530 pro 15-Klick-Session) |
| R06 | Embedding-Pipeline blockiert UI | niedrig | hoch | aktiv | Background-Queue ✓ (`background_queue.py`) + GpuSerializer respektieren |
| R07 | Modell-Update macht alte Embeddings inkompatibel | niedrig | mittel | aktiv | `model_version` pro Eintrag → Auto-Re-Compute bei Mismatch (verifiziert in `test_cache_lookup_different_model_version_misses`) |
| R08 | Schema-Drift Schema↔Dataclass kehrt zurück | mittel | hoch | aktiv | Pre-commit-Hook, CI-Check |
| R09 | sqlite-vec-Code muss später ausgetauscht werden | niedrig | mittel | aktiv | Repository-Pattern strikt → Migration auf 1 Datei begrenzt |
| **R10** | **SigLIP-2 batch=8 sprengt 6 GB GTX 1060** | ~~hoch~~ | ~~hoch~~ | **WIDERLEGT** | ~~Auto-Tuning Pflicht~~ — Spike: 758 MB reserved, läuft locker. Auto-Tuning bleibt als Defensive |
| R11 | CLAP-Inferenz auf 2h-Mix dauert >5 min trotz Batching | niedrig | mittel | aktiv | Window-Sampling adaptiv; pro Sub-Track ein Embedding |
| R12 | Hirn-Store-Korruption nach App-Crash | niedrig | hoch | aktiv | WAL-Mode, atomare Updates, automatischer Recovery aus Backup (Phase 6) |
| ~~R13~~ | ~~CC-BY-4.0 für CLAP nicht korrekt attribuiert~~ | ~~niedrig~~ | ~~mittel~~ | **ENTFÄLLT** | HF-Verify zeigt CLAP ist Apache-2.0, **keine Attribution-Pflicht**. Frueherer Plan war falsch. |
| R14 | sqlite-vec auf Windows weniger getestet als Linux | mittel | mittel | aktiv | Verifikations-Spike Phase 2 erfolgreich, aber 16k-Insert dauerte ~13 min (R18) |
| **R15** | **Pascal-CUDA-Support droppt in zukünftiger PyTorch-Major** | mittel | mittel | aktiv | Pin `torch==1.12.1+cu113`. Re-Verify 2026-05-04: cu126 unterstützt SM_61 noch, **cu128+ droppt es** (PyTorch GitHub Issue #160575). Wir bleiben auf 1.12.1+cu113. Jährlicher Re-Check empfohlen. |
| **R16** | **Gleichzeitige VRAM-Belegung (Brain+Demucs+RAFT+NVENC+Display) sprengt 6 GB** | ~~hoch~~ | hoch | **TENDENZIELL ENTSPANNT** | Spike: Brain alleine (CLAP+SigLIP koexistent) = 1178 MB. Bleiben ~3.5 GB free für Demucs/RAFT/NVENC. **Demucs-Coexistenz-Spike steht aus** |
| **R17** | **V3-Code kollidiert versehentlich mit V1/V2** | niedrig | hoch | aktiv | Strikte Namensraum-Trennung (`brain_v3/` vs `brain_v2/` vs `brain_service.py`), eigene DB-Pfade (`brain_v3/`-Subfolder), CI-Check der Imports empfohlen |
| **R18** | **KNN-Latenz <50 ms median bei 16k Vektoren** | hoch | mittel | **MISSED → kalibriert** | Spike 20260504_145231: Audio 63 ms median, Video 108 ms median. DoD wird relaxiert auf <150 ms p95. Optional: HNSW-Index in sqlite-vec ≥0.1.7 evaluieren (Phase 6) |
| **R19** | **Internet-Ausfall blockiert HF-Modell-Download** | mittel | hoch | aktiv | Modelle nach Erst-Download lokal gecached (HF cache `~/.cache/huggingface/`). Fallback: User-Doku "vor erstem Lauf einmal mit Internet starten". Beobachtet im 13:59:47-Spike-Lauf. |

---

## Detail-Mitigationen

### R03 — WAL-File-Wachstum

```python
# services/brain_v3/storage/sqlite_init.py (vorhanden ✓)

def checkpoint(conn: sqlite3.Connection, mode: str = "PASSIVE") -> None:
    """Erzwingt WAL-Checkpoint. PASSIVE/RESTART/TRUNCATE/FULL."""
    if mode not in ("PASSIVE", "RESTART", "TRUNCATE", "FULL"):
        raise ValueError(f"Ungueltiger Checkpoint-Mode: {mode}")
    conn.execute(f"PRAGMA wal_checkpoint({mode})")

# Empfehlung: TRUNCATE woechentlich (Phase 6 backup-Skript triggert),
# PASSIVE bei jedem App-Shutdown.
```

### R05 — User klickt zu wenig

Smart-Sampling-Dialog priorisiert die unsichersten Cuts (höchste Bayes-Varianz).
Bei 15 Klicks pro Lern-Session werden 102 Buckets pro Klick aktualisiert
(17 Achsen × 5 Levels) = **1275 Bucket-Updates pro Session**.

Bei 3 Lern-Sessions pro Projekt sammeln sich >3000 Bucket-Updates →
Cold-Start für die häufigsten Kontexte verlassen.

### R07 — Modell-Update-Kompatibilität

```python
# services/brain_v3/audio/audio_embedder.py (Phase 2 ✓)

CLAP_MODEL_ID = "laion/larger_clap_music"
CLAP_MODEL_VERSION = "1.0"  # erhoehe bei jedem Modell-Update

# Embedding-Cache prueft model_name + model_version exakt:
cached = cache.lookup(media_hash, CLAP_MODEL_ID, CLAP_MODEL_VERSION)
if cached is not None:
    return cached.load_embedding()
# else: re-compute via embedder.embed_mix(...)
```

Bei Modell-Update wird `MODEL_VERSION` erhöht. Alte Cache-Einträge
werden automatisch ignoriert und neu berechnet. Verifiziert in
`test_cache_lookup_different_model_version_misses`.

### R10 — VRAM-Auto-Tuning (DEFENSIVE, nicht zwingend)

```python
# services/brain_v3/video/video_embedder.py (Phase 2 ✓)

def _embed_in_batches(self, frames: list[np.ndarray]) -> list[np.ndarray]:
    bs = self.batch_size  # default 8
    while bs >= MIN_BATCH_SIZE:
        try:
            return self._infer(frames, bs)
        except Exception as exc:
            if not _is_oom(exc) or bs <= MIN_BATCH_SIZE:
                raise
            logger.warning("SigLIP-2 OOM bei batch=%d → halbiere", bs)
            bs = max(MIN_BATCH_SIZE, bs // 2)
            torch.cuda.empty_cache()
```

**Warum trotz R10-Widerlegung behalten:** Defensive bei Concurrent-Workloads
(Demucs/RAFT gleichzeitig könnte VRAM senken). Spike testete batch=8 isoliert.

### R12 — Hirn-Store-Recovery

```python
# Phase 6 TODO: services/brain_v3/storage/recovery.py

def open_with_recovery(brain_dir: Path):
    try:
        return _open_with_init(brain_dir / "weights.db")
    except sqlite3.DatabaseError as e:
        logger.error(f"weights.db korrupt: {e} — Backup-Restore versuchen")
        if _restore_from_latest_backup(brain_dir):
            return _open_with_init(brain_dir / "weights.db")
        logger.warning("Kein Backup verfuegbar, starte mit leerem Hirn-Store")
        (brain_dir / "weights.db").unlink(missing_ok=True)
        return _init_fresh(brain_dir)
```

### R18 — KNN-Latenz ist Realität, nicht Bug

**Daten aus `outputs/spike_brain_v3_knn/20260504_145231/`:**

```text
Audio 16k Vektoren (CLAP 512-dim):
  Insert pro Vektor:  48.23 ms
  KNN median:         63.48 ms       ← Plan-DoD <50 ms VERFEHLT
  KNN p95:            75.17 ms
  KNN min/max:        51.61 / 77.54 ms

Video 16k Vektoren (SigLIP-2 768-dim):
  Insert pro Vektor:  50.53 ms
  KNN median:         108.03 ms      ← Plan-DoD <50 ms VERFEHLT
  KNN p95:            145.49 ms
  KNN min/max:        81.65 / 234.42 ms
```

**Mitigationen:**

1. **DoD relaxieren** auf <150 ms p95 — realistisch für Brute-Force sqlite-vec
   bei 16k Vektoren. Pacing-Run ruft typisch 1–5 KNNs pro Cut auf, akzeptabel.
2. **HNSW-Index evaluieren** (Phase 6) — sqlite-vec ≥0.1.7 hat partiellen
   ANN-Support. Eval-Sub-Spike planen.
3. **Pre-Filter via SQL** vor KNN — z.B. nur Scenes mit `motion_score > 0.5`
   ins KNN-Set, halbiert effektive Vektor-Anzahl.

### R19 — Internet-Ausfall

**Beobachtet im Spike 20260503_135947:**
SigLIP-2-Modell-Load schlug fehl mit
`Failed to resolve 'huggingface.co' ([Errno 11001] getaddrinfo failed)`.

**Mitigationen:**
- Modelle nach Erst-Download lokal in `~/.cache/huggingface/` gecached
- `scripts/warmup_models.py` (existierend für SigLIP-1/RAFT) erweitern um
  CLAP + SigLIP-2 (Phase 6 TODO)
- User-Doku "vor erstem Lauf einmal mit Internet starten zum Modell-Download"

---

## Test-Strategie

### Phase 0 — Smoke-Tests ✓ ABGESCHLOSSEN

```text
✓ App-Start ohne Exception
✓ scripts/spike_brain_v3_gpu_coexistence.py durchlaeuft
✓ Realdaten geliefert für CLAP, SigLIP-2, Coexistenz
```

### Phase 1 — Unit-Tests ✓ 35 GRUEN

```text
✓ test_brain_v3_hashing.py (11)
✓ test_brain_v3_paths_and_schemas.py (12)
✓ test_brain_v3_subtrack_detector.py (5) — Smoke + Fallback
✓ test_brain_v3_visual_curves.py (7)
~ F-Measure ≥ 0.65 auf 5 annotierten Test-Mixes — annotierte Mixes fehlen
```

### Phase 2 — Integration-Tests ✓ 70 GRUEN + Spikes

```text
✓ test_brain_v3_gpu_serializer.py (7)
✓ test_brain_v3_storage_cache.py (15) — PRAGMA, Migration, Cache-CRUD
✓ test_brain_v3_storage_repo.py (6) — sqlite-vec KNN
✓ test_brain_v3_background_queue.py (7) — async + threading + Bug-Fix
✓ Spike spike_brain_v3_embedder_smoke.py
✓ Spike spike_brain_v3_knn_scaling.py
✓ Cache-Hit-Rate 100 % bei Re-Import (DoD ≥95% MET)
~ KNN-Latenz <50ms median verfehlt (R18 dokumentiert)
```

### Phase 3 — Brain-Logik-Tests (TODO)

```python
# tests/test_services/test_brain_v3_weight_store.py (Phase 3)

def test_posterior_mean_cold_start():
    store = WeightStore(":memory:")
    pm = store.get_posterior_mean("kick_weight", ["", "section=drop"])
    assert pm == COLD_START_DEFAULTS["kick_weight"]


def test_posterior_mean_after_clicks():
    store = WeightStore(":memory:")
    for _ in range(10):
        store.update("kick_weight", 0, "", alpha_delta=2.0, beta_delta=0)
    pm = store.get_posterior_mean("kick_weight", [""])
    expected = (20 + 1) / (20 + 0 + 2)
    assert abs(pm - expected) < 1e-6


def test_backoff_finds_specific_when_confident():
    store = WeightStore(":memory:")
    for _ in range(100):
        store.update("kick_weight", 0, "", 1.0, 0)
    for _ in range(15):
        store.update("kick_weight", 1, "section=drop", 2.0, 0)
    pm = store.get_posterior_mean("kick_weight", ["", "section=drop"])
    expected = (30 + 1) / (30 + 0 + 2)  # 15 Klicks × α=2.0
    assert abs(pm - expected) < 1e-6
```

```text
☐ test_cold_start                  Defaults aus TriggerSettings korrekt
☐ test_atomic_update_85_buckets    Crash mid-update → keine inkonsistente DB
☐ test_backoff_to_general          Level 5 leer → Level 4 → Level 3 ...
☐ test_smart_sampler_returns_15    Genau 15 Cuts mit höchster Varianz
☐ test_reset_clears_weights        Reset löscht weights.db, embedding_cache bleibt
```

### Phase 4 — Service-Tests (TODO, in-process — kein HTTP)

```python
# tests/test_services/test_brain_v3_service_smoke.py
# (Architektur-Direktive User 2026-05-05, F1: keine REST-Schicht)

from services.brain_v3.brain_v3_service import BrainV3Service
from services.brain_v3 import schemas

svc = BrainV3Service()

# 1. Pacing mit Brain V3 (in-process)
suggest_resp = svc.suggest(schemas.BrainV3SuggestRequest(
    audio_clip_id=1, video_clip_ids=[1, 2, 3], n_top=5,
))
cut_id = suggest_resp.cuts[0]["id"]

# 2. Klick simulieren
fb_resp = svc.feedback(schemas.BrainV3FeedbackRequest(
    cut_id=cut_id, rating="perfect",
))
assert fb_resp.status == "ok"

# 3. Stats abrufen
stats_resp = svc.stats()
assert stats_resp.total_clicks >= 1

# 4. Lern-Session
ls_resp = svc.learning_session()
assert len(ls_resp.cuts) == 15

# 5. Reset (mit Confirmation-Token)
token_resp = svc.reset()  # ohne Body → BrainV3ResetTokenResponse
assert token_resp.confirmation_token

reset_resp = svc.reset(schemas.BrainV3ResetConfirmRequest(
    confirmation_token=token_resp.confirmation_token,
))
assert reset_resp.status == "reset_complete"

print("✓ Alle Service-Tests (in-process) erfolgreich")
```

### Phase 5 — Manueller Test (TODO)

```text
☐ Realer Mix + 500 Clips importieren
☐ Pacing-Run mit use_brain_v3=true
☐ 50+ Klicks abgeben (gemischt: alle 4 Rating-Stufen)
☐ Stats-Panel oeffnen → Lerneffekt sichtbar (Top-5-Buckets gefuellt)
☐ Erneuter Pacing-Run → Cuts unterscheiden sich vom ersten Run
☐ Reset → Cold-Start-Status wiederhergestellt
☐ Lern-Session-Dialog → 15 Cuts mit Audio+Video-Preview
☐ V1/V2-UI weiterhin funktional (regression check)
```

### Phase 6 — Recovery-Tests (TODO)

```text
☐ Hirn-Store loeschen → App startet, Cold-Start aktiv
☐ weights.db mit 0-byte-Datei ersetzen → Recovery aus Backup
☐ Kein Backup verfuegbar → Frischer Hirn-Store, App lauffaehig
☐ Pacing-Latenz mit Brain <800 ms bei 100 Cuts gemessen
☐ Woechentliches Backup laeuft automatisch (Background-Task verifiziert)
☐ NVENC-Render + Brain-Inferenz gleichzeitig → keine OOM, keine Race
```

---

## Definition of Done — Gesamt

### Funktional

```text
☐ Brain V3 schlaegt Cuts vor mit Sub-Score-Vektor pro Achse
☐ User-Klick wird in <100ms verarbeitet, sichtbar in Bucket-Counts
☐ Cold-Start funktioniert ohne Lern-Daten
☐ Lerneffekt projektuebergreifend: Klicks aus Projekt 1 wirken in Projekt 2
☐ Mix-Import inkl. Sub-Track-Detection laeuft synchron <60 s fuer 2-4h-Mix
☐ Smart-Sampling-Dialog liefert 15 Cuts in <2 s
☐ V1 + V2 unveraendert lauffaehig (Regression check)
```

### Nicht-funktional (kalibriert)

```text
☐ Hirn-Store <100 MB nach 10.000 Klicks
☐ Projekt-Store <100 MB pro Projekt mit 500 Clips
☐ Pacing-Run mit Brain V3: <800 ms Overhead (kalibriert mit KNN-Realitaet)
☐ Embedding-Cache-Hit-Rate ≥ 95% bei Re-Imports — DoD erfuellt 100% in Spike
☐ App-Start auch bei zerstoertem Hirn-Store
~ KNN-Latenz median <150 ms p95 (R18-relaxed, frueher mit <50 ms beziffert)
```

### Code-Qualitaet

```text
☐ Schema↔Dataclass-Sync via CI
☐ 100+ Unit-Tests fuer V3-Bausteine
☐ Repository-Pattern strikt (kein direkter sqlite_vec-Import außerhalb storage/)
☐ GpuSerializer respektiert von allen GPU-Konsumenten
☐ LICENSES.md vollstaendig (Apache-2.0 fuer CLAP + SigLIP-2)
☐ Strikte Namensraum-Trennung V3 ↔ V1/V2 (CI-Check der Imports)
```

### Verifikation Tech-Stack (siehe `08_VERIFICATION.md`)

```text
✓ Phase-0-Spike GPU-Coexistenz erfolgreich
✓ Phase-2-Spike Embedder + KNN-Scaling abgeschlossen
✓ HF Hub Verify CLAP + SigLIP-2 + SigLIP-1
✓ External-Verify NVIDIA Pascal SM_61 Support in PyTorch 1.12
✓ External-Verify sqlite-vec API + Reputation
☐ HNSW-Eval (sqlite-vec ≥0.1.7) in Phase 6
☐ NVENC-Coexistenz-Test in Phase 6
☐ Demucs-Coexistenz-Spike (offen seit Phase 0)
```
