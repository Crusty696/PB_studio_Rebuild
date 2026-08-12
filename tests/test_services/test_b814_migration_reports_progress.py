"""B-814: Storage-Migration lief bei jedem Projekt-Open voellig stumm.

Befund (2026-08-12, Klassensuche nach stummen Langlaeufern nach B-810):
``StorageMigrationService.migrate_existing_outputs`` laeuft bei JEDEM
``open_project`` — direkt vor der B-810-Quellenreparatur, im selben try-Block
(``services/project_manager.py:464``). Pro Audiotrack/Videoclip mit vorhandenen
Outputs berechnet es ``compute_source_sha256(..., mode="strict")``, also einen
Hash ueber die KOMPLETTE Quelldatei.

Gemessen an der realen Projekt-DB ``outputs/test-tabelle``: 123 Clips mit
existierender Quelle UND existierenden Outputs, zusammen 1,16 GB, die bei jedem
Oeffnen komplett gelesen und gehasht werden.

Der ``progress_callback`` ist im Produktivpfad wirkungslos — kein Aufrufer
setzt ihn (``ensure_schnitt_audio_adapter`` uebergibt keinen), und das Modul
hatte ausser einem ``logger.warning`` keine einzige Ausgabe. Historischer
Beleg: ``logs/freeze_stacks_BEFORE_FIX.log`` zeigt den blockierten Main-Thread
14-mal genau in dieser Funktion.

Der Aufwand ist hier nicht gefahrlos zu senken (die Quell-Identitaet IST der
Hash, und ``project_sources`` hat keine Groessen-/mtime-Spalte fuer einen
Kurzschluss). Also gilt die zweite Regel: wenn die Dauer unvermeidbar ist, muss
sie sich melden. Genau das prueft dieser Test.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AudioTrack, Base, Project, VideoClip
from services.storage_provenance import storage_migration


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Project(id=1, name="P", path="p"))
        s.commit()
        yield s


def _clip_with_outputs(session: Session, tmp_path: Path, i: int) -> None:
    source = tmp_path / f"src{i}.mp4"
    source.write_bytes(b"video-bytes" + str(i).encode())
    proxy = tmp_path / f"proxy{i}.mp4"
    proxy.write_bytes(b"proxy-bytes")
    session.add(
        VideoClip(
            project_id=1,
            file_path=str(source),
            proxy_path=str(proxy),
        )
    )


def _migrator(session: Session, tmp_path: Path):
    return storage_migration.StorageMigrationService(
        session, storage_root=tmp_path / "storage"
    )


def test_run_reports_start_and_end(tmp_path: Path, session: Session, caplog) -> None:
    """Ohne Anfangs- und Abschlusszeile ist nicht erkennbar, ob der Lauf
    ueberhaupt arbeitet — das war der eigentliche Schaden."""
    for i in range(3):
        _clip_with_outputs(session, tmp_path, i)
    session.commit()

    with caplog.at_level(logging.INFO, logger=storage_migration.__name__):
        result = _migrator(session, tmp_path).migrate_existing_outputs()

    meldungen = [r.getMessage() for r in caplog.records]
    assert any("B-814" in m and "pruefe" in m for m in meldungen), (
        "Keine Anfangsmeldung — der Lauf startet weiterhin stumm. "
        f"Gesehen: {meldungen}"
    )
    assert any("B-814" in m and "fertig" in m for m in meldungen), (
        "Keine Abschlussmeldung — es bleibt unklar, ob der Lauf noch arbeitet. "
        f"Gesehen: {meldungen}"
    )
    assert result.video_clips == 3


def test_start_message_names_the_workload(
    tmp_path: Path, session: Session, caplog
) -> None:
    """Die Anfangsmeldung muss die Menge nennen, sonst sagt sie nichts ueber
    die zu erwartende Dauer."""
    for i in range(4):
        _clip_with_outputs(session, tmp_path, i)
    source = tmp_path / "a.wav"
    source.write_bytes(b"audio")
    session.add(AudioTrack(project_id=1, file_path=str(source)))
    session.commit()

    with caplog.at_level(logging.INFO, logger=storage_migration.__name__):
        _migrator(session, tmp_path).migrate_existing_outputs()

    start = next(
        m for m in (r.getMessage() for r in caplog.records)
        if "B-814" in m and "pruefe" in m
    )
    assert "1 Audiotrack" in start and "4 Videoclip" in start, (
        f"Anfangsmeldung nennt die Menge nicht: {start!r}"
    )


def test_progress_is_logged_during_a_long_run(
    tmp_path: Path, session: Session, caplog, monkeypatch
) -> None:
    """Laufende Meldungen: ein langer Lauf darf nicht minutenlang schweigen.

    Die Uhr wird vorgestellt statt echt gewartet — bewiesen wird das Melde-
    verhalten, nicht eine Dauer.
    """
    for i in range(6):
        _clip_with_outputs(session, tmp_path, i)
    session.commit()

    ticks = iter([0.0] + [i * 10.0 for i in range(1, 200)])
    monkeypatch.setattr(
        storage_migration.time, "monotonic", lambda: next(ticks)
    )

    with caplog.at_level(logging.INFO, logger=storage_migration.__name__):
        _migrator(session, tmp_path).migrate_existing_outputs()

    laufend = [
        m for m in (r.getMessage() for r in caplog.records)
        if "Migration laeuft" in m
    ]
    assert len(laufend) >= 2, (
        f"Nur {len(laufend)} laufende Meldung(en) — der Lauf bleibt zwischen "
        f"Start und Ende stumm. Gesehen: {laufend}"
    )


def test_empty_project_still_reports(tmp_path: Path, session: Session, caplog) -> None:
    """Abgrenzung: auch der leere Lauf meldet sich — sonst ist Stille wieder
    mehrdeutig (nichts zu tun vs. haengt)."""
    with caplog.at_level(logging.INFO, logger=storage_migration.__name__):
        _migrator(session, tmp_path).migrate_existing_outputs()

    meldungen = [r.getMessage() for r in caplog.records]
    assert any("B-814" in m and "fertig" in m for m in meldungen)
