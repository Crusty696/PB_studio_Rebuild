"""Inventar statt Suche: zaehlt auf, was es gibt, und wer es benutzt.

Anlass (2026-08-31): An denselben Stellen kamen ueber den Tag in vier Wellen
immer neue Befunde. Grund war nicht Unaufmerksamkeit allein, sondern die
Methode — es wurde *Spuren gefolgt* statt *abgezaehlt*. Wer sucht, findet in
Wellen; wer zaehlt, ist fertig.

Beispiele, die nacheinander statt gemeinsam auffielen:

* B-932/B-933/B-950 — Knopf oder Container unsichtbar, Handler trotzdem
  verdrahtet. Im Code-Review nicht auffindbar, weil dort nur nach *sichtbaren*
  Attrappen gesucht wurde.
* B-937 — ``StatusStrip.set_status`` hatte null Aufrufer.
* B-941 — sechs von elf Spalten der Stil-Presets hatten keinen Leser.
* B-940 — Chat-Aktionen ohne registrierten Worker.
* B-947 — Wert an den Konstruktor gereicht und nie gezeichnet.

Jeder Pruefer hier liefert eine **vollstaendige Liste mit Zahlen**, keinen
Bericht mit Fundstuecken. Wiederholbar, damit beim naechsten Lauf die Differenz
sichtbar wird.

Gebrauch::

    python tools/inventory_audit.py                 # alle Pruefer
    python tools/inventory_audit.py --pruefer widgets spalten
    python tools/inventory_audit.py --json inventar.json
    python tools/inventory_audit.py --vergleich alt.json

Grenze, die dieses Werkzeug nicht ueberschreitet: es prueft *ob etwas
existiert, sichtbar ist, verdrahtet ist, gelesen wird* — nicht, **ob es das
Richtige tut**. Ein Anker, der auf den falschen Clip zeigt (B-939), ist hier
unauffaellig: alles verdrahtet, nur das Ergebnis falsch.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Knopf-Beschriftungen enthalten Symbole (Hamburger-Menue, Pfeile), die die
# Windows-Konsole in cp1252 nicht darstellen kann. Ohne das bricht die Ausgabe
# mitten im Bericht ab.
for _strom in (sys.stdout, sys.stderr):
    try:
        _strom.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

# Verzeichnisse, die nie Produktivcode enthalten.
_IGNORIEREN = ("__pycache__", "tests", "docs", ".git", "build", "dist", "storage")


def _py_dateien(*unterordner: str) -> list[Path]:
    treffer: list[Path] = []
    for ordner in unterordner:
        wurzel = REPO_ROOT / ordner
        if not wurzel.is_dir():
            continue
        for pfad in wurzel.rglob("*.py"):
            if any(teil in pfad.parts for teil in _IGNORIEREN):
                continue
            treffer.append(pfad)
    return sorted(treffer)


def _testquelltext() -> str:
    """Alles unter tests/ — als eigener Topf, nicht mit dem Produktivcode."""
    wurzel = REPO_ROOT / "tests"
    if not wurzel.is_dir():
        return ""
    return "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in sorted(wurzel.rglob("*.py"))
    )


def _quelltext_gesamt(*unterordner: str) -> str:
    return "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in _py_dateien(*unterordner)
    )


# ────────────────────────────────────────────────────────────────────────────
# 1. Widgets: was steht auf dem Schirm, was nicht
# ────────────────────────────────────────────────────────────────────────────

# (Modul, Klasse, Konstruktor-Argumente)
_WORKSPACES = (
    ("ui.workspaces.media_workspace", "MediaWorkspace", ()),
    ("ui.workspaces.deliver_workspace", "DeliverWorkspace", ()),
    ("ui.workspaces.convert_workspace", "ConvertWorkspace", ()),
    ("ui.workspaces.schnitt.editor_view", "SchnittEditorView", ()),
    ("ui.workspaces.schnitt.tab_pacing_anker", "SchnittTabPacingAnker", ()),
    ("ui.workspaces.schnitt.tab_notizen", "SchnittTabNotizen", ()),
)


def pruefer_widgets() -> dict:
    """Jeder Knopf im Qt-Baum mit Sichtbarkeit — inklusive versteckter Vorfahren.

    Findet die Klasse B-932 (Knopf ausgegraut), B-933 (Container mit
    WA_DontShowOnScreen) und B-950 (Container setVisible(False), nie
    zurueckgeschaltet).
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QAbstractButton, QAbstractItemView, QApplication, QStackedWidget,
        QTabWidget,
    )

    app = QApplication.instance() or QApplication([])  # noqa: F841

    knoepfe: list[dict] = []
    fehler: list[str] = []
    offen: list = []  # haelt Referenzen, damit Qt nichts vorzeitig abraeumt
    verworfen = 0     # Knoepfe, die Qt waehrend der Pruefung abgeraeumt hat
    qt_intern = 0     # von Qt selbst gebaute Tabellen-Knoepfe

    for modulname, klassenname, args in _WORKSPACES:
        try:
            modul = __import__(modulname, fromlist=[klassenname])
            widget = getattr(modul, klassenname)(*args)
        except Exception as exc:  # noqa: BLE001 — ein kaputter Workspace stoppt nicht alles
            fehler.append(f"{modulname}.{klassenname}: {exc}")
            continue

        # findChildren allein genuegt nicht: Teile des Aufbaus haengen als
        # eigenstaendiger Baum (SectionTabs.parentWidget() ist None) und sind
        # damit keine Qt-Kinder des Workspace. Genau dort sass B-950 —
        # btn_auto_duck fehlte in findChildren und wurde deshalb im ersten
        # Wurf dieses Pruefers uebersehen. Attribute mitnehmen.
        gesammelt = list(widget.findChildren(QAbstractButton))
        bekannt = {id(k) for k in gesammelt}
        for wert in list(vars(widget).values()):
            if isinstance(wert, QAbstractButton) and id(wert) not in bekannt:
                gesammelt.append(wert)
                bekannt.add(id(wert))

        # Ohne show() ist JEDES Widget "hidden" — dann meldet der Pruefer alles
        # und damit nichts. Erst nach dem Zeigen bedeutet isHidden() das, was
        # hier interessiert: jemand hat setVisible(False) gerufen und nie
        # zurueckgenommen. Abgekoppelte Teilbaeume (parentWidget() is None)
        # brauchen ein eigenes show(), sonst entsteht genau das Falsch-Positiv,
        # das dieser Pruefer im zweiten Wurf fuer Auto-Ducking lieferte.
        widget.show()
        # Manche Knoepfe raeumt der Workspace selbst ab (Zell-Widgets in
        # Tabellen). Jeder Qt-Zugriff darauf wirft RuntimeError — abfangen,
        # zaehlen, weitermachen. Sonst bricht der ganze Pruefer an einem
        # einzelnen geloeschten QToolButton ab.
        lebend = []
        for knopf in gesammelt:
            try:
                wurzel = knopf
                while wurzel.parentWidget() is not None:
                    wurzel = wurzel.parentWidget()
                if wurzel is not widget and not wurzel.isVisible():
                    wurzel.show()
                lebend.append(knopf)
            except RuntimeError:
                verworfen += 1

        for knopf in lebend:
          try:
            # Qt baut in Tabellen eigene Knoepfe (Ecke, Kopfzeilen). Die sind
            # kein Produktcode und immer versteckt — ohne diesen Filter melden
            # sie sich als vier anonyme "selbst versteckt"-Treffer.
            eltern_direkt = knopf.parentWidget()
            if isinstance(eltern_direkt, QAbstractItemView) or (
                eltern_direkt is not None
                and isinstance(eltern_direkt.parentWidget(), QAbstractItemView)
            ):
                qt_intern += 1
                continue
            hart_versteckt: list[str] = []
            in_reiter = False
            knoten = knopf.parentWidget()
            while knoten is not None and knoten is not widget:
                eltern = knoten.parentWidget()
                # Eine Seite in QStackedWidget/QTabWidget ist versteckt, weil
                # gerade eine andere Seite oben liegt — das ist normal und darf
                # nicht als Befund gelten. Sonst ersaeuft der echte Fall
                # (B-950: Container per setVisible(False) stillgelegt) im Rauschen:
                # im ersten Lauf meldete der Pruefer 49 von 97 Knoepfen.
                if isinstance(eltern, (QStackedWidget, QTabWidget)):
                    in_reiter = True
                    knoten = eltern
                    continue
                name = knoten.objectName() or knoten.__class__.__name__
                if knoten.isHidden():
                    hart_versteckt.append(name)
                if knoten.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen):
                    hart_versteckt.append(f"{name}(WA_DontShowOnScreen)")
                knoten = eltern

            knoepfe.append({
                "workspace": klassenname,
                # Icon-Knoepfe haben keinen Text; ohne Ersatzname stehen in der
                # Liste lauter "?" und der Befund ist nicht zuzuordnen.
                "text": (knopf.text() or knopf.accessibleName()
                         or knopf.toolTip()[:40] or knopf.objectName()
                         or f"<{knopf.__class__.__name__} ohne Beschriftung>"),
                "objektname": knopf.objectName(),
                # Ein Knopf auf einer inaktiven Reiterseite ist normal versteckt.
                # Ein Knopf, dessen direkter Parent sichtbar waere, wurde dagegen
                # explizit stillgelegt — das zaehlt auch innerhalb eines Reiters.
                "selbst_versteckt": bool(
                    knopf.isHidden()
                    and not in_reiter
                    or (knopf.isHidden()
                        and knopf.parentWidget() is not None
                        and not knopf.parentWidget().isHidden())
                ),
                "aktiv": knopf.isEnabled(),
                "hart_versteckte_vorfahren": hart_versteckt,
                "liegt_in_reiter": in_reiter,
            })
          except RuntimeError:
            verworfen += 1
        # Kein deleteLater: show() laesst Qt Events verarbeiten, dabei wuerden
        # bereits eingeplante Loeschungen greifen und der naechste Workspace
        # liefe in "Internal C++ object already deleted". Die Widgets bleiben
        # bis Prozessende am Leben — das Werkzeug ist ein kurzer Einmal-Lauf.
        offen.append(widget)

    unerreichbar = [
        k for k in knoepfe if k["selbst_versteckt"] or k["hart_versteckte_vorfahren"]
    ]
    inaktiv = [k for k in knoepfe if not k["aktiv"] and k not in unerreichbar]

    return {
        "geprueft": len(knoepfe),
        "unerreichbar": len(unerreichbar),
        "dauerhaft_inaktiv": len(inaktiv),
        "in_reiter_normal_versteckt": sum(1 for k in knoepfe if k["liegt_in_reiter"]),
        "waehrend_der_pruefung_abgeraeumt": verworfen,
        "qt_intern_uebersprungen": qt_intern,
        "fehler_beim_bauen": fehler,
        "details_unerreichbar": [
            f"{k['workspace']}.{k['text'] or k['objektname'] or '?'}"
            + (f" (Vorfahr: {', '.join(k['hart_versteckte_vorfahren'])})"
               if k["hart_versteckte_vorfahren"] else " (selbst versteckt)")
            for k in unerreichbar
        ],
        "details_inaktiv": [
            f"{k['workspace']}.{k['text'] or k['objektname'] or '?'}" for k in inaktiv
        ],
    }


