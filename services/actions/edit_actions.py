"""Shim: edit_actions wurde in services/actions/edit/ aufgeteilt (AUFRAEUM B1).

Re-exportiert alle Actions + Helper, damit bestehende Importe + die
action_registry-Registrierung (Decorator-Side-Effect beim Import der
Sub-Module) unveraendert funktionieren. Reiner Verbatim-Code-Move, kein
Logik-Change.
"""

# Geteilte Globals + Private-Helper (Namen mit fuehrendem _ muessen explizit
# importiert werden — `import *` exportiert sie nicht).
from services.actions.edit._common import (
    _logger,
    _main_thread_invoker,
    _main_thread_invoker_lock,
    _get_task_manager,
    _validate_export_output_name,
    _get_main_window,
    _get_project_manager,
    _get_main_thread_invoker,
    _run_on_main_thread,
)

# Domaenen-Module importieren -> Decorators feuern -> Actions registriert.
# Public-Funktionsnamen kommen ueber `import *` (jedes Sub-Modul hat __all__).
from services.actions.edit.project_actions import *   # noqa: F401,F403
from services.actions.edit.media_actions import *     # noqa: F401,F403
from services.actions.edit.timeline_actions import *  # noqa: F401,F403
from services.actions.edit.anchor_actions import *    # noqa: F401,F403
from services.actions.edit.misc_actions import *      # noqa: F401,F403
