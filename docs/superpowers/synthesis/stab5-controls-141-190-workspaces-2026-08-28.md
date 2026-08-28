# STAB-5 Controls #141-#190 — Workspaces (Convert, Deliver, Media) (2026-08-28)

status: target-test-pass-live-pending

## Belegte Elemente

### ConvertWorkspace (#141-#146)
- **#141** `convert_resolution` (QComboBox): Items `["1920x1080 (1080p)", "2560x1440 (2K)", "3840x2160 (4K)", "1280x720 (720p)"]`, AccessibleName `Ziel-Aufloesung`, Signal `currentIndexChanged` belegt.
- **#142** `convert_fps` (QComboBox): Items `["30 fps", "24 fps", "25 fps", "50 fps", "60 fps"]`, AccessibleName `Ziel-Framerate`, Signal `currentIndexChanged` belegt.
- **#143** `convert_format` (QComboBox): Items `["mp4 (H.264)", "mp4 (H.265/HEVC)", "mov (ProRes)", "mkv (H.264)", "mp4 (Kopieren/Copy)"]`, AccessibleName `Ziel-Containerformat`, Signal `currentIndexChanged` belegt.
- **#144** `btn_standardize_all` (QPushButton): Text `"Alle Videos standardisieren"`, QTest-Click emittiert `clicked`.
- **#145** `effects_clip_combo` (QComboBox): Sub-Tab 1 (EFFEKTE), AccessibleName `"Clip fuer Effekte waehlen"`, Sichtbarkeit und Enablement belegt.
- **#146** `btn_apply_effects` (QPushButton): Sub-Tab 1 (EFFEKTE), Text `"Effekte anwenden"`, QTest-Click emittiert `clicked`.

### DeliverWorkspace (#147-#154)
- **#147** `resolution_combo` (QComboBox): Items `["1920x1080", "1280x720", "854x480", "3840x2160"]`, AccessibleName `Export Aufloesung`, Signal `currentIndexChanged` belegt.
- **#148** `fps_combo` (QComboBox): Items `["30", "24", "25", "60"]`, AccessibleName `Export Bildrate`, Signal `currentIndexChanged` belegt.
- **#149** `preset_combo` (QComboBox): Items `["Standard (H.264 fast)", "Hohe Qualitaet (H.264 slow)", "Draft (schnell)"]`, itemData `["standard", "high", "draft"]`, AccessibleName `Export Preset`, Signal `currentIndexChanged` belegt.
- **#150** `btn_preview` (QPushButton): Text `"Quick-Preview (10s)"`, QTest-Click emittiert `clicked`.
- **#151** `btn_export` (QPushButton): Text `"Video exportieren"`, QTest-Click emittiert `clicked`.
- **#152** `btn_refresh_production` (QPushButton): Text `"Aktualisieren"`, QTest-Click emittiert `clicked`.
- **#153** `btn_preview_play` (QPushButton): Text `"Play"`, Enablement + QTest-Click emittiert `clicked`.
- **#154** `btn_preview_stop` (QPushButton): Text `"Stop"`, Enablement + QTest-Click emittiert `clicked`.

### MediaWorkspace (#155-#167)
- **#155** `btn_mode_video` (QPushButton): Text `"VIDEO"`, checkable, default True, mode_stack Index 0.
- **#156** `btn_mode_audio` (QPushButton): Text `"AUDIO"`, checkable, QTest-Click schaltet checked und mode_stack Index 1.
- **#157** `btn_add_to_timeline` (QPushButton): Text `"Zur Timeline hinzufuegen"`, QTest-Click emittiert `clicked`.
- **#158** `btn_import_video` (QPushButton): Text `"+ Video"`, QTest-Click emittiert `clicked`.
- **#159** `btn_import_folder` (QPushButton): Text `"+ Ordner"`, QTest-Click emittiert `clicked`.
- **#160** `btn_delete_selected_video` (QPushButton): Text `"Loeschen"`, QTest-Click emittiert `clicked`.
- **#161** `btn_trash` (QPushButton): Text `"Papierkorb"`, QTest-Click emittiert `clicked`.
- **#162** `btn_clear_all` (QPushButton): Text `"Sammlung bereinigen"`, QTest-Click emittiert `clicked`.
- **#163** `btn_search` (QPushButton): Text `"Suchen"`, QTest-Click emittiert `clicked`.
- **#164** `btn_search_clear` (QPushButton): Text `"X"`, QTest-Click emittiert `clicked`.
- **#165** `btn_select_all_video` (QPushButton): Text `"Alle"`, QTest-Click emittiert `clicked`.
- **#166** `btn_video_list_view` (QPushButton): Text `"☰"`, QTest-Click schaltet `_video_pool_stack.currentIndex()` auf 0 (List).
- **#167** `btn_video_grid_view` (QPushButton): Text `"⊞"`, QTest-Click schaltet `_video_pool_stack.currentIndex()` auf 1 (Grid).