# ────────────────────────────────────────────────────────────────────────────
# 2. Datenbank-Spalten ohne Leser
# ────────────────────────────────────────────────────────────────────────────

_SPALTE = re.compile(r"^\s{4}(\w+)\s*=\s*Column\(", re.M)
_KLASSE = re.compile(r"^class\s+(\w+)\(Base\)", re.M)


def pruefer_spalten() -> dict:
    """Jede ORM-Spalte: wird sie irgendwo ausserhalb des Modells gelesen?

    Findet die Klasse B-941 (sechs Preset-Spalten ohne Leser) und B-931
    (Spalte existiert, wird nie gefuellt).
    """
    modelle = REPO_ROOT / "database" / "models.py"
    if not modelle.is_file():
        return {"fehler": "database/models.py nicht gefunden"}

    text = modelle.read_text(encoding="utf-8", errors="ignore")
    zeilen = text.splitlines()

    # Spalte -> Tabelle zuordnen
    klassen_zeilen = [(m.start(), m.group(1)) for m in _KLASSE.finditer(text)]

    def klasse_fuer(pos: int) -> str:
        aktuell = "?"
        for start, name in klassen_zeilen:
            if start <= pos:
                aktuell = name
            else:
                break
        return aktuell

    spalten: list[tuple[str, str]] = []
    for m in _SPALTE.finditer(text):
        spalten.append((klasse_fuer(m.start()), m.group(1)))

    # Leser: irgendein ".spaltenname" ausserhalb von models.py und migrations
    verbrauch = _quelltext_gesamt("services", "ui", "workers", "agents", "database")
    verbrauch = verbrauch.replace(text, "")  # models.py selbst ausklammern

    ohne_leser: list[str] = []
    nur_geschrieben: list[str] = []

    for tabelle, spalte in spalten:
        if spalte == "id":
            continue
        gefunden = re.escape(spalte)
        # Gelesen: als Attribut oder Schluesselname (obj.spalte, "spalte")
        wird_gelesen = re.search(r"[.\"']" + gefunden + r"\b", verbrauch)
        # Geschrieben: als Schluesselwort-Argument beim Anlegen (spalte=...)
        # Das ist der Fall AgentFeedback.ai_response — Daten werden gesammelt
        # und nie ausgewertet. Ohne diese Trennung sieht das aus wie eine
        # unbenutzte Spalte, obwohl bei jedem Feedback hineingeschrieben wird.
        wird_geschrieben = re.search(r"\b" + gefunden + r"\s*=", verbrauch)

        if wird_gelesen:
            continue
        if wird_geschrieben:
            nur_geschrieben.append(f"{tabelle}.{spalte}")
        else:
            ohne_leser.append(f"{tabelle}.{spalte}")

    return {
        "spalten_gesamt": len(spalten),
        "ohne_leser": len(ohne_leser),
        "geschrieben_aber_nie_gelesen": len(nur_geschrieben),
        "details": sorted(ohne_leser),
        "details_nur_geschrieben": sorted(nur_geschrieben),
    }


