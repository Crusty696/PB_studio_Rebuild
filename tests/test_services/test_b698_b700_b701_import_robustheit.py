"""Paket B-698 + B-700 + B-701: Import-/Probe-Robustheit.

- B-698: video_service.probe() muss ffprobe-Output als UTF-8 dekodieren
  (Locale-Default cp1252 auf DE-Windows crasht bei CJK/Emoji-Metadaten).
- B-700: FolderImportWorker darf bei einer DB-Exception (IntegrityError) nur
  DIESE Datei ueberspringen, nicht den Rest-Batch abbrechen.
- B-701: format.duration == "N/A" darf nicht alle Stream-Metadaten verwerfen
  (Defekt 2; Defekt 1 "leeres Probe -> ablehnen" ist in
  test_ingest_service.py::test_ingest_video_rejects_unreadable_file_on_probe_failure).
"""
import json
import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from unittest.mock import patch

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


# ── B-698 ────────────────────────────────────────────────────────────────────

def test_b698_probe_decodes_ffprobe_output_as_utf8(monkeypatch, tmp_path):
    """probe() muss encoding='utf-8' + errors='replace' an subprocess.run geben —
    sonst dekodiert Python mit cp1252 und crasht INNERHALB subprocess.run,
    bevor der returncode-Check greift."""
    import services.video_service as vs

    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        payload = {
            "streams": [{
                "codec_type": "video", "codec_name": "h264",
                "width": 1920, "height": 1080, "r_frame_rate": "30/1",
                # Nicht-Latin1-Metadaten — der B-698-Ausloeser.
                "tags": {"title": "\u30c6\u30b9\u30c8 \U0001F3B5"},
            }],
            "format": {"duration": "10.0"},
        }
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(vs.subprocess, "run", fake_run)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")

    vs.VideoAnalyzer().probe(str(video))

    assert captured.get("encoding") == "utf-8", (
        "probe() gibt kein encoding='utf-8' an subprocess.run (B-698) — "
        "cp1252-Decode crasht bei CJK/Emoji-Metadaten"
    )
    assert captured.get("errors") == "replace"


# ── B-700 ────────────────────────────────────────────────────────────────────

def test_b700_integrityerror_skips_file_and_batch_continues(monkeypatch, tmp_path):
    """IntegrityError bei Datei 1 -> Datei 2 wird trotzdem importiert,
    finished feuert mit dem Teilergebnis (kein error-Abbruch)."""
    _qapp()
    from sqlalchemy.exc import IntegrityError
    import workers.import_export as ie

    v1 = tmp_path / "a.mp4"
    v2 = tmp_path / "b.mp4"
    v1.write_bytes(b"x")
    v2.write_bytes(b"x")

    def fake_ingest_video(p, project_id=None, invalidate_caches=True):
        if "a.mp4" in str(p):
            raise IntegrityError("INSERT INTO video_clips", {}, Exception("UNIQUE constraint"))
        return types.SimpleNamespace(id=42)

    monkeypatch.setattr(ie, "ingest_video", fake_ingest_video)
    monkeypatch.setattr(ie, "_invalidate_pacing_caches", lambda: None)

    worker = ie.FolderImportWorker([], [str(v1), str(v2)], project_id=1)
    results = {"finished": None, "errors": [], "messages": []}
    worker.finished.connect(lambda added, clips: results.update(finished=(added, clips)))
    worker.error.connect(results["errors"].append)
    worker.file_imported.connect(results["messages"].append)

    worker.run()

    assert results["errors"] == [], (
        f"IntegrityError brach den Batch ab statt die Datei zu skippen (B-700): {results['errors']}"
    )
    assert results["finished"] is not None, "finished-Signal fehlt — Batch abgebrochen (B-700)"
    added, clips = results["finished"]
    assert added == 1 and len(clips) == 1, f"Datei 2 wurde nicht importiert: added={added}"
    assert any("Fehler" in m and "a.mp4" in m for m in results["messages"]), (
        "Uebersprungene Datei wurde dem User nicht gemeldet"
    )


# ── B-701 Defekt 2 ───────────────────────────────────────────────────────────

def test_b701_na_duration_keeps_stream_metadata(monkeypatch):
    """format.duration='N/A' -> duration None, aber width/height/fps/codec
    bleiben erhalten (frueher: komplettes {} -> alles verloren)."""
    import services.ingest_service as ing

    payload = {
        "streams": [{
            "codec_type": "video", "codec_name": "vp9",
            "width": 1280, "height": 720, "r_frame_rate": "25/1",
        }],
        "format": {"duration": "N/A"},
    }

    def fake_run(cmd, **kwargs):
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(ing.subprocess, "run", fake_run)

    meta = ing._probe_video_meta("C:/media/na_duration.webm")

    assert meta, "Probe verwarf ALLE Metadaten wegen duration='N/A' (B-701 D2)"
    assert meta["duration"] is None
    assert meta["width"] == 1280 and meta["height"] == 720
    assert meta["codec"] == "vp9"


def test_b701_stream_duration_fallback(monkeypatch):
    """Fehlt format.duration, greift die Stream-Duration."""
    import services.ingest_service as ing

    payload = {
        "streams": [{
            "codec_type": "video", "codec_name": "h264",
            "width": 640, "height": 480, "r_frame_rate": "30/1",
            "duration": "7.5",
        }],
        "format": {},
    }

    def fake_run(cmd, **kwargs):
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(ing.subprocess, "run", fake_run)

    meta = ing._probe_video_meta("C:/media/stream_dur.mp4")
    assert meta["duration"] == 7.5
