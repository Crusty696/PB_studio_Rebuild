"""Entkoppelte Leaf-Helper des Ingest-Service.

AUFRAEUM B1: verbatim aus ``services/ingest_service.py`` ausgelagert. Kein
Logik-Change. Keiner dieser Helper liest ein Modul-Global ``engine``,
``VectorDBService`` oder ``get_ffprobe_bin`` — alle DB-/Service-Zugriffe
laufen ueber Funktion-lokale Imports. Darum sind sie sicher auslagerbar,
solange ``services.ingest_service`` sie re-importiert (Re-Export).
"""

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _resolve_project_id(project_id: int | None) -> int:
    """B-053 Cycle 12: ersetzt hardcoded project_id=1.

    Wenn der Caller None passt, wird das aktive Projekt aus der DB
    aufgelöst. Fallback auf 1 nur wenn kein aktives Projekt existiert
    (z.B. brand-fresh Setup vor erstem create_project).
    """
    if project_id is not None:
        return int(project_id)
    try:
        from database.session import get_active_project_id
        active = get_active_project_id()
        if active is not None:
            return int(active)
    except (ImportError, AttributeError, RuntimeError) as exc:
        logger.warning("_resolve_project_id: get_active_project_id failed: %s", exc)
    logger.warning(
        "ingest_service: kein aktives Projekt — falle auf project_id=1 zurück. "
        "Das kann nach Projekt-Switch zu falschen Zuordnungen führen (B-053)."
    )
    return 1


def _resolve_project_id_for_ingest(project_id: int | None) -> int:
    """B-280: Project-ID-Aufloesung speziell fuer den Import-Pfad.

    Im Gegensatz zu ``_resolve_project_id`` (genutzt von Read-Pfaden, die auf
    einer leeren DB still eine leere Liste liefern duerfen) faellt der Import
    NICHT auf ``project_id=1`` zurueck, wenn kein aktives Projekt existiert.

    Vorher: Bei leerer DB loeste die ``=1``-Fallback-Kette eine irrefuehrende
    FK-Fehlermeldung ("Projekt mit id=1 existiert nicht") pro Datei aus. Jetzt
    bekommt der User eine klare, einmalige "erst Projekt anlegen/oeffnen"-
    Meldung.

    Raises:
        ValueError: Wenn ``project_id is None`` UND kein aktives Projekt in der
            DB existiert.
    """
    if project_id is not None:
        return int(project_id)
    try:
        from database.session import get_active_project_id
        active = get_active_project_id()
    except (ImportError, AttributeError, RuntimeError) as exc:
        logger.warning("_resolve_project_id_for_ingest: get_active_project_id failed: %s", exc)
        active = None
    if active is not None:
        return int(active)
    raise ValueError(
        "Kein aktives Projekt vorhanden. Bitte zuerst ein Projekt anlegen "
        "oder oeffnen, bevor Medien importiert werden."
    )


def _ensure_project_exists(project_id: int) -> None:
    """B-054: Project-FK-Pre-Check vor INSERT.

    SQLite mit WAL kann FK-Violations erst beim Commit melden →
    User sieht generisches "Import fehlgeschlagen" statt klares
    "Projekt {id} existiert nicht". Wir pruefen vorher mit einem
    schnellen SELECT.

    Raises:
        ValueError: Wenn das Projekt nicht (mehr) existiert oder
                    soft-geloescht ist.
    """
    try:
        from database import nullpool_session
        from database.models import Project
    except ImportError as exc:
        # Falls Module nicht ladbar: lass den FK-Check beim Commit feuern.
        logger.warning("B-054: _ensure_project_exists import failed: %s", exc)
        return
    try:
        with nullpool_session() as session:
            proj = (
                session.query(Project)
                .filter(Project.id == project_id, Project.deleted_at.is_(None))
                .first()
            )
            if proj is None:
                raise ValueError(
                    f"Projekt mit id={project_id} existiert nicht "
                    f"(oder ist soft-geloescht). Import abgebrochen."
                )
    except ValueError:
        raise
    except Exception as exc:
        # B-212: OperationalError (DB-Lock) ist KEIN Pre-Check-Fail im
        # gleichen Sinne wie ein fehlendes Projekt — wir muessen den User
        # konkret informieren statt das generische FK-Error vom INSERT
        # spaeter zu kassieren. SQLAlchemy / sqlite3 OperationalError fangen
        # wir ueber den Klassennamen ab (Import zur Vermeidung von
        # zirkulaerem Import bei Service-Bootstrap).
        is_db_lock = exc.__class__.__name__ in ("OperationalError", "DatabaseError")
        if is_db_lock:
            raise ValueError(
                f"DB temporaer nicht verfuegbar (Lock/Busy) — Pre-Check fuer "
                f"project_id={project_id} fehlgeschlagen: {exc}. "
                f"Bitte Vorgang erneut versuchen."
            ) from exc
        # B-054 Original: andere unerwartete Fehler (Schema-Drift, etc.)
        # nicht doppelt crashen lassen — der spaetere INSERT zeigt den
        # konkreten Fehler.
        logger.warning("B-054: _ensure_project_exists query failed: %s", exc)

def _json_loads_safe(value):
    """Parst einen JSON-String zu einer Liste/dict; gibt None zurueck bei Fehler."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _invalidate_pacing_caches():
    """Pacing-Caches leeren nach Media-Import."""
    try:
        from services.pacing_service import invalidate_pacing_caches
        invalidate_pacing_caches()
    except ImportError as e:
        logger.warning("Invalidating pacing caches after media import: %s", e)


def _apply_cross_project_reuse_after_ingest(
    session: Session,
    *,
    source_path: Path,
    media_type: str,
    media_id: int,
    project_id: int,
) -> None:
    """Best-effort OTK-021 reuse status; import itself stays authoritative."""
    try:
        from database.models import Project
        from services.storage_provenance.cross_project_reuse import apply_cross_project_reuse_status

        # B-539: pass the globally-unique project path so the by_sha manifest
        # fallback can exclude the active project's own entries (project_id is
        # not unique across per-project DBs).
        _proj = session.get(Project, project_id)
        hit = apply_cross_project_reuse_status(
            session,
            source_path,
            media_type=media_type,
            media_id=media_id,
            current_project_id=project_id,
            current_project_path=_proj.path if _proj is not None else None,
        )
        if hit is not None:
            logger.info(
                "OTK-021 cross-project reuse applied: %s/%d from project=%s steps=%s",
                media_type,
                media_id,
                hit.project_name,
                [step.analysis_step_key for step in hit.steps],
            )
    except Exception as exc:
        logger.warning(
            "OTK-021 cross-project reuse check failed for %s/%d (%s): %s",
            media_type,
            media_id,
            source_path,
            exc,
        )


def _file_meta(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")
    stat = path.stat()
    return {
        "file_path": str(path.resolve()),
        "title": path.stem,
        "size_bytes": stat.st_size,
        "extension": path.suffix.lower(),
    }
