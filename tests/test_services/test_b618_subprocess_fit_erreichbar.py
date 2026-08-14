"""B-618: der Kind-Prozess-Fit darf nicht an einem NameError scheitern.

Im Frozen-Build laeuft der UMAP/HDBSCAN-Fit bewusst in einem eigenen Prozess,
damit der Numba-JIT den Qt-Main-Thread nicht blockiert. Beim Entfernen des
Warmup-Blocks (Commit b8a73f7) verschwand ``_FIT_SUBPROCESS_TIMEOUT_S``,
obwohl ``_fit_subprocess`` sie weiter benutzt.

Der Fehler war unsichtbar: ``_fit_subprocess`` faengt jede Exception ab und
gibt ``None`` zurueck, ``fit()`` faellt dann still auf den In-Process-Pfad
zurueck. Im Dev-Run merkt man nichts, weil der Kind-Prozess dort gar nicht
verwendet wird — nur im Release-Build war die Schutzmassnahme tot.

Die Tests hier pruefen deshalb zweierlei: dass die Konstante existiert und
plausibel ist, und dass ``_fit_subprocess`` an einem echten Aufruf nicht mehr
an einem NameError stirbt.
"""

from __future__ import annotations

import numpy as np
import pytest

from services.enrichment import style_bucket_clusterer as sbc


def test_b618_timeout_konstante_existiert_und_ist_plausibel():
    assert hasattr(sbc, "_FIT_SUBPROCESS_TIMEOUT_S"), (
        "B-618: _FIT_SUBPROCESS_TIMEOUT_S fehlt — _fit_subprocess wirft dann "
        "einen NameError, der still verschluckt wird, und der Kind-Prozess-"
        "Pfad ist im Frozen-Build wirkungslos."
    )
    wert = sbc._FIT_SUBPROCESS_TIMEOUT_S
    assert isinstance(wert, (int, float))
    # Der JIT allein kostet gemessen 79 s; alles unter ein paar Minuten wuerde
    # den Kind-Prozess auf echten Datenmengen regelmaessig abwuergen.
    assert wert >= 300, f"Zeitbudget zu knapp fuer JIT + Fit: {wert}s"


def test_b618_fit_subprocess_stirbt_nicht_am_nameerror(monkeypatch, caplog):
    """Regression: der Aufruf muss den Timeout-Wert erreichen.

    Statt einen echten Kind-Prozess zu starten, wird ``subprocess.run``
    abgefangen. Der Test prueft, dass es ueberhaupt bis dorthin kommt und
    dass das Zeitbudget mitgegeben wird — vor dem Fix flog der NameError
    davor.
    """
    gesehen: dict[str, object] = {}

    def _fake_run(*args, **kwargs):
        gesehen.update(kwargs)
        raise RuntimeError("Kind-Prozess hier bewusst nicht gestartet")

    monkeypatch.setattr(sbc.subprocess, "run", _fake_run)

    clusterer = sbc.StyleBucketClusterer()
    ergebnis = clusterer._fit_subprocess(np.zeros((4, 3), dtype=np.float32))

    assert ergebnis is None, "bei Fehlschlag ist None der vereinbarte Rueckgabewert"
    assert "timeout" in gesehen, (
        "B-618: subprocess.run wurde nie mit einem timeout erreicht — der "
        "Aufruf bricht vorher ab."
    )
    assert gesehen["timeout"] == sbc._FIT_SUBPROCESS_TIMEOUT_S

    fehlertexte = " ".join(r.getMessage() for r in caplog.records)
    assert "NameError" not in fehlertexte, (
        f"B-618: NameError im Subprozess-Pfad: {fehlertexte}"
    )


def test_b618_fit_nutzt_kindprozess_nur_im_frozen_build(monkeypatch):
    """Der Kind-Prozess ist eine Frozen-Massnahme — im Dev-Run waere er reiner
    Overhead. Diese Zusage soll nicht unbemerkt kippen."""
    aufrufe: list[str] = []

    monkeypatch.setattr(
        sbc.StyleBucketClusterer, "_fit_subprocess",
        lambda self, emb: aufrufe.append("subprocess") or None,
    )
    monkeypatch.setattr(
        sbc.StyleBucketClusterer, "_fit_inprocess",
        lambda self, emb: aufrufe.append("inprocess") or "ok",
    )
    clusterer = sbc.StyleBucketClusterer()
    embeddings = np.zeros((4, 3), dtype=np.float32)

    monkeypatch.setattr(sbc.sys, "frozen", False, raising=False)
    clusterer.fit(embeddings)
    assert aufrufe == ["inprocess"]

    aufrufe.clear()
    monkeypatch.setattr(sbc.sys, "frozen", True, raising=False)
    clusterer.fit(embeddings)
    assert aufrufe == ["subprocess", "inprocess"], (
        "im Frozen-Build zuerst der Kind-Prozess, bei dessen Fehlschlag der "
        "In-Process-Fallback"
    )
