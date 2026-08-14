"""stem_paths_project_relative

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-14

B-824 — ``audio_tracks.stem_*_path`` auf projektrelative Speicherung umstellen.

Die vier Spalten hielten bisher absolute Pfade. Das ueberlebt keine
Projektkopie und keinen Laufwerkswechsel: nach dem Kopieren zeigen sie auf den
alten Ort, und weil die Dateien dort meist noch liegen, greifen alle
``Path(p).exists()``-Pruefungen beherzt daneben. Im W3-Live-Run am 2026-08-14
las ein isoliertes Testprojekt dadurch Stems aus einem Host-Ordner, obwohl
dieselben Dateien im Projekt lagen (B-822).

B-822 hat die *Auslegung* der Pfade ans aktive Projekt gebunden. Diese Revision
zieht die *Bestandsdaten* auf das neue Format nach, damit die Bindung im
Normalfall gar nichts mehr zurechtbiegen muss. Neue Werte schreibt
``services/stem_router.py`` ``to_project_relative()`` bereits relativ.

Vorgehen, bewusst konservativ:

- Relativiert wird nur, was nachweislich unterhalb von ``projects.path`` des
  eigenen Tracks liegt. Trenner wird ``/``, damit der Wert plattform- und
  laufwerksunabhaengig bleibt.
- Pfade AUSSERHALB des Projekts bleiben unangetastet. Sie irgendwie
  zurechtzubiegen waere geraten; zur Laufzeit entscheidet
  ``resolve_stem_path()`` ehrlich, ob es im aktiven Projekt eine Entsprechung
  gibt, und behandelt sie sonst als fehlend.
- Bereits relative Werte und NULL bleiben unveraendert.
- Ist ``projects.path`` leer oder die Zuordnung unklar, passiert nichts.

Die Migration liest ausschliesslich die eigene DB und fasst keine Dateien an.

``downgrade()`` macht die relativen Werte wieder absolut, sofern
``projects.path`` bekannt ist — sonst bleibt der relative Wert stehen, weil
ein geratener absoluter Pfad schlechter waere als ein ehrlich relativer.

FROZEN-Regel B-509: ``database/migrations.py`` ist eingefroren, Schema- und
Datenaenderungen ausschliesslich via Alembic.
"""
from __future__ import annotations

import logging
import posixpath
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect, text

logger = logging.getLogger("alembic.migrate.stem_paths_project_relative")

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "audio_tracks"
_COLUMNS = (
    "stem_vocals_path",
    "stem_drums_path",
    "stem_bass_path",
    "stem_other_path",
)


def _table_exists(bind, table_name: str) -> bool:
    return table_name in set(inspect(bind).get_table_names())


def _columns(bind, table_name: str) -> set[str]:
    rows = bind.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def _norm(value: str) -> str:
    """Vergleichsform: Backslashes zu Slashes, Kleinschreibung, kein Trailing-Slash.

    Windows-Pfade sind case-insensitiv und mischen beide Trenner munter; ohne
    Normalisierung wuerde ein Prefix-Vergleich zufaellig scheitern.
    """
    return value.replace("\\", "/").rstrip("/").lower()


def _is_absolute(value: str) -> bool:
    """Absolut im Windows- ODER POSIX-Sinn.

    ``os.path`` waere plattformabhaengig — eine unter Windows geschriebene DB
    kann auch anderswo migriert werden.
    """
    v = value.replace("\\", "/")
    if v.startswith("/"):
        return True
    return len(v) >= 3 and v[1] == ":" and v[2] == "/"


def _project_roots(bind) -> dict[int, str]:
    if not _table_exists(bind, "projects"):
        return {}
    cols = _columns(bind, "projects")
    if not {"id", "path"} <= cols:
        return {}
    rows = bind.execute(text("SELECT id, path FROM projects")).fetchall()
    return {int(r[0]): str(r[1]) for r in rows if r[1]}


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE):
        logger.info("%s fehlt — uebersprungen", _TABLE)
        return
    cols = _columns(bind, _TABLE)
    present = [c for c in _COLUMNS if c in cols]
    if not present or "project_id" not in cols:
        logger.info("%s: keine Stem-Spalten oder kein project_id — skip", _TABLE)
        return

    roots = _project_roots(bind)
    if not roots:
        logger.info("Keine Projektpfade bekannt — Stem-Pfade bleiben unveraendert")
        return

    select_cols = ", ".join(["id", "project_id"] + present)
    rows = bind.execute(text(f"SELECT {select_cols} FROM {_TABLE}")).fetchall()

    converted = 0
    left_foreign = 0
    for row in rows:
        track_id = row[0]
        project_id = row[1]
        root = roots.get(int(project_id)) if project_id is not None else None
        if not root:
            continue
        root_norm = _norm(root)
        updates: dict[str, str] = {}
        for offset, column in enumerate(present, start=2):
            value = row[offset]
            if not value or not _is_absolute(str(value)):
                continue
            value_norm = _norm(str(value))
            if value_norm.startswith(root_norm + "/"):
                updates[column] = value_norm[len(root_norm) + 1:]
            else:
                left_foreign += 1
        if not updates:
            continue
        assignments = ", ".join(f"{c} = :{c}" for c in updates)
        bind.execute(
            text(f"UPDATE {_TABLE} SET {assignments} WHERE id = :track_id"),
            {**updates, "track_id": track_id},
        )
        converted += len(updates)

    logger.info(
        "B-824: %d Stem-Pfade projektrelativ gemacht, %d ausserhalb des Projekts "
        "bewusst unveraendert gelassen",
        converted, left_foreign,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, _TABLE):
        return
    cols = _columns(bind, _TABLE)
    present = [c for c in _COLUMNS if c in cols]
    if not present or "project_id" not in cols:
        return

    roots = _project_roots(bind)
    if not roots:
        return

    select_cols = ", ".join(["id", "project_id"] + present)
    rows = bind.execute(text(f"SELECT {select_cols} FROM {_TABLE}")).fetchall()

    for row in rows:
        track_id = row[0]
        project_id = row[1]
        root = roots.get(int(project_id)) if project_id is not None else None
        if not root:
            continue
        root_clean = str(root).replace("\\", "/").rstrip("/")
        updates: dict[str, str] = {}
        for offset, column in enumerate(present, start=2):
            value = row[offset]
            if not value or _is_absolute(str(value)):
                continue
            updates[column] = posixpath.join(root_clean, str(value).replace("\\", "/"))
        if not updates:
            continue
        assignments = ", ".join(f"{c} = :{c}" for c in updates)
        bind.execute(
            text(f"UPDATE {_TABLE} SET {assignments} WHERE id = :track_id"),
            {**updates, "track_id": track_id},
        )
