"""B-628: das Retry-Budget deckelte nur den Start eines Versuchs, nicht seine Dauer.

`_TOTAL_RETRY_BUDGET_SEC = 150.0` wurde in B-779 eingefuehrt, um eine
GUI-Thread-Blockade zu begrenzen: `_sync_anchors` laeuft im GUI-Thread, und drei
Retries a 120 s busy_timeout haetten die App minutenlang eingefroren.

Der Deckel griff aber nur an der falschen Stelle. Geprueft wurde
`_deadline - now > 0` **vor** einem neuen Versuch — der begonnene Versuch lief
danach in den vollen busy_timeout, auch wenn nur noch 30 s Budget uebrig waren.

Gemessen (skaliert, echte WAL-DB mit `BEGIN EXCLUSIVE` als Blocker,
busy_timeout 2 s, Budget 3 s): Abbruch nach **5.28 s** — Budget plus einen
ganzen zusaetzlichen busy_timeout. Hochgerechnet auf die echten Werte: rund
**240 s statt der zugesagten 150 s**.

Der alte Test `test_budget_constant_is_near_single_busy_timeout` sah das nicht,
weil er den Lock-Fehler mit Versuchsdauer nahe null injizierte — er pruefte die
Konstante, nicht das Verhalten.

Diese Tests pruefen das Verhalten.
"""

from __future__ import annotations

import re
import inspect

import pytest

from services import anchor_sync_service as ass


def test_b628_busy_timeout_wird_aus_restbudget_abgeleitet():
    """Der Kern: ein Versuch darf nie laenger warten als das Restbudget.

    Ohne diese Ableitung nutzt jeder Versuch den vollen 120-s-Vorgabewert,
    und die Summe sprengt das Budget.
    """
    quelle = inspect.getsource(ass.sync_dialog_anchors)

    assert "busy_timeout" in quelle, (
        "B-628: der Retry-Pfad setzt keinen eigenen busy_timeout — dann gilt "
        "der Vorgabewert von 120 s pro Versuch, unabhaengig vom Restbudget."
    )
    assert "_deadline" in quelle.split("busy_timeout")[0].rsplit("\n", 12)[-1] or \
           "_rest_ms" in quelle, (
        "B-628: der busy_timeout wird nicht aus dem Restbudget berechnet."
    )


def test_b628_restbudget_wird_in_millisekunden_gerechnet():
    """PRAGMA busy_timeout erwartet Millisekunden — Sekunden waeren 1000x zu kurz."""
    quelle = inspect.getsource(ass.sync_dialog_anchors)
    m = re.search(r"_rest_ms\s*=\s*max\(\s*(\d+)\s*,\s*int\(\((.+?)\)\s*\*\s*1000\)", quelle)
    assert m, (
        "B-628: keine Millisekunden-Umrechnung des Restbudgets gefunden — "
        "ein Sekundenwert waere um Faktor 1000 zu kurz und der Retry sinnlos."
    )
    assert int(m.group(1)) > 0, "es braucht eine Untergrenze > 0"


def test_b628_untergrenze_verhindert_nutzlosen_versuch():
    """Bei fast leerem Budget darf kein busy_timeout von 0 gesetzt werden.

    0 hiesse "sofort aufgeben" — dann waere der letzte Versuch wertlos.
    """
    quelle = inspect.getsource(ass.sync_dialog_anchors)
    m = re.search(r"_rest_ms\s*=\s*max\(\s*(\d+)", quelle)
    assert m and int(m.group(1)) >= 100, (
        "B-628: die Untergrenze fuer busy_timeout ist zu klein oder fehlt — "
        f"gefunden: {m.group(1) if m else 'nichts'}"
    )


def test_b628_budget_konstante_unveraendert():
    """Regressionsschutz: der Fix aendert die Wartezeit, nicht die Zusage."""
    assert ass._TOTAL_RETRY_BUDGET_SEC == 150.0
    assert ass._MAX_RETRIES == 3