# ────────────────────────────────────────────────────────────────────────────
# 3. Chat-Aktionen ohne Worker
# ────────────────────────────────────────────────────────────────────────────

_AKTION = re.compile(r'@action_registry\.register\(\s*\n?\s*name\s*=\s*["\'](\w+)["\']')
_WORKER = re.compile(r'register_worker\(\s*\n?\s*["\'](\w+)["\']')
_SIGNAL = re.compile(r'agent_command_signal\.emit\(\s*["\'](\w+)["\']')


def pruefer_aktionen() -> dict:
    """Chat-Aktionen, die einen Worker anstossen, den es nicht gibt.

    Findet die Klasse B-940 (auto_ducking/convert_videos nie registriert).
    """
    aktionen_quelle = _quelltext_gesamt("services")
    worker_quelle = _quelltext_gesamt("workers")

    aktionen = set(_AKTION.findall(aktionen_quelle))
    registriert = set(_WORKER.findall(worker_quelle))
    angestossen = set(_SIGNAL.findall(aktionen_quelle))

    ohne_worker = sorted(angestossen - registriert)

    return {
        "aktionen_gesamt": len(aktionen),
        "worker_registriert": len(registriert),
        "aktionen_die_worker_anstossen": len(angestossen),
        "ohne_worker": len(ohne_worker),
        "details": ohne_worker,
    }


