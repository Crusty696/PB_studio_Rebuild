"""B-569/B-577 — GUI-Test gegen die ECHTE PBWindow (offscreen).

Warum es diesen Test zusaetzlich zu ``test_b569_audio_dropdown_reflects_a1.py``
und ``test_b577_async_dropdown_reflects_a1.py`` gibt:

Jene Tests fahren gegen ein ``SimpleNamespace``-Fake-Window mit nackten
``QComboBox``-Objekten. Damit ist belegt, dass die Auswahl-Logik den richtigen
Index setzt — NICHT aber:

1. dass das sichtbare SCHNITT-Dropdown
   (``PBWindow._schnitt_ws.editor_view.audio_combo``) diesen Index auch als
   Label rendert (``currentText()``), und
2. dass die Auswahl nach dem vollstaendigen Einschwingen noch steht, statt von
   einem nachgelagerten Refresh/Signal wieder auf den ersten/analysierten Track
   zurueckzuspringen.

Dieser Test schliesst genau diese Luecke: echte ``PBWindow``, echter
Projekt-Open-Pfad ``_on_project_changed -> _refresh_media_table ->
(Worker-Thread) -> _apply_refreshed_data``, Assertion auf ``currentText()``.

Diskriminierende Datenlage (auf der Maschine existierte KEIN Projekt mit dieser
Konstellation — alle Real-Projekte hatten entweder nur einen Audio-Track oder
eine leere Timeline):

    id=2 "Normalize"  bpm=128  -> erster Track UND erster analysierter
    id=3 "Zyce"       bpm=140  -> liegt in der A1-Lane, ist aber weder der
                                  erste noch der erste analysierte Track
    id=4 "Filler"     bpm=None -> zusaetzlicher Nicht-Kandidat

Ohne A1-Logik gewinnt in beiden Refresh-Pfaden Track 2 (preferred/first).
Nur mit A1-Logik gewinnt Track 3.

Schaerfung: vor dem Projekt-Open wird das Combo bewusst auf den Decoy-Track 2
gestellt. Damit kann der Test nicht dadurch gruen werden, dass die Auswahl
schon aus der Fenster-Konstruktion zufaellig richtig stand — der async-Pfad
MUSS aktiv auf Track 3 zurueckstellen.

Harness-Hinweise (reines Testverhalten, kein Produktivcode angefasst):
* ``PBWindow.closeEvent`` ruft ``engine.dispose()`` (main.py:1334). Bei der
  In-Memory-Test-Engine (StaticPool) reisst das die DB weg und laesst den
  Teardown der ``db_session``-Fixture mit "Cannot operate on a closed
  database" scheitern -> ``dispose`` wird fuer die Testdauer neutralisiert.
* ``GlobalTaskManager`` ist ein prozessweiter Singleton; nach dem ersten
  ``closeEvent`` steht ``_shutting_down=True`` und JEDER Folge-Test bekommt
  "[TaskEngine] _start_in_main_thread nach Shutdown ignoriert" -> der async
  Worker startet nie. Flag wird pro Test zurueckgesetzt.
* ``closeEvent`` kann bei laufenden Tasks ein modales ``QMessageBox.question``
  oeffnen, das offscreen nie beantwortet wird -> Dialoge werden gestubbt.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest

A1_MEDIA_ID = 3
A1_TITLE = "Zyce"
DECOY_MEDIA_ID = 2
DECOY_TITLE = "Normalize"


def _pump_until(app, predicate, timeout_ms: int, what: str):
    """Pumpt die Qt-Event-Loop bis ``predicate()`` wahr ist.

    Kein blindes ``sleep``: es wird auf einen ZUSTAND gewartet, den der
    Worker-finished-Slot setzt, mit hartem Timeout und sprechender Meldung.
    """
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            app.processEvents()  # zugestellte Folge-Events noch abarbeiten
            return
        time.sleep(0.01)
    raise AssertionError(
        f"Timeout nach {timeout_ms} ms beim Warten auf: {what}. "
        "Der async Medien-Reload ist nicht eingeschwungen — dieses Ergebnis "
        "NICHT als Aussage ueber die Auswahl-Logik werten, hier haengt "
        "Threading/Timing im Harness."
    )


@pytest.fixture
def real_window(qapp, test_engine, db_session, project, monkeypatch):
    """Echte PBWindow auf der isolierten Test-Engine, mit Seed-Daten."""
    import database
    from database import session as db_session_mod

    # Aktives Projekt deterministisch auf das Test-Projekt festnageln.
    monkeypatch.setattr(database, "get_active_project_id", lambda: project.id)
    monkeypatch.setattr(db_session_mod, "get_active_project_id", lambda: project.id)

    # --- Seed: diskriminierende Track-Konstellation + A1-Lane-Eintrag ---
    db_session.add_all([
        database.AudioTrack(
            id=DECOY_MEDIA_ID, project_id=project.id,
            file_path="/tmp/normalize.wav", title=DECOY_TITLE, bpm=128.0,
        ),
        database.AudioTrack(
            id=A1_MEDIA_ID, project_id=project.id,
            file_path="/tmp/zyce.wav", title=A1_TITLE, bpm=140.0,
        ),
        database.AudioTrack(
            id=4, project_id=project.id,
            file_path="/tmp/filler.wav", title="Filler",
        ),
    ])
    db_session.add(database.TimelineEntry(
        project_id=project.id, track="audio",
        media_id=A1_MEDIA_ID, start_time=0.0,
    ))
    db_session.commit()

    # --- Harness-Absicherungen (siehe Modul-Docstring) ---
    monkeypatch.setattr(test_engine, "dispose", lambda *a, **k: None)

    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))

    from services.task_manager import GlobalTaskManager
    GlobalTaskManager.instance()._shutting_down = False

    from services import recent_projects
    monkeypatch.setattr(recent_projects.RecentProjectsManager, "add",
                        staticmethod(lambda *a, **k: None))

    # Chat-Dock wuerde Host-Settings lesen / Ollama anfassen — fuer diesen
    # Auswahl-Test irrelevant (gleiches Vorgehen wie
    # test_workspace_setup_four_tabs.py).
    from ui.controllers.panel_setup import PanelSetupController
    monkeypatch.setattr(PanelSetupController, "setup_chat_dock", lambda self: None)

    from main import PBWindow
    win = PBWindow()
    try:
        yield win
    finally:
        win.close()


def _open_project_and_settle(qapp, win, tmp_path, what: str):
    """Faehrt den realen Projekt-Open-Pfad und wartet aufs Einschwingen."""
    ctrl = win.media_table_controller
    combo = win.audio_combo

    # Schaerfung: Auswahl bewusst auf den Decoy stellen, damit ein gruener
    # Test nicht durch "stand vorher schon richtig" zustande kommen kann.
    decoy_idx = combo.findData(DECOY_MEDIA_ID)
    assert decoy_idx >= 0, "Decoy-Track fehlt im Combo — Seed fehlgeschlagen"
    combo.setCurrentIndex(decoy_idx)
    assert combo.currentData() == DECOY_MEDIA_ID

    ctrl._reload_inflight = False

    proj_dir = tmp_path / "TestProjekt"
    proj_dir.mkdir(exist_ok=True)
    win.project_management._on_project_changed(proj_dir)

    _pump_until(
        qapp,
        lambda: not getattr(ctrl, "_reload_inflight", False) and combo.count() >= 4,
        timeout_ms=15000,
        what=what,
    )


def test_real_window_schnitt_dropdown_renders_a1_track_after_project_open(
    qapp, real_window, tmp_path
):
    """Projekt-Open gegen echte PBWindow: sichtbares Label == A1-Track."""
    win = real_window
    combo = win.audio_combo

    # Es MUSS das echte SCHNITT-Dropdown sein, nicht irgendeine Combo —
    # sonst prueft der Test das falsche Widget.
    assert combo is win._schnitt_ws.editor_view.audio_combo, (
        "win.audio_combo ist nicht das SCHNITT-Editor-Dropdown"
    )

    _open_project_and_settle(qapp, win, tmp_path, "async Medien-Reload nach Projekt-Open")

    # Vorbedingung: ohne beide Kandidaten im Combo waere die Assertion
    # trivial per Fallback erfuellbar.
    assert combo.findData(DECOY_MEDIA_ID) >= 0, "Decoy-Track 2 fehlt im Combo"
    assert combo.findData(A1_MEDIA_ID) >= 0, "A1-Track 3 fehlt im Combo"

    items = [(combo.itemData(i), combo.itemText(i)) for i in range(combo.count())]

    # (1) Auswahl-Datum
    assert combo.currentData() == A1_MEDIA_ID, (
        f"B-569/B-577: Dropdown-Auswahl ist {combo.currentData()}, erwartet "
        f"A1-Track {A1_MEDIA_ID}. Items: {items}"
    )

    # (2) GERENDERTES LABEL — der Punkt, den die Fake-Window-Tests nicht abdecken.
    assert A1_TITLE in combo.currentText(), (
        f"Sichtbares SCHNITT-Dropdown zeigt {combo.currentText()!r}, "
        f"erwartet ein Label mit {A1_TITLE!r}. Items: {items}"
    )
    assert DECOY_TITLE not in combo.currentText(), (
        f"Sichtbares Dropdown zeigt den falschen Track: {combo.currentText()!r}"
    )


def test_real_window_selection_survives_subsequent_refresh(
    qapp, real_window, tmp_path
):
    """Auswahl darf nach Einschwingen/Nachlade-Refresh nicht zurueckspringen."""
    win = real_window
    combo = win.audio_combo
    ctrl = win.media_table_controller

    _open_project_and_settle(qapp, win, tmp_path, "erster async Medien-Reload")
    assert combo.currentData() == A1_MEDIA_ID, "Vorbedingung: A1 nach Open gewaehlt"

    # Nachgelagerter Refresh (z.B. Pool-Reload nach Import) — die Auswahl
    # darf danach nicht auf den ersten/analysierten Track zurueckfallen.
    ctrl._reload_inflight = False
    ctrl._refresh_media_table()
    _pump_until(
        qapp,
        lambda: not getattr(ctrl, "_reload_inflight", False) and combo.count() >= 4,
        timeout_ms=15000,
        what="zweiter async Medien-Reload",
    )

    # Zusaetzlich die Event-Loop mehrfach durchlaufen lassen, damit verzoegerte
    # Slots (QTimer.singleShot-Debounce, DeferredDelete) noch feuern koennen.
    for _ in range(10):
        qapp.processEvents()
        time.sleep(0.01)

    items = [(combo.itemData(i), combo.itemText(i)) for i in range(combo.count())]
    assert combo.currentData() == A1_MEDIA_ID, (
        f"Auswahl ist nach dem Nachlade-Refresh auf {combo.currentData()} "
        f"zurueckgesprungen, erwartet {A1_MEDIA_ID}. Items: {items}"
    )
    assert A1_TITLE in combo.currentText(), (
        f"Sichtbares Label nach Nachlade-Refresh: {combo.currentText()!r}"
    )
