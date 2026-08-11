"""B-805: Scharfschaltung der Main-Thread-Freeze-Probe.

Vorgeschichte (Vorfall 2026-08-11 19:31–19:58): die App stand 27 Minuten,
``logs/freeze_stacks.log`` blieb leer. Ursache war NICHT, dass der Watchdog
den Zustand nicht erkannt haette — er lief ueberhaupt nicht: beide Gates
(``main.py`` PBWindow-Heartbeat und ``main()``-Watchdog-Thread) verlangten
``PB_STUDIO_FREEZE_PROBE == "1"``. Diese Variable setzt nur das Test-Harness
(``tests/gui_harness.py``), nicht der normale Start. Ohne Dump ist jede
Freeze-Analyse Raten — genau das ist eingetreten.

Deshalb ist die Probe jetzt **per Default armiert**. Abschalten geht
weiterhin explizit ueber ``PB_STUDIO_FREEZE_PROBE=0`` (bzw. ``off``/``false``/
``no``).
"""
from __future__ import annotations

import os

ENV_VAR = "PB_STUDIO_FREEZE_PROBE"
_OFF_VALUES = {"0", "off", "false", "no"}


def freeze_probe_enabled(env: "os._Environ[str] | dict[str, str] | None" = None) -> bool:
    """True, wenn Heartbeat + Stack-Dump-Watchdog laufen sollen.

    Default ist ``True``. Nur ein explizites Opt-out schaltet ab.
    """
    source = os.environ if env is None else env
    raw = str(source.get(ENV_VAR, "")).strip().lower()
    return raw not in _OFF_VALUES
