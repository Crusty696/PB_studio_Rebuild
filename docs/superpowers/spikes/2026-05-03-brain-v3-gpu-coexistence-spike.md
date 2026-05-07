# Brain V3 — Phase-0-Spike: GPU-Coexistenz + VRAM-Budget

**Datum:** 2026-05-03
**Owner:** David
**Hardware-Ziel:** GTX 1060 6 GB Pascal (Compute 6.1)
**Status:** `completed` — auf Ziel-Hardware (GTX 1060 6 GB) verifiziert am 2026-05-03 12:00 mit Lauf `outputs/spike_brain_v3_gpu/20260503_115926/`
**Skript:** `scripts/spike_brain_v3_gpu_coexistence.py`

---

## Warum dieser Spike (Plan-Doc 02 #21+#22, Plan-Doc 07 R10+R16)

Der V3-Plan setzt zwei Annahmen, die nicht durch Code-Studium beweisbar sind,
sondern reale Messung auf der Ziel-Hardware brauchen:

1. **VRAM-Budget:** Brain-Inferenz darf max ~3.5 GB belegen, weil 6 GB GTX
   1060 minus Reserve (Display, Demucs, RAFT, NVENC) so eng ist.
2. **Coexistenz:** CLAP + SigLIP-2 gleichzeitig im VRAM zu halten ist
   wahrscheinlich nicht moeglich → sequenzieller Modell-Lifecycle wird
   Architektur-Prinzip statt Optimierung.

Solange diese Annahmen nicht real gemessen sind, sind alle Phase-2-DoDs
(Default-Batch, Erst-Embedding-Zeit, Cache-Hit-Rate-Schwelle) Spekulation
und duerfen nicht als "OK" markiert werden.

CLAUDE.md OBERSTE REGEL: nicht raten, real messen.

---

## Was das Skript misst

| Test | Was wird gemessen | Erwartetes Ergebnis (Hypothese) |
|---|---|---|
| `baseline` | VRAM nach reinem `torch.cuda.init()` + 1-Tensor-Alloc | <300 MB allocated, ein paar 100 MB reserved (CUDA-Kontext) |
| `clap` | `laion/larger_clap_music` Load + Inferenz auf 10 s Random-Audio + Unload | Peak ~1.6–2.0 GB allocated bei FP32, ~50–100 MB Rest nach `empty_cache()` |
| `siglip2` | `google/siglip2-base-patch16-384` Vision-Tower bei `batch=1,2,4,8` | batch=1: ~600–900 MB. batch=8: vermutlich OOM auf 6 GB. OOM-Punkt ist die Antwort die wir suchen. |
| `siglip_existing` (opt.) | `google/siglip-so400m-patch14-384` (Bestand V1/V2) | ~2.5–4 GB allocated FP32 — Vergleich, nicht Plan-relevant |
| `coexistence` | CLAP laden, dann SigLIP-2 zusaetzlich laden | **OOM erwartet auf 6 GB.** Wenn nicht OOM, ist Plan-Doc 02 #21 entspannbar. |
| `demucs` (opt.) | `htdemucs` Load + apply auf 10 s Stereo-Audio | Peak ~1–2 GB; relevant fuer GPULockMiddleware-Erweiterung |

Alle Snapshots werden inkrementell in `outputs/spike_brain_v3_gpu/<timestamp>/snapshots.json`
geschrieben — falls ein spaeterer Test crasht, bleiben die vorigen Daten erhalten.

---

## Wie ausfuehren

### Voraussetzungen

```text
# Python-Env muss CUDA-faehig sein:
python scripts/diagnose_cuda.py   # muss >= "Diagnose OK" liefern

# Modelle koennen beim ersten Lauf gedownloaded werden:
#   laion/larger_clap_music         ~1.4 GB
#   google/siglip2-base-patch16-384 ~370 MB
# Internet-Verbindung beim ersten Lauf erforderlich.
```

### Standard-Lauf (alles)

```text
# Standard-Stack (Python 3.11 + torch 2.5.1+cu124):
.venv\Scripts\python.exe scripts/spike_brain_v3_gpu_coexistence.py

# Surface-Book-2 (Python 3.10 + torch 1.12.1+cu113) — falls dort ausgefuehrt:
.venv310\Scripts\python.exe scripts/spike_brain_v3_gpu_coexistence.py
```

### Schnell-Lauf (ohne Demucs, ohne SigLIP-Bestand)

Default-Tests reichen (`baseline,clap,siglip2,coexistence`). Demucs und
existierender SigLIP-1 sind opt-in.

### Inkl. existierendes SigLIP-1 (V1/V2-Vergleich)

```text
python scripts/spike_brain_v3_gpu_coexistence.py --include-existing-siglip
```

### Nur einzelne Tests

```text
python scripts/spike_brain_v3_gpu_coexistence.py --tests baseline,coexistence
```

### Custom Batch-Stufen fuer SigLIP-2

```text
python scripts/spike_brain_v3_gpu_coexistence.py --siglip2-batches 1,2,3,4
```

---

## Output

```text
outputs/spike_brain_v3_gpu/<YYYYMMDD_HHMMSS>/
    snapshots.json   — strukturierte Roh-Messungen
    report.md        — Markdown-Synthese mit Empfehlung
    run.log          — Roh-Log mit Zeitstempeln
```

### Wie der Report zu lesen ist

- **`status: ok`** = Test ohne Fehler durchgelaufen, Snapshots brauchbar
- **`status: oom`** = OutOfMemoryError eingefangen — das ist eine **Antwort**,
  kein Bug. Letzter Snapshot vor OOM zeigt das reale Limit.
- **`status: error`** = anderer Fehler, manuelle Pruefung im `run.log` noetig
- **`status: skipped`** = Voraussetzung fehlte (z.B. demucs nicht installiert)

