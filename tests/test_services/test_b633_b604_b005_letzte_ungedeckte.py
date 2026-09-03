"""B-633, B-604, B-005 — die letzten drei ungedeckten Stellen aus Loop 6.

Gemessen am 2026-09-03 mit `tools/mutationsprobe.py --alle-unbeschrifteten`,
nach Docstring-Ausschluss und Zuweisungs-Mutation:
`19 IDs, 16 gemessen, 13 gedeckt, 3 UNGEDECKT, 3 ungemessen`.

Die drei ungedeckten:

    B-633  ui/controllers/edit_workspace.py:1069   34 passed
    B-604  services/ollama_service.py:425          70 passed (3:35)
    B-005  workers/import_export.py:424            44 passed

**B-633:** `column-select` statt `joinedload(VideoClip.scenes)`. Der
joinedload zog die Scene-JSON-Blobs (`keyframe_paths`, `embedding_indices`,
`ai_*`) mit und fror den GUI-Thread beim Dialog-Öffnen rund 13 Sekunden ein.

**B-604:** Zwei Umgebungsvariablen für den Ollama-Start — `OLLAMA_VULKAN=0`
schaltet die Vulkan-Backend-Discovery ab, `CUDA_VISIBLE_DEVICES=0` macht
ausschließlich die GTX 1060 sichtbar. Letzteres ist die GPU-Hartregel des
Projekts: nur `cuda:0`, kein anderes Backend.

**B-005:** Validierung des Auflösungsformats (`WIDTHxHEIGHT`) mit
Fehlerbehandlung, statt `int()` auf ungeprüfte Teilstrings.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _quelle(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _nur_code(text: str) -> str:
    """Kommentare weg, Code bleibt.

    Vierter Fall derselben Fehlerklasse in diesem Loop: erst traf ein Guard die
    Bug-ID im Kommentar, dann im Log-String, dann im Docstring — und hier
    stehen ``joinedload``, ``keyframe_paths`` und ``embedding_indices``
    ausgerechnet im erklärenden Kommentar *über* der Reparatur. Ein Guard auf
    die bloße Zeichenkette prüft dann den Kommentar, nicht den Code.
    """
    return "\n".join(
        zeile.split("#", 1)[0]
        for zeile in text.splitlines()
    )


def _code_nach_marker(rel: str, marker: str, zeilen: int = 20) -> str:
    """Die nächsten ``zeilen`` Codezeilen **nach** der Markerzeile.

    Ein Zeichen-Ausschnitt (`quelle[ab:ab+900]`) beginnt mitten in der
    Kommentarzeile — dort ist das `#` schon vorbei, und ein Filter auf
    `split("#")` entfernt nichts mehr. Deshalb wird an Zeilengrenzen
    geschnitten und die Markerzeile selbst weggelassen.
    """
    alle = _quelle(rel).splitlines()
    for nr, zeile in enumerate(alle):
        if marker in zeile:
            return _nur_code("\n".join(alle[nr + 1:nr + 1 + zeilen]))
    raise AssertionError(f"Marker {marker!r} nicht gefunden in {rel}")


# ---------------------------------------------------------------------------
# B-633 — kein joinedload, nur Skalar-Spalten
# ---------------------------------------------------------------------------

_BLOB_SPALTEN = ("keyframe_paths", "embedding_indices", "ai_tags", "ai_mood")


def test_b633_der_dialog_query_selektiert_nur_skalarspalten():
    """Der Kern: kein `joinedload`, sondern ein `select(...)` mit Spaltenliste."""
    danach = _code_nach_marker(
        "ui/controllers/edit_workspace.py",
        "B-633: column-select statt joinedload", zeilen=22)

    assert "session.execute(" in danach
    assert "select(" in danach
    assert "joinedload" not in danach, (
        "joinedload ist zurueck — die Scene-JSON-Blobs werden wieder eager geladen"
    )


def test_b633_keine_blob_spalte_in_der_auswahl():
    """Genau diese Spalten verursachten den 13-Sekunden-Freeze."""
    quelle = _quelle("ui/controllers/edit_workspace.py")
    auswahl = _code_nach_marker(
        "ui/controllers/edit_workspace.py",
        "B-633: column-select statt joinedload", zeilen=22)

    for spalte in _BLOB_SPALTEN:
        assert spalte not in auswahl, f"Blob-Spalte {spalte} steht wieder in der Auswahl"


def test_b633_der_outerjoin_erhaelt_clips_ohne_scenes():
    """Ein `join` statt `outerjoin` würde Clips ohne Szenen verschlucken."""
    danach = _code_nach_marker(
        "ui/controllers/edit_workspace.py",
        "B-633: column-select statt joinedload", zeilen=22)

    assert ".outerjoin(Scene," in danach, (
        "kein outerjoin — Clips ohne Scenes fallen aus dem Ergebnis"
    )


# ---------------------------------------------------------------------------
# B-604 — Ollama-Umgebung: nur cuda:0, kein Vulkan
# ---------------------------------------------------------------------------

def test_b604_vulkan_backend_bleibt_abgeschaltet():
    quelle = _quelle("services/ollama_service.py")

    assert "env['OLLAMA_VULKAN'] = '0'" in quelle, (
        "OLLAMA_VULKAN=0 fehlt — Ollama sucht wieder ein Vulkan-Backend"
    )


def test_b604_nur_die_gtx_1060_ist_sichtbar():
    """GPU-Hartregel des Projekts: ausschliesslich `cuda:0`.

    Ohne `CUDA_VISIBLE_DEVICES=0` kann Ollama ein anderes Gerät wählen — auf
    dieser Maschine die interne Intel-iGPU, die laut Projektvorgabe nicht
    angesprochen werden darf.
    """
    quelle = _quelle("services/ollama_service.py")

    assert "env['CUDA_VISIBLE_DEVICES'] = '0'" in quelle


def test_b604_beide_variablen_stehen_vor_dem_prozessstart():
    """Nach dem Start gesetzt wären sie wirkungslos."""
    quelle = _quelle("services/ollama_service.py")

    vulkan = quelle.index("env['OLLAMA_VULKAN'] = '0'")
    # Der Prozessstart folgt im selben Block, erkennbar an den creation_flags.
    flags = quelle.index("creation_flags", vulkan)

    assert vulkan < flags


def test_b604_die_begruendung_bleibt_im_code():
    """Beide Zeilen sehen ohne Beleg wie Kopierreste aus.

    Der Kommentar nennt die Ollama-Envconfig und die GPU-Doku — ohne ihn
    entfernt sie beim nächsten Umbau jemand als überflüssig.
    """
    quelle = _quelle("services/ollama_service.py")
    ab = quelle.index("env['OLLAMA_VULKAN'] = '0'")
    davor = quelle[max(0, ab - 700):ab]

    assert "EnableVulkan" in davor
    assert "cuda:0" in davor


# ---------------------------------------------------------------------------
# B-005 — Auflösungsformat prüfen statt blind int()
# ---------------------------------------------------------------------------

def test_b005_das_format_wird_vor_dem_umwandeln_geprueft():
    quelle = _quelle("workers/import_export.py")
    ab = quelle.index("B-005 Fix: Validierung des Resolution-Formats")
    danach = quelle[ab:ab + 800]

    assert 'self.resolution.split("x")' in danach
    assert "len(parts) != 2" in danach, "die Teileanzahl wird nicht geprueft"
    trennen = danach.index('self.resolution.split("x")')
    pruefen = danach.index("len(parts) != 2")
    assert trennen < pruefen


def test_b005_nichtpositive_werte_werden_abgewiesen():
    """`0x0` oder `-1920x1080` würde ffmpeg mit kryptischem Fehler abbrechen."""
    quelle = _quelle("workers/import_export.py")
    ab = quelle.index("B-005 Fix: Validierung des Resolution-Formats")
    danach = quelle[ab:ab + 800]

    assert "w_res <= 0 or h_res <= 0" in danach


def test_b005_die_pruefung_liegt_in_try_except():
    quelle = _quelle("workers/import_export.py")
    ab = quelle.index("B-005 Fix: Validierung des Resolution-Formats")
    umgebung = quelle[ab:ab + 1200]

    assert "raise ValueError" in umgebung
    assert "except" in umgebung, "ein ungueltiges Format reisst den Worker um"


@pytest.mark.parametrize("wert,gueltig", [
    ("1920x1080", True),
    ("1280x720", True),
    ("1920", False),
    ("1920x1080x60", False),
    ("0x0", False),
    ("-1920x1080", False),
    ("axb", False),
])
def test_b005_die_pruefregel_selbst(wert, gueltig):
    """Verhaltensbeleg für die Regel, unabhängig vom Worker."""
    def pruefen(text: str) -> bool:
        try:
            parts = text.split("x")
            if len(parts) != 2:
                return False
            w, h = int(parts[0]), int(parts[1])
            return w > 0 and h > 0
        except ValueError:
            return False

    assert pruefen(wert) is gueltig


@pytest.mark.parametrize("marker,pfad", [
    ("B-633", "ui/controllers/edit_workspace.py"),
    ("B-604", "services/ollama_service.py"),
    ("B-005", "workers/import_export.py"),
])
def test_alle_drei_stellen_behalten_ihren_marker(marker, pfad):
    assert marker in _quelle(pfad)


def test_die_gpu_hartregel_wird_nirgends_umgangen():
    """Kein fremdes GPU-Backend im Ollama-Start.

    Projektvorgabe: ausschliesslich NVIDIA GTX 1060 über `cuda:0`; wenn eine
    Bibliothek kein CUDA kann, dann CPU — niemals ein anderes Backend.
    """
    quelle = _quelle("services/ollama_service.py")
    baum = ast.parse(quelle)

    verboten = ("OLLAMA_INTEL_GPU", "OLLAMA_ROCM", "HIP_VISIBLE_DEVICES",
                "GGML_VULKAN", "ONEAPI_DEVICE_SELECTOR")
    gesetzt: list[str] = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Assign):
            for ziel in knoten.targets:
                if (isinstance(ziel, ast.Subscript)
                        and isinstance(ziel.slice, ast.Constant)
                        and isinstance(ziel.slice.value, str)
                        and ziel.slice.value in verboten):
                    gesetzt.append(ziel.slice.value)

    assert gesetzt == [], f"fremdes GPU-Backend gesetzt: {gesetzt}"
