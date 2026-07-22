"""Keyword-/Tool-Dispatch-Tabellen fuer den OrchestratorAgent.

VERBATIM ausgelagert aus ``agents/orchestrator_agent.py`` (AUFRAEUM B2).
Kein Logik-Change — reine Daten-Konstanten (Tuples/Frozensets/Listen),
zustandslos. Werden von ``orchestrator_agent`` re-importiert und bleiben
dort als Modul-Globals erreichbar (Public-API unveraendert).
"""

from __future__ import annotations

# B-243: Whitelist nur lese-/abfragender Tools fuer den LLM-Fallback.
# Trigger-Tools (Worker-Spawns), destruktive Aktionen und auto_edit/export
# sind ausgeschlossen — Brain darf Daten lesen, aber keine Pipelines
# eigenmaechtig starten.
# B-245 + B-246: describe_video_clip + describe_set_overview ergaenzt.
_BRAIN_SAFE_TOOLS: tuple[str, ...] = (
    "summarize_project",
    "describe_audio_track",
    "describe_video_clip",       # B-245
    "describe_set_overview",     # B-246 Phase 1
    "match_clips_to_segment",    # B-246 Phase 2 — Cross-Modal SigLIP
    "explain_clip",
    "suggest_pacing",
    "search_video",
    "search_knowledge",
    "model_status",
    "list_actions",
)

_DIRECT_READ_TOOL_MESSAGES: frozenset[str] = frozenset({
    "summarize_project",
    "describe_audio_track",
    "describe_video_clip",
    "describe_set_overview",
})

# B-411: Imperative Aktions-Verben. Erreicht ein Befehl, der mit einem solchen Verb
# BEGINNT, den Chat-Fallback (kein Agent/keine Action hat ihn ausgeführt, Modell ohne
# Tool-Support), darf das LLM keinen Erfolg halluzinieren — wir antworten transparent.
# Start-mit-Verb-Heuristik haelt Fragen ("wie sperre ich…", "kannst du…") ausgeschlossen.
_ACTION_COMMAND_VERBS = frozenset({
    "sperre", "entsperre", "lock", "unlock", "loesche", "lösche", "loesch", "lösch",
    "delete", "entferne", "entfern", "remove", "erstelle", "erzeuge", "generiere",
    "generate", "exportiere", "export", "rendere", "render", "starte", "start",
    "importiere", "import", "konvertiere", "convert", "verschiebe", "move",
    "speichere", "save", "oeffne", "öffne", "schneide", "ducke", "wende",
})

# Generische Analyse-Keywords (treffen auf mehrere Domänen zu)
ANALYZE_ALL_KEYWORDS = [
    "analysiere alle", "analyze all", "alle analysieren",
    "alle files", "all files", "importiert", "imported",
    "alles analysieren", "alles prüfen",
]

# Multi-Step Keywords: Sowohl Bild ALS AUCH Ton
MULTI_STEP_KEYWORDS = [
    ("bild", "ton"), ("video", "audio"), ("visual", "audio"),
    ("sehen", "gesagt"), ("sieht", "hört"), ("visuell", "akustisch"),
    ("szene", "sprache"), ("zeigt", "sagt"), ("passiert", "gesagt"),
    ("inhalt", "transkri"), ("bild und ton", None),
    ("video und audio", None), ("analysiere bild und ton", None),
]

# Compound-Action Keywords: Mehrere unabhängige Aktionen in einem Satz
# Jeder Eintrag: (keywords_set, action_name, param_builder)
COMPOUND_ACTION_MAP = [
    {
        "keywords": ["proxy", "proxy-daten", "proxy daten", "proxy-video", "vorschau"],
        "action": "create_proxy",
    },
    {
        "keywords": ["stem", "stems", "stem-file", "stem files", "spuren trennen",
                      "vocals", "separation", "separier"],
        "action": "separate_stems",
    },
]

# B-468: Zustands-aendernde (nicht-destruktive) Actions duerfen im
# _route_to_registry-Loose-Pfad NICHT von einem schwachen Einzelwort-Fuzzy-Match
# ausgeloest werden. "zeige Projektstatus" fuzzy-matchte "save_project" mit 64%
# und fuehrte einen Write aus. Destruktive Actions sind separat geschuetzt
# (DESTRUCTIVE_FUZZY_THRESHOLD im Registry); dies erweitert dieselbe Idee auf
# Writes — sie matchen weiter bei quasi-exaktem Score. create_proxy/separate_stems
# werden bereits frueher ueber COMPOUND_ACTION_MAP abgefangen.
WRITE_ACTION_FUZZY_THRESHOLD = 90
WRITE_ACTIONS: frozenset[str] = frozenset({
    "save_project", "save_project_as", "create_project", "open_project",
    "import_file", "convert_videos", "auto_edit", "add_to_timeline",
    "set_clip_effects", "move_clip", "apply_style_preset", "add_anchor",
    "sync_anchors", "learn_anchor", "auto_ducking", "rl_feedback",
    "undo_timeline", "redo_timeline", "create_proxy",
})

# B-468: Read-Intent-Verben. Eine Lese-Anfrage nach dem Projektstatus soll zur
# Read-Action summarize_project gehen, nicht per Fuzzy zu einer Write-Action.
READ_INTENT_KEYWORDS = (
    "zeige", "zeig ", "zeig'", "show", "anzeige", "anzeigen",
    "wie ist", "wie steht", "gib mir", "was ist der",
)
PROJECT_MENTION_KEYWORDS = (
    "projektstatus", "projekt", "project", "ueberblick", "überblick", "overview",
)

# B-464: Destruktive Natural-Language-Befehle (z.B. "loesche alle Videos") werden
# sonst vom VisionAgent abgefangen (Score 0.45 wegen "Videos"/"Clip") und
# erreichen NIE den Confirm-Gate im Action-Registry. Ein Pre-Router VOR dem
# Agent-Routing erkennt destruktive Intent und leitet sie an die passende
# destruktive Action — deren Confirm-Gate dann (ohne confirm=True) anschlaegt.
DESTRUCTIVE_INTENT_VERBS = (
    "loesche", "lösche", "loesch", "lösch", "delete", "entferne", "entfern",
    "remove", "leere", "leer ", "lösche", "lösch",
)
DESTRUCTIVE_BULK_WORDS = (
    "alle", "all ", "gesamte", "gesamten", "komplett", "saemtliche", "sämtliche",
)
DESTRUCTIVE_MEDIA_WORDS = (
    "medien", "media", "videos", "clips", "dateien", "material", "audios",
)
