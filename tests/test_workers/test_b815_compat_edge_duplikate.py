"""B-815: der Compat-Graph sammelte doppelte Raenge an.

An der echten Projekt-DB belegt (440 Szenen / 366 Clips): **9054 statt 8800
Kanten**, 20 Szenen mit Grad 31-35 statt der erwarteten 20, und **259 doppelte
`(scene_id_a, rank_in_a)`**.

Ursache: ``write_compat_edges`` loescht im Nicht-Full-Library-Modus nur Kanten,
die eine Szene des gerade verarbeiteten Clips beruehren. Geschrieben werden
aber auch **Rueckwaertskanten**, deren Quellszene eine *fremde* Szene ist
(fremd -> Clip-Szene). Von deren altem Kantensatz wird nur die eine Kante zur
Clip-Szene entfernt — die uebrigen bleiben stehen. Die fremde Szene bekommt
damit neue Raenge 1..20 **zusaetzlich** zu ihren alten: zwei Rangfolgen
vermischt.

Das ist Bestandsverhalten und aelter als B-813.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@dataclass
class _Kante:
    scene_id_a: int
    scene_id_b: int
    cosine_similarity: float
    rank_in_a: int


@pytest.fixture()
def session():
    eng = create_engine("sqlite://")
    with eng.connect() as c:
        c.execute(text(
            "CREATE TABLE struct_compat_edge ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " scene_id_a INTEGER, scene_id_b INTEGER,"
            " cosine_similarity REAL, rank_in_a INTEGER)"
        ))
        c.commit()
    with Session(eng) as s:
        yield s


def _bestand(session, kanten):
    for k in kanten:
        session.execute(
            text("INSERT INTO struct_compat_edge "
                 "(scene_id_a, scene_id_b, cosine_similarity, rank_in_a) "
                 "VALUES (:a, :b, :sim, :r)"),
            {"a": k.scene_id_a, "b": k.scene_id_b,
             "sim": k.cosine_similarity, "r": k.rank_in_a},
        )
    session.commit()


def test_b815_fremde_quellszene_behaelt_keine_alten_raenge(session):
    """Der Kern: Szene 99 darf nach dem Schreiben nicht zwei Rang-1 haben."""
    from workers.structure_enrichment import write_compat_edges

    # Bestand: fremde Szene 99 hat bereits drei Kanten mit Rang 1,2,3.
    _bestand(session, [
        _Kante(99, 50, 0.9, 1),
        _Kante(99, 51, 0.8, 2),
        _Kante(99, 52, 0.7, 3),
    ])

    # Neuer Lauf fuer Clip-Szene 10: Rueckwaertskante 99 -> 10 mit Rang 1.
    write_compat_edges(
        session,
        [_Kante(10, 99, 0.95, 1), _Kante(99, 10, 0.95, 1)],
        this_clip_scene_ids={10},
        full_library=False,
    )
    session.commit()

    doppelt = session.execute(text(
        "SELECT scene_id_a, rank_in_a, COUNT(*) c FROM struct_compat_edge "
        "GROUP BY scene_id_a, rank_in_a HAVING c > 1"
    )).fetchall()
    assert not doppelt, (
        f"B-815: doppelte (scene_id_a, rank_in_a) nach dem Schreiben: {doppelt} "
        "— zwei Rangfolgen derselben Quellszene vermischt."
    )


def test_b815_grad_bleibt_bei_der_neuen_rangfolge(session):
    """Die fremde Quellszene darf nur ihre NEUEN Kanten behalten."""
    from workers.structure_enrichment import write_compat_edges

    _bestand(session, [
        _Kante(99, 50, 0.9, 1),
        _Kante(99, 51, 0.8, 2),
        _Kante(99, 52, 0.7, 3),
    ])

    write_compat_edges(
        session,
        [_Kante(10, 99, 0.95, 1), _Kante(99, 10, 0.95, 1)],
        this_clip_scene_ids={10},
        full_library=False,
    )
    session.commit()

    grad = session.execute(text(
        "SELECT COUNT(*) FROM struct_compat_edge WHERE scene_id_a = 99"
    )).scalar()
    assert grad == 1, (
        f"B-815: Szene 99 hat Grad {grad} statt 1 — die alten Kanten der "
        "fremden Quellszene wurden nicht entfernt."
    )


def test_b815_unbeteiligte_szenen_bleiben_unberuehrt(session):
    """Grenze: wer nicht neu geschrieben wird, darf nicht geloescht werden."""
    from workers.structure_enrichment import write_compat_edges

    _bestand(session, [
        _Kante(77, 60, 0.9, 1),
        _Kante(77, 61, 0.8, 2),
    ])

    write_compat_edges(
        session,
        [_Kante(10, 99, 0.95, 1), _Kante(99, 10, 0.95, 1)],
        this_clip_scene_ids={10},
        full_library=False,
    )
    session.commit()

    unbeteiligt = session.execute(text(
        "SELECT COUNT(*) FROM struct_compat_edge WHERE scene_id_a = 77"
    )).scalar()
    assert unbeteiligt == 2, (
        "B-815: Kanten einer voellig unbeteiligten Szene wurden mitgeloescht."
    )


def test_b815_full_library_unveraendert(session):
    """Der Full-Library-Pfad raeumt ohnehin alles ab — nicht antasten."""
    from workers.structure_enrichment import write_compat_edges

    _bestand(session, [_Kante(1, 2, 0.5, 1), _Kante(3, 4, 0.5, 1)])

    write_compat_edges(
        session, [_Kante(5, 6, 0.9, 1)],
        this_clip_scene_ids=set(), full_library=True,
    )
    session.commit()

    zeilen = session.execute(
        text("SELECT scene_id_a FROM struct_compat_edge")
    ).fetchall()
    assert [z[0] for z in zeilen] == [5]