# ────────────────────────────────────────────────────────────────────────────
# 4. Oeffentliche Methoden ohne Aufrufer
# ────────────────────────────────────────────────────────────────────────────

_NIE_TOT = {
    "run", "main", "setUp", "tearDown", "paintEvent", "resizeEvent", "closeEvent",
    "showEvent", "hideEvent", "mousePressEvent", "mouseMoveEvent", "keyPressEvent",
    "mouseReleaseEvent", "wheelEvent", "dragEnterEvent", "dropEvent", "eventFilter",
    "sizeHint", "minimumSizeHint", "enterEvent", "leaveEvent", "contextMenuEvent",
    "mouseDoubleClickEvent", "focusInEvent", "focusOutEvent", "changeEvent",
}


def pruefer_methoden() -> dict:
    """Oeffentliche Methoden in ui/widgets, die niemand ruft.

    Findet die Klasse B-937 (``StatusStrip.set_status`` mit null Aufrufern).
    """
    dateien = _py_dateien("ui/widgets")
    gesamtquelle = _quelltext_gesamt("services", "ui", "workers", "agents", "main.py")
    # Tests getrennt halten: eine Methode, die nur ein Test ruft, ist keine
    # tote Methode, sondern eine Pruefschnittstelle. Ohne die Trennung
    # standen vier solche Faelle faelschlich in derselben Liste wie echter
    # toter Code.
    testquelle = _testquelltext()

    ohne_aufrufer: list[str] = []
    nur_tests: list[str] = []
    gesamt = 0

    for pfad in dateien:
        try:
            baum = ast.parse(pfad.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.ClassDef):
                continue
            for element in knoten.body:
                if not isinstance(element, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                name = element.name
                if name.startswith("_") or name in _NIE_TOT:
                    continue
                gesamt += 1

                # Eine @property wird als ".name" gelesen, nie als ".name(".
                # Ohne diese Unterscheidung meldet der Pruefer jede Property
                # als tot — im ersten Lauf waren 7 der 14 Treffer genau das.
                dekoratoren = {
                    d.id if isinstance(d, ast.Name) else getattr(d, "attr", "")
                    for d in element.decorator_list
                }
                ist_property = bool(
                    dekoratoren & {"property", "cached_property", "setter"})

                if ist_property:
                    muster = r"\." + re.escape(name) + r"\b(?!\s*\()"
                else:
                    muster = r"\." + re.escape(name) + r"\s*\("
                treffer = len(re.findall(muster, gesamtquelle))
                treffer += len(re.findall(
                    r"connect\([^)]*\." + re.escape(name) + r"\b",
                    gesamtquelle))
                if treffer == 0:
                    eintrag = f"{pfad.relative_to(REPO_ROOT)}::{knoten.name}.{name}"
                    if re.search(muster, testquelle):
                        nur_tests.append(eintrag)
                    else:
                        ohne_aufrufer.append(eintrag)

    return {
        "methoden_geprueft": gesamt,
        "ohne_aufrufer": len(ohne_aufrufer),
        "nur_von_tests_benutzt": len(nur_tests),
        "details": sorted(ohne_aufrufer),
        "details_nur_tests": sorted(nur_tests),
    }


# ────────────────────────────────────────────────────────────────────────────
# 5. Konstruktor-Werte, die nie verwendet werden
# ────────────────────────────────────────────────────────────────────────────

def pruefer_konstruktorwerte() -> dict:
    """``self._x = x`` im __init__, danach nirgends im Modul gelesen.

    Findet die Klasse B-947 (Genre an die Karte gereicht, nie gezeichnet).
    """
    tote: list[str] = []
    gesamt = 0

    for pfad in _py_dateien("ui"):
        quelle = pfad.read_text(encoding="utf-8", errors="ignore")
        try:
            baum = ast.parse(quelle)
        except SyntaxError:
            continue
        for klasse in [k for k in ast.walk(baum) if isinstance(k, ast.ClassDef)]:
            init = next(
                (e for e in klasse.body
                 if isinstance(e, ast.FunctionDef) and e.name == "__init__"), None)
            if init is None:
                continue
            parameter = {a.arg for a in init.args.args} - {"self"}
            for knoten in ast.walk(init):
                if not isinstance(knoten, ast.Assign):
                    continue
                for ziel in knoten.targets:
                    if not (isinstance(ziel, ast.Attribute)
                            and isinstance(ziel.value, ast.Name)
                            and ziel.value.id == "self"):
                        continue
                    # nur Zuweisungen aus einem Konstruktor-Parameter
                    quelle_namen = {n.id for n in ast.walk(knoten.value)
                                    if isinstance(n, ast.Name)}
                    if not (quelle_namen & parameter):
                        continue
                    feld = ziel.attr
                    gesamt += 1
                    # Wie oft wird self.feld sonst noch gelesen?
                    treffer = len(re.findall(rf"self\.{re.escape(feld)}\b", quelle))
                    if treffer <= 1:  # nur die Zuweisung selbst
                        tote.append(
                            f"{pfad.relative_to(REPO_ROOT)}::{klasse.name}.{feld}")

    return {
        "konstruktorwerte_geprueft": gesamt,
        "nie_gelesen": len(tote),
        "details": sorted(tote),
    }


PRUEFER = {
    "widgets": pruefer_widgets,
    "spalten": pruefer_spalten,
    "aktionen": pruefer_aktionen,
    "methoden": pruefer_methoden,
    "konstruktorwerte": pruefer_konstruktorwerte,
}

# Welcher Pruefer haette welchen bekannten Bug gefunden — dient dem Nachweis,
# dass die Pruefer wirken, statt nur zu laufen (tests/test_tools/).
BEKANNTE_FAELLE = {
    "widgets": "B-932 (ausgegraut), B-933 (WA_DontShowOnScreen), B-950 (Container versteckt)",
    "spalten": "B-941 (6 von 11 Preset-Spalten ohne Leser), B-931 (Spalte nie gefuellt)",
    "aktionen": "B-940 (auto_ducking/convert_videos ohne Worker)",
    "methoden": "B-937 (StatusStrip.set_status ohne Aufrufer)",
    "konstruktorwerte": "B-947 (Genre durchgereicht, nie gezeichnet)",
}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pruefer", nargs="*", choices=sorted(PRUEFER), default=None)
    p.add_argument("--json", default=None, help="Ergebnis hierhin schreiben")
    p.add_argument("--vergleich", default=None, help="frueheres Ergebnis zum Abgleich")
    p.add_argument("--details", action="store_true", help="alle Fundstellen auflisten")
    args = p.parse_args()

    ausgewaehlt = args.pruefer or sorted(PRUEFER)
    ergebnis: dict = {}

    for name in ausgewaehlt:
        print(f"\n=== {name} ===")
        print(f"    findet: {BEKANNTE_FAELLE.get(name, '?')}")
        try:
            werte = PRUEFER[name]()
        except Exception as exc:  # noqa: BLE001 — ein Pruefer stoppt nicht alle
            print(f"    FEHLER: {exc}")
            ergebnis[name] = {"fehler": str(exc)}
            continue
        ergebnis[name] = werte
        for schluessel, wert in werte.items():
            if schluessel.startswith("details"):
                continue
            print(f"    {schluessel}: {wert}")
        for schluessel, wert in werte.items():
            if not schluessel.startswith("details") or not wert:
                continue
            grenze = None if args.details else 10
            for eintrag in wert[:grenze]:
                print(f"      - {eintrag}")
            if grenze and len(wert) > grenze:
                print(f"      ... {len(wert) - grenze} weitere (--details)")

    if args.vergleich:
        alt = json.loads(Path(args.vergleich).read_text(encoding="utf-8"))
        print("\n=== Vergleich ===")
        for name, werte in ergebnis.items():
            frueher = alt.get(name, {})
            for schluessel, wert in werte.items():
                if schluessel.startswith("details") or not isinstance(wert, int):
                    continue
                vorher = frueher.get(schluessel)
                if vorher is not None and vorher != wert:
                    pfeil = "mehr" if wert > vorher else "weniger"
                    print(f"    {name}.{schluessel}: {vorher} -> {wert} ({pfeil})")

    if args.json:
        Path(args.json).write_text(
            json.dumps(ergebnis, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nInventar geschrieben: {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
