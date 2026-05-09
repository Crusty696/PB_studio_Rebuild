"""Phase 10.4: QSettings workflow stage v2 migration (5-tab -> 4-tab)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSettings, QCoreApplication
from PySide6.QtWidgets import QApplication
from ui.controllers.workspace_setup import _migrate_workflow_stage_index


def _qapp():
    QCoreApplication.setOrganizationName("PBStudio")
    QCoreApplication.setApplicationName("PBStudioApp")
    return QApplication.instance() or QApplication([])


def test_migrates_3_to_2():
    _qapp()
    s = QSettings("PBStudio", "PBStudioApp")
    s.setValue("window/workflowStageIndex", 3)
    s.remove("window/workflowStageMigratedV2")
    _migrate_workflow_stage_index(s)
    assert int(s.value("window/workflowStageIndex")) == 2
    assert s.value("window/workflowStageMigratedV2", False, type=bool) is True


def test_migrates_4_to_3():
    _qapp()
    s = QSettings("PBStudio", "PBStudioApp")
    s.setValue("window/workflowStageIndex", 4)
    s.remove("window/workflowStageMigratedV2")
    _migrate_workflow_stage_index(s)
    assert int(s.value("window/workflowStageIndex")) == 3


def test_idempotent_when_already_migrated():
    _qapp()
    s = QSettings("PBStudio", "PBStudioApp")
    s.setValue("window/workflowStageIndex", 2)
    s.setValue("window/workflowStageMigratedV2", True)
    _migrate_workflow_stage_index(s)
    assert int(s.value("window/workflowStageIndex")) == 2
