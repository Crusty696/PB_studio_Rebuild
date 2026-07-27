"""B-718: Identitaets-Pruefung des beat_this-Checkpoints vor torch.load().

Der Checkpoint wird von ``beat_this.inference.load_checkpoint()`` per
``torch.load()`` deserialisiert (torch 1.12 = kein ``weights_only``), also
entpickelt. Wer die Cache-Datei austauscht, fuehrt beim naechsten
Modell-Load beliebigen Code aus.

Die Tests laden KEIN echtes Modell: ``File2Beats`` wird durch einen Spy
ersetzt, der nur mitschreibt, ob er aufgerufen wurde.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import services.beat_analysis_service as bas
from services.beat_analysis_service import (
    BEAT_THIS_CHECKPOINT_FILENAME,
    BeatAnalysisService,
    verify_beat_this_checkpoint,
)


class _File2BeatsSpy:
    """Ersatz fuer beat_this.inference.File2Beats — laedt nichts."""

    calls: list[dict] = []

    def __init__(self, device=None, dbn=None):
        type(self).calls.append({"device": device, "dbn": dbn})

    def __call__(self, path):  # pragma: no cover - wird hier nie gebraucht
        raise AssertionError("Inferenz darf im Test nicht laufen")


class _ModelManagerStub:
    def unload(self):
        return None


@pytest.fixture()
def fresh_service(monkeypatch):
    """Frischer Singleton + neutralisierte GPU-/Modell-Abhaengigkeiten."""
    import beat_this.inference as bt_inference
    import services.model_manager as mm

    _File2BeatsSpy.calls = []
    monkeypatch.setattr(bt_inference, "File2Beats", _File2BeatsSpy)
    monkeypatch.setattr(mm, "ModelManager", _ModelManagerStub)

    previous = BeatAnalysisService._instance
    BeatAnalysisService._instance = None
    svc = BeatAnalysisService(device="cpu")
    try:
        yield svc
    finally:
        BeatAnalysisService._instance = previous


def _point_torch_hub_at(monkeypatch, root: Path) -> Path:
    """torch.hub.get_dir() auf ein Test-Verzeichnis umbiegen.

    Das ist exakt der Pfad, den ``torch.hub.load_state_dict_from_url()``
    in beat_this fuer die gecachte ``beat_this-final0.ckpt`` benutzt.
    """
    import torch

    monkeypatch.setattr(torch.hub, "get_dir", lambda: str(root))
    ckpt_dir = root / "checkpoints"
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    return ckpt_dir / BEAT_THIS_CHECKPOINT_FILENAME


def test_verify_reports_mismatch_for_tampered_file(tmp_path, monkeypatch):
    ckpt = _point_torch_hub_at(monkeypatch, tmp_path)
    ckpt.write_bytes(b"not-the-real-checkpoint")

    report = verify_beat_this_checkpoint()

    assert report["exists"] is True
    assert report["ok"] is False
    assert report["reason"] == "sha256_mismatch"
    assert report["actual_sha256"] == hashlib.sha256(
        b"not-the-real-checkpoint"
    ).hexdigest().upper()
    assert report["actual_sha256"] != report["expected_sha256"]


def test_verify_reports_missing_when_not_cached(tmp_path, monkeypatch):
    _point_torch_hub_at(monkeypatch, tmp_path)

    report = verify_beat_this_checkpoint()

    assert report["exists"] is False
    assert report["ok"] is False
    assert report["reason"] == "missing"


def test_ensure_model_refuses_tampered_checkpoint(tmp_path, monkeypatch, fresh_service):
    """Kern-Beweis: manipulierter Checkpoint darf NIE torch.load() erreichen.

    Ohne den B-718-Fix wird ``File2Beats`` trotzdem konstruiert und
    deserialisiert die manipulierte Datei -> Spy wuerde einen Aufruf sehen.
    """
    ckpt = _point_torch_hub_at(monkeypatch, tmp_path)
    ckpt.write_bytes(b"\x80\x04\x95evil-pickle-payload")

    with pytest.raises(RuntimeError) as excinfo:
        fresh_service._ensure_model()

    msg = str(excinfo.value)
    assert "B-718" in msg
    assert "SHA256" in msg
    # Kein Load-Versuch: File2Beats wurde nicht konstruiert.
    assert _File2BeatsSpy.calls == []
    # Und der Fehler wurde nicht als "VRAM reicht nicht" maskiert.
    assert "VRAM" not in msg
    assert fresh_service._model is None


def test_ensure_model_loads_when_hash_matches(tmp_path, monkeypatch, fresh_service):
    """Gegenprobe: passender Hash -> normaler Ladepfad bleibt unangetastet."""
    ckpt = _point_torch_hub_at(monkeypatch, tmp_path)
    payload = b"pretend-this-is-the-real-checkpoint"
    ckpt.write_bytes(payload)
    monkeypatch.setattr(
        bas,
        "BEAT_THIS_CHECKPOINT_SHA256",
        hashlib.sha256(payload).hexdigest().upper(),
    )

    fresh_service._ensure_model()

    assert len(_File2BeatsSpy.calls) == 1
    assert _File2BeatsSpy.calls[0]["dbn"] is False
    assert fresh_service._model is not None


def test_ensure_model_keeps_download_path_when_checkpoint_missing(
    tmp_path, monkeypatch, fresh_service
):
    """Fehlende Datei darf das bisherige Download-/Fallback-Verhalten nicht brechen."""
    _point_torch_hub_at(monkeypatch, tmp_path)

    fresh_service._ensure_model()

    assert len(_File2BeatsSpy.calls) == 1
    assert fresh_service._model is not None


def test_pin_matches_real_checkpoint_if_present():
    """Der gepinnte Hash muss zur real installierten Datei passen.

    Skippt, wenn der Checkpoint auf dieser Maschine nicht heruntergeladen ist.
    """
    real = bas.beat_this_checkpoint_path()
    if not real.is_file():
        pytest.skip(f"beat_this-Checkpoint nicht vorhanden: {real}")

    report = verify_beat_this_checkpoint(real)
    assert report["ok"] is True, report
    assert report["actual_size"] == report["expected_size"]
