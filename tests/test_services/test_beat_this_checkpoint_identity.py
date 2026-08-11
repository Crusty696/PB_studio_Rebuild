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


def _stub_download(monkeypatch, payload: bytes | None):
    """torch.hub.download_url_to_file ersetzen.

    ``payload=None`` simuliert einen fehlgeschlagenen Download (kein Netz).
    """
    import torch

    seen: list[tuple[str, str]] = []

    def _fake(url, dst, *args, **kwargs):
        seen.append((url, str(dst)))
        if payload is None:
            raise OSError("kein Netz (Test-Stub)")
        Path(dst).write_bytes(payload)

    monkeypatch.setattr(torch.hub, "download_url_to_file", _fake)
    return seen


def test_ensure_model_keeps_download_path_when_checkpoint_missing(
    tmp_path, monkeypatch, fresh_service
):
    """Fehlende Datei + kein Netz: bisheriges Download-/Fallback-Verhalten bleibt."""
    _point_torch_hub_at(monkeypatch, tmp_path)
    _stub_download(monkeypatch, None)

    fresh_service._ensure_model()

    assert len(_File2BeatsSpy.calls) == 1
    assert fresh_service._model is not None


# --- B-718 Restluecke 2026-08-11: Erstdownload ------------------------------


def test_first_download_is_verified_before_it_lands_in_cache(tmp_path, monkeypatch):
    """Erstdownload wird gehasht und erst dann in den Torch-Cache uebernommen."""
    ckpt = _point_torch_hub_at(monkeypatch, tmp_path)
    payload = b"echter-checkpoint"
    monkeypatch.setattr(
        bas, "BEAT_THIS_CHECKPOINT_SHA256", hashlib.sha256(payload).hexdigest().upper()
    )
    seen = _stub_download(monkeypatch, payload)

    assert bas.download_beat_this_checkpoint_verified() is True
    assert ckpt.read_bytes() == payload
    # Geladen wurde in eine Temp-Datei, nicht direkt auf den Cache-Pfad.
    assert seen[0][0] == bas.BEAT_THIS_CHECKPOINT_URL
    assert seen[0][1].endswith(".b718-part")
    assert list(ckpt.parent.glob("*.b718-part")) == []


def test_tampered_first_download_never_reaches_cache_or_torch_load(
    tmp_path, monkeypatch, fresh_service
):
    """Kern-Beweis der Restluecke: manipuliertes Erst-Artefakt -> Abbruch.

    Ohne den Fix wuerde beat_this selbst herunterladen und die Datei per
    ``torch.load()`` entpickeln -> Spy saehe einen Aufruf.
    """
    ckpt = _point_torch_hub_at(monkeypatch, tmp_path)
    _stub_download(monkeypatch, b"\x80\x04\x95evil-payload-vom-endpunkt")

    with pytest.raises(RuntimeError) as excinfo:
        fresh_service._ensure_model()

    msg = str(excinfo.value)
    assert "B-718" in msg
    assert "SHA256" in msg
    assert not ckpt.exists()
    assert list(ckpt.parent.glob("*.b718-part")) == []
    assert _File2BeatsSpy.calls == []
    assert fresh_service._model is None


def test_verified_first_download_feeds_normal_load_path(
    tmp_path, monkeypatch, fresh_service
):
    """Gegenprobe: passender Erstdownload -> Modell laedt normal weiter."""
    ckpt = _point_torch_hub_at(monkeypatch, tmp_path)
    payload = b"echter-checkpoint"
    monkeypatch.setattr(
        bas, "BEAT_THIS_CHECKPOINT_SHA256", hashlib.sha256(payload).hexdigest().upper()
    )
    _stub_download(monkeypatch, payload)

    fresh_service._ensure_model()

    assert ckpt.read_bytes() == payload
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
