"""Die zwölf ungedeckten Stellen aus dem ersten gültigen Mutationsprobe-Lauf.

Gemessen am 2026-09-03 mit `tools/mutationsprobe.py --alle-unbeschrifteten`
(erster Lauf, der nach vier behobenen Messfehlern gültig war):
`17 gemessen, 5 gedeckt, 12 UNGEDECKT, 29 ungemessen`.

Jede der zwölf Zeilen unten stand im Bericht als UNGEDECKT — kehrt man den Fix
um, bleibt die Suite grün:

    B-657  ui/controllers/project_management.py:451   34 passed
    B-601  services/ai_audio_service.py:613           83 passed (9:10)
    B-601  services/ai_audio_service.py:806           83 passed (9:32)
    B-350  services/ingest_service.py:881             23 passed, 14 skipped
    B-252  ui/controllers/panel_setup.py:109          41 passed
    B-252  ui/controllers/panel_setup.py:168          41 passed
    B-011  services/task_manager.py:595              111 passed (7:49)
    B-011  services/task_manager.py:608              111 passed (5:41)
    B-011  workers/audio_analysis.py:46               45 passed, 9 skipped
    B-010  services/task_manager.py:198              111 passed (5:50)
    B-008  database/session.py:422                   190 passed (9:10)
    B-001  services/project_manager.py:516            62 passed

Die Tests sind Quellcode-Guards plus Verhaltensbelege dort, wo einer ohne
Qt-Fenster und ohne DB möglich ist. Ein Quellcode-Guard ist hier nicht die
faule Variante: bei allen zwölf besteht die Reparatur genau darin, dass eine
bestimmte Zeile an einer bestimmten Stelle steht (ein Lock, ein `finally`, ein
Null-Check, ein `hide()`). Fällt sie weg, ist der Schaden zurück — und
gemessen ist, dass kein Verhaltenstest der Suite das merkt.
"""

from __future__ import annotations

