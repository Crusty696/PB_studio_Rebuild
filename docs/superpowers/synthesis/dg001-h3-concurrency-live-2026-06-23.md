# DG-001 H3 Concurrency Live Verify — 2026-06-23

status: agent-live-pass
gate: DG-001 H3
hardware: NVIDIA GeForce GTX 1060 6 GB, CUDA 11.3
runner: `scripts/diag/verify_dg001_h3_concurrency.py`

## Ergebnis

Echter gleichzeitiger Lauf in einem Python-Prozess, je Pipeline in eigenem
Thread:

- Audio: synthetische 8-s-Stereo-PCM-WAV, echter `htdemucs_ft`-CUDA-Lauf,
  `reused=False`, vier Stems, anschließend alle acht Audio-V2-Stages.
- Video: synthetisches 4-s-H.264-Video, sieben Stages inklusive echtem
  SigLIP und RAFT.
- Beide Threads starteten gleichzeitig und endeten ohne Deadlock.
- Finaler Run: `20260623-050437`, Audio-Seed `1476850520`.
- Gesamt-Walltime: `36.375 s`.
- Audio: `ok=true`, `failures=[]`, acht Ergebnis-Keys.
- Video: `completed_count=7`, `failed_count=0`, `cancelled=false`.
- Video-Artefakte: Proxy, Scenes, Keyframes, Embeddings, Motion, Captions und
  Cut-Plan vorhanden.
- GPU-Peak: `4534 / 6144 MiB`.
- Nach Lauf: `0 / 6144 MiB`, GPU-Last 1 %.

## Lock-/Ablaufbeleg

Demucs verwendet `GPU_EXECUTION_LOCK`; SigLIP und RAFT verwenden den
app-globalen `GpuSerializer`, der zuerst denselben Legacy-Lock greift.
Laufzeiten zeigen Serialisierung unter echter Contention:

- Demucs CUDA-Chunk: ungefähr `05:04:47–05:04:55`.
- SigLIP-Modellload begann danach um `05:04:56`.
- Kein gleichzeitiger VRAM-Peak beider Modelle, kein Timeout, kein OOM.

Damit sind H3.1, H3.2 und H3.3 agentisch neu belegt.

## Persistente Rohbelege

Rohdateien liegen lokal unter
`test-report/dg001-h3-concurrency-20260623/20260623-050437/` und sind durch `.gitignore`
ausgeschlossen:

- `result.json`: SHA256
  `C402AD35A10627D5A1CF9D1BAA41B969081237FC98D0713860BCAF7A1EFD4A1E`
- `h3.log`: SHA256
  `C7A2B04CCD06885AEBD67D5140E36F34A5B681CE5029FD703EAD626391127A31`

Der reproduzierbare Runner und diese kompakte Evidenz sind versioniert.

## Warnungen / Grenzen

- Torchaudio warnte vor PCM24-Rundung.
- Hugging Face meldete eine `resume_download`-Deprecation.
- Librosa meldete ein leeres Tuning-Frequenzset für synthetischen Input.
- RAFT meldete ein nicht beschreibbares NumPy-Array.
- NumPy meldete für einen leeren synthetischen Teilwert `Mean of empty slice`.
- Synthetische Quellen prüfen Concurrency, Locking und Pipeline-Korrektheit,
  nicht Langform-Endurance.
- Kein User-`fixed` oder Release-Sign-off.
