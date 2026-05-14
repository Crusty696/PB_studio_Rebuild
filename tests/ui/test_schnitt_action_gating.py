import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from services.schnitt_context import SchnittDataContext


def _qapp():
    return QApplication.instance() or QApplication([])


def _context(**overrides):
    data = dict(
        project_id=1,
        project_path="C:/tmp/p",
        audio_id=1,
        video_ids=(2,),
        timeline_entry_count=0,
        has_stems=False,
        has_waveform=False,
        has_beatgrid=True,
        has_video_analysis=False,
        missing_reasons=(),
    )
    data.update(overrides)
    return SchnittDataContext(**data)


def test_action_binder_disables_buttons_with_missing_reasons():
    _qapp()
    from ui.controllers.schnitt_action_binder import SchnittActionBinder

    btn_generate = QPushButton("Timeline generieren")
    btn_auto_edit = QPushButton("Auto-Edit")
    binder = SchnittActionBinder(btn_generate=btn_generate, btn_auto_edit=btn_auto_edit)

    binder.apply_context(
        _context(
            audio_id=None,
            has_beatgrid=False,
            missing_reasons=("Audio fehlt", "Beatgrid fehlt"),
        )
    )

    assert btn_generate.isEnabled() is False
    assert btn_auto_edit.isEnabled() is False
    assert "Audio fehlt" in btn_auto_edit.toolTip()
    assert "Beatgrid fehlt" in btn_generate.toolTip()


def test_action_binder_enables_buttons_when_context_ready():
    _qapp()
    from ui.controllers.schnitt_action_binder import SchnittActionBinder

    btn_generate = QPushButton("Timeline generieren")
    btn_auto_edit = QPushButton("Auto-Edit")
    binder = SchnittActionBinder(btn_generate=btn_generate, btn_auto_edit=btn_auto_edit)

    binder.apply_context(_context())

    assert btn_generate.isEnabled() is True
    assert btn_auto_edit.isEnabled() is True
    assert "bereit" in btn_auto_edit.toolTip().lower()


def test_generate_timeline_guard_stops_before_loading_when_context_blocked():
    from ui.controllers.edit_workspace import EditWorkspaceController

    messages = []
    refreshes = []
    window = SimpleNamespace(
        logger=None,
        console_text=SimpleNamespace(append=lambda text: messages.append(text)),
        _schnitt_ws=SimpleNamespace(
            enter_loading=lambda: messages.append("loading"),
            refresh_state_from_db=lambda: refreshes.append(True),
        ),
        _schnitt_action_binder=SimpleNamespace(
            refresh_current_project=lambda: False,
            block_reason=lambda: "Audio fehlt; Video fehlt",
        ),
    )

    controller = EditWorkspaceController(window)
    controller._generate_timeline_impl()

    assert messages == ["[SCHNITT] Timeline generieren blockiert: Audio fehlt; Video fehlt"]
    assert refreshes == [True]


def test_workflow_gates_do_not_count_combo_placeholders_as_ready(qapp):
    from ui.controllers.workspace_setup import WorkspaceSetupController

    audio_combo = QComboBox()
    video_combo = QComboBox()
    audio_combo.addItem("-- kein Audio --", None)
    video_combo.addItem("-- kein Video --", None)
    btn_generate = QPushButton("Timeline generieren")
    btn_auto_edit = QPushButton("Auto-Edit")

    window = SimpleNamespace(
        logger=SimpleNamespace(debug=lambda *args, **kwargs: None),
        audio_combo=audio_combo,
        video_combo=video_combo,
        btn_generate=btn_generate,
        btn_auto_edit=btn_auto_edit,
        _schnitt_action_binder=None,
    )

    WorkspaceSetupController(window)._update_workflow_gates()

    assert btn_generate.isEnabled() is False
    assert btn_auto_edit.isEnabled() is False
    assert "Audio und Video" in btn_auto_edit.toolTip()
