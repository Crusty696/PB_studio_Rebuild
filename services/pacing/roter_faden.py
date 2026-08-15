"""Musikgetriebener Schnitt und roter Faden (User-Anweisung 2026-08-15).

Der Nutzer wollte zweierlei:

1. *"immer versuchen, die maximale Länge eines Clips zu verwenden, solange es
   passt"* — also lange Einstellungen, die nur dann enden, wenn die Musik einen
   Grund liefert. Nicht mehr starr im Beat-Raster.
2. *"einen roten Faden durch das ganze Video"* — vier Aspekte, alle vom Nutzer
   bestätigt: weiche Übergänge, wiederkehrende Motive, ein dramaturgischer
   Bogen und weniger Clip-Wiederholungen.

Ausgangslage war ein Auto-Edit-Lauf mit 212 Segmenten auf 337 s, Median-Dauer
1,37 s — hektisch, und 102 der 110 verwendeten Clips kamen doppelt vor.

Dieses Modul liefert die Bausteine dafür. Es rechnet nur und fasst weder
Datenbank noch UI an; die bestehende Raster-Auswahl in
``_select_cut_beats_advanced`` bleibt unangetastet und weiter benutzbar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Musikgetriebener Schnitt ────────────────────────────────────────────────

# Ein Schnitt fällt, wenn die Energie gegenüber dem gleitenden Mittel um mehr
# als diesen Anteil springt. 0.35 heisst: 35 % über dem bisherigen Verlauf.
# Darunter reagiert der Schnitt auf blosses Rauschen der Energiekurve.
ENERGIE_SPRUNG_SCHWELLE = 0.35

# Fenster für das gleitende Mittel, in Beats. Vier Takte à vier Beat.
ENERGIE_FENSTER_BEATS = 16

# Spätestens nach so vielen Takten wird geschnitten, auch wenn die Musik
# keinen Anlass liefert. Sonst stünde bei ruhigem Material eine einzige
# Einstellung über Minuten.
MAX_TAKTE_OHNE_SCHNITT = 8

# Sections, deren Beginn immer einen Schnitt bekommt — dort wechselt der
# Charakter des Stücks hörbar.
HARTE_SECTION_GRENZEN = frozenset({"DROP", "BREAKDOWN", "CHORUS", "BUILDUP"})


@dataclass(frozen=True)
class Schnittanlass:
    """Ein Grund, an dieser Stelle zu schneiden."""

    zeit: float
    grund: str  # section | drop | energie | maximaldauer


def _naechster_downbeat(zeit: float, downbeats: list[float], toleranz: float) -> float:
    """Den nächstgelegenen Downbeat suchen, sonst die Zeit unverändert lassen.

    Schnitte auf dem Taktanfang wirken gewollt, Schnitte dazwischen wie ein
    Fehler — deshalb wird jeder Anlass auf das Taktraster gezogen, sofern einer
    nah genug liegt.
    """
    if not downbeats:
        return zeit
    bester = min(downbeats, key=lambda d: abs(d - zeit))
    return bester if abs(bester - zeit) <= toleranz else zeit


def schnitt_anlaesse(
    beats: list[float],
    total_duration: float,
    sections: list | None = None,
    energy_per_beat: list[float] | None = None,
    downbeats: list[float] | None = None,
    max_takte: int = MAX_TAKTE_OHNE_SCHNITT,
    energie_schwelle: float = ENERGIE_SPRUNG_SCHWELLE,
) -> list[Schnittanlass]:
    """Schnittzeitpunkte aus der Musik ableiten statt aus einem festen Raster.

    Geschnitten wird, wenn einer dieser Gründe vorliegt:

    * **section** — eine neue Section beginnt (DROP, BREAKDOWN, CHORUS, BUILDUP)
    * **energie** — die Energie springt gegenüber dem gleitenden Mittel über
      ``energie_schwelle``
    * **maximaldauer** — seit dem letzten Schnitt sind ``max_takte`` Takte
      vergangen; Notbremse gegen minutenlange Standbilder

    Alle Zeitpunkte werden auf den nächsten Downbeat gezogen, solange dieser
    höchstens einen halben Takt entfernt liegt.

    Rückgabe ist aufsteigend sortiert und frei von Doppelungen — ein
    Section-Wechsel, der mit einem Energiesprung zusammenfällt, ergibt einen
    Schnitt, nicht zwei.
    """
    if not beats:
        return []

    beat_dauer = _mittlere_beat_dauer(beats)
    takt_dauer = beat_dauer * 4
    toleranz = takt_dauer / 2

    anlaesse: list[Schnittanlass] = [Schnittanlass(zeit=beats[0], grund="start")]

    # 1. Section-Grenzen
    for sec in sections or []:
        typ = str(getattr(sec, "section_type", "") or "").upper()
        start = float(getattr(sec, "start", 0.0))
        if typ in HARTE_SECTION_GRENZEN and 0.0 < start < total_duration:
            grund = "drop" if typ == "DROP" else "section"
            anlaesse.append(
                Schnittanlass(zeit=_naechster_downbeat(start, downbeats or [], toleranz), grund=grund)
            )

    # 2. Energiesprünge
    if energy_per_beat:
        for zeit in _energiespruenge(beats, energy_per_beat, total_duration, energie_schwelle):
            anlaesse.append(
                Schnittanlass(zeit=_naechster_downbeat(zeit, downbeats or [], toleranz), grund="energie")
            )

    anlaesse.sort(key=lambda a: a.zeit)
    anlaesse = _entdoppeln(anlaesse, mindestabstand=beat_dauer)

    # 3. Notbremse: nirgends darf eine Lücke über max_takte entstehen
    anlaesse = _luecken_fuellen(
        anlaesse, total_duration, takt_dauer * max_takte, downbeats or [], toleranz
    )

    logger.info(
        "Roter Faden: %d Schnittanlaesse auf %.1fs (%s)",
        len(anlaesse), total_duration,
        ", ".join(f"{g}={sum(1 for a in anlaesse if a.grund == g)}"
                  for g in ("start", "section", "drop", "energie", "maximaldauer")),
    )
    return anlaesse


def _mittlere_beat_dauer(beats: list[float]) -> float:
    if len(beats) < 2:
        return 0.5
    return max((beats[-1] - beats[0]) / (len(beats) - 1), 0.01)


def _energiespruenge(
    beats: list[float],
    energy_per_beat: list[float],
    total_duration: float,
    schwelle: float,
) -> list[float]:
    """Stellen finden, an denen die Energie deutlich über ihr Mittel springt."""
    treffer: list[float] = []
    for i, zeit in enumerate(beats):
        if zeit >= total_duration or i >= len(energy_per_beat):
            break
        fenster_start = max(0, i - ENERGIE_FENSTER_BEATS)
        fenster = energy_per_beat[fenster_start:i]
        if len(fenster) < 4:
            continue
        mittel = sum(fenster) / len(fenster)
        if mittel <= 0:
            continue
        if (energy_per_beat[i] - mittel) / mittel >= schwelle:
            treffer.append(zeit)
    return treffer


def _entdoppeln(anlaesse: list[Schnittanlass], mindestabstand: float) -> list[Schnittanlass]:
    """Anlässe zusammenfassen, die praktisch am selben Punkt liegen.

    Der jeweils gewichtigere Grund gewinnt: ein Drop erklärt den Schnitt besser
    als ein zufällig danebenliegender Energiesprung.
    """
    rang = {"start": 0, "drop": 1, "section": 2, "energie": 3, "maximaldauer": 4}
    ergebnis: list[Schnittanlass] = []
    for anlass in anlaesse:
        if ergebnis and anlass.zeit - ergebnis[-1].zeit < mindestabstand:
            if rang.get(anlass.grund, 9) < rang.get(ergebnis[-1].grund, 9):
                ergebnis[-1] = anlass
            continue
        ergebnis.append(anlass)
    return ergebnis


def _luecken_fuellen(
    anlaesse: list[Schnittanlass],
    total_duration: float,
    max_luecke: float,
    downbeats: list[float],
    toleranz: float,
) -> list[Schnittanlass]:
    """Zwischenschnitte setzen, wo die Musik zu lange keinen Anlass liefert."""
    if max_luecke <= 0:
        return anlaesse

    ergebnis: list[Schnittanlass] = []
    grenzen = [a.zeit for a in anlaesse] + [total_duration]
    for i, anlass in enumerate(anlaesse):
        ergebnis.append(anlass)
        naechste = grenzen[i + 1]
        zeit = anlass.zeit + max_luecke
        while zeit < naechste - max_luecke * 0.25:
            ergebnis.append(
                Schnittanlass(zeit=_naechster_downbeat(zeit, downbeats, toleranz), grund="maximaldauer")
            )
            zeit += max_luecke
    ergebnis.sort(key=lambda a: a.zeit)
    return ergebnis


# ── Dramaturgischer Bogen ───────────────────────────────────────────────────

# Stützpunkte (Position im Track, Zielintensität 0..1). Dazwischen wird linear
# interpoliert. Ruhiger Einstieg, Steigerung, Höhepunkt bei zwei Dritteln,
# Auflösung zum Schluss.
_BOGEN_STUETZPUNKTE: tuple[tuple[float, float], ...] = (
    (0.00, 0.30),
    (0.20, 0.45),
    (0.60, 0.80),
    (0.75, 1.00),
    (1.00, 0.40),
)


def bogen_intensitaet(position: float) -> float:
    """Zielintensität an einer relativen Position im Track (0..1).

    Der Wert sagt, wie kräftig das Bild an dieser Stelle sein soll — hohe
    Bewegung, hohe Sättigung, harte Kontraste. Er ersetzt keine Auswahl,
    sondern verschiebt sie: bei 0,3 gewinnen ruhige Clips, bei 1,0 die
    energischsten.
    """
    p = max(0.0, min(1.0, float(position)))
    vorher = _BOGEN_STUETZPUNKTE[0]
    for punkt in _BOGEN_STUETZPUNKTE[1:]:
        if p <= punkt[0]:
            spanne = punkt[0] - vorher[0]
            if spanne <= 0:
                return punkt[1]
            anteil = (p - vorher[0]) / spanne
            return vorher[1] + anteil * (punkt[1] - vorher[1])
        vorher = punkt
    return _BOGEN_STUETZPUNKTE[-1][1]


def bogen_abweichung(position: float, clip_intensitaet: float) -> float:
    """Wie weit ein Clip vom Ziel des Bogens abweicht — 0,0 ist perfekt.

    Als Strafterm gedacht, damit der Scorer Clips bevorzugt, die zur Stelle im
    Track passen.
    """
    return abs(bogen_intensitaet(position) - max(0.0, min(1.0, float(clip_intensitaet))))


# ── Wiederkehrende Motive ───────────────────────────────────────────────────

def motiv_zuordnung(sections: list | None) -> dict[str, int]:
    """Jedem Section-Typ eine feste Motivgruppe zuweisen.

    Der Kern des Wiedererkennens: alle CHORUS-Abschnitte bekommen dieselbe
    Gruppennummer und damit dieselbe Bildwelt, alle DROPs eine andere. Kehrt
    der Refrain wieder, kehrt auch sein Aussehen wieder.

    Die Nummern sind stabil sortiert, damit derselbe Track bei jedem Lauf
    dieselbe Zuordnung ergibt — sonst wäre das Ergebnis nicht reproduzierbar.
    """
    typen = sorted({
        str(getattr(sec, "section_type", "") or "").upper()
        for sec in (sections or [])
        if getattr(sec, "section_type", None)
    })
    return {typ: nr for nr, typ in enumerate(typen)}


def motiv_gruppe_fuer_zeit(zeit: float, sections: list | None, zuordnung: dict[str, int]) -> int | None:
    """Die Motivgruppe, die an dieser Stelle im Track gelten soll."""
    for sec in sections or []:
        start = float(getattr(sec, "start", 0.0))
        ende = float(getattr(sec, "end", 0.0))
        if start <= zeit < ende:
            typ = str(getattr(sec, "section_type", "") or "").upper()
            return zuordnung.get(typ)
    return None
