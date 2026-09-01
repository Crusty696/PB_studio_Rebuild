---
title: Waechter - Konfiguration Loop 1
status: laufend
created: 2026-09-01 07:58
---

# Waechter - Loop 1

## 1. Bilanz des Vorlaufs

Es gibt keinen Vorlauf. Loop 1 ist der erste. Ausgangsstand aus `abdeckung.md`:
6 von 57 Aktionen live belegt (**10,5 %**), 4 nur per Werkzeug, 47 ungeprueft.

## 2. Blindstellen, die schon feststehen

- Die fuenf Pruefwerkzeuge finden Struktur- und Regressionsfehler, **nicht** ob eine Funktion
  inhaltlich richtig arbeitet. Belegt am 2026-08-31: B-939, B-942 und B-934 kamen ausschliesslich
  aus Live-Tests.
- `test_b353_...` prueft im vollen Testlauf gar nichts (B-958, rc=-1). Solange die Ursache offen
  ist, sind Aussagen aus dem vollen Lauf ueber Thread-Aufraeumung wertlos.
- Parallelitaet: GUI-Tests lassen sich nicht parallel fahren - eine App, ein Fenster, ein Zeiger.
  Der Userwunsch "oder arbeite parallel" ist hier technisch nicht erfuellbar; Loop 1 arbeitet
  streng nacheinander.

## 3. Konfiguration

**Werkzeuge (vom User festgelegt):** `pruefstand`, `consulting-team`, `caveman ultra`.
Sonst nichts.

**App:** `tests/gui_harness.py start --force`, PID 9856, gestartet 07:53:17.
**Aufzeichnung:** `test-report/live/loop-1.log` - Log-Datei, kein Screen-Recorder.

**Reihenfolge (Userauftrag "mach alles davon eines nach dem anderen"):**

| Block | Aktionen | Warum diese Reihenfolge |
|---|---|---|
| A Projekt | create_project, open_project, save_project, save_project_as, get_project_info, import_file, refresh_media, list_media, delete_media | Ohne Projekt laesst sich nichts anderes ausloesen |
| B Timeline | add_to_timeline, move_clip, remove_clip, clear_timeline, undo_timeline, redo_timeline, add_anchor, remove_anchor, sync_anchors, learn_anchor | Braucht Material aus A |
| C Chat/Agent | ask_ai, explain_clip, suggest_pacing, summarize_project, search_video, search_knowledge, describe_audio_track, describe_video_clip, describe_set_overview, brain_stats, brain_recall, brain_learn_note, brain_explain_cut, model_status, list_actions, list_projects, list_timeline, get_settings | Braucht Projekt und Timeline als Gegenstand |
| D Offene Kernprozesse | Vorschau abspielen (B-922/B-923), RL-Feedback (B-951) | Bekannte Verdachtsfaelle, brauchen eine gefuellte Timeline |

**Pruefstand:** laeuft nach dem GUI-Block, mit `--projekt Erstlauf_Test_2026-08-30 --preset Standard`,
Ausgabe live in eine Datei. Nicht `--schnell`.

**Bewusst ausgelassen:** cancel_task, create_proxy, generate_embeddings, detect_scenes,
analyze_motion, analyze_video, analyze_audio, separate_stems - laufen als lange Analysen und
gehoeren in einen eigenen Block, sonst blockieren sie Loop 1 stundenlang. Wird in Loop 2
nachgeholt, nicht vergessen.

## 4. Zielliste

Alle Aktionen aus A-D von `ungeprueft` auf `live` heben - oder mit Beleg als defekt melden.
Rechnerisches Ziel: von 6 auf bis zu 45 von 57. Ob das erreichbar ist, entscheidet der Lauf,
nicht die Absicht.

## 5. Abbruchkriterium

Loop 1 gilt als erledigt, wenn jede Aktion aus A-D entweder einen Log-Beleg im
`loop-1.log` hat oder als Fund mit Datei:Zeile, Messwert und Reproduktionsbefehl aufgeschrieben
ist. Ein "geht wahrscheinlich" zaehlt nicht.
