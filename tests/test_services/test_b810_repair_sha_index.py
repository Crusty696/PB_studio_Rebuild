"""B-810: Projekt-Open hing 6:38 min ohne Rueckmeldung an der Quellen-Reparatur.

Live gemessen 2026-08-12: ``repair_missing_sources_on_project_open`` brauchte
beim Oeffnen eines Projekts (213 project_sources, 91 fehlend, 486 video_clips)
**6 Minuten 38 Sekunden** — ohne eine einzige Logzeile dazwischen. Windows
meldete den Prozess durchgehend als reagierend, aber Titel und TASKS-Panel
standen still. Fuer einen Nutzer ohne Log-Zugriff nicht von einem Freeze zu
unterscheiden.

Ursache: ``_find_by_sha`` lief **pro fehlender Quelle** einmal komplett per
``rglob("*")`` durch den Projektordner und berechnete dabei fuer **jede** Datei
einen SHA256. Bei 91 fehlenden Quellen also 91 volle Durchlaeufe inklusive
Proxies und Stems — der Aufwand multiplizierte sich mit der Zahl der Luecken.

Der Fix baut den Index **einmal**. Genau das pruefen diese Tests: nicht nur,
dass die Reparatur weiterhin funktioniert, sondern dass der Aufwand nicht mehr
mit der Zahl der fehlenden Quellen waechst.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.storage_provenance import file_tracking


@pytest.fixture()
def dateien(tmp_path):
    """Ein paar echte Dateien mit unterscheidbarem Inhalt."""
    root = tmp_path / "projekt"
    root.mkdir()
    pfade = []
    for i in range(6):
        p = root / f"clip{i}.mp4"
        p.write_bytes(f"inhalt-{i}".encode())
        pfade.append(p)
    return root, pfade


def test_b810_index_haelt_ersten_treffer_je_hash(dateien, monkeypatch):
    """Verhalten wie vorher: der erste Treffer je SHA gewinnt."""
    root, pfade = dateien
    monkeypatch.setattr(
        file_tracking, "compute_source_sha256",
        lambda p, media_type, mode: p.read_bytes().decode(),
    )

    index = file_tracking._build_sha_index([root], media_type="video")

    assert index["inhalt-0"] == pfade[0]
    assert len(index) == 6


def test_b810_aufwand_waechst_nicht_mit_zahl_der_luecken(dateien, monkeypatch):
    """Der Kern: eine Datei darf nur EINMAL gehasht werden, egal wie viele
    Quellen fehlen.

    Vorher war es einmal pro fehlender Quelle — daraus entstanden die 6:38 min.
    """
    root, pfade = dateien
    aufrufe: list[Path] = []

    def _zaehlend(p, media_type, mode):
        aufrufe.append(p)
        return p.read_bytes().decode()

    monkeypatch.setattr(file_tracking, "compute_source_sha256", _zaehlend)

    file_tracking._build_sha_index([root], media_type="video")

    assert len(aufrufe) == 6, (
        f"B-810: {len(aufrufe)} Hash-Berechnungen fuer 6 Dateien — der Index "
        "wird mehrfach aufgebaut."
    )
    assert len(set(aufrufe)) == len(aufrufe), (
        "B-810: dieselbe Datei wurde mehrfach gehasht."
    )


def test_b810_unlesbare_datei_stoppt_den_index_nicht(dateien, monkeypatch):
    """Eine kaputte Datei darf die Reparatur nicht abbrechen."""
    root, pfade = dateien

    def _mit_fehler(p, media_type, mode):
        if p.name == "clip3.mp4":
            raise OSError("nicht lesbar")
        return p.read_bytes().decode()

    monkeypatch.setattr(file_tracking, "compute_source_sha256", _mit_fehler)

    index = file_tracking._build_sha_index([root], media_type="video")

    assert len(index) == 5, "die uebrigen Dateien muessen im Index landen"
    assert "inhalt-3" not in index


def test_b810_fehlende_wurzel_wird_uebersprungen(tmp_path, monkeypatch):
    """Ein nicht existierender Suchpfad darf nicht werfen."""
    monkeypatch.setattr(
        file_tracking, "compute_source_sha256",
        lambda p, media_type, mode: "x",
    )
    index = file_tracking._build_sha_index(
        [tmp_path / "gibtsnicht"], media_type="video",
    )
    assert index == {}


def test_b810_meldet_fortschritt(dateien, monkeypatch, caplog):
    """Der Lauf darf nicht mehr stumm sein — sonst wirkt er wie ein Freeze."""
    root, _ = dateien
    monkeypatch.setattr(
        file_tracking, "compute_source_sha256",
        lambda p, media_type, mode: p.read_bytes().decode(),
    )

    with caplog.at_level("INFO"):
        file_tracking._build_sha_index([root], media_type="video", gesucht=3)

    text = " ".join(r.message for r in caplog.records)
    assert "B-810" in text, "B-810: der Indexlauf meldet gar nichts."
    assert "Index fertig" in text, (
        "B-810: es fehlt die Abschlussmeldung — dann bleibt unklar, ob der "
        "Lauf beendet ist oder noch haengt."
    )
