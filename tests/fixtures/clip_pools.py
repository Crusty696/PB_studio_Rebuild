"""Clip-Pools fuer Laengen- und Auswahllogik — inklusive der Randfaelle.

Hintergrund (Selbstpruefung 2026-08-31): Der B-942-Fix senkte die
Segment-Obergrenze auf den kuerzesten Clip im Pool. Verifiziert wurde er gegen
das Projekt Erstlauf_Test_2026-08-30 — dort liegen **alle 121 Clips zwischen
7.79 und 10.00 s**. Ein 1.5-Sekunden-Schnipsel haette jedes Segment des ganzen
Videos gedeckelt; im Testmaterial konnte das strukturell nicht auffallen.

Diese Pools bilden die Faelle ab, die echtes Nutzermaterial mitbringt und ein
gleichfoermiger Testordner nicht:

* ein einzelner sehr kurzer Clip zwischen langen
* stark gemischte Laengen (Handyschnipsel neben Drohnenflug)
* fehlende oder unbrauchbare Dauer in der Datenbank
* ein Pool, in dem **kein** Clip das Segment traegt

Verwendung::

    from tests.fixtures.clip_pools import POOL_MIT_SCHNIPSEL, video_info

    info = video_info(POOL_MIT_SCHNIPSEL)
"""

from __future__ import annotations

# Jeder Pool ist {clip_id: dauer_in_sekunden}. ``None`` heisst: Dauer fehlt.

POOL_GLEICHFOERMIG: dict[int, float | None] = {
    i: 8.0 + (i % 3) * 0.5 for i in range(1, 11)
}
"""Was das Testprojekt hat: alles gleich lang. Faengt keine Randfaelle."""

POOL_MIT_SCHNIPSEL: dict[int, float | None] = {
    1: 10.0, 2: 9.5, 3: 9.8, 4: 1.5, 5: 10.0, 6: 8.2,
}
"""Ein 1.5-s-Schnipsel zwischen langen Clips — der Fall, der B-944 ausloeste."""

POOL_GEMISCHT: dict[int, float | None] = {
    1: 0.8, 2: 2.0, 3: 4.5, 4: 12.0, 5: 45.0, 6: 120.0, 7: 3.3, 8: 6.7,
}
"""Realistischer Nutzerordner: Handyschnipsel neben Drohnenflug."""

POOL_OHNE_DAUER: dict[int, float | None] = {
    1: 10.0, 2: None, 3: 0.0, 4: 9.0,
}
"""Dauer fehlt oder ist 0 — kommt bei abgebrochenem Import vor."""

POOL_ALLE_ZU_KURZ: dict[int, float | None] = {
    1: 2.0, 2: 2.5, 3: 1.8,
}
"""Kein Clip traegt ein langes Segment. Der Fallback muss greifen."""

ALLE_POOLS: dict[str, dict[int, float | None]] = {
    "gleichfoermig": POOL_GLEICHFOERMIG,
    "mit_schnipsel": POOL_MIT_SCHNIPSEL,
    "gemischt": POOL_GEMISCHT,
    "ohne_dauer": POOL_OHNE_DAUER,
    "alle_zu_kurz": POOL_ALLE_ZU_KURZ,
}


def video_info(pool: dict[int, float | None], *, prefix: str = "clip") -> dict[int, dict]:
    """Baut die ``video_info``-Struktur, die der Pacing-Code erwartet."""
    info: dict[int, dict] = {}
    for clip_id, dauer in pool.items():
        eintrag: dict = {"path": f"{prefix}_{clip_id}.mp4"}
        if dauer is not None:
            eintrag["duration"] = dauer
        info[clip_id] = eintrag
    return info


def clip_ids(pool: dict[int, float | None]) -> list[int]:
    return sorted(pool)


def kuerzester(pool: dict[int, float | None]) -> float:
    """Kuerzeste bekannte Dauer — die Zahl, an der B-942 entgleiste."""
    werte = [d for d in pool.values() if d]
    return min(werte) if werte else 0.0
