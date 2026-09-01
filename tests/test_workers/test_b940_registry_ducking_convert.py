"""B-940 — auto_ducking und convert_videos waren nie in der Worker-Registry.

Beide Worker existieren seit jeher (``AutoDuckingWorker``,
``BatchConvertWorker``), waren aber nie registriert. Die Chat-Aktionen meldeten
deshalb "kein Worker registriert" (seit d175a51 wenigstens ehrlich) und liefen
nur ueber die Oberflaeche. Userentscheidung 2026-08-31: beide freischalten.
"""

import pytest

import workers.registry  # noqa: F401 — Side-Effect: registriert die Worker
from services.task_manager import GlobalTaskManager
from workers.audio import AutoDuckingWorker
from workers.import_export import BatchConvertWorker
from workers.registry import _map_auto_ducking, _map_convert_videos


@pytest.mark.parametrize("action, worker_class", [
    ("auto_ducking", AutoDuckingWorker),
    ("convert_videos", BatchConvertWorker),
])
def test_action_haengt_am_richtigen_worker(action, worker_class):
    eintrag = GlobalTaskManager._WORKER_REGISTRY.get(action)

    assert eintrag is not None, f"'{action}' ist nicht registriert"
    assert eintrag[0] is worker_class


@pytest.mark.parametrize("action", ["auto_ducking", "convert_videos"])
def test_die_aktion_meldet_keinen_fehlenden_worker_mehr(action):
    """Der Guard aus d175a51 darf jetzt durchlassen."""
    from services.actions.edit.media_actions import _worker_registered

    assert _worker_registered(action) is True


def test_ducking_mapper_liefert_die_drei_pfade(test_engine):
    from sqlalchemy.orm import Session
    from database import AudioTrack, Project

    with Session(test_engine) as session:
        session.add(Project(id=1, name="P", path="."))
        session.add(AudioTrack(
            id=5, project_id=1, file_path="t.mp3", title='Ta:ck/1',
            stem_other_path="other.wav", stem_vocals_path="vocals.wav",
        ))
        session.commit()

    kwargs = _map_auto_ducking({"audio_track_id": 5})

    assert set(kwargs) == {"music_path", "voice_path", "output_path"}
    # Verbotene Zeichen im Titel duerfen nicht im Dateinamen landen.
    assert ":" not in kwargs["output_path"].split("ducked")[-1]
    assert kwargs["output_path"].endswith("_ducked.wav")
    AutoDuckingWorker(**kwargs)  # Konstruktor-Vertrag


def test_ducking_mapper_wirft_nie(monkeypatch):
    """Der Mapper laeuft in einem Qt-Slot ohne Fehlerbehandlung.

    Faellt der DB-Zugriff aus, muss er leere Pfade liefern statt zu werfen —
    der Worker meldet den Fehler dann sichtbar im TaskManagerDock.
    """
    import workers.registry as reg

    def _boom(*a, **k):
        raise RuntimeError("DB weg")

    monkeypatch.setattr("database.nullpool_session", _boom)
    kwargs = reg._map_auto_ducking({"audio_track_id": 999})

    assert kwargs["music_path"] == ""
    assert kwargs["voice_path"] == ""


@pytest.mark.parametrize("codec, erwartet_vcodec, erwartet_ext", [
    ("h265", "hevc_nvenc", ".mp4"),
    ("prores", "prores_ks", ".mov"),
])
def test_convert_mapper_codec_zuordnung(codec, erwartet_vcodec, erwartet_ext, monkeypatch):
    # B-949: Ohne diesen Patch haengt das Ergebnis von der Maschine ab — auf
    # einem Rechner ohne NVENC waere hevc_nvenc die falsche Erwartung.
    monkeypatch.setattr(
        "services.convert_service.detect_nvenc",
        lambda: {"h264_nvenc": True, "hevc_nvenc": True},
    )
    monkeypatch.setattr("services.ingest_service.get_all_video", lambda: [])

    kwargs = _map_convert_videos({"codec": codec, "resolution": "3840x2160", "fps": "60"})

    assert kwargs["vcodec"] == erwartet_vcodec
    assert kwargs["ext"] == erwartet_ext
    assert kwargs["resolution"] == "3840x2160"
    assert kwargs["fps"] == "60"
    BatchConvertWorker(**kwargs)  # Konstruktor-Vertrag


