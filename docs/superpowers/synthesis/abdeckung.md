---
title: Abdeckungsregister - der 100-%-Zaehler
status: aktiv
created: 2026-09-01
updated: 2026-09-01 09:13
---

# Abdeckungsregister

Grundgesamtheit **62 Aktionen**, gemessen zur Laufzeit ueber die Chat-Aktion `list_actions`
(2026-09-01 08:10:44). `tools/inventory_audit.py` meldete zunaechst 57 - der Unterschied war
[[B-959-inventory-audit-untererfasst-aktionen]], inzwischen behoben.

## Stand nach Loop 1: 62 von 62 live gemessen (100 %)

Alle Belege in `test-report/live/loop-1.log` und `logs/pb_studio.log` mit Zeitstempel.

| Ergebnis | Anzahl |
|---|---|
| funktioniert | 32 |
| durch Bestaetigungssperre geschuetzt (korrektes Verhalten) | 4 |
| defekt: fehlender Pflichtparameter ([[B-961-pflichtparameter-wird-nicht-geprueft]]) | 25 |
| ohne Worker (bekannt) | 1 |

Quer dazu: [[B-960-exakter-aktionsname-geht-durch-llm]] betrifft jede Aktion, deren Name einen
Agenten triggert - erkennbar an Antwortzeiten von 40-95 s statt 1,7-2,0 s.

## Einzelnachweis

| Aktion | Ergebnis | Beleg |
|---|---|---|
| `add_anchor` | **defekt (B-961)** | TypeError: missing required positional argument |
| `add_to_timeline` | **defekt (B-961)** | TypeError: missing required positional argument |
| `analyze_audio` | **defekt (B-961)** | TypeError: missing required positional argument |
| `analyze_lufs` | **defekt (B-961)** | TypeError: missing required positional argument |
| `analyze_motion` | **defekt (B-961)** | TypeError: missing required positional argument |
| `analyze_spectral` | **defekt (B-961)** | TypeError: missing required positional argument |
| `analyze_video` | **defekt (B-961)** | TypeError: missing required positional argument |
| `analyze_video_content` | **defekt (B-961)** | TypeError: missing required positional argument |
| `apply_style_preset` | **defekt (B-961)** | TypeError: missing required positional argument |
| `ask_ai` | **defekt (B-961)** | TypeError: missing required positional argument |
| `auto_ducking` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `auto_edit` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `brain_explain_cut` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `brain_learn_note` | **defekt (B-961)** | TypeError: missing required positional argument |
| `brain_recall` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `brain_stats` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `cancel_task` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `classify_audio` | **defekt (B-961)** | TypeError: missing required positional argument |
| `clear_search` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `clear_timeline` | gesperrt (korrekt) | Confirmation required for destructive action |
| `convert_videos` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `create_project` | **defekt (B-961)** | TypeError: missing required positional argument |
| `create_proxy` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `delete_media` | gesperrt (korrekt) | Confirmation required for destructive action |
| `describe_audio_track` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `describe_set_overview` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `describe_video_clip` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `detect_key` | **defekt (B-961)** | TypeError: missing required positional argument |
| `detect_scenes` | **defekt (B-961)** | TypeError: missing required positional argument |
| `detect_structure` | **defekt (B-961)** | TypeError: missing required positional argument |
| `explain_clip` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `export_timeline` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `generate_embeddings` | **defekt (B-961)** | TypeError: missing required positional argument |
| `generate_keyframe_strings` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `get_project_info` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `get_settings` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `import_file` | **defekt (B-961)** | TypeError: missing required positional argument |
| `learn_anchor` | **defekt (B-961)** | TypeError: missing required positional argument |
| `list_actions` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `list_media` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `list_projects` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `list_timeline` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `match_clips_to_segment` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `model_status` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `move_clip` | **defekt (B-961)** | TypeError: missing required positional argument |
| `open_project` | **defekt (B-961)** | TypeError: missing required positional argument |
| `preview_export` | **ohne Worker** | Aktion ist derzeit nicht verfuegbar: kein Worker registriert |
| `redo_timeline` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `refresh_media` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `remove_anchor` | gesperrt (korrekt) | Confirmation required for destructive action |
| `remove_clip` | gesperrt (korrekt) | Confirmation required for destructive action |
| `rl_feedback` | **defekt (B-961)** | TypeError: missing required positional argument |
| `save_project` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `save_project_as` | **defekt (B-961)** | TypeError: missing required positional argument |
| `search_knowledge` | **defekt (B-961)** | TypeError: missing required positional argument |
| `search_video` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `separate_stems` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `set_clip_effects` | **defekt (B-961)** | TypeError: missing required positional argument |
| `suggest_pacing` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `summarize_project` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `sync_anchors` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
| `undo_timeline` | funktioniert | Antwort mit echten Werten im Chat-Verlauf |
