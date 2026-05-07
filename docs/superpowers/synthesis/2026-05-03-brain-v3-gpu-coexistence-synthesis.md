# Brain V3 — Phase-0-Spike Synthese (Real-Daten 2026-05-03)

**Spike-Lauf:** `outputs/spike_brain_v3_gpu/20260503_115926/`
**Hardware:** GTX 1060 6 GB, Pascal SM 6.1, total VRAM 6143.9 MB
**Stack:** Python 3.10.20, torch 1.12.1+cu113, transformers 4.38.2, conda-env `pb-studio`
**Status:** alle 4 Tests `status: ok`. Erkenntnisse blockieren keine Phase 1, aber **mehrere Plan-Annahmen widerlegt → Plan-Doc-Korrekturen folgen unten**.

---

## Reale Mess-Daten

| Workload | VRAM allocated | VRAM reserved | Free nach Lade-Schritt | Bemerkung |
|---|---|---|---|---|
| baseline before torch | 0 MB | 0 MB | **5217 MB** | System belegt schon ~927 MB (Display + andere) |
| baseline after CUDA-Init | 0 MB | 2 MB | 4907 MB | CUDA-Kontext kostet ~310 MB |
| baseline after empty_cache | 0 MB | 0 MB | 4909 MB | nutzbares Maximum für Brain |
| **CLAP** load | **742.0 MB** | 776.0 MB | 4133 MB | `laion/larger_clap_music` |
| CLAP nach 10 s-Inferenz | 742.3 MB | 808.0 MB | 3865 MB | feature_dim=512, shape `[1, 512]` |
| CLAP nach unload + empty_cache | 0 MB | 0 MB | 4673 MB | sauberer Lifecycle |
| **SigLIP-2 Vision** load | **355.8 MB** | 402.0 MB | 4271 MB | `google/siglip2-base-patch16-384` |
| SigLIP-2 batch=1 inference | 359.8 MB | 434.0 MB | 4239 MB | |
| SigLIP-2 batch=2 inference | 363.4 MB | 506.0 MB | 4167 MB | |
| SigLIP-2 batch=4 inference | 369.3 MB | 606.0 MB | 4067 MB | |
| **SigLIP-2 batch=8 inference** | **383.8 MB** | **758.0 MB** | **3915 MB** | **kein OOM, läuft sauber** |
| **Coexistenz CLAP + SigLIP-2** | **1097.5 MB** | **1178.0 MB** | **3495 MB** | beide Modelle gleichzeitig im VRAM |
| Coexistenz nach cleanup | 0 MB | 0 MB | 4673 MB | |

---

## Plan-Doc-Korrekturen (basierend auf Realdaten)

### Plan-Doc 02 — Designentscheidungen

| # | Punkt | Vorher (Hypothese) | Nachher (real) |
|---|---|---|---|
| 16 | SigLIP-2-base-patch16-384 | Annahme: ~370 MB Disk | **bestätigt 355.8 MB allocated, batch=8 mit 758 MB reserved** |
| 21 | VRAM-Budget 3.5 GB max | konservative Reserve | **kann auf 4.0 GB hochgesetzt werden** (real 4673 MB nutzbar nach CLAP/SigLIP-Test) |
| **22** | FP32 Default, FP16 als VRAM-Notfall | "FP16 evaluieren bei Engpass" | **FP32 ist vollkommen ausreichend, FP16 nicht mehr nötig — entfernt aus Phase 6** |
| **23** | sequenzieller Modell-Lifecycle | als Pflicht spezifiziert | **von "Pflicht" auf "Empfohlen für Sicherheit" runterstufen** — beide Modelle passen real gleichzeitig in VRAM (1178 MB reserved bei zusammen 6 GB total) |

### Plan-Doc 03 — Tech-Stack

**Performance-Tabelle KOMPLETT KORRIGIEREN:**

| Workload | Plan (Schätzung) | Real (gemessen) |
|---|---|---|
| CLAP VRAM | 1.6–2.0 GB FP32 | **742 MB FP32** (halb so viel) |
| SigLIP-2 batch=8 | "vermutlich OOM" | **läuft, 758 MB reserved** |
| Coexistenz beide Modelle | "wahrscheinlich nicht möglich" | **funktioniert, 1178 MB reserved** |
| CLAP Inferenz 10 s Window | nicht beziffert | ~1.7 s reine Inferenz nach Load |
| SigLIP-2 batch=1→8 Skalierung | nicht beziffert | ~73 ms Differenz batch1→batch8 |

**Inferenz-Pfad-Block bleibt:** PyTorch + CUDA, FP32. Keine FP16/BF16 nötig.

### Plan-Doc 06 — Bau-Phasen

**Phase 2 DoD kalibrieren:**
- "Default-Batch SigLIP-2" → **batch=8 freigegeben** (nicht batch=2 wie konservativ geplant)
- VRAM-Auto-Tuning ist **nicht zwingend Pflicht** sondern Defensive — Spike zeigt batch=8 läuft sauber
- Erst-Embedding-Schwelle bleibt offen — wurde im Spike nicht mit echtem 2 h-Mix getestet

