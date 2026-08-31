"""Immer dieselben Kennzahlen fuer einen Auto-Edit-Lauf.

Hintergrund (Selbstpruefung 2026-08-31): Jede Pacing-Aenderung des Tages wurde
anders geprueft - mal Segmentzahl, mal Laengen, mal die Reparatur-Zaehler im
Log. Dadurch fiel erst spaet auf, dass ein Fix 38 geschlossene Luecken und
6 Ueberlappungen erzeugte, und ein anderer ein Segment mit gekappter Quelle
hinterliess. Wer jedes Mal andere Zahlen ansieht, vergleicht nichts.

Dieses Werkzeug faehrt ``auto_edit_phase3`` und gibt immer dieselben Groessen
aus. Es schreibt **nichts** in die Timeline - der Lauf endet vor ``apply``.

    python tools/pacing_metrics.py --projekt <pfad> --preset Standard
    python tools/pacing_metrics.py --projekt <pfad> --preset Ambient --json lauf.json
    python tools/pacing_metrics.py --projekt <pfad> --vergleich referenz.json

Kennzahlen:

* Segmente, Laufzeit
* Segmentlaenge min / Mittel / Median / max
* **gekappte Quellen** - Timeline-Slot laenger als das Quellmaterial; jede
  davon wird spaeter zu einer Luecke, die die Reparatur schliesst
* **Luecken und Ueberlappungen** zwischen aufeinanderfolgenden Segmenten
* Clip-Vielfalt und direkte Wiederholungen
* Abweichung zu einem Referenzlauf (Anteil gleicher Clips je Position)

Exit-Code 1, sobald gekappte Quellen oder Ueberlappungen auftreten - beides
ist immer ein Fehlerzustand, kein Geschmacksfall.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def kennzahlen(segmente, laufzeit: float, clip_dauern: dict) -> dict:
    laengen = [s.end - s.start for s in segmente]
    quellen = [s.source_end - s.source_start for s in segmente]

    gekappt = [
        {
            "start": round(s.start, 2),
            "slot": round(s.end - s.start, 2),
            "quelle": round(s.source_end - s.source_start, 2),
            "clip": s.video_id,
            "clipdauer": round(float(clip_dauern.get(s.video_id, 0.0)), 2),
        }
        for s, slot, quelle in zip(segmente, laengen, quellen)
        if quelle + 0.01 < slot
    ]

    luecken, ueberlappungen = [], []
    for a, b in zip(segmente, segmente[1:]):
        abstand = b.start - a.end
        if abstand > 0.01:
            luecken.append(round(abstand, 3))
        elif abstand < -0.01:
            ueberlappungen.append(round(-abstand, 3))

    folgen = [s.video_id for s in segmente]
    return {
        "segmente": len(segmente),
        "laufzeit_s": round(laufzeit, 1),
        "laenge_min": round(min(laengen), 2) if laengen else 0.0,
        "laenge_mittel": round(statistics.mean(laengen), 2) if laengen else 0.0,
        "laenge_median": round(statistics.median(laengen), 2) if laengen else 0.0,
        "laenge_max": round(max(laengen), 2) if laengen else 0.0,
        "gekappte_quellen": len(gekappt),
        "gekappt_details": gekappt[:5],
        "luecken": len(luecken),
        "luecken_summe_s": round(sum(luecken), 3),
        "ueberlappungen": len(ueberlappungen),
        "verschiedene_clips": len(set(folgen)),
        "direkte_wiederholungen": sum(1 for x, y in zip(folgen, folgen[1:]) if x == y),
        "clip_folge": folgen,
    }


def lauf(projekt: str, preset: str | None, audio_id: int | None) -> dict:
    logging.basicConfig(level=logging.ERROR)
    from database.session import set_project

    set_project(projekt)

    import database
    from sqlalchemy.orm import Session
    from database import AudioTrack, VideoClip

    with Session(database.engine) as session:
        track = (session.get(AudioTrack, audio_id) if audio_id
                 else session.query(AudioTrack).first())
        if track is None:
            raise SystemExit("Kein Audio-Track im Projekt gefunden.")
        clips = {c.id: float(c.duration or 0.0) for c in session.query(VideoClip).all()}
        track_id, titel = track.id, track.title

    if not clips:
        raise SystemExit("Keine Video-Clips im Projekt gefunden.")

    from services.pacing_beat_grid import AdvancedPacingSettings
    from services.pacing_service import auto_edit_phase3
    from services.pacing.style_preset_loader import lade_preset_felder

    felder = lade_preset_felder(preset) if preset else {}
    start = time.time()
    segmente, _ = auto_edit_phase3(
        track_id, sorted(clips), AdvancedPacingSettings(**felder))
    dauer = time.time() - start

    werte = kennzahlen(segmente, dauer, clips)
    werte.update({
        "projekt": projekt,
        "audio": "#%s %s" % (track_id, titel),
        "preset": preset or "(keins)",
        "preset_felder": felder,
        "clips_im_pool": len(clips),
        "clip_dauer_min": round(min(clips.values()), 2),
        "clip_dauer_max": round(max(clips.values()), 2),
    })
    return werte


def zeige(werte: dict, referenz: dict | None = None) -> None:
    print("Projekt : %s" % werte["projekt"])
    print("Audio   : %s" % werte["audio"])
    print("Preset  : %s  %s" % (werte["preset"], werte["preset_felder"] or ""))
    print("Pool    : %d Clips, %s-%ss" % (
        werte["clips_im_pool"], werte["clip_dauer_min"], werte["clip_dauer_max"]))
    print("")
    print("Segmente              %d   (%ss Rechenzeit)" % (
        werte["segmente"], werte["laufzeit_s"]))
    print("Laenge min/med/max    %s / %s / %ss   (Mittel %ss)" % (
        werte["laenge_min"], werte["laenge_median"],
        werte["laenge_max"], werte["laenge_mittel"]))
    hinweis = "   <-- werden zu Luecken" if werte["gekappte_quellen"] else ""
    print("Gekappte Quellen      %d%s" % (werte["gekappte_quellen"], hinweis))
    for eintrag in werte["gekappt_details"]:
        print("    bei %ss: Slot %ss, Quelle %ss (Clip %s, %ss)" % (
            eintrag["start"], eintrag["slot"], eintrag["quelle"],
            eintrag["clip"], eintrag["clipdauer"]))
    print("Luecken               %d (%ss)" % (
        werte["luecken"], werte["luecken_summe_s"]))
    print("Ueberlappungen        %d" % werte["ueberlappungen"])
    print("Verschiedene Clips    %d von %d" % (
        werte["verschiedene_clips"], werte["clips_im_pool"]))
    print("Direkte Wiederholung  %d" % werte["direkte_wiederholungen"])

    if referenz:
        a, b = werte["clip_folge"], referenz.get("clip_folge", [])
        gleich = sum(1 for x, y in zip(a, b) if x == y)
        laenge = max(len(a), len(b)) or 1
        print("")
        print("Vergleich mit Referenz (%s, %s Segmente):" % (
            referenz.get("preset", "?"), referenz.get("segmente", "?")))
        print("  gleiche Clip-Wahl an %d von %d Positionen (%.0f%%)" % (
            gleich, laenge, 100.0 * gleich / laenge))
        for feld in ("segmente", "laenge_min", "laenge_max", "gekappte_quellen",
                     "luecken", "ueberlappungen"):
            alt, neu = referenz.get(feld), werte.get(feld)
            if alt != neu:
                print("  %s: %s -> %s" % (feld, alt, neu))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--projekt", required=True, help="Projektordner (mit pb_studio.db)")
    p.add_argument("--preset", default=None, help="Stil-Preset, z.B. Standard")
    p.add_argument("--audio-id", type=int, default=None)
    p.add_argument("--json", default=None, help="Kennzahlen hierhin schreiben")
    p.add_argument("--vergleich", default=None, help="frueher geschriebene JSON-Datei")
    args = p.parse_args()

    werte = lauf(args.projekt, args.preset, args.audio_id)
    referenz = (json.loads(Path(args.vergleich).read_text(encoding="utf-8"))
                if args.vergleich else None)
    zeige(werte, referenz)

    if args.json:
        Path(args.json).write_text(
            json.dumps(werte, indent=2, ensure_ascii=False), encoding="utf-8")
        print("")
        print("Kennzahlen geschrieben: %s" % args.json)

    return 1 if (werte["gekappte_quellen"] or werte["ueberlappungen"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