### MediaWorkspace Pagination (#168-#169)
- **#168/#169** `btn_video_page_prev`/`next` (QPushButton): Manuell klassifiziert als `manual-excluded` / `legacy-hidden` (Attribut existiert, verhalten absichtlich versteckt; Pagination erfolgt ueber Scroll/fetchMore; Evidenz in `stab5-controls-168-169-video-pagination-2026-08-26.md`). Abwesenheit der Sichtbarkeit explizit im Test belegt.

### MediaWorkspace / Analysis Actions (#170-#190)
- **#170** `btn_analyze_video` (QPushButton): Text `"Szenen"`, QTest-Click emittiert `clicked`.
- **#171** `btn_video_pipeline` (QPushButton): Text `"Video komplett analysieren"`, QTest-Click emittiert `clicked`.
- **#172** `btn_keyframe_string` (QPushButton): Text `"Keyframe-String"`, QTest-Click emittiert `clicked`.
- **#173** `btn_import_audio` (QPushButton): Audio-Modus, Text `"+ Audio"`, QTest-Click emittiert `clicked`.
- **#174** `_btn_import_folder_audio` (QPushButton): Audio-Modus, Text `"+ Ordner"`, QTest-Click emittiert `clicked`.
- **#175** `btn_delete_selected_audio` (QPushButton): Audio-Modus, Text `"Loeschen"`, QTest-Click emittiert `clicked`.
- **#176** `btn_select_all_audio` (QPushButton): Audio-Modus, Text `"Alle"`, QTest-Click emittiert `clicked`.
- **#177** `btn_audio_list_view` (QPushButton): Audio-Modus, Text `"☰"`, QTest-Click schaltet `_audio_pool_stack.currentIndex()` auf 0 (List).
- **#178** `btn_audio_grid_view` (QPushButton): Audio-Modus, Text `"⊞"`, QTest-Click schaltet `_audio_pool_stack.currentIndex()` auf 1 (Grid).
- **#179** `btn_audio_page_prev` (QPushButton): Audio-Modus, Text `"◀"`, initial disabled bei leerem Pool, Enablement + QTest-Click emittiert `clicked`.
- **#180** `btn_audio_page_next` (QPushButton): Audio-Modus, Text `"▶"`, initial disabled bei leerem Pool, Enablement + QTest-Click emittiert `clicked`.
- **#181** `btn_analyze` (QPushButton): Audio-Modus, Text `"BPM / Beatgrid"`, QTest-Click emittiert `clicked`.
- **#182** `btn_waveform` (QPushButton): Audio-Modus, Text `"Wellenform"`, QTest-Click emittiert `clicked`.
- **#183** `btn_key_detect` (QPushButton): Audio-Modus, Text `"Tonart"`, QTest-Click emittiert `clicked`.
- **#184** `btn_lufs_analyze` (QPushButton): Audio-Modus, Text `"LUFS"`, QTest-Click emittiert `clicked`.
- **#185** `btn_mood_classify` (QPushButton): Audio-Modus, Text `"Mood / Genre"`, QTest-Click emittiert `clicked`.
- **#186** `btn_spectral_analyze` (QPushButton): Audio-Modus, Text `"Spektralanalyse"`, QTest-Click emittiert `clicked`.
- **#187** `btn_structure_detect` (QPushButton): Audio-Modus, Text `"Songstruktur"`, QTest-Click emittiert `clicked`.
- **#188** `btn_stem_separate` (QPushButton): Audio-Modus, Text `"Stems"`, QTest-Click emittiert `clicked`.
- **#189** `btn_auto_duck` (QPushButton): Audio-Modus, Text `"Auto-Ducking"`, QTest-Click emittiert `clicked`.
- **#190** `btn_analyze_all` (QPushButton): Audio-Modus, Text `"Audio komplett analysieren"`, QTest-Click emittiert `clicked`.

## Verifikation

`tests/ui/test_stab5_workspaces_controls.py` (neu, 49 Tests) -> `49 passed in 16.10s`.
Offscreen PySide6 QtTests fuer alle Controls #141-#190. Kein Produktcodeedit.

## Grenzen

Echte FFmpeg-Exporte, reale Medienanalysen und physische UI-Klicks bleiben Live-Endgate.
