"""B-844: Das B-828-Muster bestand in zwei Workern weiter.

B-828 wurde in `services/video_analysis_service.py` behoben: ein Schritt, der
nichts erzeugt hat, meldet `degraded` statt `done`. Eine Gegenprüfung fand
dasselbe Muster an zwei weiteren Stellen, die damals nicht angefasst wurden:

* **`workers/audio_pipeline_v2_worker.py`** — `_on_done` markiert jede Stage
  grün. Die einzige Ausnahme ist `ctx.degraded[name]`, das nur von vier
  Stages gesetzt wird. Ungeschützt blieben unter anderem `av_pacing`
  (vier stille Null-Pfade), `structure` (leeres Ergebnis ohne Exception),
  `beat_grid` (`bpm: None`) und `waveform` (`num_samples: 0`).

* **`workers/audio_analysis.py`** — `BaseAnalysisWorker` ruft `mark_done`
  unbedingt nach `_save_to_db`. Bei vier Sub-Workern ist `_save_to_db` ein
  No-op, wenn die Track-Zeile fehlt oder soft-deleted ist (`if track:` ohne
  `else`). Der B-066-Guard fängt nur geratene Werte ab, nicht nicht-
  persistierte.

Dazu die falsche Dauermeldung aus B-843: `pacing_service` meldete
„64 Segmente, 337.1s Gesamtdauer", während die geschriebene Timeline bei
330,015 s endete.
"""

from __future__ import annotations

import inspect

import pytest


class TestLeerErkennungV2Worker:
    """Die Stages des Audio-V2-Workers brauchen eine Leer-Prüfung."""

    def test_leer_erkennung_existiert(self):
        from workers.audio_pipeline_v2_worker import _leeres_ergebnis

        assert callable(_leeres_ergebnis)

    @pytest.mark.parametrize("name,payload", [
        ("beat_grid", {"bpm": None}),
        ("beat_grid", {}),
        ("waveform", {"num_samples": 0}),
        ("structure", {"segments_count": 0}),
        ("av_pacing", {"stored_samples": 0}),
        ("onset", {"ok": False}),
        ("key", {"key": None}),
        ("lufs", {"integrated_lufs": None}),
    ])
    def test_leere_ergebnisse_werden_erkannt(self, name, payload):
        from workers.audio_pipeline_v2_worker import _leeres_ergebnis

        grund = _leeres_ergebnis(name, payload)
        assert grund, f"{name} mit {payload} müsste als leer gelten"
        assert isinstance(grund, str) and len(grund) > 10, (
            "die Begründung muss dem Nutzer sagen, was fehlt"
        )

    @pytest.mark.parametrize("name,payload", [
        ("beat_grid", {"bpm": 128.0}),
        ("waveform", {"num_samples": 4096}),
        ("structure", {"segments_count": 27}),
        ("av_pacing", {"stored_samples": 512}),
        ("onset", {"ok": True}),
        ("key", {"key": "Am"}),
        ("lufs", {"integrated_lufs": -9.3}),
    ])
    def test_gefuellte_ergebnisse_gelten_nicht_als_leer(self, name, payload):
        from workers.audio_pipeline_v2_worker import _leeres_ergebnis

        assert _leeres_ergebnis(name, payload) is None

    def test_unbekannte_stage_gilt_nicht_als_leer(self):
        """Keine Regel heisst: nicht beurteilbar, also durchlassen."""
        from workers.audio_pipeline_v2_worker import _leeres_ergebnis

        assert _leeres_ergebnis("gibt_es_nicht", {"irgendwas": 1}) is None

    def test_kaputte_payload_wirft_nicht(self):
        from workers.audio_pipeline_v2_worker import _leeres_ergebnis

        for payload in (None, "text", 42, [], object()):
            assert _leeres_ergebnis("beat_grid", payload) is None

    def test_worker_nutzt_die_leer_erkennung(self):
        import workers.audio_pipeline_v2_worker as modul

        quelle = inspect.getsource(modul)
        assert "_leeres_ergebnis(" in quelle.replace("def _leeres_ergebnis(", ""), (
            "die Funktion wird nirgends aufgerufen"
        )
        stelle = quelle.find("mark_done(\"audio\"")
        assert stelle > 0
        umfeld = quelle[max(0, stelle - 1200):stelle]
        assert "_leeres_ergebnis" in umfeld, (
            "vor mark_done wird nicht auf ein leeres Ergebnis geprueft"
        )


class TestBaseAnalysisWorker:
    """mark_done darf nicht fallen, wenn nichts persistiert wurde."""

    def test_save_to_db_meldet_ob_geschrieben_wurde(self):
        import workers.audio_analysis as modul

        quelle = inspect.getsource(modul)
        stelle = quelle.find("self._save_to_db(result)")
        assert stelle > 0, "_save_to_db-Aufruf nicht gefunden"
        umfeld = quelle[stelle:stelle + 900]
        assert "mark_degraded" in umfeld, (
            "B-844: nach einem No-op-Save faellt weiterhin mark_done"
        )

    def test_track_pruefung_existiert(self):
        import workers.audio_analysis as modul

        quelle = inspect.getsource(modul)
        assert "_track_vorhanden" in quelle, (
            "es fehlt eine Pruefung, ob die Track-Zeile ueberhaupt existiert"
        )

    def test_pruefung_ist_gegen_fehler_abgesichert(self):
        """Eine kaputte DB-Abfrage darf den Worker nicht zum Absturz bringen."""
        import workers.audio_analysis as modul

        quelle = inspect.getsource(modul)
        stelle = quelle.find("def _track_vorhanden")
        assert stelle > 0
        abschnitt = quelle[stelle:stelle + 1400]
        assert "except Exception" in abschnitt, (
            "eine kaputte DB-Abfrage darf den Worker-Abschluss nicht reissen"
        )
        assert "return True" in abschnitt, (
            "im Fehlerfall muss durchgelassen werden — ein Statusproblem darf "
            "nicht haerter treffen als das eigentliche Ergebnis"
        )


class TestDauermeldungStimmt:
    """B-843-Nachtrag: die gemeldete Dauer muss dem Geschriebenen entsprechen."""

    def test_phase3_meldet_die_echte_segmentdauer(self):
        from services import pacing_service

        quelle = inspect.getsource(pacing_service._auto_edit_phase3_inner)
        stelle = quelle.find("Phase 3: %d Segmente")
        assert stelle > 0, "die Abschlussmeldung wurde umbenannt"
        umfeld = quelle[max(0, stelle - 700):stelle + 400]
        assert "B-844" in umfeld, (
            "die gemeldete Gesamtdauer wird weiterhin nicht aus den Segmenten "
            "abgeleitet — sie log im Livelauf 337,1s, geschrieben waren 330,0s"
        )
