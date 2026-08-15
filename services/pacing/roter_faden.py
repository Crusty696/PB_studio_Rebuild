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
#
# Der Wert ist an echten Projektdaten kalibriert (738 Beats, 27 Sections,
# 337 s, Stem-gewichtete Energie wie im Auto-Edit) — gemessen über die
# Cut-Rate-Stufen, die ``dichte_parameter`` daraus ableitet:
#
#    1 Beat (2 Takte)  -> 302 Schnitte, Median 0,91 s
#    2 Beat (4 Takte)  -> 156 Schnitte, Median 1,82 s
#    4 Beat (8 Takte)  ->  94 Schnitte, Median 3,63 s   <- Vorgabe
#    8 Beat (16 Takte) ->  59 Schnitte, Median 5,47 s
#   16 Beat (32 Takte) ->  38 Schnitte, Median 9,08 s
#
# Eine Praxis-Recherche ergab als Zielkorridor für Musikvideos rund 3-5 s
# Median, für diese Länge also etwa 70-130 Schnitte. Die Vorgabestufe trifft
# das; die übrigen Stufen liegen bewusst darüber und darunter, damit der
# Regler in beide Richtungen etwas bewirkt.
#
# Wichtig für die Kalibrierung: eine frühere Messung mit KONSTANTER Energie
# (0.5) ergab 31 Schnitte bei Median 12,7 s und war damit wertlos — konstante
# Energie erzeugt per Definition keinen einzigen Energiesprung. Mit den echten
# Werten steuern Energiesprünge allein 32 Schnitte bei.
MAX_TAKTE_OHNE_SCHNITT = 8

# Takt-Raster je Section. Zweite Ebene unterhalb der Section-Grenzen: nicht
# jede Passage verträgt dieselbe Dichte. Ein Breakdown lebt von Ruhe, ein Drop
# von Schlagzahl — durchgehend gleicher Abstand wirkt mechanisch und ignoriert
# die Spannungskurve des Stücks.
#
# Die Werte folgen der gängigen Praxis (Drop/Chorus 1-2 Takte, Buildup
# verdichtend, Intro/Breakdown/Outro 4-8 Takte) und decken sich mit der
# Hierarchie, die Final Cut Pro anbietet: Song Parts > Bars > Beats.
# Die Werte sind an echten Projektdaten kalibriert: mit DROP=1/CHORUS=2 ergab
# die Vorgabestufe 145 Schnitte bei Median 1,82 s und lag damit über dem
# Zielkorridor. Verdoppelt trifft sie ihn.
TAKTE_PRO_SECTION: dict[str, int] = {
    "DROP": 2,
    "CHORUS": 4,
    "BUILDUP": 4,
    "VERSE": 4,
    "TRANSITION": 4,
    "WARMUP": 8,
    "BREAKDOWN": 8,
    "COOLDOWN": 8,
}

# Sections, deren Beginn immer einen Schnitt bekommt — dort wechselt der
# Charakter des Stücks hörbar.
HARTE_SECTION_GRENZEN = frozenset({"DROP", "BREAKDOWN", "CHORUS", "BUILDUP"})


@dataclass(frozen=True)
class Schnittanlass:
    """Ein Grund, an dieser Stelle zu schneiden."""

    zeit: float
    grund: str  # section | drop | energie | maximaldauer


