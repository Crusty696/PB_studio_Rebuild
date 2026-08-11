"""B-803: Löschen eines Clips entfernt Timeline-Segmente — der User muss es erfahren.

Live-Verify 2026-08-11 (Runde 4): Beim Soft-Delete eines in der Timeline
verwendeten Clips fielen die Timeline-Einträge sofort von 6 auf 1 — ohne
Log-Marker, ohne Toast, ohne Anzahl. Die Schnittarbeit verschwand stillschweigend.

Das erklärt zugleich, warum die für B-580 erwartete Export-Warnung nie erschien:
zum Exportzeitpunkt ist die Timeline längst bereinigt, es gibt gar nichts mehr
zu überspringen. Der Fix saß an der falschen Stelle — nicht der Export ist der
Ort der Wahrheit, sondern der Löschvorgang.

Wichtig für die Einordnung: die Platzierung ist durch das M1-Backup (B-706)
gesichert und kehrt beim Wiederherstellen zurück. Es geht also nicht um
Datenverlust, sondern darum, dass der User das nicht weiß und seine Arbeit für
verloren hält.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from database import Project, TimelineEntry, VideoClip
from services import ingest_service


class _FakeVectorDB:
    """Muster aus tests/test_services/test_b706_m1_restore_timeline_placement.py.

    Ohne diesen Ersatz greift der Testschutz B-727 (Zugriff auf die echte
    embeddings.db wird blockiert) und der Soft-Delete rollt zurueck — der
    Test wuerde dann ein Problem melden, das gar nicht der Testgegenstand ist.
    """

    def delete_all(self):
        return None

    def delete_by_clip_ids(self, clip_ids):
        return None


@pytest.fixture(autouse=True)
def _fake_vectordb(monkeypatch):
    monkeypatch.setattr(ingest_service, "VectorDBService", _FakeVectorDB)


@pytest.fixture()
def projekt_mit_timeline(test_engine):
    """Ein Projekt mit einem Clip, der in mehreren Timeline-Segmenten liegt."""
    with Session(test_engine) as s:
        p = Project(name="B-803", path="/tmp/b803")
        s.add(p)
        s.commit()
        clip = VideoClip(file_path="/tmp/b803/clip.mp4", project_id=p.id)
        s.add(clip)
        s.commit()
        for i in range(6):
            s.add(TimelineEntry(
                project_id=p.id, track="video", media_id=clip.id,
                start_time=float(i * 5), end_time=float(i * 5 + 5),
            ))
        s.commit()
        return p.id, clip.id


def test_b803_meldet_entfernte_timeline_segmente(projekt_mit_timeline, test_engine):
    """Der Kern: die Anzahl entfernter Segmente muss gemeldet werden."""
    _pid, clip_id = projekt_mit_timeline
    gemeldet: list[int] = []

    ingest_service.delete_selected_media(
        [clip_id], [], on_timeline_removed=gemeldet.append,
    )

    assert gemeldet, (
        "B-803: das Loeschen entfernte Timeline-Segmente, ohne es zu melden — "
        "genau der stille Verlust aus dem Live-Verify."
    )
    assert gemeldet[0] == 6, f"erwartet 6 gemeldete Segmente, gemeldet: {gemeldet}"


def test_b803_segmente_sind_wirklich_weg(projekt_mit_timeline, test_engine):
    """Belegt die Grundlage der Meldung: die Eintraege verschwinden tatsaechlich."""
    pid, clip_id = projekt_mit_timeline
    with Session(test_engine) as s:
        vorher = s.query(TimelineEntry).filter_by(project_id=pid).count()
    assert vorher == 6

    ingest_service.delete_selected_media([clip_id], [])

    with Session(test_engine) as s:
        nachher = s.query(TimelineEntry).filter_by(project_id=pid).count()
    assert nachher == 0, (
        f"Timeline-Eintraege nach dem Loeschen: {nachher} (erwartet 0) — "
        "die Meldung muss zum tatsaechlichen Verhalten passen."
    )


def test_b803_ohne_timeline_keine_meldung(test_engine):
    """Kein Rauschen: ein Clip ohne Timeline-Nutzung meldet nichts."""
    with Session(test_engine) as s:
        p = Project(name="B-803-leer", path="/tmp/b803leer")
        s.add(p)
        s.commit()
        clip = VideoClip(file_path="/tmp/b803leer/clip.mp4", project_id=p.id)
        s.add(clip)
        s.commit()
        clip_id = clip.id

    gemeldet: list[int] = []
    ingest_service.delete_selected_media(
        [clip_id], [], on_timeline_removed=gemeldet.append,
    )

    assert gemeldet == [], (
        "B-803: es wurde eine Timeline-Meldung erzeugt, obwohl der Clip in "
        "keinem Segment lag."
    )


def test_b803_callback_ist_optional(projekt_mit_timeline, test_engine):
    """Bestehende Aufrufer duerfen unveraendert weiterlaufen."""
    _pid, clip_id = projekt_mit_timeline
    # Ohne on_timeline_removed — darf nicht werfen.
    ergebnis = ingest_service.delete_selected_media([clip_id], [])
    assert ergebnis >= 1


def test_b803_fehler_im_callback_kippt_das_loeschen_nicht(
    projekt_mit_timeline, test_engine,
):
    """Eine kaputte UI-Meldung darf den Loeschvorgang nicht scheitern lassen."""
    _pid, clip_id = projekt_mit_timeline

    def _kaputt(_n):
        raise RuntimeError("UI ist weg")

    ergebnis = ingest_service.delete_selected_media(
        [clip_id], [], on_timeline_removed=_kaputt,
    )

    assert ergebnis >= 1, (
        "B-803: eine fehlgeschlagene Meldung hat das Loeschen mitgerissen."
    )
