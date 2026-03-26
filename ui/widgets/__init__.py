"""PB Studio UI Widgets Module."""

from .stem_workspace import StemWorkspace, StemTrackWidget, WaveformWidget, TransportBar, PeakWorker
from .pacing_curve import PacingCurveWidget
from .video_preview import VideoPreviewWidget
from .task_manager_dock import TaskManagerDock
from .nav_bar import WorkspaceNavBar

__all__ = [
    "StemWorkspace", "StemTrackWidget", "WaveformWidget", "TransportBar", "PeakWorker",
    "PacingCurveWidget", "VideoPreviewWidget", "TaskManagerDock", "WorkspaceNavBar",
]
