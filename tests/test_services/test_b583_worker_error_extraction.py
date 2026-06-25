"""B-583: zentrale, robuste Fehler-Extraktion aus Worker-error-Signalen.

Worker-error-Signale sind nicht einheitlich (Signal(str) vs Signal(int, str)).
extract_worker_error_message muss IMMER den Text liefern, auch bei einer
kuenftigen Signal(str, int)-Signatur, die das alte str(args[-1]) als Zahl
fehlinterpretiert haette.
"""
import logging

from services.task_manager import extract_worker_error_message


def test_empty_args_returns_generic():
    assert extract_worker_error_message(()) == "Unbekannter Fehler"


def test_single_string_signal_str():
    # Signal(str) — import_export.ExportWorker
    assert extract_worker_error_message(("Encode fehlgeschlagen",)) == "Encode fehlgeschlagen"


def test_int_then_string_signal_int_str():
    # Signal(int, str) — audio/video/audio_analysis Worker (haeufigster Fall)
    assert extract_worker_error_message((42, "Datei nicht gefunden")) == "Datei nicht gefunden"


def test_string_then_int_signal_str_int_picks_text_not_number():
    # Die gefaehrliche Signatur: altes str(args[-1]) haette "7" geliefert.
    assert extract_worker_error_message(("Stem-Trennung abgebrochen", 7)) == "Stem-Trennung abgebrochen"


def test_no_string_arg_falls_back_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        result = extract_worker_error_message((500,))
    assert result == "500"
    assert any("unerwartete Signatur" in rec.message or "unerwartete Signatur" in rec.getMessage()
               for rec in caplog.records)


def test_multiple_strings_returns_last_string():
    # Letztes String-Arg = der eigentliche Text (Konvention der Consumer).
    assert extract_worker_error_message(("ctx", 1, "echte Meldung")) == "echte Meldung"
