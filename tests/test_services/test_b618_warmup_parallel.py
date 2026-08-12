"""B-618: der Warmup lief sequenziell und machte den Kaltstart langsamer.

Messung 2026-08-09 an einem echten Kaltstart: der In-Process-Teil sank durch
den Warmup von 110 s auf 66,5 s — der GESAMTE Kaltstart stieg dabei aber von
110 s auf 169-190 s, weil die 102,8 s des Warmup-Subprozesses vollstaendig
oben drauf kamen. Der Fix machte damit genau das schlimmer, was er beheben
sollte.

Diese Tests sichern den nebenlaeufigen Start ab:
- ``start_umap_warmup_async`` kehrt sofort zurueck (blockiert nicht),
- ein spaeterer ``warm_umap_cache`` wartet auf das laufende Ergebnis, statt
  einen zweiten Subprozess zu starten,
- im Frozen-Build passiert weiterhin nichts (dort ist Numba nicht cachebar).
"""

from __future__ import annotations

import threading
import time

import pytest

from services.enrichment import style_bucket_clusterer as sbc


@pytest.fixture(autouse=True)
def _frischer_warmup_zustand(monkeypatch):
    """Jeder Test startet mit unbenutztem Warmup-Zustand."""
    monkeypatch.setitem(sbc._WARMUP_STATE, "done", False)
    monkeypatch.setattr(sbc, "_WARMUP_ASYNC_THREAD", None, raising=False)
    monkeypatch.setattr(sbc, "_WARMUP_LOCK", threading.Lock())
    monkeypatch.setattr(sbc, "_WARMUP_ASYNC_LOCK", threading.Lock())
    # umap darf nicht importiert sein, sonst kuerzt der Warmup sofort ab.
    monkeypatch.delitem(sbc.sys.modules, "umap", raising=False)
    yield


def _langsamer_subprozess(dauer: float, zaehler: list):
    def _run(*a, **kw):
        zaehler.append(1)
        time.sleep(dauer)

        class _Fertig:
            returncode = 0

        return _Fertig()

    return _run


def test_b618_async_start_blockiert_den_aufrufer_nicht():
    """Der Kern: der App-Start darf nicht auf den Warmup warten."""
    zaehler: list = []
    sbc.subprocess.run = _langsamer_subprozess(1.5, zaehler)  # type: ignore[assignment]
    try:
        beginn = time.monotonic()
        gestartet = sbc.start_umap_warmup_async()
        vergangen = time.monotonic() - beginn

        assert gestartet is True
        assert vergangen < 0.5, (
            f"B-618: start_umap_warmup_async blockierte {vergangen:.2f} s — "
            "dann laeuft der Warmup wieder sequenziell und der Kaltstart wird "
            "insgesamt langsamer statt schneller."
        )
    finally:
        import subprocess as _sp

        sbc.subprocess.run = _sp.run  # type: ignore[assignment]
        if sbc._WARMUP_ASYNC_THREAD:
            sbc._WARMUP_ASYNC_THREAD.join(timeout=5)


def test_b618_spaeterer_sync_aufruf_startet_keinen_zweiten_subprozess():
    """Doppelter Warmup waere die Kaltstart-Verschlechterung ein zweites Mal."""
    zaehler: list = []
    sbc.subprocess.run = _langsamer_subprozess(0.8, zaehler)  # type: ignore[assignment]
    try:
        sbc.start_umap_warmup_async()
        time.sleep(0.1)  # Thread hat den Lock sicher
        ergebnis = sbc.warm_umap_cache()  # muss warten, nicht neu starten

        assert ergebnis is True
        assert len(zaehler) == 1, (
            f"B-618: {len(zaehler)} Warmup-Subprozesse statt einem — der "
            "synchrone Aufruf wartet nicht auf den laufenden Hintergrundlauf."
        )
    finally:
        import subprocess as _sp

        sbc.subprocess.run = _sp.run  # type: ignore[assignment]
        if sbc._WARMUP_ASYNC_THREAD:
            sbc._WARMUP_ASYNC_THREAD.join(timeout=5)


def test_b618_zweiter_async_start_startet_keinen_zweiten_thread():
    """Idempotenz: mehrfacher Aufruf darf nicht mehrfach warmlaufen."""
    zaehler: list = []
    sbc.subprocess.run = _langsamer_subprozess(0.8, zaehler)  # type: ignore[assignment]
    try:
        sbc.start_umap_warmup_async()
        erster = sbc._WARMUP_ASYNC_THREAD
        sbc.start_umap_warmup_async()
        assert sbc._WARMUP_ASYNC_THREAD is erster
        time.sleep(1.2)
        assert len(zaehler) == 1
    finally:
        import subprocess as _sp

        sbc.subprocess.run = _sp.run  # type: ignore[assignment]
        if sbc._WARMUP_ASYNC_THREAD:
            sbc._WARMUP_ASYNC_THREAD.join(timeout=5)


def test_b618_frozen_startet_keinen_hintergrund_warmup(monkeypatch):
    """Im Frozen ist Numba nicht cachebar — der Warmup waere reine Zeitverschwendung."""
    monkeypatch.setattr(sbc.sys, "frozen", True, raising=False)
    try:
        assert sbc.start_umap_warmup_async() is False
        assert sbc._WARMUP_ASYNC_THREAD is None
    finally:
        monkeypatch.delattr(sbc.sys, "frozen", raising=False)


def test_b618_bereits_erledigt_startet_nichts():
    """Ein warmer Prozess braucht keinen weiteren Lauf."""
    sbc._WARMUP_STATE["done"] = True
    assert sbc.start_umap_warmup_async() is False
    assert sbc._WARMUP_ASYNC_THREAD is None


def test_b618_app_start_stoesst_den_warmup_an():
    """Ohne Aufruf beim App-Start bleibt der Warmup sequenziell."""
    from pathlib import Path

    quelle = Path("main.py").read_text(encoding="utf-8")
    assert "start_umap_warmup_async" in quelle, (
        "B-618: main.py startet den Warmup nicht — er laeuft dann wieder erst "
        "unmittelbar vor dem Cluster-Fit und blockiert ihn."
    )
