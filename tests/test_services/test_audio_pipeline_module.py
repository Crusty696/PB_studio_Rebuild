"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T1.1: Modul-Skeleton services.audio_pipeline.
"""
from __future__ import annotations


def test_module_importable():
    """T1.1 RED: services.audio_pipeline existiert als Modul."""
    import services.audio_pipeline  # noqa: F401


def test_module_has_version_attr():
    """T1.1 Modul stellt __version__ bereit fuer Compat-Checks."""
    import services.audio_pipeline as mod
    assert hasattr(mod, "__version__")
    assert isinstance(mod.__version__, str)
