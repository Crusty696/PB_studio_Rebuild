"""Brain V3 — lernfaehiger Audio-Video-Reranker als Layer ueber PacingPipeline.

Designed fuer GTX 1060 6 GB Pascal, Python 3.10 + torch 1.12.1+cu113 +
transformers 4.38.2 (siehe Phase-0-Spike unter
docs/superpowers/synthesis/2026-05-03-brain-v3-gpu-coexistence-synthesis.md).

V3 lebt parallel zu V1 (services/brain_service.py) und V2
(services/brain_v2/). Eigener Namespace, eigene DB-Files unter
%APPDATA%\\PB_Studio\\brain_v3\\. V1/V2-Refactor ist freigegeben
(User-Direktive 2026-05-05, F2), erfordert aber pro Refactor eine
Live-Verifikation der V1/V2-Funktion.

Architektur-Standard (User-Direktive 2026-05-05, F1): PB Studio Rebuild
ist reine PySide6-Desktop-App mit in-process Service-Aufrufen.
Brain V3 stellt einen BrainV3Service-Fassaden-Wrapper bereit (Phase 4)
— kein FastAPI-Server, kein REST-Layer.

Phasen-Status (Plan-Doc 06, Stand 2026-05-05):
- Phase 0: GPU-Coexistenz-Spike — DONE (live verifiziert)
- Phase 1: Datenseite (hashing, schemas, subtrack_detector, visual_curves)
           — code-complete (35 pytest), App-Sync PENDING
- Phase 2: Embedding-Pipeline (CLAP + SigLIP-2 + sqlite-vec)
           — code-complete (70 pytest + Validation-Spike), App-Sync PENDING
- Phase 3: Brain-Core (Beta-Bernoulli mit Hierarchical Backoff)
           — code-complete (112/112 pytest, Lauf 2026-05-05), App-Sync PENDING
- Phase 4: Pacing-Integration (Reranker-Hook in PacingPipeline.select_best
           + in-process BrainV3Service-Wrapper) — TODO
- Phase 5: PySide6-UI (in-process BrainV3Service-Aufrufe) — TODO
- Phase 6: Haertung (Backup, Recovery, Lizenz-Attribution) — TODO
"""

__version__ = "0.3.0-code-complete-app-sync-pending"
