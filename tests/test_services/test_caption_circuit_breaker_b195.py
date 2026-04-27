"""B-195 regression tests — Caption-Circuit-Breaker + SettingsDialog
Modell-Validierung.

Hintergrund: Nach der Conda-Migration (D-029) hat der User im
SettingsDialog ein nicht-installiertes Ollama-Modell gewaehlt
(``tripolskypetr/qwen3.5-uncensored-aggressive:4b``). Resultat:
- Caption-Aufrufe lieferten HTTP 404 (Modell nicht da).
- ``OllamaService.vision()`` returnt bei HTTP-Fehler einen
  ``"Fehler: 404"``-String, kein Exception. Caller versuchte das
  als JSON zu parsen → ``json.JSONDecodeError``.
- Caption-Loop fing das per ``except Exception`` ab — aber lief weiter
  fuer alle 218 Videos. Bei Timeout 15s pro Call: stundenlanger
  Hintergrund-Hang.
- Wenige Sekunden spaeter: 12420ms MouseRelease + nativer SIGSEGV
  (genaue Ursache unklar, aber die 404-Spirale war Trigger).

Diese Tests verifizieren beide Schutzschichten:
1. ``video_analysis_service.analyze_scene_with_caption`` bricht nach 3
   consecutive Failures ab (Circuit-Breaker).
2. ``OllamaService.vision``-String ``"Fehler: <code>"`` wird als
   Failure erkannt — nicht durch JSON-Parser geschickt.
"""

from __future__ import annotations

import inspect

from services import video_analysis_service as vas


def test_caption_loop_has_circuit_breaker_constant() -> None:
    """B-195: Der Caption-Loop muss einen Failure-Threshold definieren.
    Source-Inspection — Konstante ``_CAPTION_FAIL_THRESHOLD`` muss da
    sein und auf einen kleinen Integer (<=10) gesetzt sein.
    """
    src = inspect.getsource(vas.analyze_scene_with_caption)
    assert "_CAPTION_FAIL_THRESHOLD" in src, (
        "B-195: analyze_scene_with_caption() braucht einen Circuit-Breaker-"
        "Schwellwert. Sonst rennt die Pipeline 218x in 15s-Timeouts."
    )
    # Schwellwert sollte konservativ sein (<=10).
    assert any(
        f"_CAPTION_FAIL_THRESHOLD = {n}" in src for n in range(1, 11)
    ), (
        "B-195: _CAPTION_FAIL_THRESHOLD sollte zwischen 1 und 10 liegen."
    )


def test_caption_loop_breaks_on_consecutive_failures() -> None:
    """B-195: Source-Inspection — der Loop muss bei
    ``_consecutive_failures >= _CAPTION_FAIL_THRESHOLD`` mit ``break``
    aussteigen.
    """
    src = inspect.getsource(vas.analyze_scene_with_caption)
    assert "_consecutive_failures" in src
    # Patterns die bei der Implementierung dranbleiben muessen
    assert "_consecutive_failures += 1" in src
    assert "_consecutive_failures = 0" in src, (
        "B-195: Erfolgreiche Caption muss den Failure-Counter reset'en, "
        "sonst loest ein einmaliger Hang am Anfang die Bremse aus."
    )
    # Break nach Threshold-Erreichen
    assert any(
        line.strip() == "break"
        for line in src.splitlines()
        if "break" in line and "Loop" in src[max(0, src.find(line) - 200):src.find(line)]
    ) or src.count("break") >= 3, (
        "B-195: Der Circuit-Breaker muss den Loop per break verlassen."
    )


def test_caption_loop_treats_fehler_string_as_failure() -> None:
    """B-195: ``OllamaService.vision()`` returnt bei HTTP-Fehler einen
    ``"Fehler: <code>"``-String. Frueher wurde das durch json.loads
    geschickt → JSONDecodeError → spaete Diagnose. Wir wollen, dass
    der Caption-Loop diesen String fruehzeitig als Failure erkennt.
    """
    src = inspect.getsource(vas.analyze_scene_with_caption)
    # Erwartete Detection-Heuristik
    assert 'startswith("Fehler:"' in src or 'startswith("Fehler ")' in src, (
        "B-195: Caption-Loop muss \"Fehler:\"-String aus OllamaService.vision "
        "als Failure behandeln, nicht als JSON-parsbare Antwort."
    )


# ---------------------------------------------------------------------------
# SettingsDialog: Modell-Validierung vor Save
# ---------------------------------------------------------------------------


def test_settings_dialog_has_model_validator() -> None:
    """B-195: SettingsDialog muss eine Pre-Save-Validierung haben,
    die das gewaehlte Ollama-Modell gegen die installierten Modelle
    prueft.
    """
    from ui.dialogs import settings_dialog as sd

    assert hasattr(sd.SettingsDialog, "_validate_ollama_model"), (
        "B-195: SettingsDialog._validate_ollama_model fehlt — User kann "
        "ein nicht-installiertes Modell speichern und triggert die "
        "404-Spirale."
    )


def test_settings_dialog_on_accept_calls_validator() -> None:
    """B-195: ``_on_accept`` muss den Validator aufrufen und bei
    User-Cancel ohne Save abbrechen.
    """
    from ui.dialogs import settings_dialog as sd

    src = inspect.getsource(sd.SettingsDialog._on_accept)
    assert "_validate_ollama_model" in src, (
        "B-195: _on_accept ruft den Modell-Validator nicht — Save "
        "passiert ungebremst."
    )
    # Cancel-Pfad: bei Validator==False muss return statt save erfolgen
    assert "return" in src, (
        "B-195: _on_accept braucht einen frueh-return wenn der "
        "Validator False liefert."
    )
