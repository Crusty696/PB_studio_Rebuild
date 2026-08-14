"""B-815: der inkrementelle Compat-Graph muss zum Full-Rebuild konvergieren.

Erste Runde des Bugs: fremde Quellszenen sammelten zwei Rangfolgen an — Grad
31-35 statt 20, 259 doppelte `(scene_id_a, rank_in_a)`. Der Fix `b582e3e`
loescht seitdem den kompletten alten Kantensatz jeder fremden Quellszene.

Zurueckgeschrieben wurde davon aber nur die eine Kante zur Clip-Szene, denn
der Insert-Filter blieb unveraendert. Aus dem Ueberschuss wurde damit ein
Verlust: dieselben Szenen standen danach mit Grad 1 statt 20 da. Ein
Konsument, der "Top-N ueber rank_in_a" liest, bekam dort einen Nachbarn statt
zwanzig.

Beide Richtungen faengt nur eine Assertion auf den Grad JEDER Quellszene —
und am staerksten die Konvergenz-Assertion: nach beliebig vielen
inkrementellen Laeufen muss dieselbe Zeilenmenge dastehen wie nach einem
Full-Rebuild mit denselben Kanten. Ein einzelner inkrementeller Lauf zeigt
den Defekt nicht; es braucht zwei aufeinanderfolgende.

Das Schema hier entspricht der echten Migration
`2026_04_23_b5d5adc80d3a_add_struct_layer_tables.py`: PK ist
`(scene_id_a, scene_id_b)`, es gibt keine `id`-Spalte. Eine Fixture mit
AUTOINCREMENT-`id` wuerde Doppelpaare zulassen, die die echte DB abweist.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from workers.structure_enrichment import write_compat_edges

_K = 5
_CLIPS = [
    {1, 2, 3, 4, 5},
    {6, 7, 8, 9, 10},
    {11, 12, 13, 14, 15},
    {16, 17, 18, 19, 20},
]
_ALLE = sorted(s for clip in _CLIPS for s in clip)


@dataclass(frozen=True)
class _Edge:
    scene_id_a: int
    scene_id_b: int
    cosine_similarity: float
    rank_in_a: int


def _voller_graph() -> list[_Edge]:
    """Deterministischer Top-K-Graph ueber alle 20 Szenen.

    Nachbarn jeder Szene sind die K folgenden im Ring — damit beruehrt jeder
    Clip zwangslaeufig fremde Quellszenen, genau der Fall aus dem Bugreport.
    """
    edges: list[_Edge] = []
    n = len(_ALLE)
    for i, a in enumerate(_ALLE):
        for rang in range(1, _K + 1):
            b = _ALLE[(i + rang) % n]
            edges.append(_Edge(a, b, 1.0 - rang / 100.0, rang))
    return edges


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'compat.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE struct_compat_edge ("
            " scene_id_a INTEGER NOT NULL,"
            " scene_id_b INTEGER NOT NULL,"
            " cosine_similarity REAL,"
            " rank_in_a INTEGER,"
            " PRIMARY KEY (scene_id_a, scene_id_b)"
            ")"
        ))
    with Session(engine) as s:
        yield s
    engine.dispose()


def _grade(session) -> dict[int, int]:
    rows = session.execute(text(
        "SELECT scene_id_a, COUNT(*) FROM struct_compat_edge GROUP BY scene_id_a"
    )).all()
    return {int(a): int(n) for a, n in rows}


def _rang_duplikate(session) -> list[tuple[int, int, int]]:
    rows = session.execute(text(
        "SELECT scene_id_a, rank_in_a, COUNT(*) FROM struct_compat_edge "
        "GROUP BY scene_id_a, rank_in_a HAVING COUNT(*) > 1"
    )).all()
    return [(int(a), int(r), int(n)) for a, r, n in rows]


def _zeilen(session) -> set[tuple[int, int, int]]:
    rows = session.execute(text(
        "SELECT scene_id_a, scene_id_b, rank_in_a FROM struct_compat_edge"
    )).all()
    return {(int(a), int(b), int(r)) for a, b, r in rows}


def test_b815_zwei_inkrementelle_laeufe_halten_jeden_grad(session):
    """Faengt beide Fehlerrichtungen: Ueberschuss UND Verlust."""
    edges = _voller_graph()
    write_compat_edges(session, edges, this_clip_scene_ids=set(), full_library=True)
    session.commit()

    for clip in _CLIPS[:2]:
        write_compat_edges(session, edges, this_clip_scene_ids=clip, full_library=False)
        session.commit()

    grade = _grade(session)
    assert set(grade) == set(_ALLE), (
        f"Quellszenen fehlen komplett: {sorted(set(_ALLE) - set(grade))}"
    )
    abweichend = {a: g for a, g in grade.items() if g != _K}
    assert not abweichend, (
        f"B-815: Grad weicht von K={_K} ab — {abweichend}. "
        "Zu klein heisst, dass geloeschte Kanten fremder Quellszenen nicht "
        "zurueckgeschrieben werden; zu gross heisst, dass sich zwei "
        "Rangfolgen mischen."
    )


def test_b815_keine_doppelten_raenge(session):
    edges = _voller_graph()
    write_compat_edges(session, edges, this_clip_scene_ids=set(), full_library=True)
    session.commit()
    for clip in _CLIPS[:2]:
        write_compat_edges(session, edges, this_clip_scene_ids=clip, full_library=False)
        session.commit()

    dup = _rang_duplikate(session)
    assert not dup, f"B-815: doppelte (scene_id_a, rank_in_a): {dup}"


def test_b815_inkrementell_konvergiert_gegen_full_rebuild(session, tmp_path):
    """Die staerkste Zusage: gleiches Ergebnis, egal auf welchem Weg."""
    edges = _voller_graph()

    write_compat_edges(session, edges, this_clip_scene_ids=set(), full_library=True)
    session.commit()
    for clip in _CLIPS:
        write_compat_edges(session, edges, this_clip_scene_ids=clip, full_library=False)
        session.commit()
    inkrementell = _zeilen(session)

    session.execute(text("DELETE FROM struct_compat_edge"))
    session.commit()
    write_compat_edges(session, edges, this_clip_scene_ids=set(), full_library=True)
    session.commit()
    voll = _zeilen(session)

    fehlend = voll - inkrementell
    zuviel = inkrementell - voll
    assert not fehlend and not zuviel, (
        f"B-815: inkrementell weicht vom Full-Rebuild ab — "
        f"{len(fehlend)} Kanten fehlen, {len(zuviel)} zu viel. "
        f"Beispiel fehlend: {sorted(fehlend)[:3]}"
    )


def test_b815_unberuehrte_szene_bleibt_unveraendert(session):
    """Ein inkrementeller Lauf darf nur anfassen, was er anfassen muss."""
    edges = _voller_graph()
    write_compat_edges(session, edges, this_clip_scene_ids=set(), full_library=True)
    session.commit()

    # Szene 13 liegt in Clip 3 und ist weder Quelle noch Ziel von Clip 1.
    unbeteiligt = {
        z for z in _zeilen(session)
        if z[0] == 13 and z[1] not in _CLIPS[0]
    }
    assert unbeteiligt, "Testaufbau: Szene 13 braucht Kanten ausserhalb von Clip 1"

    write_compat_edges(session, edges, this_clip_scene_ids=_CLIPS[0], full_library=False)
    session.commit()

    danach = {z for z in _zeilen(session) if z[0] == 13 and z[1] not in _CLIPS[0]}
    assert danach == unbeteiligt, (
        "B-815: Kanten einer unbeteiligten Quellszene wurden veraendert"
    )
