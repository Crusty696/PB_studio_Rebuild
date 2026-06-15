"""OTK-018 — Echter End-to-End-Lauf der Audio-V2-Pipeline (Orchestrator).

Faehrt den portierten AudioAnalysisPipeline-Orchestrator synchron durch ALLE
8 Default-Stages auf einer echten Audio-Datei (Demucs-StemGen auf GTX 1060,
GPU-Lock, Beat/Onset/Key/Structure/LUFS/Spectral/AV-Pacing). Belegt "fachlich
portiert und getestet" (Plan AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17),
bevor Caller-Migration/GUI-Aktivierung beginnt.

Nutzung:
    python tests/e2e_audio_pipeline_orchestrator.py [--audio PATH]
"""
# main.py-Early-Init (CUDA/FFmpeg/PATH) wie e2e_functional_test.
from dotenv import load_dotenv
load_dotenv()

import os
import sys
import time
import logging
import argparse
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[2]  # scripts/diag/ -> Repo-Root (CRF-020-Move-Fix)
_BIN_DIR = str(_APP_ROOT / "bin")
if "PATH" in os.environ and _BIN_DIR not in os.environ["PATH"]:
    os.environ["PATH"] = _BIN_DIR + os.pathsep + os.environ["PATH"]
sys.path.insert(0, str(_APP_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
)
log = logging.getLogger("e2e_orchestrator")

DEFAULT_AUDIO = r"C:\Users\David Lochmann\Music\pb_short_3min.mp3"
PROJECT_ROOT = _APP_ROOT / "test-report" / "e2e-orchestrator-project"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default=DEFAULT_AUDIO)
    args = ap.parse_args()

    audio_path = str(Path(args.audio).resolve())
    if not Path(audio_path).exists():
        log.error("Audio fehlt: %s", audio_path)
        return 2

    # QApplication fuer QObject/QThreadPool-Affinitaet (wir laufen synchron via _run_stages).
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)

    # Test-Projekt-Root aktivieren.
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    from database.session import set_project
    set_project(PROJECT_ROOT)
    log.info("Projekt-Root: %s", PROJECT_ROOT)

    # DB-Init + Projekt sicherstellen (ingest braucht aktives/explizites Projekt).
    from database import init_db, engine, AudioTrack, Project
    from sqlalchemy.orm import Session
    init_db()
    with Session(engine) as s:
        project = s.query(Project).filter(Project.deleted_at.is_(None)).first()
        if project is None:
            project = Project(name="E2E Orchestrator Project",
                              path=str(PROJECT_ROOT), resolution="1920x1080", fps=30.0)
            s.add(project)
            s.commit()
        project_id = project.id
    log.info("project_id=%s", project_id)

    # Audio importieren -> track_id.
    with Session(engine) as s:
        existing = s.query(AudioTrack).filter(AudioTrack.file_path == audio_path).first()
        track_id = existing.id if existing else None
    if track_id is None:
        from services.ingest_service import ingest_audio
        res = ingest_audio(audio_path, project_id=project_id)
        if res is None:
            with Session(engine) as s:
                t = s.query(AudioTrack).filter(AudioTrack.file_path == audio_path).first()
                track_id = t.id if t else None
        else:
            track_id = res.id
    if track_id is None:
        log.error("Import fehlgeschlagen")
        return 3
    log.info("track_id=%s (%s)", track_id, audio_path)

    # GPU-Status.
    try:
        import torch
        log.info("CUDA=%s GPU=%s", torch.cuda.is_available(),
                 torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-")
    except Exception as e:
        log.warning("torch-Status: %s", e)

    # Pipeline bauen + synchron fahren.
    from services.audio_pipeline.context import PipelineContext
    from services.audio_pipeline.orchestrator import AudioAnalysisPipeline
    from services.audio_pipeline.stages import build_default_stages

    ctx = PipelineContext(track_id=track_id, original_path=audio_path)
    pipe = AudioAnalysisPipeline(build_default_stages())

    timings: dict[str, float] = {}
    _t = {"start": None}

    def _started(name):
        _t["start"] = time.time()
        log.info(">>> STAGE START: %s", name)

    def _done(name, payload):
        dt = time.time() - (_t["start"] or time.time())
        timings[name] = dt
        log.info("<<< STAGE DONE : %s (%.1fs) %s", name, dt, payload)

    def _failed(name, msg):
        log.error("XXX STAGE FAIL : %s : %s", name, msg)

    pipe.stage_started.connect(_started)
    pipe.stage_done.connect(_done)
    pipe.stage_failed.connect(_failed)

    t0 = time.time()
    failed = {"any": False}
    pipe.stage_failed.connect(lambda *_: failed.__setitem__("any", True))
    try:
        pipe._run_stages(ctx)
    except Exception as e:
        log.error("Pipeline-Stop (fail-fast): %s", e)
    total = time.time() - t0

    log.info("=" * 60)
    log.info("ERGEBNIS track_id=%s total=%.1fs failed=%s", track_id, total, failed["any"])
    for name, payload in ctx.results.items():
        log.info("  %-10s %s", name, payload)
    log.info("=" * 60)
    return 1 if failed["any"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
