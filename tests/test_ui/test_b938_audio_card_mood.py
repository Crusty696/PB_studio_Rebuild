"""B-938 — Mood und Genre erreichten die Audio-Kachel nie.

``AudioCard`` kennt ``mood``/``genre`` seit jeher (`media_grid.py:525-526`) und
zeigt die Stimmung als gruenes Label (`:568-569`). ``_create_card`` reichte
beide Werte aber nicht durch, obwohl die Analyse sie fuellt
(`ingest_service.py:441-442`) und Filter und Sortierung sie lesen
(`media_grid.py:1032`, `:1044-1046`). Die Anzeige war damit unerreichbar.
"""

import pytest

from ui.widgets.media_grid import AudioCard, MediaPoolGrid


@pytest.fixture
def grid(qapp):
    g = MediaPoolGrid("audio")
    yield g
    g.deleteLater()


def test_mood_und_genre_landen_auf_der_karte(grid):
    card = grid._create_card({
        "id": 1,
        "title": "Sub-Alot",
        "file_path": "sub-alot.mp3",
        "bpm": 124.0,
        "key": "Am",
        "mood": "dark",
        "genre": "techno",
    })

    assert isinstance(card, AudioCard)
    assert card._mood == "dark"
    assert card._genre == "techno"


def test_ohne_mood_bleibt_die_karte_leer_statt_zu_brechen(grid):
    card = grid._create_card({
        "id": 2,
        "title": "Ohne Analyse",
        "file_path": "roh.wav",
    })

    assert card._mood is None
    assert card._genre is None


def test_mood_erzeugt_ein_sichtbares_label(qapp):
    """Der Zweig bei media_grid.py:568 war vorher nie erreichbar."""
    from PySide6.QtWidgets import QLabel

    mit = AudioCard(media_id=3, title="A", file_path="a.mp3", mood="uplifting")
    ohne = AudioCard(media_id=4, title="A", file_path="a.mp3")

    texte_mit = {w.text() for w in mit.findChildren(QLabel)}
    texte_ohne = {w.text() for w in ohne.findChildren(QLabel)}

    assert "uplifting" in texte_mit
    assert "uplifting" not in texte_ohne
