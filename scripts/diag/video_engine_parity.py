"""Paritaets-Harness: Monolith-Video-Pipeline vs. DAG-Engine.

NEUBAU-VOLLINTEGRATION M3 (D-065 / USE-003, Verify-Schritt).

Faehrt DENSELBEN Clip sequentiell durch beide Pfade und vergleicht die vom
Rest der App gelesenen Senken (Scene-Tabelle + LanceDB), NICHT die
Datei-Artefakte. Sequentiell, weil beide Pfade GPU (GTX 1060, 6 GB) nutzen —
ein Parallellauf riskiert OOM/Heap-Korruption.

WICHTIG: braucht eine echte GPU + ein reales Projekt mit dem Ziel-VideoClip.
Nicht im CI/headless-Parallelbetrieb starten — GPU-Zugriff mit dem
Haupt-Worktree koordinieren (eine Karte). Kein Byte-Match erwartet
(fp16-Nichtdeterminismus, andere Motion-Aufloesung) — Vergleich mit
Toleranzen.

Aufruf (conda-Env pb-studio):
    python scripts/diag/video_engine_parity.py --clip-id 42 \
        --project "C:/pfad/zum/projekt"

Ausgabe: Report nach tests/qa_artifacts/video_engine_parity_<clip>.md
und Exit-Code 0 (Paritaet innerhalb Toleranz) bzw. 1 (Abweichung).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Repo-Root in den Importpfad (Direktaufruf legt nur scripts/diag/ hinein).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# Toleranzen (dokumentiert in D-065): Szenen-Anzahl exakt; Energy im Mittel
# innerhalb ENERGY_MEAN_TOL (andere Motion-Aufloesung -> Skala-Drift);
# Embedding-Zeilen-Anzahl exakt.
ENERGY_MEAN_TOL = 0.20
SCENE_COUNT_EXACT = True


def _snapshot_scenes(clip_id: int) -> list[dict]:
    from database import nullpool_session, Scene
    with nullpool_session() as s:
        rows = (
            s.query(Scene)
            .filter(Scene.video_clip_id == clip_id)
            .order_by(Scene.start_time)
            .all()
        )
        return [
            {"start": float(r.start_time), "end": float(r.end_time),
             "energy": float(r.energy or 0.0),
             "has_caption": bool(r.ai_caption)}
            for r in rows
        ]


def _vectordb_count() -> int:
    from services.vector_db_service import VectorDBService
    return VectorDBService().count()


def _resolve_video_path(clip_id: int) -> str:
    from database import nullpool_session, VideoClip
    with nullpool_session() as s:
        clip = s.query(VideoClip).filter(VideoClip.id == clip_id).first()
        if clip is None:
            raise SystemExit(f"VideoClip {clip_id} nicht in aktiver Projekt-DB.")
        return clip.file_path


def _run_monolith(clip_id: int, video_path: str) -> None:
    from services.video_analysis_service import run_full_pipeline
    run_full_pipeline(video_path, clip_id)


def _run_engine(clip_id: int, video_path: str, storage_dir: Path) -> None:
    from services.video_pipeline.app_integration import run_video_pipeline_on_clip
    run_video_pipeline_on_clip(clip_id, video_path, storage_dir)


def _compare(mono: list[dict], eng: list[dict],
             mono_vdb: int, eng_vdb: int) -> tuple[bool, list[str]]:
    notes: list[str] = []
    ok = True

    if SCENE_COUNT_EXACT and len(mono) != len(eng):
        ok = False
        notes.append(
            f"FEHLER Szenen-Anzahl: Monolith={len(mono)} vs Engine={len(eng)}")
    else:
        notes.append(f"Szenen: Monolith={len(mono)}, Engine={len(eng)}")

    n = min(len(mono), len(eng))
    if n:
        energy_diffs = [abs(mono[i]["energy"] - eng[i]["energy"]) for i in range(n)]
        mean_diff = sum(energy_diffs) / n
        max_diff = max(energy_diffs)
        notes.append(
            f"Energy-Diff: Mittel={mean_diff:.4f} (Toleranz {ENERGY_MEAN_TOL}), "
            f"Max={max_diff:.4f}")
        if mean_diff > ENERGY_MEAN_TOL:
            ok = False
            notes.append(
                "FEHLER Energy-Mittelwert-Abweichung ueber Toleranz "
                "(erwartet bei Skala-Drift; Toleranz ggf. anpassen + "
                "Motion-Normalisierung pruefen).")

    notes.append(f"VectorDB-Count: Monolith={mono_vdb}, Engine={eng_vdb}")
    if mono_vdb != eng_vdb:
        ok = False
        notes.append("FEHLER VectorDB-Embedding-Anzahl weicht ab.")

    eng_caps = sum(1 for s in eng if s["has_caption"])
    mono_caps = sum(1 for s in mono if s["has_caption"])
    notes.append(
        f"Captions: Monolith={mono_caps}/{len(mono)}, "
        f"Engine={eng_caps}/{len(eng)} "
        "(Engine-VLM ist Stub -> weniger/keine strukturierten Captions "
        "erwartet, kein Paritaets-Fehler).")

    return ok, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--clip-id", type=int, required=True)
    ap.add_argument("--project", type=str, default=None,
                    help="Projektordner (set_project) falls nicht default.")
    args = ap.parse_args()

    if args.project:
        from database.session import set_project
        set_project(args.project)
        # Aeltere Projekt-DBs (z.B. kopierte Bestandsprojekte) auf das
        # aktuelle Schema heben — set_project legt nur fehlende Tabellen an,
        # keine fehlenden Spalten (z.B. projects.transition_type).
        try:
            from database.migrations import init_db
            init_db()
        except Exception as exc:
            print(f"[warn] init_db/Migration nach set_project: {exc}")

    clip_id = args.clip_id
    video_path = _resolve_video_path(clip_id)

    scratch = Path("tests/qa_artifacts") / f"engine_parity_clip{clip_id}"
    scratch.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] Monolith-Lauf auf Clip {clip_id} ({video_path}) ...")
    _run_monolith(clip_id, video_path)
    mono_scenes = _snapshot_scenes(clip_id)
    mono_vdb = _vectordb_count()
    print(f"      Monolith: {len(mono_scenes)} Szenen, VectorDB={mono_vdb}")

    print(f"[2/4] Engine-Lauf auf Clip {clip_id} ...")
    _run_engine(clip_id, video_path, scratch / "engine_storage")
    eng_scenes = _snapshot_scenes(clip_id)
    eng_vdb = _vectordb_count()
    print(f"      Engine:   {len(eng_scenes)} Szenen, VectorDB={eng_vdb}")

    print("[3/4] Vergleich ...")
    ok, notes = _compare(mono_scenes, eng_scenes, mono_vdb, eng_vdb)

    print("[4/4] Report schreiben ...")
    report = Path("tests/qa_artifacts") / f"video_engine_parity_{clip_id}.md"
    lines = [
        f"# Video-Engine-Paritaet — Clip {clip_id}",
        "",
        f"Video: `{video_path}`",
        f"Ergebnis: {'PARITAET (innerhalb Toleranz)' if ok else 'ABWEICHUNG'}",
        "",
        "## Befunde",
        "",
    ]
    lines += [f"- {n}" for n in notes]
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"      -> {report}")
    for n in notes:
        print("   ", n)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
