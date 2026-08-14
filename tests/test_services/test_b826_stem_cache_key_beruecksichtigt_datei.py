"""B-826: der Stem-Audio-Cache ignoriert, WELCHE Datei geladen wurde.

`_stem_audio_cache` in `services/pacing_beat_grid.py` ist modul-global und
wird nur mit `audio_id` und `stem_name` gekeyt — der Pfad geht nicht ein.
Aendert sich der Inhalt unter derselben `audio_id`, liefert der Cache
weiterhin das alte Audio.

Das ist kein Randfall:

- Die Stem-Selbstheilung schreibt bei fehlendem Artefakt neue Stems an
  denselben Pfad (live belegt am 2026-08-14). Danach rechnet Pacing mit dem
  alten Signal weiter.
- Seit B-822/B-824 kann dieselbe `audio_id` in einer Projektkopie auf einen
  ganz anderen Ort zeigen.
- In der Testsuite verschmutzten sich Tests gegenseitig: derselbe Cache
  ueberlebt Testgrenzen, weil er am Modul haengt.

Genau dieses Testsymptom wurde unter B-823 zuerst einem fehlenden RNG-Seed
zugeschrieben. Der Seed hat den Test nicht stabilisiert — die Ursache lag hier.
"""

from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from services import pacing_beat_grid as pbg


@pytest.fixture(autouse=True)
def _sauberer_cache():
    pbg.invalidate_pacing_caches()
    yield
    pbg.invalidate_pacing_caches()


def _schreibe_ton(pfad, amplitude: float, sr: int = 22050, sekunden: float = 1.0):
    n = int(sr * sekunden)
    signal = np.full(n, amplitude, dtype=np.float32)
    sf.write(str(pfad), signal, sr)
    return pfad


def test_b826_anderer_pfad_liefert_anderes_audio(tmp_path):
    """Zwei Projektkopien, dieselbe audio_id — es muss die richtige Datei kommen."""
    leise = _schreibe_ton(tmp_path / "leise.wav", 0.01)
    laut = _schreibe_ton(tmp_path / "laut.wav", 0.5)

    y1, _ = pbg._get_cached_stem_audio(1, str(leise), "vocals")
    y2, _ = pbg._get_cached_stem_audio(1, str(laut), "vocals")

    assert float(np.abs(y1).mean()) < 0.1
    assert float(np.abs(y2).mean()) > 0.3, (
        "B-826: der Cache lieferte fuer einen anderen Pfad das alte Audio — "
        "der Pfad geht nicht in den Schluessel ein."
    )


def test_b826_neu_geschriebene_datei_wird_neu_geladen(tmp_path):
    """Der Fall aus der Stem-Selbstheilung: gleicher Pfad, neuer Inhalt."""
    pfad = _schreibe_ton(tmp_path / "vocals.wav", 0.01)
    y1, _ = pbg._get_cached_stem_audio(2, str(pfad), "vocals")
    assert float(np.abs(y1).mean()) < 0.1

    # Wie nach einer Neuseparation: dieselbe Datei, anderer Inhalt.
    import time
    time.sleep(0.01)
    _schreibe_ton(pfad, 0.5)

    y2, _ = pbg._get_cached_stem_audio(2, str(pfad), "vocals")
    assert float(np.abs(y2).mean()) > 0.3, (
        "B-826: nach dem Neuschreiben derselben Datei kam das alte Signal "
        "aus dem Cache — die Stem-Selbstheilung wirkt sich damit nicht aufs "
        "Pacing aus."
    )


def test_b826_unveraenderte_datei_wird_weiter_gecacht(tmp_path):
    """Gegenprobe: der Cache darf nicht wirkungslos werden.

    Sonst waere der Fix nur ein teurer Weg, ihn abzuschalten — er soll ja
    gerade die vier librosa-Loads pro Auto-Edit sparen.
    """
    pfad = _schreibe_ton(tmp_path / "vocals.wav", 0.2)
    aufrufe = {"n": 0}

    import librosa
    original = librosa.load

    def _zaehlend(*args, **kwargs):
        aufrufe["n"] += 1
        return original(*args, **kwargs)

    librosa.load = _zaehlend
    try:
        pbg._get_cached_stem_audio(3, str(pfad), "vocals")
        pbg._get_cached_stem_audio(3, str(pfad), "vocals")
        pbg._get_cached_stem_audio(3, str(pfad), "vocals")
    finally:
        librosa.load = original

    assert aufrufe["n"] == 1, (
        f"unveraenderte Datei wurde {aufrufe['n']}x geladen statt einmal — "
        "der Cache greift nicht mehr"
    )
