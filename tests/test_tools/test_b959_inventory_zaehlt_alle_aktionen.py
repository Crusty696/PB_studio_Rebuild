"""B-959 — inventory_audit zaehlte 57 Aktionen, die App kennt 62.

Der Suchausdruck fand nur den Dekorator ``@action_registry.register``. Fuenf
Audio-Aktionen entstehen in ``services/actions/audio_actions.py`` ueber die
Fabrik ``_make_enqueue_action(name=...)`` und fehlten deshalb.

Das war mehr als eine falsche Zahl: Aussagen wie "aktionen_ohne_worker: 2"
galten nur fuer die 57 gesehenen. Fuer die fuenf ungesehenen konnte das Werkzeug
grundsaetzlich keinen Befund melden - und meldete stattdessen nichts, was sich
wie "geprueft" liest.

Dieser Test kam nach dem Fix dazu: ``tools/fix_ohne_test.py`` meldete am
2026-09-02, dass B-959 im Produktivcode steht, aber in keinem Test vorkommt.
Dasselbe Muster wie bei B-963 und B-964 - drittes Mal an einem Tag.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def aktionen_im_code() -> set[str]:
    """Die Namen, die tools/inventory_audit.py im Quelltext findet."""
    import importlib.util

    pfad = REPO_ROOT / "tools" / "inventory_audit.py"
    spec = importlib.util.spec_from_file_location("_inv_audit", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)

    quelle = modul._quelltext_gesamt("services")
    return set(modul._AKTION.findall(quelle))


@pytest.fixture(scope="module")
def aktionen_zur_laufzeit() -> set[str]:
    """Die Namen, die die Registry beim Import der Aktionsmodule kennt."""
    from services.action_registry import action_registry
    from services.actions import (  # noqa: F401 — Import registriert
        ai_actions, audio_actions, brain_actions, edit_actions, video_actions,
    )

    return set(action_registry.list_actions())


def test_der_ausdruck_findet_genauso_viele_wie_die_registry(
    aktionen_im_code, aktionen_zur_laufzeit
):
    """Der Kern des Befunds: 57 gegen 62.

    Beide Mengen muessen uebereinstimmen. Weicht der Quelltext-Scan ab, meldet
    das Werkzeug fuer die Differenz grundsaetzlich nichts - und Schweigen liest
    sich wie Unbedenklichkeit.
    """
    fehlend = aktionen_zur_laufzeit - aktionen_im_code

    assert not fehlend, (
        f"inventory_audit findet {len(fehlend)} Aktionen nicht: {sorted(fehlend)}"
    )


@pytest.mark.parametrize("name", [
    "detect_key", "analyze_lufs", "classify_audio",
    "analyze_spectral", "detect_structure",
])
def test_die_fabrik_aktionen_werden_gefunden(name, aktionen_im_code):
    """Genau die fuenf, die im urspruenglichen Befund fehlten."""
    assert name in aktionen_im_code


def test_der_ausdruck_kennt_beide_registrierungswege():
    """Quellcode-Guard: ohne die Fabrik faellt die Zahl wieder auf 57."""
    quelle = (REPO_ROOT / "tools" / "inventory_audit.py").read_text(
        encoding="utf-8", errors="replace")
    block = quelle.split("_AKTION = re.compile(", 1)[1].split(")", 1)[0]

    assert "action_registry" in block
    assert "_make_enqueue_action" in block


def test_die_fabrik_registriert_wirklich_ueber_den_dekorator():
    """Beleg fuer die Ursache, nicht nur fuer das Symptom.

    Die fuenf Aktionen fehlten, weil ihr Registrierungsaufruf im Quelltext
    anders heisst — nicht, weil sie anders registriert wuerden.
    """
    quelle = (REPO_ROOT / "services" / "actions" / "audio_actions.py").read_text(
        encoding="utf-8", errors="replace")

    assert "_make_enqueue_action(" in quelle
    assert re.search(r"name\s*=\s*[\"']detect_key[\"']", quelle)
