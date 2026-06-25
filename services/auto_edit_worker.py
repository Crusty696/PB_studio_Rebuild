"""Re-Export-Shim fuer AutoEditWorker.

Plan ``docs/superpowers/archive/2026-05-09-schnitt-workspace-redesign/
09_WORKER_REFACTOR.md`` referenziert ``services.auto_edit_worker``;
die Klasse lebt aber historisch in ``workers.edit``. Dieser Shim
haelt den im Plan dokumentierten Import-Pfad funktionsfaehig, ohne
den Worker doppelt zu pflegen.
"""
from __future__ import annotations

from workers.edit import AutoEditWorker

__all__ = ["AutoEditWorker"]