def dichte_parameter(
    base_cut_rate: int | None, energy_reactivity: int | None = 50
) -> tuple[int, float]:
    """Die Cut-Rate-Combo als Dichte-Regler übersetzen.

    Ohne diese Übersetzung wäre die Combo im musikgetriebenen Modus
    wirkungslos — sie wird dort sonst nirgends gelesen. Genau dieser Regler
    war beim Nutzer über Tage der Hauptkritikpunkt; er darf nicht ein zweites
    Mal ins Leere laufen, nur eine Ebene tiefer.

    Die Combo schreibt kein starres Raster mehr vor. Section-Wechsel und Drops
    bleiben von ihr unabhängig und bilden die Untergrenze; sie bestimmt, wie
    viel **zusätzlich** geschnitten wird. Das entspricht dem, was
    Profi-Werkzeuge anbieten — Premiere nennt es "Edit Length: Short ↔ Long",
    Filmora "Beat Cut Speed".

    Rückgabe: ``(max_takte, energie_schwelle)``.

    * ``max_takte`` skaliert linear mit der Stufe: 4 Beat (die Mitte) ergibt
      den unveränderten Vorgabewert, 1 Beat schneidet dichter, 16 Beat ruhiger.
    * ``energie_schwelle`` bestimmt, wie leicht ein Energiesprung einen Schnitt
      auslöst. Feine Stufen sprechen früher an. Die Reaktivität wirkt als
      zweiter Faktor auf dieselbe Schwelle — damit bekommt auch dieser Regler
      im neuen Modus wieder eine Wirkung.
    """
    try:
        stufe = int(base_cut_rate) if base_cut_rate else 4
    except (TypeError, ValueError):
        stufe = 4
    if stufe <= 0:
        stufe = 4

    try:
        reaktivitaet = int(energy_reactivity) if energy_reactivity is not None else 50
    except (TypeError, ValueError):
        reaktivitaet = 50
    reaktivitaet = max(0, min(100, reaktivitaet))

    max_takte = max(1, round(MAX_TAKTE_OHNE_SCHNITT * stufe / 4))

    schwelle = ENERGIE_SPRUNG_SCHWELLE * (stufe / 4) ** 0.5
    # Hohe Reaktivität heisst: die Energie soll leichter einen Schnitt
    # auslösen, die Schwelle also sinken.
    schwelle *= 1.5 - reaktivitaet / 100.0
    schwelle = max(0.05, min(0.9, schwelle))

    return max_takte, schwelle


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
    # Nicht-endliche Werte aussortieren, bevor gerechnet wird. Ein einzelnes
    # NaN in den Beat-Positionen wanderte sonst unbemerkt bis in die Timeline
    # — der Vergleich `nan < x` ist immer falsch, also fällt es durch jede
    # Prüfung. Gleiches gilt für eine unbrauchbare Gesamtdauer.
    import math

    beats = [float(b) for b in beats if isinstance(b, (int, float)) and math.isfinite(b)]
    if not beats or not math.isfinite(total_duration) or total_duration <= 0:
        return []

    beat_dauer = _mittlere_beat_dauer(beats)
    takt_dauer = beat_dauer * 4
    toleranz = takt_dauer / 2

    # Der erste Anlass sitzt auf 0.0, nicht auf dem ersten Beat. Der liegt bei
    # diesem Material bei 0,04 s; zusammen mit dem 0.0, das der Aufrufer davor
    # setzt, entstand daraus ein 0,04-Sekunden-Schnipsel am Anfang.
    anlaesse: list[Schnittanlass] = [Schnittanlass(zeit=0.0, grund="start")]

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

    # 3. Takt-Raster: Lücken auffüllen, je Section unterschiedlich dicht
    anlaesse = _luecken_fuellen(
        anlaesse, total_duration, takt_dauer, max_takte,
        sections, downbeats or [], toleranz,
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


def _takte_fuer_section(zeit: float, sections: list | None, grundwert: int) -> int:
    """Wie viele Takte eine Einstellung an dieser Stelle höchstens stehen darf.

    ``TAKTE_PRO_SECTION`` gibt die Charakteristik vor (Drop dicht, Breakdown
    ruhig), die Cut-Rate-Combo skaliert sie über ``grundwert``. Ohne erkannte
    Section gilt der Grundwert unverändert.
    """
    typ = ""
    for sec in sections or []:
        start = float(getattr(sec, "start", 0.0))
        ende = float(getattr(sec, "end", 0.0))
        if start <= zeit < ende:
            typ = str(getattr(sec, "section_type", "") or "").upper()
            break

    if not typ or typ not in TAKTE_PRO_SECTION:
        return max(1, grundwert)

    # Der Grundwert ist auf MAX_TAKTE_OHNE_SCHNITT normiert: steht die Combo
    # auf der Mitte, gilt die Tabelle unveraendert.
    faktor = grundwert / max(1, MAX_TAKTE_OHNE_SCHNITT)
    return max(1, round(TAKTE_PRO_SECTION[typ] * faktor))


def _luecken_fuellen(
    anlaesse: list[Schnittanlass],
    total_duration: float,
    takt_dauer: float,
    grund_takte: int,
    sections: list | None,
    downbeats: list[float],
    toleranz: float,
) -> list[Schnittanlass]:
    """Zwischenschnitte im Takt-Raster setzen, je Section unterschiedlich dicht.

    Ohne diesen Schritt trüge allein die Section-Struktur den Schnitt — ein
    40-Sekunden-Chorus bliebe eine einzige Einstellung. Das Raster ist die
    zweite Ebene unterhalb der Sections, wie sie auch Final Cut Pro anbietet
    (Song Parts > Bars > Beats).
    """
    if takt_dauer <= 0:
        return anlaesse

    ergebnis: list[Schnittanlass] = []
    grenzen = [a.zeit for a in anlaesse] + [total_duration]
    for i, anlass in enumerate(anlaesse):
        ergebnis.append(anlass)
        naechste = grenzen[i + 1]
        # Die Section am Beginn der Lücke bestimmt deren Dichte.
        luecke = takt_dauer * _takte_fuer_section(anlass.zeit, sections, grund_takte)
        if luecke <= 0:
            continue
        # Die Lücke gleichmässig aufteilen, statt vom Anfang her in festen
        # Schritten zu laufen. Die frühere Fassung liess über die Toleranz
        # `luecke * 0.25` Abstände bis zum 1,25-fachen zu — gemessen 20,0 s
        # bei einem Limit von 16,0 s. Damit galt die Zusage "spätestens nach N
        # Takten" nicht. Jetzt bestimmt die Anzahl der Teilstücke den Abstand,
        # und der ist damit garantiert höchstens `luecke`.
        gesamt = naechste - anlass.zeit
        if gesamt <= luecke:
            continue
        teile = int(-(-gesamt // luecke))  # aufrunden
        schritt = gesamt / teile
        for n in range(1, teile):
            roh = anlass.zeit + n * schritt
            gesnappt = _naechster_downbeat(roh, downbeats, toleranz)
            # Der Snap darf die Zusage nicht wieder aufreissen: liegt der
            # Taktanfang so weit weg, dass der Abstand zum Vorgänger das Limit
            # überschreitet, bleibt die Rohzeit stehen.
            vorheriger = ergebnis[-1].zeit if ergebnis else anlass.zeit
            if gesnappt - vorheriger > luecke:
                gesnappt = roh
            ergebnis.append(Schnittanlass(zeit=gesnappt, grund="maximaldauer"))
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
    import math

    try:
        p = float(position)
    except (TypeError, ValueError):
        p = 0.0
    # NaN rutscht durch jeden Vergleich: `min(1.0, nan)` liefert 1.0, womit ein
    # unbrauchbarer Wert stillschweigend als "Track-Ende" gelesen würde.
    if not math.isfinite(p):
        p = 0.0
    p = max(0.0, min(1.0, p))
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


# ── Anwendung auf die Clip-Auswahl ──────────────────────────────────────────

# Wie stark Bogen und Motiv den Score verschieben dürfen. Bewusst klein: sie
# sollen die Auswahl färben, nicht bestimmen. Rollenpassung, Energie und
# Stilkohärenz bleiben die tragenden Kriterien.
BOGEN_GEWICHT = 0.12
MOTIV_GEWICHT = 0.10


class MotivGedaechtnis:
    """Merkt sich, welche Bildwelt in welcher Motivgruppe schon lief.

    Gespeichert wird nicht der Clip, sondern sein ``style_bucket`` — der
    Recherche-Befund dazu war eindeutig: wörtlich dasselbe Material im zweiten
    Refrain wirkt wie Materialmangel. Wiedererkennbar soll die *Bildwelt* sein,
    das Material darf variieren.
    """

    def __init__(self) -> None:
        self._buckets: dict[int, dict[int, int]] = {}

    def merken(self, gruppe: int | None, style_bucket: int | None) -> None:
        if gruppe is None or style_bucket is None:
            return
        zaehler = self._buckets.setdefault(int(gruppe), {})
        zaehler[int(style_bucket)] = zaehler.get(int(style_bucket), 0) + 1

    def passt_zur_gruppe(self, gruppe: int | None, style_bucket: int | None) -> float:
        """0.0 = unbekannt oder fremd, bis 1.0 = prägend für diese Gruppe."""
        if gruppe is None or style_bucket is None:
            return 0.0
        zaehler = self._buckets.get(int(gruppe))
        if not zaehler:
            return 0.0
        gesamt = sum(zaehler.values())
        if gesamt <= 0:
            return 0.0
        return zaehler.get(int(style_bucket), 0) / gesamt


def roter_faden_bonus(
    track_position: float,
    clip_intensitaet: float | None,
    motiv_gruppe: int | None = None,
    style_bucket: int | None = None,
    gedaechtnis: "MotivGedaechtnis | None" = None,
) -> float:
    """Score-Verschiebung aus Spannungsbogen und Motiv-Wiedererkennung.

    Rückgabe liegt etwa zwischen ``-BOGEN_GEWICHT`` und
    ``+(BOGEN_GEWICHT + MOTIV_GEWICHT)`` und wird auf den Fitness-Score
    addiert.

    * **Bogen** — je näher die Intensität des Clips am Ziel der Stelle liegt,
      desto besser. Am Höhepunkt gewinnen kräftige Bilder, im Intro ruhige.
    * **Motiv** — ein Clip aus der Bildwelt, die in dieser Section-Art schon
      lief, bekommt einen Bonus. Nie einen Malus: sonst würde die erste Wahl
      in einer Gruppe alle späteren blockieren.
    """
    bonus = 0.0

    if clip_intensitaet is not None:
        # Abweichung 0.0 -> voller Bonus, 1.0 -> voller Malus.
        abweichung = bogen_abweichung(track_position, clip_intensitaet)
        bonus += BOGEN_GEWICHT * (1.0 - 2.0 * abweichung)

    if gedaechtnis is not None:
        bonus += MOTIV_GEWICHT * gedaechtnis.passt_zur_gruppe(motiv_gruppe, style_bucket)

    return bonus
