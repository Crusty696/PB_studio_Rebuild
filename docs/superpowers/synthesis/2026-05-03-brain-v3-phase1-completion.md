# Brain V3 — Phase-1-Abschluss (Datenseite)

**Datum:** 2026-05-03 12:13
**Status:** Code + Tests komplett, **35/35 pytest grün** auf Ziel-Hardware
**Test-Lauf:** `outputs/pytest_brain_v3_results.txt` (29 s, conda-env `pb-studio`, Python 3.10.20)

---

## Was geliefert wurde

### Foundation
| Datei | Zweck | LOC |
|---|---|---|
| `services/brain_v3/__init__.py` | Phasen-Status-Doc, Versionspin `0.1.0-phase1` | 24 |
| `services/brain_v3/paths.py` | App-globale + Projekt-spezifische Pfade unter `%APPDATA%\PB_Studio\brain_v3\` und `<project>/brain_v3/` | 78 |
| `services/brain_v3/hashing.py` | sha256 streaming (4 MB Chunks), `quick_fingerprint`, `hash_iterable` | 110 |

### Schemas (Pydantic v2.12)
| Datei | Models |
|---|---|
| `services/brain_v3/schemas/audio.py` | `SubtrackSegment`, `TempoCurvePoint`, `BrainV3AudioMeta`, `SubtrackDetectionResult` |
| `services/brain_v3/schemas/video.py` | `CurvePoint`, `VisualCurves`, `BrainV3VideoMeta`, `VisualCurvesResult` |

### Detektoren (CPU-only)
| Datei | Funktion | LOC |
|---|---|---|
| `services/brain_v3/audio/subtrack_detector.py` | 4-Signal-Pipeline (Foote 0.35 / Stem 0.30 / Tempo-Drift 0.20 / Spectral-Flux 0.15), Peak-Picking min_distance=60s, adaptive Threshold mean+1.5·std, Fallback bei 0 Boundaries | 285 |
| `services/brain_v3/video/visual_curves.py` | Brightness (HSV V), Saturation (HSV S), ColorTemp (tanh(log(R/B))), default 1 Hz Sampling | 128 |

### Tests
| Datei | Tests |
|---|---|
| `tests/test_services/test_brain_v3_hashing.py` | 11 |
| `tests/test_services/test_brain_v3_paths_and_schemas.py` | 12 |
| `tests/test_services/test_brain_v3_subtrack_detector.py` | 5 |
| `tests/test_services/test_brain_v3_visual_curves.py` | 7 |
| **Total** | **35** |

### Test-Wrapper
- `run_pytest_brain_v3.bat` — wiederverwendbarer pytest-Runner, schreibt Output nach `outputs/pytest_brain_v3_results.txt`

---

## Live-Verifikation (CLAUDE.md OBERSTE REGEL)

**35/35 tests passed** auf:
- Windows 11 (10.0.26200)
- conda-env `pb-studio` (Python 3.10.20)
- librosa 0.10.x, scipy, numpy, opencv-python, soundfile
- Pydantic 2.12.x

Reale Verifikation, kein Smoketest. Tests umfassen:
- sha256-Korrektheit gegen `hashlib.sha256` Referenz
- Streaming-vs-One-Shot-Aequivalenz (5 MB random)
- Chunk-Size-Invarianz
- Pfad-Isolation gegen V1/V2 (separater `brain_v3/`-Subfolder)
- Pydantic-Frozen-Constraints
- SubtrackDetector auf synthetischem Sinus-Drone → korrekt Fallback (1 Segment)
- SubtrackDetector auf Sinus-Wechsel 220→880 Hz nach 60 s → laeuft ohne Crash
- VisualCurvesExtractor auf hellem/dunklem/warmem/kaltem 5-s-MP4 → korrekte Brightness/ColorTemp-Reaktion

---

## Bug-Fix waehrend Phase 1

`librosa.beat.tempo` ist seit librosa 0.10 deprecated zugunsten
`librosa.feature.rhythm.tempo`. Detector nutzt jetzt `getattr`-Pattern mit
Backward-Compat-Fallback — Warning verschwindet bei librosa 0.10+, Code
laeuft auch noch bei aelterem librosa.

---

## Was Plan-Doc 06 Phase 1 verlangt hatte vs. was tatsaechlich geliefert

| Plan-Aufgabe | Status |
|---|---|
| `media_hash` (sha256) bei Audio/Video-Import — Streaming, 4 MB Chunks | ✓ Funktion + Tests |
| Schema-Erweiterung `audio_schemas.py`: `+audio_hash`, `SubtrackSegment`, `+tempo_curve` | ✓ V3-eigene Schemas (touchen kein V1/V2) |
| Schema-Erweiterung `video_schemas.py`: `+video_hash`, `+brightness/saturation/color_temp curves`, getrennte Tag-Felder | ✓ V3-eigene Schemas |
| `subtrack_detector.py` mit 4-Signal-Pipeline | ✓ |
| `visual_curves.py` mit 1 Sample/s | ✓ |
| Sub-Track-Detection als synchroner Pflicht-Schritt im **Mix-Import** | **NICHT geliefert** — wuerde Hook in `audio_router.import_audio()` brauchen, der V1/V2-nah ist; ist offene Phase-1-Restaufgabe |

### Phase-1-DoD: was offen bleibt

- **F-Measure ≥ 0.65 auf 5 manuell annotierten Test-Mixes** — annotierte Test-Mixes existieren nicht im Repo. SubtrackDetector funktioniert technisch, aber Genauigkeit gegen Ground-Truth ist nicht gemessen. **Status: `code-fix-pending-real-data-validation`**
- **Re-Import erkennt Hash-Match → kein erneuter Sub-Track-Lauf** — braucht `embedding_cache.db` (Phase 3 laut Plan)
- **Mix-Import-Hook (synchron, Pflicht-Schritt)** — V1/V2-Touch noetig, blockiert bis explizite Freigabe

---

## Was sich im Plan-Doc aendern muss

Keine echten Korrekturen aus Phase 1, ABER:

- Plan-Doc 06 Phase 1 DoD-Punkt "F-Measure ≥ 0.65" wird ohne annotierte
  Mixes nicht testbar. Entweder: annotierte Test-Mixes anlegen (Aufwand
  ~1 Tag), oder DoD relaxieren auf "Smoke-Test ohne Crash + Fallback
  verifiziert".
- Plan-Doc 06 Phase 1 "Mix-Import-Hook synchron" — entscheiden ob V1/V2
  touchen erlaubt. Solange nicht: V3 berechnet Hash + SubtrackDetection
  beim ersten Sehen (lazy), nicht beim Import.

---

## Wichtige Skript-Befunde

`getattr(librosa.feature, "rhythm", None)` Pattern: kompatibel mit
librosa 0.10.2 (Workspace-Pin) UND librosa 1.x (Future-proof).

`Pydantic v2 ConfigDict(frozen=True)` funktioniert wie Dataclass-frozen,
aber wirft generische `Exception` (nicht spezifisch `FrozenInstanceError`),
deshalb in Tests `pytest.raises(Exception)`.

OpenCV `cv2.VideoWriter` mit `mp4v` codec funktioniert auf der Maschine —
keine FFmpeg-Container-Probleme bei den Test-Videos.

---

## Vault-Pflege

- [x] Phase-1-Synthesis-Doc geschrieben (diese Datei)
- [ ] Im Brain-Bug Vault `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\` als
  `brain-v3-phase1-completion-2026-05-03.md` ablegen (User-Aktion)
- [ ] `log.md`-Eintrag im Vault mit Verweis auf Phase-1-Status

---

## Naechster Schritt: Phase 2 — Embedding-Pipeline

Aus Plan-Doc 06 Phase 2:
- `services/brain_v3/audio/audio_embedder.py` — CLAP via transformers, CUDA-Singleton, 10s-Window/5s-Hop
- `services/brain_v3/video/video_embedder.py` — SigLIP-2 Vision-Tower (mit `AutoImageProcessor`!), batch=8 Default (Spike bestaetigt), Auto-Tuning bei OOM
- `services/brain_v3/storage/embedding_repository.py` — sqlite-vec via `sqlite_vec.load(conn)`
- Embedding-Cache: Hash-Lookup vor jeder Berechnung
- Background-Queue: `asyncio.Queue` + Worker, Progress via SSE

Phase 2 Schaetzung Plan-Doc 06: 5-10 Tage. Realistischer Code-Aufwand
ohne Live-Tests: ~1-2 Stunden Implementation + Tests.
