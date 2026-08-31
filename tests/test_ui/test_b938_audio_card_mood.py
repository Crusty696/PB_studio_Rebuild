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


# ── B-947: Genre wurde durchgereicht, aber nie gezeichnet ─────────────────

def test_genre_erscheint_auf_der_karte(qapp):
    """B-938 reichte das Genre durch, B-947 zeigt es an.

    Die Selbstpruefung am 2026-08-31 fand, dass mein eigener B-938-Commit
    ("Mood und Genre erreichen die Audio-Kachel") nur zur Haelfte stimmte:
    ``_genre`` wurde gesetzt und nirgends gerendert.
    """
    from PySide6.QtWidgets import QLabel

    mit = AudioCard(media_id=10, title="A", file_path="a.mp3", genre="techno")
    ohne = AudioCard(media_id=11, title="A", file_path="a.mp3")

    assert "techno" in {w.text() for w in mit.findChildren(QLabel)}
    assert "techno" not in {w.text() for w in ohne.findChildren(QLabel)}


def test_mood_und_genre_stehen_nebeneinander(qapp):
    from PySide6.QtWidgets import QLabel

    karte = AudioCard(media_id=12, title="A", file_path="a.mp3",
                      bpm=128.0, key="Am", mood="dark", genre="techno")

    texte = {w.text() for w in karte.findChildren(QLabel)}

    assert {"128", "BPM", "Am", "dark", "techno"} <= texte
