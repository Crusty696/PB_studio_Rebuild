"""PBWindow Mixins — extrahierte Methoden-Gruppen."""

from ui.mixins.worker_dispatcher import WorkerDispatcherMixin
from ui.mixins.audio_analysis import AudioAnalysisMixin
from ui.mixins.video_analysis import VideoAnalysisMixin
from ui.mixins.edit_workspace import EditWorkspaceMixin
from ui.mixins.import_media import ImportMediaMixin
from ui.mixins.convert import ConvertMixin
from ui.mixins.export import ExportMixin
from ui.mixins.stems import StemsMixin
from ui.mixins.search import SearchMixin
from ui.mixins.workspace_setup import WorkspaceSetupMixin
from ui.mixins.panel_setup import PanelSetupMixin
from ui.mixins.project_management import ProjectManagementMixin
from ui.mixins.media_table import MediaTableMixin

__all__ = [
    "WorkerDispatcherMixin",
    "AudioAnalysisMixin",
    "VideoAnalysisMixin",
    "EditWorkspaceMixin",
    "ImportMediaMixin",
    "ConvertMixin",
    "ExportMixin",
    "StemsMixin",
    "SearchMixin",
    "WorkspaceSetupMixin",
    "PanelSetupMixin",
    "ProjectManagementMixin",
    "MediaTableMixin",
]
