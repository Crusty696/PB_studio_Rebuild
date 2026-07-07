"""Fixplan 2026-07-07 Schritt 5: gezielte Re-Analyse motion_scores (+ Captions).

Nach dem Schritt-1-Fix (Motion-Sampling/Normalisierung) und Schritt-2-Fix
(Caption-Validierung) traegt dieses Skript korrigierte Werte in eine
bestehende Projekt-DB nach, ohne die komplette Pipeline (SceneDetect,
Keyframes, SigLIP) neu zu rechnen.

Aufruf (conda-env pb-studio):
    python scripts/diag/fixplan_reanalyze_motion_captions.py \
        --db outputs/final-check/pb_studio.db [--captions]

GPU-Regel: RAFT ausschliesslich via ModelManager auf cuda:0 (GTX 1060).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def reanalyze_motion(db_path: Path) -> tuple[int, int]:
    """Berechnet motion_scores fuer alle Szenen der DB neu (RAFT, Batch-Modus).

    Returns: (anzahl_szenen_aktualisiert, anzahl_videos)
    """
    from services.video_analysis_service import (
        SceneInfo, _load_raft_model, compute_motion_scores,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT vc.id, vc.file_path, s.id, s.start_time, s.end_time "
            "FROM video_clips vc JOIN scenes s ON s.video_clip_id = vc.id "
            "WHERE vc.deleted_at IS NULL ORDER BY vc.id, s.start_time"
        ).fetchall()

        by_video: dict[int, dict] = {}
        for vc_id, fpath, s_id, s_start, s_end in rows:
            by_video.setdefault(vc_id, {"path": fpath, "scenes": []})
            by_video[vc_id]["scenes"].append((s_id, s_start, s_end))

        model, device = _load_raft_model()
        print(f"RAFT: {'cuda' if model is not None else 'CPU-Fallback'} ({device})")

        updated = 0
        for vc_id, info in by_video.items():
            vpath = info["path"]
            if not Path(vpath).exists():
                print(f"  SKIP video {vc_id}: Datei fehlt: {vpath}")
                continue
            scene_objs = [
                SceneInfo(index=i, start_time=s, end_time=e)
                for i, (_sid, s, e) in enumerate(info["scenes"])
            ]
            scene_objs = compute_motion_scores(
                vpath, scene_objs, raft_model_device=(model, device))
            for (sid, _s, _e), sc in zip(info["scenes"], scene_objs):
                conn.execute(
                    "UPDATE scenes SET energy = ? WHERE id = ?",
                    (float(sc.motion_score or 0.0), sid))
                updated += 1
            conn.execute(
                "UPDATE analysis_status SET status='done', value_summary=?, "
                "completed_at=? WHERE media_type='video' AND media_id=? "
                "AND step_key='motion_scores'",
                (json.dumps({"avg_motion": round(
                    sum(s.motion_score or 0 for s in scene_objs)
                    / max(1, len(scene_objs)), 3),
                    "reanalyzed": "fixplan-2026-07-07"}),
                 datetime.now().isoformat(timespec="seconds"), vc_id))
            conn.commit()
            scores = [f"{s.motion_score:.3f}" for s in scene_objs]
            print(f"  video {vc_id}: {Path(vpath).name[:50]:52s} motion={scores}")

        if model is not None:
            from services.model_manager import ModelManager
            ModelManager().unload_raft()
        return updated, len(by_video)
    finally:
        conn.close()


def reanalyze_captions(db_path: Path) -> tuple[int, int]:
    """Ersetzt Junk-Captions durch validierte Vision-Captions (wenn Ollama laeuft).

    Returns: (anzahl_neu_gecaptioned, anzahl_junk_geloescht)
    """
    from services.video_analysis_service import (
        SceneInfo, _validate_caption_dict, analyze_scene_with_caption,
    )

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT s.id, s.video_clip_id, s.start_time, s.end_time, "
            "s.ai_caption, s.keyframe_paths, vc.file_path "
            "FROM scenes s JOIN video_clips vc ON vc.id = s.video_clip_id "
            "ORDER BY s.video_clip_id, s.start_time").fetchall()

        # Keyframe-Ableitung: scenes.keyframe_paths ist in Alt-Projekten NULL,
        # die JPGs liegen aber unter storage/keyframes mit dem Muster
        # <video_stem>_proxy_scene%04d.jpg (Index = Szenen-Reihenfolge).
        kf_dir = db_path.parent / "storage" / "keyframes"
        scene_idx_per_video: dict[int, int] = {}

        junk_cleared = 0
        to_caption: list[tuple[int, SceneInfo]] = []
        for sid, vc_id, s_start, s_end, cap_json, kf_json, vc_path in rows:
            _idx = scene_idx_per_video.get(vc_id, 0)
            scene_idx_per_video[vc_id] = _idx + 1
            if not kf_json and vc_path:
                cand = kf_dir / f"{Path(vc_path).stem}_proxy_scene{_idx:04d}.jpg"
                if cand.exists():
                    kf_json = json.dumps([str(cand)])
                    conn.execute(
                        "UPDATE scenes SET keyframe_paths=? WHERE id=?",
                        (kf_json, sid))
            parsed = None
            if cap_json:
                try:
                    parsed = json.loads(cap_json)
                except json.JSONDecodeError:
                    parsed = None
            if _validate_caption_dict(parsed) is not None:
                continue  # Caption ist brauchbar — nicht anfassen
            if cap_json:
                conn.execute(
                    "UPDATE scenes SET ai_caption=NULL, ai_mood=NULL, "
                    "ai_tags=NULL WHERE id=?", (sid,))
                junk_cleared += 1
            kf = None
            if kf_json:
                try:
                    kfs = json.loads(kf_json)
                    kf = kfs[0] if isinstance(kfs, list) and kfs else None
                except json.JSONDecodeError:
                    kf = None
            if kf and Path(kf).exists():
                si = SceneInfo(index=sid, start_time=s_start, end_time=s_end)
                si.keyframe_path = kf
                to_caption.append((sid, si))
        conn.commit()
        print(f"Junk-Captions geloescht: {junk_cleared}; "
              f"Kandidaten fuer Re-Caption: {len(to_caption)}")

        if not to_caption:
            return 0, junk_cleared

        scenes = [si for _sid, si in to_caption]
        analyze_scene_with_caption(scenes)

        captioned = 0
        for (sid, _), si in zip(to_caption, scenes):
            if si.ai_caption:
                conn.execute(
                    "UPDATE scenes SET ai_caption=?, ai_mood=?, ai_tags=? "
                    "WHERE id=?",
                    (json.dumps(si.ai_caption, ensure_ascii=False),
                     si.ai_mood,
                     json.dumps(si.ai_tags or [], ensure_ascii=False), sid))
                captioned += 1
        conn.commit()
        return captioned, junk_cleared
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--captions", action="store_true",
                    help="Junk-Captions loeschen + via Ollama neu erzeugen")
    args = ap.parse_args()
    if not args.db.exists():
        print(f"DB nicht gefunden: {args.db}")
        return 1

    updated, n_videos = reanalyze_motion(args.db)
    print(f"\nMotion-Re-Analyse: {updated} Szenen in {n_videos} Videos aktualisiert")

    if args.captions:
        captioned, cleared = reanalyze_captions(args.db)
        print(f"Captions: {cleared} Junk geloescht, {captioned} neu erzeugt")

    conn = sqlite3.connect(str(args.db))
    vals = [r[0] for r in conn.execute("SELECT energy FROM scenes")]
    conn.close()
    import numpy as np
    arr = np.array(vals)
    print(f"\nVerifikation scenes.energy: n={len(arr)} min={arr.min():.3f} "
          f"median={np.median(arr):.3f} max={arr.max():.3f} "
          f"distinct={len(set(np.round(arr, 3)))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