def test_convert_mapper_faellt_ohne_nvenc_auf_cpu_zurueck(monkeypatch):
    """GPU-Hartregel: nur h264_nvenc/hevc_nvenc, sonst CPU — nie ein anderes Backend."""
    monkeypatch.setattr("services.ingest_service.get_all_video", lambda: [])
    monkeypatch.setattr("services.convert_service.detect_nvenc", lambda: {"h264_nvenc": False})

    assert _map_convert_videos({"codec": "h264"})["vcodec"] == "libx264"


def test_convert_mapper_nutzt_nvenc_wenn_vorhanden(monkeypatch):
    monkeypatch.setattr("services.ingest_service.get_all_video", lambda: [])
    monkeypatch.setattr("services.convert_service.detect_nvenc", lambda: {"h264_nvenc": True})

    assert _map_convert_videos({"codec": "h264"})["vcodec"] == "h264_nvenc"


def test_convert_mapper_wirft_nie(monkeypatch):
    def _boom():
        raise RuntimeError("Pool weg")

    monkeypatch.setattr("services.ingest_service.get_all_video", _boom)
    monkeypatch.setattr("services.convert_service.detect_nvenc", lambda: {"h264_nvenc": True})

    assert _map_convert_videos({})["videos"] == []


# ── B-949: h265 muss NVENC genauso pruefen wie h264 ──────────────────────────
#
# Diese vier Faelle standen schon in der Commit-Nachricht von `bc19d9b` — sie
# wurden dort aber nie eingecheckt. Der Commit enthielt ausschliesslich vier
# geloeschte Importzeilen. Der h265-Zweig setzte weiterhin bedingungslos
# hevc_nvenc, also genau der Zustand, den die Nachricht als behoben beschrieb.
# Gefunden am 2026-09-01 durch eine Nachpruefung des eigenen Commits.

def _nvenc(monkeypatch, **verfuegbar):
    monkeypatch.setattr("services.convert_service.detect_nvenc", lambda: dict(verfuegbar))
    monkeypatch.setattr("services.ingest_service.get_all_video", lambda: [])


def test_h265_faellt_ohne_hevc_nvenc_auf_die_cpu(monkeypatch):
    """Fehlt hevc_nvenc, muss libx265 gewaehlt werden statt eines Encodes, der scheitert."""
    _nvenc(monkeypatch, h264_nvenc=True, hevc_nvenc=False)

    kwargs = _map_convert_videos({"codec": "h265"})

    assert kwargs["vcodec"] == "libx265"
    assert kwargs["ext"] == ".mp4"


def test_h264_darf_auf_die_gpu_auch_wenn_hevc_fehlt(monkeypatch):
    """Die beiden Schluessel werden getrennt ausgewertet, nicht als ein Schalter."""
    _nvenc(monkeypatch, h264_nvenc=True, hevc_nvenc=False)

    kwargs = _map_convert_videos({"codec": "h264"})

    assert kwargs["vcodec"] == "h264_nvenc"


def test_h265_nutzt_die_gpu_wenn_hevc_nvenc_da_ist(monkeypatch):
    _nvenc(monkeypatch, h264_nvenc=False, hevc_nvenc=True)

    kwargs = _map_convert_videos({"codec": "h265"})

    assert kwargs["vcodec"] == "hevc_nvenc"


@pytest.mark.parametrize("codec", ["h264", "h265", "prores"])
def test_kein_fremdes_gpu_backend(codec, monkeypatch):
    """GPU-Hartregel: ausschliesslich NVENC oder CPU, nie qsv/amf/vaapi/videotoolbox."""
    _nvenc(monkeypatch, h264_nvenc=False, hevc_nvenc=False)

    vcodec = _map_convert_videos({"codec": codec})["vcodec"]

    assert vcodec in {"libx264", "libx265", "prores_ks"}
    for fremd in ("qsv", "amf", "vaapi", "videotoolbox"):
        assert fremd not in vcodec