import ast
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _quelle(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _methode(rel: str, name: str, klasse: str | None = None) -> str:
    """Der Rumpf einer Methode, per AST abgegrenzt.

    ``klasse`` ist nötig, sobald mehrere Klassen derselben Datei eine Methode
    gleichen Namens haben. Ohne den Parameter gewann der erste ``__init__`` der
    Datei — und der gehörte in ``services/task_manager.py`` nicht zu
    ``GlobalTaskManager``.
    """
    quelle = _quelle(rel)
    baum = ast.parse(quelle)
    zeilen = quelle.splitlines()

    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.ClassDef):
            continue
        if klasse is not None and knoten.name != klasse:
            continue
        for element in knoten.body:
            if (isinstance(element, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and element.name == name):
                ende = getattr(element, "end_lineno", element.lineno)
                return "\n".join(zeilen[element.lineno - 1:ende])

    if klasse is None:
        for knoten in ast.walk(baum):
            if (isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and knoten.name == name):
                ende = getattr(knoten, "end_lineno", knoten.lineno)
                return "\n".join(zeilen[knoten.lineno - 1:ende])

    raise AssertionError(f"{klasse or ''}.{name} nicht gefunden in {rel}")


# ---------------------------------------------------------------------------
# B-011 — Lock schützt die Task-Tabelle
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("methode", ["update_task", "finish_task"])
def test_b011_der_dict_zugriff_steht_unter_dem_lock(methode):
    """Ohne Lock lief der dict-Zugriff aus mehreren Threads gleichzeitig."""
    rumpf = _methode("services/task_manager.py", methode, "GlobalTaskManager")

    assert "with self._tasks_lock:" in rumpf, (
        f"{methode} greift ohne Lock auf _tasks zu"
    )
    ab_lock = rumpf.index("with self._tasks_lock:")
    assert "self._tasks[" in rumpf[ab_lock:], (
        f"{methode}: der dict-Zugriff steht nicht innerhalb des Locks"
    )
    # Auch die Existenzprüfung gehört dazu. Ohne sie wirft der Zugriff bei
    # einem unbekannten Task-Key; die Mutationsprobe setzte genau diese
    # Bedingung auf `if False:` und 136 Tests liefen weiter durch.
    assert "if task_id in self._tasks:" in rumpf[ab_lock:], (
        f"{methode}: die Existenzpruefung im Lock fehlt"
    )


def test_b011_das_lock_wird_im_konstruktor_angelegt():
    rumpf = _methode("services/task_manager.py", "__init__", "GlobalTaskManager")

    assert "self._tasks_lock = threading.Lock()" in rumpf


def test_b011_ein_lock_serialisiert_zwei_threads_wirklich():
    """Verhaltensbeleg für das Muster, unabhängig vom TaskManager."""
    lock = threading.Lock()
    ablauf: list[str] = []

    def arbeiten(name: str):
        with lock:
            ablauf.append(f"{name}-start")
            ablauf.append(f"{name}-ende")

    t1 = threading.Thread(target=arbeiten, args=("a",))
    t2 = threading.Thread(target=arbeiten, args=("b",))
    t1.start(); t2.start(); t1.join(); t2.join()

    # Kein Verschränken: jedes start hat sein ende direkt dahinter.
    assert ablauf[0].endswith("-start") and ablauf[1].endswith("-ende")
    assert ablauf[2].endswith("-start") and ablauf[3].endswith("-ende")


def test_b011_der_audio_worker_ruft_super_init():
    """`CancellableMixin.__init__` setzt `_cancelled` und `_errored`.

    Ohne `super().__init__()` folgt der Konstruktor nicht der MRO und die
    Abbruch-Flags existieren nicht.
    """
    rumpf = _methode("workers/audio_analysis.py", "__init__", "BaseAnalysisWorker")

    # Nur Code, keine Kommentare. Der erklärende Kommentar direkt über dem
    # Aufruf nennt „super().__init__()" wörtlich — ein Guard auf die blosse
    # Zeichenkette bleibt deshalb grün, selbst wenn der Aufruf durch `pass`
    # ersetzt wird. Genau das ist am 2026-09-03 passiert: die Mutationsprobe
    # meldete die Stelle weiterhin als UNGEDECKT, obwohl dieser Test dafür da
    # war. Zweites Mal derselbe Fehler nach B-797.
    anweisungen = [
        z.split("#", 1)[0].strip()
        for z in rumpf.splitlines()
        if z.split("#", 1)[0].strip()
    ]

    assert "super().__init__()" in anweisungen, (
        f"kein echter super().__init__()-Aufruf, nur Kommentar: {anweisungen[:4]}"
    )


# ---------------------------------------------------------------------------
# B-010 — QApplication als Parent
# ---------------------------------------------------------------------------

def test_b010_der_taskmanager_haengt_an_der_qapplication():
    """Ohne Parent wird das QObject vom Garbage Collector eingesammelt."""
    rumpf = _methode("services/task_manager.py", "__init__", "GlobalTaskManager")

    assert "super().__init__(QApplication.instance())" in rumpf


# ---------------------------------------------------------------------------
# B-008 — dispose()-Fehler nicht schlucken
# ---------------------------------------------------------------------------

def test_b008_dispose_fehler_werden_geloggt_nicht_geschluckt():
    quelle = _quelle("database/session.py")
    ab = quelle.index("if self._dispose_engine:")
    umgebung = quelle[ab:ab + 500]

    assert "self._eng.dispose()" in umgebung
    assert "except Exception as dispose_err" in umgebung
    assert "logger.warning" in umgebung, "der Fehler wird still verschluckt"


def test_b008_das_aufraeumen_steht_im_finally():
    """Sonst läuft es nur, wenn vorher nichts geworfen hat."""
    quelle = _quelle("database/session.py")
    ab = quelle.index("if self._dispose_engine:")
    davor = quelle[max(0, ab - 300):ab]

    assert "finally:" in davor


# ---------------------------------------------------------------------------
# B-001 — APP_ROOT-Null-Check
# ---------------------------------------------------------------------------

def test_b001_ein_fehlendes_app_root_wirft_klar_statt_spaeter_krumm():
    quelle = _quelle("services/project_manager.py")

    assert "if _session.APP_ROOT is None:" in quelle
    ab = quelle.index("if _session.APP_ROOT is None:")
    assert "raise RuntimeError" in quelle[ab:ab + 300]
    assert "Path(_session.APP_ROOT)" in quelle[ab:ab + 600], (
        "der Null-Check steht nicht vor der Verwendung"
    )


# ---------------------------------------------------------------------------
# B-601 — GPU-Aufräumen im finally
# ---------------------------------------------------------------------------

def test_b601_die_chunk_schleife_liegt_in_try_finally():
    quelle = _quelle("services/ai_audio_service.py")
    ab = quelle.index("B-601 Fix: GPU-Code in try/finally")
    danach = quelle[ab:ab + 400]

    assert "try:" in danach
    assert "for i in range(num_chunks):" in danach


def test_b601_das_finally_gibt_vram_frei():
    """`gc.collect()` und `empty_cache()` müssen auch nach einem Abbruch laufen.

    Sonst bleibt der CUDA-Context belegt — auf dieser Maschine (GTX 1060,
    6 GB) reicht das für einen Folgelauf nicht mehr.
    """
    quelle = _quelle("services/ai_audio_service.py")
    ab = quelle.index("B-601 Fix: Cleanup falls Exception in Chunk-Processing")
    danach = quelle[ab:ab + 300]

    assert "gc.collect()" in danach
    assert "torch.cuda.empty_cache()" in danach
    assert "torch.cuda.is_available()" in danach, (
        "empty_cache ohne Verfügbarkeitsprüfung wirft auf CPU-Maschinen"
    )


def test_b601_das_aufraeumen_haengt_an_einem_finally():
    quelle = _quelle("services/ai_audio_service.py")
    ab = quelle.index("B-601 Fix: Cleanup falls Exception in Chunk-Processing")
    davor = quelle[max(0, ab - 800):ab]

    assert "finally:" in davor


# ---------------------------------------------------------------------------
# B-350 — VectorDB-Cleanup vor dem SQL-Commit
# ---------------------------------------------------------------------------

def test_b350_der_vectordb_cleanup_laeuft_vor_dem_sql_commit():
    """Reihenfolge ist der ganze Fix.

    Schlägt die VectorDB fehl, muss der Soft-Delete zurückgerollt werden —
    sonst findet die Semantic-Search Clips, die in SQL schon gelöscht sind.
    """
    quelle = _quelle("services/ingest_service.py")
    ab = quelle.index("VectorDB-Cleanup VOR SQL-Commit")
    danach = quelle[ab:ab + 2000]

    assert "delete_by_clip_ids(video_ids)" in danach
    loeschen = danach.index("delete_by_clip_ids(video_ids)")
    assert "commit" in danach[loeschen:], (
        "kein commit nach dem VectorDB-Cleanup — die Reihenfolge ist verdreht"
    )
    # Der Cleanup hängt an `if video_ids:`. Die Mutationsprobe setzte genau
    # diese Bedingung auf `if False:` — dann steht der Aufruf noch im
    # Quelltext, läuft aber nie. 51 Tests liefen dabei durch.
    assert "if video_ids:" in danach[:loeschen], (
        "der Cleanup haengt nicht mehr an der video_ids-Pruefung"
    )


def test_b350_ein_vectordb_fehler_fuehrt_zum_rollback():
    quelle = _quelle("services/ingest_service.py")
    ab = quelle.index("VectorDB-Cleanup VOR SQL-Commit")
    danach = quelle[ab:ab + 1200]

    assert "except (RuntimeError, OSError, ImportError)" in danach
    fehlerzweig = danach[danach.index("except (RuntimeError, OSError, ImportError)"):]
    assert "rollback" in fehlerzweig.lower(), (
        "der Fehlerzweig rollt den Soft-Delete nicht zurueck"
    )


# ---------------------------------------------------------------------------
# B-252 — leere Dock-Geisterhüllen ausblenden
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dock", ["_task_mgr_dock", "chat_dock"])
def test_b252_die_leere_dockhuelle_wird_ausgeblendet(dock):
    """Der Inhalt wandert in einen Tab; das leere DockWidget bleibt sonst sichtbar."""
    quelle = _quelle("ui/controllers/panel_setup.py")

    assert f"self.window.{dock}.hide()" in quelle, (
        f"{dock} wird nicht mehr ausgeblendet — leere Huelle bleibt sichtbar"
    )


def test_b252_das_ausblenden_folgt_dem_einhaengen_in_den_tab():
    """Erst den Inhalt umhängen, dann die Hülle verstecken."""
    quelle = _quelle("ui/controllers/panel_setup.py")

    tab = quelle.index('addTab(task_w, "TASKS")')
    verstecken = quelle.index("self.window._task_mgr_dock.hide()")

    assert tab < verstecken


# ---------------------------------------------------------------------------
# B-657 — Timeline-Usage nach dem Projektwechsel neu lesen
# ---------------------------------------------------------------------------

def test_b657_die_usage_markierung_wird_nach_dem_projektwechsel_gelesen():
    """Bewusst NACH `load_from_db`, damit die Timeline-Tabelle schon steht."""
    quelle = _quelle("ui/controllers/project_management.py")
    rumpf = _methode("ui/controllers/project_management.py", "_on_project_changed")

    assert "self.window.edit_workspace._refresh_timeline_usage_marking()" in rumpf, (
        "die Usage-Markierung wird nach dem Projektwechsel nicht mehr gelesen"
    )
    assert "B-657" in quelle


def test_b657_der_aufruf_ist_gegen_fehler_abgesichert():
    rumpf = _methode("ui/controllers/project_management.py", "_on_project_changed")
    ab = rumpf.index("self.window.edit_workspace._refresh_timeline_usage_marking()")
    umgebung = rumpf[max(0, ab - 300):ab + 300]

    assert "try:" in umgebung
    assert "except" in umgebung


@pytest.mark.parametrize("marker,pfad", [
    ("B-657", "ui/controllers/project_management.py"),
    ("B-601", "services/ai_audio_service.py"),
    ("B-350", "services/ingest_service.py"),
    ("B-252", "ui/controllers/panel_setup.py"),
    ("B-011", "services/task_manager.py"),
    ("B-011", "workers/audio_analysis.py"),
    ("B-010", "services/task_manager.py"),
    ("B-008", "database/session.py"),
    ("B-001", "services/project_manager.py"),
])
def test_alle_stellen_behalten_ihren_marker(marker, pfad):
    """Ohne Marker findet kein Werkzeug die Stelle wieder."""
    assert marker in _quelle(pfad)
