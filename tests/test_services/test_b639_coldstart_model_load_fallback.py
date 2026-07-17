"""B-639: Kaltstart-Modell-Loads ohne local_files_only/try-except.

Fundstelle 1 (audio_embedder.py CLAP): B-554-Muster (lokal-first, dann
online-Fallback bei OSError/EnvironmentError) uebertragen — Schwester-
Embedder video_embedder.py hatte den Fix bereits.

Fundstelle 2 (raft_motion_service.py raft_large): torchvision-Weights haben
keinen local_files_only-Parameter (torch.hub cached bereits implizit
lokal-first), aber ein unbehandelter Netzwerkfehler beim ERSTEN Laden
(kein Cache-Treffer) crashte bisher roh WAEHREND GPU_LOAD_LOCK gehalten
wird. Fix: try/except mit klar definierter RuntimeError-Meldung.
"""
from __future__ import annotations

import sys
import types

import pytest


# ── Fundstelle 1: ClapAudioEmbedder ───────────────────────────────────────────


class _FakeClapProcessor:
    def __init__(self, local_only: bool):
        self.local_only = local_only


class _FakeClapModel:
    def __init__(self, local_only: bool):
        self.local_only = local_only

    def eval(self):
        return self

    def to(self, device):
        self.device = device
        return self


def _install_fake_transformers_clap(monkeypatch, calls: list, side_effect_on_local=None):
    fake = types.ModuleType("transformers")

    class ClapProcessor:
        @staticmethod
        def from_pretrained(model_id, local_files_only=False):
            calls.append(("processor", local_files_only))
            if local_files_only and side_effect_on_local is not None:
                raise side_effect_on_local
            return _FakeClapProcessor(local_files_only)

    class ClapModel:
        @staticmethod
        def from_pretrained(model_id, local_files_only=False):
            calls.append(("model", local_files_only))
            if local_files_only and side_effect_on_local is not None:
                raise side_effect_on_local
            return _FakeClapModel(local_files_only)

    fake.ClapProcessor = ClapProcessor
    fake.ClapModel = ClapModel
    monkeypatch.setitem(sys.modules, "transformers", fake)


def test_clap_embedder_tries_local_files_only_first(monkeypatch):
    """B-639: Modell wird zuerst NUR aus dem lokalen HF-Cache geladen."""
    from services.brain.audio.audio_embedder import ClapAudioEmbedder

    calls: list = []
    _install_fake_transformers_clap(monkeypatch, calls)

    emb = ClapAudioEmbedder(device="cpu")
    emb._ensure_loaded()

    assert emb.is_loaded
    assert ("processor", True) in calls
    assert ("model", True) in calls
    # Kein Online-Fallback noetig, da lokal-Load "erfolgreich" war (Fake).
    assert ("processor", False) not in calls
    assert ("model", False) not in calls


def test_clap_embedder_falls_back_to_online_on_missing_cache(monkeypatch):
    """B-639: Lokaler Cache-Miss (OSError) -> Online-Fallback, kein Crash."""
    from services.brain.audio.audio_embedder import ClapAudioEmbedder

    calls: list = []
    _install_fake_transformers_clap(
        monkeypatch, calls, side_effect_on_local=OSError("not cached locally")
    )

    emb = ClapAudioEmbedder(device="cpu")
    emb._ensure_loaded()  # darf NICHT raisen

    assert emb.is_loaded
    assert ("processor", True) in calls
    assert ("processor", False) in calls
    assert ("model", False) in calls
