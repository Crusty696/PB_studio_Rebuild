"""Aktions-Rauchtest — welche Registry-Aktion antwortet mit einer Python-Meldung?

Am 2026-09-01 kostete es einen anderthalbstuendigen GUI-Durchlauf, um zu
messen, dass 25 der 62 Chat-Aktionen bei fehlendem Pflichtparameter eine rohe
Meldung der Form ``TypeError: x() missing 1 required positional argument``
bis in die Oberflaeche durchreichen (B-961). Kein Pruefwerkzeug sah das.

Dieses Werkzeug misst dasselbe in Sekunden — und **ohne eine einzige Aktion
auszufuehren**. Das ist keine Sparmassnahme, sondern Notwendigkeit: ein echter
Aufruf von ``create_proxy`` startet 121 Konvertierungen, ``delete_media``
loescht.

Stattdessen wird verglichen, was die Registry beim Ausfuehren taete:

* ``services/action_registry.py`` filtert unbekannte Parameter heraus und ruft
  den Handler mit dem Rest. Eine Pruefung gegen ``param_schema["required"]``
  findet nicht statt.
* Hat der Handler also Parameter ohne Default, wirft Python beim Aufruf mit
  leeren Parametern einen ``TypeError`` — genau den, den der Nutzer zu sehen
  bekommt.

Beides ist aus der Signatur und dem Schema ablesbar.

    python tools/action_smoke.py
    python tools/action_smoke.py --json bericht.json

Exit 1, sobald mindestens eine Aktion so antworten wuerde.
"""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _pflichtparameter(handler) -> list[str]:
    """Parameter ohne Default — genau die, ueber die Python stolpert."""
    try:
        sig = inspect.signature(handler)
    except (TypeError, ValueError):
        return []
    pflicht = []
    for name, param in sig.parameters.items():
        if name in ("self", "cls"):
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if param.default is inspect.Parameter.empty:
            pflicht.append(name)
    return pflicht


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--json", default=None, help="Ergebnis zusaetzlich hierhin schreiben")
    args = p.parse_args()

    # Import erst hier. `import services.actions` allein registriert nichts —
    # gemessen: 0 Aktionen. Die Registrierung passiert erst beim Import der
    # einzelnen Module, weil dort die Dekoratoren und Fabriken stehen.
    from services.action_registry import action_registry
    from services.actions import (  # noqa: F401 — Import registriert die Aktionen
        ai_actions, audio_actions, brain_actions, edit_actions, video_actions,
    )

    aktionen = action_registry.list_actions()
    if not aktionen:
        print("Keine Aktionen in der Registry gefunden — Import fehlgeschlagen?")
        return 0

    roh: list[dict] = []
    sauber: list[str] = []
    for name in aktionen:
        definition = action_registry.get(name)
        if definition is None:
            continue
        pflicht = _pflichtparameter(definition.handler)
        schema = getattr(definition, "param_schema", None) or {}
        deklariert = list(schema.get("required", []))
        if pflicht:
            roh.append({
                "aktion": name,
                "fehlt_beim_aufruf": pflicht,
                "im_schema_deklariert": deklariert,
                "schema_deckt_ab": sorted(deklariert) == sorted(pflicht),
            })
        else:
            sauber.append(name)

    print(f"Aktionen in der Registry : {len(aktionen)}")
    print(f"ohne Pflichtparameter    : {len(sauber)}")
    print(f"mit Pflichtparametern    : {len(roh)}")
    print()
    print("Diese Aktionen wuerfen einen TypeError, wenn die Registry sie mit")
    print("leeren Parametern ausfuehrt (B-961) — sie prueft param_schema['required']")
    print("vor dem Aufruf nicht.")
    print()
    print("Das ist die Registry-Ebene, nicht die Nutzer-Ebene: der Orchestrator")
    print("fuellt manche Felder vorher aus dem Text. Gemessen am 2026-09-01 traf es")
    print("live 25 Aktionen, hier stehen mehr — z.B. search_video, das live")
    print("'5 Treffer fuer \"\"' lieferte, weil query als leerer String ankam.")
    print("Die Liste ist also die Obergrenze, nicht die Trefferzahl.")
    print()
    for e in sorted(roh, key=lambda x: x["aktion"]):
        fehlt = ", ".join(e["fehlt_beim_aufruf"])
        marke = "" if e["schema_deckt_ab"] else "   [Schema weicht ab: %s]" % (
            ", ".join(e["im_schema_deklariert"]) or "nichts deklariert")
        print(f"  {e['aktion']:<28} fehlt: {fehlt}{marke}")

    abweichungen = [e for e in roh if not e["schema_deckt_ab"]]
    if abweichungen:
        print()
        print(f"Davon {len(abweichungen)} mit einem Schema, das die Pflichtfelder nicht")
        print("korrekt abbildet — dort hilft auch eine Schema-Pruefung nicht ohne Nacharbeit.")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"mit_pflicht": roh, "ohne_pflicht": sauber}, indent=2),
            encoding="utf-8",
        )
        print(f"\nJSON: {args.json}")

    print()
    print("Dieses Werkzeug fuehrt keine Aktion aus. Es liest Signatur und Schema.")
    return 1 if roh else 0


if __name__ == "__main__":
    raise SystemExit(main())
