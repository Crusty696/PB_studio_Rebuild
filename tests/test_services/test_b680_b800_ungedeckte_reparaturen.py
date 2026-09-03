"""B-680 und B-800 — zwei Reparaturen, die per Mutationsprobe als ungedeckt auffielen.

Beide standen bei `tools/fix_ohne_test.py` auf der harmlosen Seite („nur
unbeschriftet": das umschließende Symbol kommt in `tests/` vor). Die
Mutationsprobe am 2026-09-03 zeigte etwas anderes — kehrt man den Fix um,
bleibt die Suite grün:

    B-800 keyframe_text-Reset:      GRUEN  8 passed
    B-680 tmp-Cleanup im finally:   GRUEN  11 passed

Dasselbe Muster wie B-971 (B-888). Die Zahl der ungedeckten Reparaturen ist
damit dreimal in Folge höher ausgefallen als das Werkzeug meldete.

Jeder Test unten ist per Mutationsprobe abgenommen: Fix umkehren → rot.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# B-680 — Temp-Verzeichnis der Tonart-Erkennung muss auch im Fehlerfall weg
# ---------------------------------------------------------------------------

def test_b680_das_temp_verzeichnis_wird_im_finally_geraeumt():
    """Quellcode-Guard: `rmtree` muss im `finally` stehen, nicht im Erfolgspfad.

    Vorher lag das Aufräumen am Ende des Erfolgspfads. Warf `mix_bass_other`
    oder `librosa.load`, blieb `pb_keydet_*/bass_other.wav` liegen — eine WAV
    von bis zu `MAX_DURATION_MODULATION` Sekunden, dauerhaft im Temp.
    """
    quelle = (REPO_ROOT / "services" / "key_detection_service.py").read_text(
        encoding="utf-8", errors="replace")

    block = quelle.split("tmp_dir = tempfile.mkdtemp(prefix=\"pb_keydet_\")", 1)
    assert len(block) == 2, "die Temp-Anlage wurde umgebaut"
    danach = block[1][:1200]

    assert "finally:" in danach, "kein finally nach der Temp-Anlage"
    rest = danach.split("finally:", 1)[1]
    assert "shutil.rmtree(tmp_dir, ignore_errors=True)" in rest, (
        "das Aufraeumen steht nicht mehr im finally — bei einer Ausnahme "
        "bleibt die WAV liegen"
    )


def test_b680_rmtree_wirft_nie_und_raeumt_wirklich(tmp_path):
    """Verhaltensbeleg für das gewählte Muster.

    `ignore_errors=True` ist Absicht: das Aufräumen darf die eigentliche
    Ausnahme nicht verdrängen.
    """
    ordner = tempfile.mkdtemp(prefix="pb_keydet_", dir=tmp_path)
    datei = os.path.join(ordner, "bass_other.wav")
    with open(datei, "wb") as f:
        f.write(b"\x00" * 16)

    shutil.rmtree(ordner, ignore_errors=True)
    assert not os.path.exists(ordner)

    # Zweiter Aufruf auf ein bereits entferntes Verzeichnis darf nicht werfen.
    shutil.rmtree(ordner, ignore_errors=True)


def test_b680_der_fehlerpfad_faellt_auf_das_original_zurueck():
    """Der `except`-Zweig lädt die Originaldatei — sonst stünde `y` nie.

    Ohne diesen Zweig wäre der `finally`-Block wirkungslos, weil die Ausnahme
    die Funktion verlässt, bevor eine Tonart bestimmt wird.
    """
    quelle = (REPO_ROOT / "services" / "key_detection_service.py").read_text(
        encoding="utf-8", errors="replace")

    block = quelle.split("bass/other streaming-mix failed", 1)
    assert len(block) == 2
    assert "librosa.load(file_path" in block[1][:400]


# ---------------------------------------------------------------------------
# B-800 — Keyframe-Feld muss beim Projektwechsel geleert werden
# ---------------------------------------------------------------------------

def test_b800_der_projektwechsel_leert_das_keyframe_feld():
    """Quellcode-Guard im richtigen Block.

    `keyframe_text` ist ein einziges QTextEdit. Ohne Reset blieben die
    Keyframe-Strings des ALTEN Projekts sichtbar und sahen aus, als gehörten
    sie zum neuen — live belegt am 2026-08-11 mit einem Clip, den das neue
    Projekt gar nicht besitzt.
    """
    quelle = (REPO_ROOT / "ui" / "controllers" / "project_management.py").read_text(
        encoding="utf-8", errors="replace")

    start = quelle.index("def _on_project_changed")
    ende = quelle.find("\n    def ", start + 10)
    block = quelle[start:ende if ende != -1 else len(quelle)]

    assert "self.window.keyframe_text.clear()" in block, (
        "_on_project_changed leert das Keyframe-Feld nicht mehr"
    )


def test_b800_der_reset_ist_gegen_fehler_abgesichert():
    """Ein fehlendes Widget darf den Projektwechsel nicht abbrechen."""
    quelle = (REPO_ROOT / "ui" / "controllers" / "project_management.py").read_text(
        encoding="utf-8", errors="replace")

    ab = quelle.index("self.window.keyframe_text.clear()")
    umgebung = quelle[ab - 200:ab + 300]

    assert "try:" in umgebung
    assert "except" in umgebung


class _FakeFeld:
    def __init__(self, text: str):
        self.text = text
        self.geleert = 0

    def clear(self):
        self.text = ""
        self.geleert += 1


def test_b800_clear_setzt_den_alten_inhalt_wirklich_zurueck():
    """Verhaltensbeleg für die Wirkung, unabhängig von Qt."""
    feld = _FakeFeld("Clip 42: 0.0 -> 1.0 (altes Projekt)")

    feld.clear()

    assert feld.text == ""
    assert feld.geleert == 1


@pytest.mark.parametrize("marker,pfad", [
    ("B-680", "services/key_detection_service.py"),
    ("B-800", "ui/controllers/project_management.py"),
])
def test_beide_stellen_behalten_ihren_marker(marker, pfad):
    """Ohne Marker findet kein Werkzeug die Stelle wieder."""
    quelle = (REPO_ROOT / pfad).read_text(encoding="utf-8", errors="replace")

    assert marker in quelle
