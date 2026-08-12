"""B-809: eine verwaiste Junction blockierte den SCHNITT-Audio-Adapter.

Live beobachtet 2026-08-12 beim Projekt-Open:

    OTK-021: SCHNITT-Audio-Adapter/File-Tracking konnte beim Projekt-Open
    nicht initialisiert werden: mklink /J failed ... Eine Datei kann nicht
    erstellt werden, wenn sie bereits vorhanden ist.

Ursache: ``Path.exists()`` **folgt** der Junction. Zeigt eine vorhandene
Junction auf ein inzwischen geloeschtes Ziel, liefert ``exists()`` ``False`` —
obwohl der Pfad im Dateisystem belegt ist. ``create_directory_link`` hielt den
Pfad daher fuer frei und rief ``mklink``, das prompt scheiterte.

Der Fehler trat bei **jedem** Projekt-Open auf, solange die verwaiste Junction
lag. Sichtbare Folge: der Audio-Adapter blieb uninitialisiert.

Die Tests laufen nur auf Windows — Junctions gibt es anderswo nicht.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "nt", reason="Junctions gibt es nur auf Windows"
)


def _junction(link: Path, ziel: Path) -> None:
    import subprocess

    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(ziel)],
        capture_output=True, check=True,
    )


def test_b809_verwaiste_junction_wird_neu_gesetzt(tmp_path):
    """Der Kern: Junction zeigt ins Leere -> Link muss trotzdem entstehen."""
    from services.storage_provenance.layout import create_directory_link

    altes_ziel = tmp_path / "altes_ziel"
    altes_ziel.mkdir()
    link = tmp_path / "verknuepfung"
    _junction(link, altes_ziel)

    # Ziel verschwindet — die Junction bleibt und zeigt ins Leere.
    altes_ziel.rmdir()
    assert os.path.lexists(link), "Vorbedingung: die Junction liegt noch da"
    assert not link.exists(), "Vorbedingung: exists() folgt ihr und sagt False"

    neues_ziel = tmp_path / "neues_ziel"
    neues_ziel.mkdir()
    (neues_ziel / "beleg.txt").write_text("da", encoding="utf-8")

    ergebnis = create_directory_link(link, neues_ziel)

    assert ergebnis == link
    assert (link / "beleg.txt").is_file(), (
        "B-809: der Link zeigt nicht auf das neue Ziel — genau hier scheiterte "
        "mklink mit 'Datei existiert bereits' und der Audio-Adapter blieb tot."
    )


def test_b809_intakte_junction_bleibt_unangetastet(tmp_path):
    """Regressionsschutz: eine gueltige Junction darf nicht neu gebaut werden."""
    from services.storage_provenance.layout import create_directory_link

    ziel = tmp_path / "ziel"
    ziel.mkdir()
    (ziel / "inhalt.txt").write_text("unveraendert", encoding="utf-8")
    link = tmp_path / "verknuepfung"
    _junction(link, ziel)

    ergebnis = create_directory_link(link, ziel)

    assert ergebnis == link
    assert (link / "inhalt.txt").read_text(encoding="utf-8") == "unveraendert"


def test_b809_echtes_verzeichnis_wird_nicht_geloescht(tmp_path):
    """Ein normales Verzeichnis am Linkpfad darf nie entfernt werden.

    Sonst wuerde der Fix Nutzerdaten vernichten.
    """
    from services.storage_provenance.layout import create_directory_link

    link = tmp_path / "verknuepfung"
    link.mkdir()
    (link / "wichtig.txt").write_text("nicht loeschen", encoding="utf-8")

    ziel = tmp_path / "ziel"
    ziel.mkdir()

    create_directory_link(link, ziel)

    assert (link / "wichtig.txt").is_file(), (
        "B-809: ein echtes Verzeichnis wurde angetastet — Datenverlust."
    )
