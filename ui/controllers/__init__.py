"""PBWindow Controllers — Refactored from Mixins."""

from ui.controllers.worker_dispatcher import WorkerDispatcherController
from ui.controllers.audio_analysis import AudioAnalysisController
from ui.controllers.video_analysis import VideoAnalysisController
from ui.controllers.edit_workspace import EditWorkspaceController
from ui.controllers.import_media import ImportMediaController
from ui.controllers.convert import ConvertController
from ui.controllers.export import ExportController
from ui.controllers.stems import StemsController
from ui.controllers.search import SearchController
from ui.controllers.workspace_setup import WorkspaceSetupController
from ui.controllers.panel_setup import PanelSetupController
from ui.controllers.project_management import ProjectManagementController
from ui.controllers.media_table import MediaTableController

__all__ = [
    "WorkerDispatcherController",
    "AudioAnalysisController",
    "VideoAnalysisController",
    "EditWorkspaceController",
    "ImportMediaController",
    "ConvertController",
    "ExportController",
    "StemsController",
    "SearchController",
    "WorkspaceSetupController",
    "PanelSetupController",
    "ProjectManagementController",
    "MediaTableController",
]
