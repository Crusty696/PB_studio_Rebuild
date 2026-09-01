"""Log-Pruefer — liest das App-Log und meldet, was sich dort wiederholt.

Der Pruefstand fand am 2026-09-01 in zwei vollen Laeufen keinen einzigen der
sechs Funde des Tages. Einer davon, B-963, stand 1403 Mal woertlich im Log der
laufenden App: ``OllamaClient: Singleton erstellt``. Kein Werkzeug hat je in
diese Datei gesehen.

Dieses Werkzeug schliesst die Luecke. Es bewertet nichts und kennt die App
nicht — es zaehlt, was sich wiederholt, und legt die Zahlen vor:

* **Wiederholungen**: dieselbe Meldung ueber der Schwelle (Standard 50).
  Ein Singleton, der 1403 Mal entsteht, ist keiner.
* **Fehler**: ERROR-, CRITICAL- und Traceback-Zeilen, nach Text gruppiert.
* **Takt**: Meldungen, die in festem Abstand wiederkehren. Ein Fuenf-Sekunden-
  Takt ueber Stunden ist fast immer eine Schleife, die niemand wollte.

    python tools/log_audit.py
    python tools/log_audit.py --log logs/pb_studio.log --schwelle 50
    python tools/log_audit.py --seit "2026-09-01 07:00"

Exit 1, sobald etwas ueber der Schwelle liegt — damit der Pruefstand es als
Befund fuehrt.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STANDARD_LOG = REPO_ROOT / "logs" / "pb_studio.log"

# 2026-09-01 09:17:17 [INFO    ] services.ollama_client: Text
_ZEILE = re.compile(
    r"^(?P<zeit>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"\[(?P<stufe>\w+)\s*\]\s+(?P<quelle>[\w.]+):\s*(?P<text>.*)$"
)

# Zahlen, Pfade und Hex-Ids rausnehmen, damit "Task 17 fertig" und
# "Task 18 fertig" als dieselbe Meldung zaehlen.
_ZAHL = re.compile(r"\b\d+\b")
_HEX = re.compile(r"\b[0-9a-f]{8,}\b")
_PFAD = re.compile(r"[A-Za-z]:\\[^\s]+|/[^\s]{6,}")


def _muster(text: str) -> str:
    text = _PFAD.sub("<pfad>", text)
    text = _HEX.sub("<id>", text)
    text = _ZAHL.sub("<n>", text)
    return text.strip()[:160]


def _lesen(pfad: Path, seit: datetime | None) -> list[dict]:
    zeilen = []
    with pfad.open("r", encoding="utf-8", errors="replace") as f:
        for roh in f:
            treffer = _ZEILE.match(roh.rstrip("\n").rstrip("\r"))
            if not treffer:
                continue
            zeit = datetime.strptime(treffer["zeit"], "%Y-%m-%d %H:%M:%S")
            if seit and zeit < seit:
                continue
            zeilen.append({
                "zeit": zeit,
                "stufe": treffer["stufe"].strip(),
                "quelle": treffer["quelle"],
                "text": treffer["text"],
                "muster": _muster(treffer["text"]),
            })
    return zeilen


def _takt(zeitpunkte: list[datetime]) -> float | None:
    """Mittlerer Abstand in Sekunden, wenn er regelmaessig ist — sonst None."""
    if len(zeitpunkte) < 5:
        return None
    abstaende = [
        (b - a).total_seconds()
        for a, b in zip(zeitpunkte, zeitpunkte[1:])
        if (b - a).total_seconds() > 0
    ]
    if len(abstaende) < 4:
        return None
    mittel = sum(abstaende) / len(abstaende)
    if mittel <= 0:
        return None
    abweichung = sum(abs(a - mittel) for a in abstaende) / len(abstaende)
    # Regelmaessig heisst: mittlere Abweichung unter einem Viertel des Takts.
    return mittel if abweichung < mittel * 0.25 else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--log", default=str(STANDARD_LOG))
    p.add_argument("--schwelle", type=int, default=50,
                   help="ab wievielen gleichen Meldungen es ein Befund ist")
    p.add_argument("--seit", default=None,
                   help='nur ab diesem Zeitpunkt, z.B. "2026-09-01 07:00"')
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args()

    pfad = Path(args.log)
    if not pfad.exists():
        print(f"Log nicht gefunden: {pfad}")
        return 0  # kein Befund, aber auch keine Aussage

    seit = None
    if args.seit:
        seit = datetime.strptime(args.seit, "%Y-%m-%d %H:%M")

    zeilen = _lesen(pfad, seit)
    if not zeilen:
        print(f"Keine auswertbaren Zeilen in {pfad}")
        return 0

    print(f"Log      : {pfad}")
    print(f"Zeilen   : {len(zeilen)}")
    print(f"Zeitraum : {zeilen[0]['zeit']} bis {zeilen[-1]['zeit']}")
    print(f"Schwelle : {args.schwelle} gleiche Meldungen")
    print()

    befund = False

    zaehler = Counter(z["muster"] for z in zeilen)
    zeiten: dict[str, list[datetime]] = defaultdict(list)
    quelle: dict[str, str] = {}
    for z in zeilen:
        zeiten[z["muster"]].append(z["zeit"])
        quelle.setdefault(z["muster"], z["quelle"])

    ueber = [(m, n) for m, n in zaehler.most_common() if n >= args.schwelle]
    print(f"=== Wiederholungen ueber der Schwelle: {len(ueber)} ===")
    for muster, anzahl in ueber[:args.top]:
        anteil = 100.0 * anzahl / len(zeilen)
        takt = _takt(zeiten[muster])
        takt_text = f", Takt {takt:.1f}s" if takt else ""
        print(f"  {anzahl:>6}x ({anteil:4.1f} %{takt_text})  {quelle[muster]}")
        print(f"          {muster}")
    if ueber:
        befund = True
    if len(ueber) > args.top:
        print(f"  ... ({len(ueber) - args.top} weitere)")
    print()

    fehler = [z for z in zeilen if z["stufe"] in ("ERROR", "CRITICAL")]
    fehler_zaehler = Counter(z["muster"] for z in fehler)
    print(f"=== ERROR/CRITICAL: {len(fehler)} Zeilen, {len(fehler_zaehler)} verschiedene ===")
    for muster, anzahl in fehler_zaehler.most_common(args.top):
        print(f"  {anzahl:>6}x  {muster}")
    if fehler:
        befund = True
    print()

    getaktet = [
        (m, len(t), _takt(t)) for m, t in zeiten.items()
        if len(t) >= 10 and _takt(t) is not None and _takt(t) <= 60
    ]
    getaktet.sort(key=lambda x: -x[1])
    print(f"=== Regelmaessiger Takt unter 60 s: {len(getaktet)} Muster ===")
    for muster, anzahl, takt in getaktet[:args.top]:
        print(f"  {anzahl:>6}x alle {takt:5.1f}s  {muster}")
    if getaktet:
        befund = True

    print()
    print("Dieses Werkzeug bewertet nichts. Ein Befund heisst: hier wiederholt sich")
    print("etwas auffaellig oft — ob das richtig oder falsch ist, entscheidet der Leser.")
    return 1 if befund else 0


if __name__ == "__main__":
    raise SystemExit(main())
