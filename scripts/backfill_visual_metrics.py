"""
scripts/backfill_visual_metrics.py
===================================

Nachruest-Pfad fuer BESTEHENDE Projekte: fuellt die von Alembic-Revision
``f2a3b4c5d6e7`` auf ``struct_clip_tags`` nachgeruesteten Spalten, ohne dass
die komplette Video-Analyse neu laufen muss.

* ``avg_brightness`` / ``avg_saturation`` / ``color_temp`` /
  ``visual_frame_count`` / ``visual_metrics_version``
  — gemessen aus den bereits auf Platte liegenden Keyframe-JPEGs
    (``<APP_ROOT>/storage/keyframes/``). CPU-only, kein GPU, kein ffmpeg.

* optional ``--roles``: ``role`` / ``role_confidence`` / ``role_source``
  — neu bestimmt ueber die bereits vorhandenen SigLIP-Embeddings
    (``<APP_ROOT>/data/vector/embeddings.db``) gegen
    ``config/role_prototypes.npz``. Ebenfalls kein Modell-Load: die
    Embeddings liegen fertig in der Vector-DB, die Prototypen als .npz.

Verwendung::

    # Vorschau, schreibt nichts
    python scripts/backfill_visual_metrics.py --db outputs/test-tabelle/pb_studio.db --dry-run

    # Bildmetriken schreiben
    python scripts/backfill_visual_metrics.py --db outputs/test-tabelle/pb_studio.db

    # Bildmetriken + Rollen neu bestimmen
    python scripts/backfill_visual_metrics.py --db ... --roles

    # bereits gefuellte Zeilen ueberschreiben
    python scripts/backfill_visual_metrics.py --db ... --force

Ohne ``--db`` wird die DB des aktiven Projekts ueber ``database.session``
aufgeloest.

Das Skript schreibt ausschliesslich per ``UPDATE`` auf vorhandene
``struct_clip_tags``-Zeilen. Szenen ohne solche Zeile (= nie enriched, z.B.
weil kein Embedding vorlag) werden gemeldet, aber nicht angelegt — die
NOT-NULL-Spalten ``mood_refined``/``style_bucket_id`` liessen sich hier nicht
ehrlich befuellen. Fuer diese Szenen ist ein normaler Enrichment-Lauf noetig.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from services.enrichment.visual_metrics import (  # noqa: E402
    compute_scene_metrics,
    resolve_scene_keyframes,
)

_VISUAL_COLUMNS = (
    "avg_brightness",
    "avg_saturation",
    "color_temp",
    "visual_frame_count",
    "visual_metrics_version",
    "role_source",
)


# ---------------------------------------------------------------------------
def _resolve_db(db_arg: str | None) -> Path:
    if db_arg:
        return Path(db_arg).resolve()
    import database.session as _session

    return Path(_session.APP_ROOT / "pb_studio.db").resolve()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _load_scene_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Szenen + Clip-Pfade + vorhandene struct_clip_tags-Werte."""
    sql = (
        "SELECT s.id, s.video_clip_id, s.start_time, s.scene_index, "
        "       s.keyframe_paths, vc.file_path, vc.proxy_path, "
        "       t.scene_id IS NOT NULL AS has_tags, t.avg_brightness "
        "FROM scenes s "
        "JOIN video_clips vc ON vc.id = s.video_clip_id "
        "LEFT JOIN struct_clip_tags t ON t.scene_id = s.id "
        "ORDER BY s.video_clip_id, s.start_time"
    )
    rows = conn.execute(sql).fetchall()
    out: list[dict[str, Any]] = []
    pos_per_clip: dict[int, int] = {}
    for (
        sid,
        clip_id,
        start_time,
        scene_index,
        kf_raw,
        file_path,
        proxy_path,
        has_tags,
        avg_brightness,
    ) in rows:
        pos = pos_per_clip.get(clip_id, 0)
        pos_per_clip[clip_id] = pos + 1
        stored: list[str] = []
        if kf_raw:
            try:
                parsed = json.loads(kf_raw) if isinstance(kf_raw, str) else kf_raw
            except (TypeError, ValueError):
                parsed = None
            if isinstance(parsed, list):
                stored = [str(p) for p in parsed if p]
            elif isinstance(parsed, str):
                stored = [parsed]
        out.append(
            {
                "scene_id": sid,
                "clip_id": clip_id,
                "start_time": start_time,
                # scene_index ist in Alt-Projekten NULL -> Positions-Fallback
                "scene_index": scene_index if scene_index is not None else pos,
                "keyframe_paths": stored,
                "file_path": file_path,
                "proxy_path": proxy_path,
                "has_tags": bool(has_tags),
                "avg_brightness": avg_brightness,
            }
        )
    return out


