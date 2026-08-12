from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

# B-810: Abstand zwischen Fortschrittsmeldungen beim Indizieren. Der Lauf war
# vorher minutenlang stumm — fuer den Nutzer nicht von einem Freeze zu
# unterscheiden.
_INDEX_LOG_INTERVAL_S = 5.0

from sqlalchemy.orm import Session

from database.models import ProjectSource
from services.storage_provenance.source_identity import compute_source_sha256


@dataclass(frozen=True)
class FileRepairResult:
    checked: int
    repaired: int
    missing: tuple[int, ...]


def repair_missing_sources(
    session: Session,
    *,
    search_roots: Iterable[str | Path],
    media_type: str,
    source_ids: Iterable[int] | None = None,
) -> FileRepairResult:
    """Repair missing ``project_sources.current_source_path`` values by SHA."""

    roots = [Path(root) for root in search_roots]
    query = session.query(ProjectSource)
    if source_ids is not None:
        query = query.filter(ProjectSource.id.in_(tuple(source_ids)))
    sources = query.all()
    repaired = 0
    missing: list[int] = []

    # B-810: Erst sammeln, wen es ueberhaupt betrifft. Vorher lief pro
    # fehlender Quelle ein kompletter rglob("*") mit SHA256 ueber JEDE Datei —
    # bei 91 fehlenden Quellen also 91 volle Durchlaeufe durch den
    # Projektordner inklusive Proxies und Stems. Live gemessen: 6 Minuten
    # 38 Sekunden beim Projekt-Open, ohne eine einzige Logzeile dazwischen.
    zu_suchen = [
        source for source in sources
        if not Path(source.current_source_path).exists()
    ]
    if not zu_suchen:
        session.commit()
        return FileRepairResult(checked=len(sources), repaired=0, missing=())

    # Ein einziger Durchlauf statt einer je Quelle: Index sha -> Pfad.
    sha_index = _build_sha_index(roots, media_type=media_type, gesucht=len(zu_suchen))

    for source in zu_suchen:
        match = sha_index.get(source.source_sha256)
        if match is None:
            missing.append(source.id)
            continue

        source.current_source_path = str(match)
        source.last_seen_at = datetime.utcnow()
        repaired += 1

    session.commit()
    return FileRepairResult(checked=len(sources), repaired=repaired, missing=tuple(missing))


def _build_sha_index(
    roots: list[Path], *, media_type: str, gesucht: int = 0,
) -> dict[str, Path]:
    """B-810: einmal alle Kandidaten hashen statt einmal pro fehlender Quelle.

    Der erste Treffer je SHA gewinnt — genau wie beim frueheren
    ``_find_by_sha``, das beim ersten Match zurueckkehrte.

    Der Aufwand bleibt derselbe wie fuer EINE Suche; vorher multiplizierte er
    sich mit der Zahl der fehlenden Quellen. Zusaetzlich meldet die Funktion
    Fortschritt: der Lauf war vorher minutenlang stumm und damit von einem
    Freeze nicht zu unterscheiden.
    """
    index: dict[str, Path] = {}
    start = time.monotonic()
    geprueft = 0
    letzte_meldung = start

    logger.info(
        "B-810: suche %d fehlende Quelle(n) — indiziere %s ...",
        gesucht, ", ".join(str(r) for r in roots) or "(keine Wurzel)",
    )
    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            geprueft += 1
            jetzt = time.monotonic()
            if jetzt - letzte_meldung >= _INDEX_LOG_INTERVAL_S:
                logger.info(
                    "B-810: %d Dateien indiziert (%.0fs) — Suche laeuft ...",
                    geprueft, jetzt - start,
                )
                letzte_meldung = jetzt
            try:
                candidate_sha = compute_source_sha256(
                    candidate, media_type=media_type, mode="strict",
                )
            except (OSError, ValueError):
                continue
            index.setdefault(candidate_sha, candidate)

    logger.info(
        "B-810: Index fertig — %d Dateien, %d eindeutige Hashes, %.1fs.",
        geprueft, len(index), time.monotonic() - start,
    )
    return index


def _find_by_sha(source_sha256: str, roots: list[Path], *, media_type: str) -> Path | None:
    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            try:
                candidate_sha = compute_source_sha256(candidate, media_type=media_type, mode="strict")
            except (OSError, ValueError):
                continue
            if candidate_sha == source_sha256:
                return candidate
    return None