Auto-Synthese am Ende des Reports macht Vorschlag fuer Default-Batch.
**Diese Empfehlung ist eine Hypothese auf Basis der Messung — nicht autoritativ.**

---

## Was der Spike entscheidet

Nach erfolgreichem Lauf:

1. **Plan-Doc 02 #21 (sequenzieller Lifecycle)** wird entweder bestaetigt
   (Coexistenz OOM) oder optional (Coexistenz OK).
2. **Plan-Doc 02 #22 (FP32 Default)** bleibt vermutlich, aber falls SigLIP-2
   batch>=4 schon FP32 sprengt, wird FP16-Eval in Phase 2 vorgezogen.
3. **Plan-Doc 06 Phase 2 DoD** wird kalibriert:
   - `Default-Batch SigLIP-2 = max(OK-Batches)`
   - `Erst-Embedding-Schwelle <X min` mit X aus realer Messung statt
     aus Pascal-vs-RDNA3-Extrapolation
4. **Plan-Doc 07 R10 / R16** koennen von Wahrscheinlichkeit "hoch" auf
   "mittel/niedrig" runtergestuft werden, falls Spike sie widerlegt — oder
   bestaetigt bleiben, falls Spike sie reproduziert.

---

## Vault-Pflicht (CLAUDE.md)

Nach erfolgreichem Lauf:

1. **Report kopieren** nach `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\gpu-coexistence-spike-2026-05-03.md`
   (Datum ggf. an Lauf-Datum anpassen).
2. **`log.md` Eintrag** im Vault mit Verweis auf:
   - Skript-Pfad
   - Spike-Output-Verzeichnis
   - Konsequenz fuer Phase-2-DoD (welcher Default-Batch, welche
     Erst-Embedding-Schwelle)
3. **Diese Spike-Doc** auf `status: completed` setzen + Datum +
   verlinkt-zu `wiki/synthesis/...`-Eintrag.

---

## Was dieser Spike NICHT testet

Bewusste Lücken — falls relevant, separater Spike:

- **Demucs + CLAP/SigLIP gleichzeitig** (nicht nur sequentiell). Aktueller
  Test misst beide einzeln, nicht in Kombination.
- **NVENC + Brain-Inferenz parallel** (Plan-Doc 02 #23). Braucht echtes
  Render-Job-Setup.
- **RAFT + Brain-Inferenz parallel.**
- **PySide6-App-Prozess als Baseline** — Skript misst leeren Python-Prozess,
  nicht den vollstaendigen App-Boot mit Qt-Display etc. Erwartete Differenz:
  +200–500 MB durch Qt+OpenGL-Compositor.

Diese Luecken sollten als separate Phase-0-Spikes folgen, falls die ersten
Messungen knapp werden.

---

## Status-Tracking

- [x] Skript geschrieben (`scripts/spike_brain_v3_gpu_coexistence.py`)
- [x] Spike-Pre-Doc geschrieben (diese Datei)
- [x] Skript auf Ziel-Hardware ausgefuehrt — **erfolgreich Lauf 20260503_115926**
- [ ] Output in Vault `wiki/synthesis/` kopiert (Pre-Doc liegt in `docs/superpowers/synthesis/`)
- [x] Phase-2-DoD-Schwellen aus Mess-Daten kalibriert (siehe Synthesis-Doc)
- [x] Plan-Doc 07 R10/R16 neu-bewertet (siehe Synthesis-Doc)
- [x] Spike-Doc auf `status: completed` gesetzt

---

## Erst-Lauf 2026-05-03 ~10:31 Uhr — BLOCKIERT

**Status:** `blocked-by-cuda-unavailable`

`scripts/diagnose_cuda.py` lief vollstaendig durch und meldete in Sektion 4:

```text
[!!] torch.cuda.is_available: False
    cuda compile-time version: 11030
    torch.cuda.device_count: 0
    -> moegliche Ursachen: NVIDIA Treiber zu alt,
       GPU im Energiesparmodus, CUDA_VISIBLE_DEVICES gesetzt,
       oder anderer Prozess haelt CUDA exklusiv.
```

Alle anderen Sektionen GRUEN:
- Python: conda-env `pb-studio` (Python 3.10.20)
- torch 1.12.1+cu113, torchvision 0.13.1+cu113
- 13 NVIDIA-Treiber-Ordner im DriverStore
- 0 PATH-Konflikte
- RAFT-Load auf CPU: OK
- Tiny-SigLIP-Smoke: OK

`spike_brain_v3_gpu_coexistence.py` brach in `_check_cuda_or_exit()` mit
Exit-Code 2 ab — wie spezifiziert. Kein `outputs/spike_brain_v3_gpu/`
Verzeichnis erstellt.

**Konsequenz:** Brain V3 Phase 0 kann nicht abgeschlossen werden, solange
CUDA nicht verfuegbar ist. Das blockiert auch die normale PB-Studio-App
mit GPU-Workloads.

**Naechste Diagnose-Schritte (priorisiert):**

1. Pruefen ob anderer CUDA-Prozess laeuft (`python.exe`, `pb_studio.exe`,
   `ollama.exe`) → Task-Manager
2. `nvidia-smi` in frischem cmd → zeigt ob Treiber + GPU grundsaetzlich
   antwortet
3. `CUDA_VISIBLE_DEVICES` Env-Variable pruefen
4. `scripts/cuda_recovery.ps1` als Admin ausfuehren (Stuck-Driver-Reset,
   benoetigt UAC-Bestaetigung vom User)
5. PC-Neustart als letzter Ausweg

**Wiederholungs-Lauf:** Nach Recovery erneut `run_spike_brain_v3.bat`
doppelklicken — wenn `is_available() = True`, laeuft Spike voll durch.