def _load_embeddings(vector_db: Path) -> dict[tuple[str, int], np.ndarray]:
    """{(video_path, scene_index): embedding} aus der Vector-DB (read-only)."""
    if not vector_db.exists():
        return {}
    uri = f"file:{vector_db.as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        rows = con.execute(
            "SELECT video_path, scene_index, embedding FROM clip_embeddings"
        ).fetchall()
    return {
        (str(vp), int(si)): np.frombuffer(blob, dtype=np.float32)
        for vp, si, blob in rows
    }


# ---------------------------------------------------------------------------
def _variance_report(label: str, values: list[float]) -> None:
    finite = [v for v in values if v is not None]
    if not finite:
        print(f"  {label:<22} keine Werte")
        return
    distinct = len({round(v, 6) for v in finite})
    print(
        f"  {label:<22} n={len(finite):<4} min={min(finite):+.4f} "
        f"max={max(finite):+.4f} spread={max(finite) - min(finite):.4f} "
        f"distinct={distinct}"
    )


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        rec = getattr(stream, "reconfigure", None)
        if rec is not None:
            rec(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(
        description="Backfill visual metrics (and optionally roles) into struct_clip_tags."
    )
    ap.add_argument("--db", default=None, help="Pfad zur Projekt-DB (pb_studio.db).")
    ap.add_argument(
        "--keyframe-dir",
        default=None,
        help="Keyframe-Verzeichnis (default: <db-dir>/storage/keyframes).",
    )
    ap.add_argument(
        "--vector-db",
        default=None,
        help="Vector-DB (default: <db-dir>/data/vector/embeddings.db).",
    )
    ap.add_argument(
        "--prototypes",
        default=None,
        help="Rollen-Prototypen .npz (default: config/role_prototypes.npz).",
    )
    ap.add_argument(
        "--roles",
        action="store_true",
        help="Zusaetzlich role/role_confidence/role_source aus Embeddings neu bestimmen.",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Auch bereits gefuellte Zeilen ueberschreiben.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur rechnen und berichten, nichts schreiben.",
    )
    args = ap.parse_args()

    db_path = _resolve_db(args.db)
    if not db_path.exists():
        print(f"ERROR: DB nicht gefunden: {db_path}", file=sys.stderr)
        return 1
    root = db_path.parent
    kf_dir = Path(args.keyframe_dir) if args.keyframe_dir else root / "storage" / "keyframes"
    vec_db = Path(args.vector_db) if args.vector_db else root / "data" / "vector" / "embeddings.db"

    print(f"DB           : {db_path}")
    print(f"Keyframes    : {kf_dir}  (exists={kf_dir.is_dir()})")
    if args.roles:
        print(f"Vector-DB    : {vec_db}  (exists={vec_db.exists()})")
    print(f"Modus        : {'DRY-RUN' if args.dry_run else 'WRITE'}"
          f"{' +force' if args.force else ''}")

    conn = sqlite3.connect(str(db_path))
    try:
        cols = _columns(conn, "struct_clip_tags")
        if not cols:
            print("ERROR: Tabelle struct_clip_tags fehlt.", file=sys.stderr)
            return 2
        missing = [c for c in _VISUAL_COLUMNS if c not in cols]
        if missing:
            print(
                "ERROR: Spalten fehlen: " + ", ".join(missing) + "\n"
                "       Zuerst migrieren: alembic upgrade head "
                "(Revision f2a3b4c5d6e7).",
                file=sys.stderr,
            )
            return 2

        scenes = _load_scene_rows(conn)
        print(f"\nSzenen       : {len(scenes)}  "
              f"(mit struct_clip_tags-Zeile: {sum(1 for s in scenes if s['has_tags'])})")

        classifier = None
        embeddings: dict[tuple[str, int], np.ndarray] = {}
        if args.roles:
            from services.enrichment.role_embedding_classifier import (
                RoleEmbeddingClassifier,
                RolePrototypesUnavailable,
            )

            try:
                classifier = RoleEmbeddingClassifier(prototypes_path=args.prototypes)
            except RolePrototypesUnavailable as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 3
            embeddings = _load_embeddings(vec_db)
            print(f"Embeddings   : {len(embeddings)}  "
                  f"Rollen: {', '.join(classifier.roles)}")

        updated_visual = 0
        updated_roles = 0
        skipped_no_tags = 0
        skipped_existing = 0
        no_keyframe = 0
        brights: list[float] = []
        sats: list[float] = []
        temps: list[float] = []
        role_counts: dict[str, int] = {}
        role_confs: list[float] = []

        for s in scenes:
            if not s["has_tags"]:
                skipped_no_tags += 1
                continue
            if s["avg_brightness"] is not None and not args.force:
                skipped_existing += 1
                continue

            kf_files = resolve_scene_keyframes(
                keyframe_dir=kf_dir,
                scene_index=int(s["scene_index"]),
                stored_paths=s["keyframe_paths"],
                video_path=s["file_path"],
                proxy_path=s["proxy_path"],
            )
            vm = compute_scene_metrics(kf_files) if kf_files else None
            if vm is None:
                no_keyframe += 1
            else:
                brights.append(vm.brightness)
                sats.append(vm.saturation)
                temps.append(vm.color_temp)

            role_update: tuple[str, float, str] | None = None
            if classifier is not None:
                emb = embeddings.get((str(s["file_path"]), int(s["scene_index"])))
                if emb is None:
                    role_update = ("unknown", 0.0, "unknown:no_embedding")
                else:
                    try:
                        r, c = classifier.classify(emb)
                        role_update = (r, c, "embedding")
                        role_confs.append(c)
                    except ValueError as exc:
                        role_update = ("unknown", 0.0, f"unknown:{exc}"[:200])
                role_counts[role_update[0]] = role_counts.get(role_update[0], 0) + 1

            if args.dry_run:
                if vm is not None:
                    updated_visual += 1
                if role_update is not None:
                    updated_roles += 1
                continue

            if vm is not None:
                conn.execute(
                    "UPDATE struct_clip_tags SET avg_brightness=?, avg_saturation=?, "
                    "color_temp=?, visual_frame_count=?, visual_metrics_version=? "
                    "WHERE scene_id=?",
                    (
                        vm.brightness,
                        vm.saturation,
                        vm.color_temp,
                        vm.frame_count,
                        vm.version,
                        s["scene_id"],
                    ),
                )
                updated_visual += 1
            if role_update is not None:
                conn.execute(
                    "UPDATE struct_clip_tags SET role=?, role_confidence=?, "
                    "role_source=? WHERE scene_id=?",
                    (role_update[0], role_update[1], role_update[2], s["scene_id"]),
                )
                updated_roles += 1

        if not args.dry_run:
            conn.commit()

        print("\nErgebnis")
        print(f"  Bildmetriken geschrieben : {updated_visual}")
        if args.roles:
            print(f"  Rollen geschrieben       : {updated_roles}")
            print(f"  Rollen-Verteilung        : {role_counts}")
        print(f"  ohne Keyframe            : {no_keyframe}")
        print(f"  ohne struct_clip_tags    : {skipped_no_tags}")
        print(f"  schon gefuellt (skip)    : {skipped_existing}")

        print("\nVarianz der neu berechneten Werte")
        _variance_report("avg_brightness", brights)
        _variance_report("avg_saturation", sats)
        _variance_report("color_temp", temps)
        if args.roles:
            _variance_report("role_confidence", role_confs)
            print(f"  {'distinkte Rollen':<22} {len(role_counts)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
