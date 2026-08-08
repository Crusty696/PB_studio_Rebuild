"""B-729 — Enrichment-Backfill fuer ALLE Szenen des aktiven Projekts.

Problem: struct_clip_tags hatte nur 4 von ~440 Szenen (Rest role=unknown im
Pacing), weil das Structure-Enrichment nie flaechendeckend lief. Dieses Script
fuehrt den IDENTISCHEN Klassifikationspfad der App aus — keinerlei
Reimplementierung:

    database.session.set_project(<projekt>)          # Engine + APP_ROOT-Swap
    StructureEnrichmentWorker(clip_id=None).run()    # Regeln (config/
        enrichment_rules.yaml) -> Fallback RoleEmbeddingClassifier (SigLIP-
        Cosine gegen config/role_prototypes.npz) -> ehrlich 'unknown'.
        Schreibt struct_clip_tags per INSERT OR REPLACE inkl. role_source,
        dazu struct_style_bucket (Refit) und struct_compat_edge (Neuaufbau).

GPU-Hartregel: Der gesamte Pfad ist CPU (numpy-Cosine, PIL-Bildmetriken,
UMAP/HDBSCAN). Kein torch noetig, keine iGPU.

Vor jedem Schreiben wird ein Datei-Backup pb_studio.db.bak-b729-<timestamp>
angelegt (sqlite3-Backup-API, WAL-sicher).

Aufruf (App muss beendet sein):
    python scripts/diag/b729_enrichment_backfill.py
    python scripts/diag/b729_enrichment_backfill.py --project <projektordner>
    python scripts/diag/b729_enrichment_backfill.py --dry-run   # nur Zaehlen
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_PROJECT = (
    REPO_ROOT.parent / "projects" / "new_test_august"
)


def role_distribution(db_file: Path) -> list[tuple]:
    con = sqlite3.connect(str(db_file))
    try:
        rows = con.execute(
            "SELECT role, role_source, COUNT(*) FROM struct_clip_tags "
            "GROUP BY role, role_source ORDER BY 3 DESC"
        ).fetchall()
        total = con.execute("SELECT COUNT(*) FROM struct_clip_tags").fetchone()[0]
        scenes = con.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
    finally:
        con.close()
    print(f"  scenes gesamt: {scenes} | struct_clip_tags Zeilen: {total}")
    for role, src, n in rows:
        print(f"  role={role!r:14} role_source={src!r:12} count={n}")
    return rows


def backup_db(db_file: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = db_file.with_name(f"{db_file.name}.bak-b729-{ts}")
    src = sqlite3.connect(str(db_file))
    try:
        dst = sqlite3.connect(str(bak))
        try:
            src.backup(dst)  # WAL-sicher, konsistenter Snapshot
        finally:
            dst.close()
    finally:
        src.close()
    print(f"Backup angelegt: {bak} ({bak.stat().st_size} Bytes)")
    return bak


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--project", type=Path, default=DEFAULT_PROJECT,
        help=f"Projektordner mit pb_studio.db (Default: {DEFAULT_PROJECT})",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Nur Vorher-Verteilung ausgeben, nichts schreiben.",
    )
    args = ap.parse_args()

    project = args.project.resolve()
    db_file = project / "pb_studio.db"
    if not db_file.exists():
        print(f"FEHLER: {db_file} existiert nicht.")
        return 2

    print(f"Projekt: {project}")
    print("Verteilung VORHER:")
    role_distribution(db_file)

    if args.dry_run:
        print("--dry-run: Ende ohne Schreiben.")
        return 0

    backup_db(db_file)

    # Aktives Projekt setzen (Engine-Swap + APP_ROOT + Service-Pfade) —
    # derselbe Mechanismus, den die App beim Projektwechsel nutzt.
    import database.session as db_session

    db_session.set_project(project)

    from workers.structure_enrichment import StructureEnrichmentWorker

    worker = StructureEnrichmentWorker(clip_id=None)
    worker.progress.connect(lambda p, m: print(f"  [{p:3d}%] {m}"))
    result = worker.run()
    print(f"Worker-Ergebnis: {result}")
    if "error" in result:
        print("FEHLER — kein Commit erfolgt, Backup unangetastet.")
        return 1

    print("Verteilung NACHHER:")
    role_distribution(db_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
