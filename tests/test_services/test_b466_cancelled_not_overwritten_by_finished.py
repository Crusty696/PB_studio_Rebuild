"""B-466: Ein abgebrochener Task darf nicht als "Fertig" enden.

Kooperativer Abbruch setzt "cancelled". Der Worker laeuft danach oft normal zu
Ende und ruft ueber seinen on_finish-Handler finish_task(..., "finished", ...).
Frueher ueberschrieb das den "cancelled"-Status -> TASKS-Panel zeigte "Fertig".
Fix: finish_task ignoriert ein "finished", wenn der Task bereits "cancelled" ist.
"""

from __future__ import annotations


def test_b466_finished_does_not_overwrite_cancelled(qapp):
    from services.task_manager import GlobalTaskManager
    mgr = GlobalTaskManager.instance()
    task = mgr.create_task("Cancel then complete")

    # Kooperativer Abbruch (create_task -> status 'running' -> cancel ok)
    mgr.cancel_task(task.task_id)
    assert mgr.get_task(task.task_id).status == "cancelled"

    # Worker laeuft normal zu Ende und meldet "finished"
    mgr.finish_task(task.task_id, "finished", "Fertig")

    t = mgr.get_task(task.task_id)
    assert t.status == "cancelled", (
        f"B-466: 'finished' hat 'cancelled' ueberschrieben -> {t.status}"
    )


def test_b466_error_still_overrides_cancelled(qapp):
    """Nur 'finished' wird geblockt; ein echter Fehler darf weiter gesetzt werden."""
    from services.task_manager import GlobalTaskManager
    mgr = GlobalTaskManager.instance()
    task = mgr.create_task("Cancel then error")

    mgr.cancel_task(task.task_id)
    assert mgr.get_task(task.task_id).status == "cancelled"

    mgr.finish_task(task.task_id, "error", "Teardown-Fehler")
    assert mgr.get_task(task.task_id).status == "error"


def test_b466_normal_finish_unaffected(qapp):
    """Ohne vorherigen Cancel laeuft finish_task('finished') unveraendert."""
    from services.task_manager import GlobalTaskManager
    mgr = GlobalTaskManager.instance()
    task = mgr.create_task("Normal finish")

    mgr.finish_task(task.task_id, "finished", "Done")
    t = mgr.get_task(task.task_id)
    assert t.status == "finished"
    assert t.message == "Done"