**Phase 6:**
- ONNX/TensorRT-Eval: bleibt optional, aber Begründung ändert sich — nicht mehr "weil VRAM knapp", sondern "weil Inferenz-Zeit reduzierbar"

### Plan-Doc 07 — Risiken

| ID | Vorher | Nachher |
|---|---|---|
| **R10** | "SigLIP-2 batch=8 sprengt 6 GB" — Wahrsch. hoch, Impact hoch | **WIDERLEGT.** Wahrsch. niedrig, Impact niedrig. Real: batch=8 nutzt 758 MB reserved, ~3.9 GB free verbleiben. |
| **R16** | "Brain + Demucs + RAFT + NVENC sprengen 6 GB" | **TENDENZIELL ENTSPANNT.** Brain alleine (CLAP+SigLIP-2 koexistent) = 1178 MB. Bleiben 3495 MB für Demucs/RAFT/NVENC/Display — komfortabel. **Test mit echtem Demucs-Run separat empfohlen** (Spike-Test `--tests demucs` ergänzbar). |

---

## Skript-Bug-Fix (während Spike-Lauf)

**Erst-Lauf 11:55:50** scheiterte bei `siglip2`-Test mit:
```
TypeError: expected str, bytes or os.PathLike object, not NoneType
  in transformers/models/siglip/tokenization_siglip.py:150
```

**Root-Cause:** `AutoProcessor.from_pretrained` lädt ImageProcessor PLUS Tokenizer.
Der SigLIP-2-Tokenizer hat in transformers 4.38.2 noch keinen sauberen Resolver →
`vocab_file` resolved auf `None`.

**Fix:** `AutoProcessor` → `AutoImageProcessor` in `_try_load_siglip_vision`.
Wir brauchen für Brain V3 ohnehin nur die Vision-Seite, nicht Text/Tokenizer.

**Zweit-Lauf 11:59:26** mit Fix → alle 4 Tests grün.

**Implikation für Brain V3 Code:** Auch im produktiven `VideoEmbedder` wird
`AutoImageProcessor` statt `AutoProcessor` verwendet. transformers 4.38.2
ist damit ausreichend, **kein transformers-Upgrade nötig**, V1/V2-Stack bleibt
unangetastet.

---

## Was nicht getestet wurde (offene Spikes)

1. **Demucs + Brain coexistence** — separater Spike-Lauf mit `--tests demucs,clap` erforderlich
2. **NVENC + Brain coexistence** — braucht echten Render-Job, nicht Skript-isoliert
3. **PySide6-App-Prozess als Baseline** — Spike misst leeren Python-Prozess, nicht App mit Qt-Display
4. **Echter 2 h-Mix-Run mit CLAP** — Window-Sliding-Inferenz auf realer Audio-Datei, nicht Random-Audio
5. **SigLIP-2 mit echten Frames** (statt random uint8) — Embedding-Qualität ist nicht Spike-Thema, aber Inferenz-Zeit könnte abweichen
6. **transformers 4.38.2 + AutoImageProcessor für SigLIP-2 in Production-Pipeline** — Spike validiert nur einzelne Calls, nicht Long-Running-Loop

Empfohlen: Phase 2 startet, diese Spikes laufen daneben oder bei Bedarf.

---

## Vault-Pflege (CLAUDE.md)

- [x] Spike-Doc auf `status: completed`
- [x] Synthesis-Doc geschrieben (diese Datei)
- [ ] Im Brain-Bug Vault `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\` als
  `gpu-coexistence-spike-2026-05-03.md` ablegen (Pfad ist außerhalb des
  Workspace, User-Aktion erforderlich)
- [ ] `log.md`-Eintrag im Vault mit Verweis auf Spike + Plan-Korrekturen
- [ ] Plan-Doc-Korrekturen anwenden (separater Schritt — Plan-Docs liegen
  im Project-Cache `019dec39-…/docs/`, also auch außerhalb Workspace)

---

## Konsequenzen für nächste Schritte

**Phase 0 ist abgeschlossen.** GPU-Coexistenz funktioniert besser als geplant,
keine harten Blocker für Phase 1.

**Phase 1 (Datenseite)** kann starten:
- `media_hash` (sha256) bei Audio/Video-Import
- Schema-Erweiterungen `audio_schemas.py` / `video_schemas.py`
- `services/brain_v3/audio/subtrack_detector.py` (4-Signal-Heuristik, CPU)
- `services/brain_v3/video/visual_curves.py` (CPU)

**Phase 2 (Embedding-Pipeline)** kann mit konkreten DoD-Werten geplant werden:
- Default-Batch SigLIP-2: **8** (statt geplant 2)
- VRAM-Auto-Tuning: **als Defensive behalten, aber nicht Blocker**
- CLAP-Singleton + SigLIP-Singleton: weiterhin via `GPULockMiddleware`,
  aber sequenzieller Lifecycle nicht mehr zwingend
