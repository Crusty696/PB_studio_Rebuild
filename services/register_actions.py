"""
Registriert die bestehenden PB Studio Funktionen im ActionRegistry.

Dieses Modul wird beim App-Start aufgerufen. Neue Funktionen einfach
hier mit @action_registry.register(...) hinzufügen.
"""

from services.action_registry import action_registry


# --- Audio-Aktionen ---

@action_registry.register(
    name="analyze_audio",
    description="Analysiert eine Audiodatei: BPM, Beat-Positionen und Energiekurve.",
    param_schema={
        "type": "object",
        "properties": {
            "track_id": {
                "type": "integer",
                "description": "ID des AudioTracks in der Datenbank."
            }
        },
        "required": ["track_id"]
    }
)
def analyze_audio(track_id: int) -> dict:
    from services.audio_service import AudioAnalyzer
    return AudioAnalyzer().analyze_and_store(track_id)


@action_registry.register(
    name="separate_stems",
    description="Trennt einen Audiotrack in Stems (Vocals, Drums, Bass, Other) mittels KI.",
    param_schema={
        "type": "object",
        "properties": {
            "track_id": {
                "type": "integer",
                "description": "ID des AudioTracks in der Datenbank."
            }
        },
        "required": ["track_id"]
    }
)
def separate_stems(track_id: int) -> dict:
    from services.ai_audio_service import AIAudioService
    return AIAudioService().separate_stems(track_id)


# --- Video-Aktionen ---

@action_registry.register(
    name="analyze_video",
    description="Analysiert einen Videoclip: Szenen, Dauer, Auflösung.",
    param_schema={
        "type": "object",
        "properties": {
            "clip_id": {
                "type": "integer",
                "description": "ID des VideoClips in der Datenbank."
            }
        },
        "required": ["clip_id"]
    }
)
def analyze_video(clip_id: int) -> dict:
    from services.video_service import VideoAnalyzer
    return VideoAnalyzer().analyze_and_store(clip_id)


# --- Pacing-Aktionen ---

@action_registry.register(
    name="auto_edit",
    description="Erstellt automatisch eine Timeline mit Schnitten auf den Beats der Musik.",
    param_schema={
        "type": "object",
        "properties": {
            "audio_track_id": {
                "type": "integer",
                "description": "ID des AudioTracks (liefert Beat-Positionen)."
            }
        },
        "required": ["audio_track_id"]
    }
)
def auto_edit(audio_track_id: int) -> list:
    from services.pacing_service import PacingEngine
    return PacingEngine().auto_edit(audio_track_id)


# --- Ingest-Aktionen ---

@action_registry.register(
    name="import_file",
    description="Importiert eine Audio- oder Videodatei in das aktuelle Projekt.",
    param_schema={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Vollständiger Pfad zur Datei."
            },
            "project_id": {
                "type": "integer",
                "description": "ID des Zielprojekts."
            }
        },
        "required": ["file_path", "project_id"]
    }
)
def import_file(file_path: str, project_id: int) -> dict:
    from services.ingest_service import IngestService
    return IngestService().import_file(file_path, project_id)


# --- Export-Aktionen ---

@action_registry.register(
    name="export_timeline",
    description="Exportiert die aktuelle Timeline als fertige Videodatei.",
    param_schema={
        "type": "object",
        "properties": {
            "project_id": {
                "type": "integer",
                "description": "ID des Projekts zum Exportieren."
            },
            "output_path": {
                "type": "string",
                "description": "Pfad für die Ausgabedatei (optional)."
            }
        },
        "required": ["project_id"]
    }
)
def export_timeline(project_id: int, output_path: str | None = None) -> dict:
    from services.export_service import ExportService
    return ExportService().export(project_id, output_path)


# --- Info-Aktionen ---

@action_registry.register(
    name="list_actions",
    description="Zeigt alle verfügbaren Aktionen an, die die KI ausführen kann.",
    param_schema={"type": "object", "properties": {}}
)
def list_actions() -> list[str]:
    return action_registry.list_actions()
