"""PB Studio Workspace Widgets — each workspace is a self-contained QWidget.

Tier-3-Sunset (2026-05-09): ``EditWorkspace`` entfernt — abgelöst durch
``SchnittWorkspace`` (siehe ``schnitt_workspace.py``).
"""

from .media_workspace import MediaWorkspace
from .stems_workspace import StemsWorkspace
from .convert_workspace import ConvertWorkspace
from .deliver_workspace import DeliverWorkspace
from .workflow_pages import AnalysisWorkspace, MaterialAnalysisWorkspace, PrepareWorkspace, ProjectDashboard

__all__ = [
    "MediaWorkspace", "StemsWorkspace",
    "ConvertWorkspace", "DeliverWorkspace",
    "AnalysisWorkspace", "MaterialAnalysisWorkspace", "PrepareWorkspace", "ProjectDashboard",
]
