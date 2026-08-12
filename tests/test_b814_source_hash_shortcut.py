"""B-814 — Zaehltests fuer den Quell-Hash-Kurzschluss beim Projekt-Open.

``StorageMigrationService.migrate_existing_outputs`` laeuft bei JEDEM
``open_project``. Vorher hashte es pro Lauf jede Quelldatei komplett neu
(real gemessen: 123 Clips / 1,16 GB). Diese Tests belegen ueber einen
Aufruf-Zaehler auf ``compute_source_sha256``, dass

* ein zweiter Open gar nicht mehr hasht (0 statt N),
* eine GEAENDERTE Datei sehr wohl neu gehasht wird,
* eine Bestandszeile ohne Stat-Fingerabdruck genau einmal hasht und den
  Wert nachtraegt (Selbstheilung).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database.models import Base, Project, ProjectSource, VideoClip
from services.storage_provenance import storage_migration as sm


CLIP_COUNT = 3


@pytest.fixture()
def env(tmp_path: Path):
    """Frische DB + 3 Videoclips mit existierender Quelle und Proxy."""
    db_path = tmp_path / "b814.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    sources_dir = tmp_path / "sources"
    proxies_dir = tmp_path / "proxies"
    sources_dir.mkdir()
    proxies_dir.mkdir()

    session = Session(engine)
    project = Project(name="B-814", path=str(tmp_path))
    session.add(project)
    session.flush()

    sources: list[Path] = []
    for i in range(CLIP_COUNT):
        source = sources_dir / f"clip{i}.mp4"
        source.write_bytes(b"quelle-" + bytes([i]) * 4096)
        proxy = proxies_dir / f"clip{i}_proxy.mp4"
        proxy.write_bytes(b"proxy-" + bytes([i]) * 128)
        session.add(
            VideoClip(
                project_id=project.id,
                file_path=str(source),
                proxy_path=str(proxy),
            )
        )
        sources.append(source)
    session.commit()

    yield session, tmp_path / "storage", sources, project.id

    session.close()
    engine.dispose()


class _Counter:
    """Zaehlt die echten Voll-Hash-Laeufe ueber die Quelldateien."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[str] = []
        original = sm.compute_source_sha256

        def _wrapped(path, *, media_type, mode="fast"):
            self.calls.append(str(path))
            return original(path, media_type=media_type, mode=mode)

        monkeypatch.setattr(sm, "compute_source_sha256", _wrapped)

    def reset(self) -> None:
        self.calls.clear()

    @property
    def count(self) -> int:
        return len(self.calls)


def _run(session: Session, storage_root: Path) -> None:
    sm.StorageMigrationService(session, storage_root=storage_root).migrate_existing_outputs()


def test_zweiter_open_hasht_keine_quelle_mehr(env, monkeypatch):
    """Kernbeweis: Open 1 hasht N Quellen, Open 2 hasht 0."""
    session, storage_root, _sources, _pid = env
    counter = _Counter(monkeypatch)

    _run(session, storage_root)
    erster_lauf = counter.count
    assert erster_lauf == CLIP_COUNT, (
        f"Erster Open muss jede Quelle einmal hashen, war {erster_lauf}"
    )

    counter.reset()
    _run(session, storage_root)
    assert counter.count == 0, (
        "Zweiter Open darf keine Quelldatei mehr lesen — gehasht wurden: "
        f"{counter.calls}"
    )


def test_stat_fingerabdruck_wird_persistiert(env, monkeypatch):
    """Nach dem ersten Lauf stehen Groesse und mtime in project_sources."""
    session, storage_root, sources, _pid = env
    _Counter(monkeypatch)

    _run(session, storage_root)

    rows = session.execute(
        select(
            ProjectSource.current_source_path,
            ProjectSource.source_bytes,
            ProjectSource.source_mtime_ns,
        )
    ).all()
    assert len(rows) == CLIP_COUNT
    per_path = {os.path.normcase(p): (b, m) for p, b, m in rows}
    for source in sources:
        stat = source.stat()
        assert per_path[os.path.normcase(str(source))] == (
            stat.st_size,
            stat.st_mtime_ns,
        )


def test_geaenderte_datei_wird_neu_gehasht(env, monkeypatch):
    """Inhaltsaenderung darf NICHT durchrutschen."""
    session, storage_root, sources, _pid = env
    counter = _Counter(monkeypatch)

    _run(session, storage_root)
    alte_shas = {
        row[0]
        for row in session.execute(select(ProjectSource.source_sha256)).all()
    }

    # Eine Quelle inhaltlich veraendern (andere Groesse UND andere mtime).
    geaendert = sources[1]
    geaendert.write_bytes(b"komplett anderer inhalt" * 500)

    counter.reset()
    _run(session, storage_root)

    assert counter.count == 1, (
        "Genau die geaenderte Quelle muss neu gehasht werden, gehasht: "
        f"{counter.calls}"
    )
    assert os.path.normcase(counter.calls[0]) == os.path.normcase(str(geaendert))

    neue_shas = {
        row[0]
        for row in session.execute(select(ProjectSource.source_sha256)).all()
    }
    assert neue_shas - alte_shas, "Fuer den neuen Inhalt fehlt eine neue sha-Row"


