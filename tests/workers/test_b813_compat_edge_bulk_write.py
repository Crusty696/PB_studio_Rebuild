"""B-813: Compat-Graph-Kanten wurden einzeln geschrieben — stumm und quadratisch.

Befund (2026-08-12, Klassensuche nach stummen Langlaeufern nach B-810):
``StructureEnrichmentWorker._do_enrich`` schrieb zwischen
``progress.emit(80, "Compat-Graph aufbauen …")`` und ``progress.emit(95, …)``
JEDE Kante mit einem eigenen ``session.execute``. ``CompatGraphBuilder`` liefert
top_k=20 Kanten je Szene in beide Richtungen — bei einer Bibliothek der
Groessenordnung 486 Clips a ~20 Szenen sechsstellig viele Einzel-Rundreisen,
waehrend die Anzeige unveraendert auf 80 % stand.

Der inkrementelle Zweig war zusaetzlich quadratisch: pro Szene EIN
``DELETE ... WHERE scene_id_a = :sid OR scene_id_b = :sid``. Das OR ueber zwei
Spalten kann keinen Index nutzen -> ein voller Tabellen-Scan je Szene.

Beweis ist der Zaehltest (wie oft wird die DB angefasst?), nicht die Stoppuhr.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from services.enrichment.compat_graph_builder import CompatEdge
from workers.structure_enrichment import write_compat_edges


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE struct_compat_edge ("
                " scene_id_a INTEGER NOT NULL,"
                " scene_id_b INTEGER NOT NULL,"
                " cosine_similarity REAL,"
                " rank_in_a INTEGER,"
                " PRIMARY KEY (scene_id_a, scene_id_b))"
            )
        )
    with Session(engine) as s:
        s.info["engine"] = engine
        yield s


def _count(session):
    box = {"n": 0}
    engine = session.info["engine"]

    def _on_exec(conn, cursor, statement, parameters, context, executemany):
        box["n"] += 1

    event.listen(engine, "before_cursor_execute", _on_exec)
    box["stop"] = lambda: event.remove(engine, "before_cursor_execute", _on_exec)
    return box


def _edges(n_scenes: int, top_k: int = 20) -> list[CompatEdge]:
    """Kanten wie CompatGraphBuilder sie liefert: top_k je Szene, beide Richtungen."""
    out = []
    for a in range(1, n_scenes + 1):
        for rank in range(1, top_k + 1):
            b = ((a + rank - 1) % n_scenes) + 1
            if b == a:
                continue
            out.append(CompatEdge(a, b, 0.9 - rank / 100.0, rank))
    return out


def test_write_count_does_not_grow_per_edge(session):
    """Kernbeweis: 10x so viele Kanten duerfen NICHT 10x so viele DB-Aufrufe kosten."""
    small = _edges(10)
    big = _edges(100)
    assert len(big) > 8 * len(small)

    counter = _count(session)
    write_compat_edges(session, small, this_clip_scene_ids=set(), full_library=True)
    n_small = counter["n"]
    counter["stop"]()

    counter = _count(session)
    write_compat_edges(session, big, this_clip_scene_ids=set(), full_library=True)
    n_big = counter["n"]
    counter["stop"]()

    assert n_big <= n_small + 1, (
        f"{len(small)} Kanten kosteten {n_small} DB-Aufrufe, {len(big)} Kanten "
        f"{n_big}. Es wird weiter pro Kante geschrieben."
    )
    assert n_big < 10, f"Erwartet wenige Sammel-Aufrufe, waren {n_big}."


def test_incremental_delete_is_one_statement(session):
    """Gegen den quadratischen Zweig: EIN DELETE fuer alle Szenen des Clips."""
    edges = _edges(60)
    write_compat_edges(session, edges, this_clip_scene_ids=set(), full_library=True)

    target = set(range(1, 41))  # 40 Szenen

    counter = _count(session)
    write_compat_edges(
        session, edges, this_clip_scene_ids=target, full_library=False
    )
    n = counter["n"]
    counter["stop"]()

    assert n <= 3, (
        f"{len(target)} Szenen erzeugten {n} DB-Aufrufe. Erwartet: 1 DELETE + "
        "wenige executemany-Bloecke, nicht ein DELETE je Szene."
    )


def test_written_rows_are_identical_to_per_row_write(session):
    """Gleichheitsprobe: Sammel-Schreiben muss dieselben Zeilen erzeugen wie
    das frueher zeilenweise Schreiben."""
    edges = _edges(30)

    write_compat_edges(session, edges, this_clip_scene_ids=set(), full_library=True)
    bulk = set(
        session.execute(
            text(
                "SELECT scene_id_a, scene_id_b, cosine_similarity, rank_in_a "
                "FROM struct_compat_edge"
            )
        ).all()
    )

    session.execute(text("DELETE FROM struct_compat_edge"))
    for e in edges:  # exakt der alte Pfad
        session.execute(
            text(
                "INSERT OR REPLACE INTO struct_compat_edge "
                "(scene_id_a, scene_id_b, cosine_similarity, rank_in_a) "
                "VALUES (:a, :b, :sim, :rank)"
            ),
            {"a": e.scene_id_a, "b": e.scene_id_b,
             "sim": e.cosine_similarity, "rank": e.rank_in_a},
        )
    per_row = set(
        session.execute(
            text(
                "SELECT scene_id_a, scene_id_b, cosine_similarity, rank_in_a "
                "FROM struct_compat_edge"
            )
        ).all()
    )

    assert bulk, "Sammel-Schreiben hat gar nichts geschrieben."
    assert bulk == per_row, "Sammel-Schreiben erzeugt andere Zeilen als der alte Pfad."


def test_incremental_delete_removes_the_same_rows(session):
    """Ein DELETE mit IN muss genau die Kanten treffen, die der alte
    Pro-Szene-DELETE getroffen haette (beide Richtungen)."""
    edges = _edges(30)
    target = {1, 2, 3}

    write_compat_edges(session, edges, this_clip_scene_ids=set(), full_library=True)
    write_compat_edges(session, [], this_clip_scene_ids=target, full_library=False)
    rest = session.execute(
        text("SELECT scene_id_a, scene_id_b FROM struct_compat_edge")
    ).all()

    assert rest, "Es wurden ALLE Kanten geloescht, nicht nur die des Clips."
    assert not [
        r for r in rest if r[0] in target or r[1] in target
    ], "Kanten der Ziel-Szenen blieben stehen."


def test_progress_is_reported_while_writing(session):
    """Der eigentliche Schaden war die Stille: es muss waehrenddessen melden."""
    seen: list[tuple[int, str]] = []
    write_compat_edges(
        session,
        _edges(400),  # ~8000 Kanten -> mehrere Bloecke
        this_clip_scene_ids=set(),
        full_library=True,
        progress=lambda pct, msg: seen.append((pct, msg)),
    )

    assert len(seen) >= 2, (
        f"Nur {len(seen)} Fortschrittsmeldung(en) waehrend des Schreibens — "
        "der Block bleibt fuer den Nutzer stumm."
    )
    assert all(80 <= pct <= 95 for pct, _ in seen)
    assert seen[-1][0] >= seen[0][0]
