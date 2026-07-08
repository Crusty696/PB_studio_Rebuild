"""Read-only Snapshot einer PB-Studio-Projekt-DB fuer den Dataflow-Recorder.

Gibt EINE JSON-Zeile mit Tabellen-Counts + Audio-Track-Feldern + Status-Verteilung
aus. mode=ro, lockt die laufende App nicht. Aufruf:
    python _dataflow_snapshot.py <pfad-zur-pb_studio.db>
"""
import sys
import json
import sqlite3

out = {"tables": {}, "audio": [], "counts": {}}
if len(sys.argv) < 2:
    print(json.dumps({"error": "no db path"}))
    sys.exit(0)
db = sys.argv[1]
try:
    con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True, timeout=2)
    cur = con.cursor()

    def count(t):
        try:
            return cur.execute("select count(*) from " + t).fetchone()[0]
        except Exception:
            return None

    for t in ("audio_tracks", "beatgrids", "waveform_data", "video_clips",
              "scenes", "timeline_entries", "analysis_status"):
        out["tables"][t] = count(t)

    try:
        rows = cur.execute(
            "select id, mood, genre, sub_genre, is_dj_mix, duration "
            "from audio_tracks order by id"
        ).fetchall()
        for r in rows:
            out["audio"].append({
                "id": r[0], "mood": r[1], "genre": r[2], "sub_genre": r[3],
                "is_dj_mix": r[4], "dur": round(r[5], 1) if r[5] else None,
            })
    except Exception:
        pass

    try:
        for trk, n in cur.execute(
                "select track, count(*) from timeline_entries group by track"):
            out["counts"]["timeline_" + str(trk)] = n
    except Exception:
        pass

    try:
        for st, n in cur.execute(
                "select status, count(*) from analysis_status group by status"):
            out["counts"]["astatus_" + str(st)] = n
    except Exception:
        pass

    con.close()
except Exception as e:  # noqa: BLE001
    out["error"] = str(e)

print(json.dumps(out, default=str))