def test_gleiche_groesse_andere_mtime_wird_neu_gehasht(env, monkeypatch):
    """Der Grund fuer mtime: Groesse allein wuerde diesen Fall verschlucken."""
    session, storage_root, sources, _pid = env
    counter = _Counter(monkeypatch)

    _run(session, storage_root)

    ziel = sources[2]
    alt = ziel.read_bytes()
    vorher_ns = ziel.stat().st_mtime_ns
    # gleiche Byte-Zahl, anderer Inhalt
    ziel.write_bytes(bytes((b + 1) % 256 for b in alt))
    assert ziel.stat().st_size == len(alt)
    if ziel.stat().st_mtime_ns == vorher_ns:
        # Dateisystem mit grober Zeitaufloesung: mtime explizit vorruecken,
        # sonst testet der Fall nicht das, was er testen soll.
        neu = vorher_ns + 2_000_000_000
        os.utime(ziel, ns=(neu, neu))
    assert ziel.stat().st_mtime_ns != vorher_ns

    counter.reset()
    _run(session, storage_root)

    assert counter.count == 1, (
        "Gleiche Groesse, neuer Inhalt: die mtime muss den Kurzschluss "
        f"verhindern. Gehasht: {counter.calls}"
    )


def test_bestandszeile_ohne_fingerabdruck_hasht_einmal_und_heilt(env, monkeypatch):
    """Vor-B-814-Zeilen (source_bytes/mtime NULL) heilen sich beim ersten Open."""
    session, storage_root, _sources, _pid = env
    counter = _Counter(monkeypatch)

    _run(session, storage_root)

    # Bestandszustand simulieren: Fingerabdruck loeschen, sha behalten.
    for row in session.query(ProjectSource).all():
        row.source_bytes = None
        row.source_mtime_ns = None
    session.commit()

    counter.reset()
    _run(session, storage_root)
    assert counter.count == CLIP_COUNT, (
        "Ohne gespeicherten Fingerabdruck muss regulaer gehasht werden"
    )

    for row in session.query(ProjectSource).all():
        assert row.source_bytes is not None, "Groesse wurde nicht nachgetragen"
        assert row.source_mtime_ns is not None, "mtime wurde nicht nachgetragen"

    # ... und der Folge-Open ist wieder frei.
    counter.reset()
    _run(session, storage_root)
    assert counter.count == 0, f"Heilung unvollstaendig, gehasht: {counter.calls}"


def test_mehrdeutiger_pfad_kuerzt_nicht_ab(env, monkeypatch):
    """Zwei sha-Rows zum selben Pfad => keine Abkuerzung, sonst falsche Identitaet.

    ``compute_source_sha256`` mischt den ``media_type`` in den Hash. Derselbe
    Pfad kann daher unter zwei ``source_sha256`` in ``project_sources`` stehen
    (einmal als Audio, einmal als Video gehasht). ``project_sources`` hat keine
    media_type-Spalte — der Kurzschluss darf hier nicht raten.
    """
    session, storage_root, sources, project_id = env
    counter = _Counter(monkeypatch)

    _run(session, storage_root)

    # Zweite, stat-identische Row fuer denselben Pfad unterschieben.
    kollision = sources[0]
    stat = kollision.stat()
    session.add(
        ProjectSource(
            project_id=project_id,
            source_sha256="deadbeef" * 8,
            current_source_path=str(kollision),
            source_bytes=stat.st_size,
            source_mtime_ns=stat.st_mtime_ns,
        )
    )
    session.commit()

    counter.reset()
    _run(session, storage_root)

    assert counter.count == 1, (
        "Bei mehrdeutigem Pfad muss regulaer gehasht werden statt zu raten. "
        f"Gehasht: {counter.calls}"
    )
    assert os.path.normcase(counter.calls[0]) == os.path.normcase(str(kollision))


def test_kurzschluss_liefert_denselben_sha_wie_der_vollhash(env, monkeypatch):
    """Korrektheit: der abgekuerzte Wert ist exakt der echte strict-Hash."""
    session, storage_root, sources, _pid = env
    _Counter(monkeypatch)

    _run(session, storage_root)

    gespeichert = {
        os.path.normcase(p): sha
        for p, sha in session.execute(
            select(ProjectSource.current_source_path, ProjectSource.source_sha256)
        ).all()
    }
    for source in sources:
        erwartet = sm.compute_source_sha256(source, media_type="video", mode="strict")
        assert gespeichert[os.path.normcase(str(source))] == erwartet
