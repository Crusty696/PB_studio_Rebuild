"""B-108 / BUG-5-b regression test:

``services/analysis_status_service.py`` used the deprecated
``datetime.utcnow()``. Python 3.12 raises a ``DeprecationWarning`` and
3.14+ removes it. Sister modules already use the timezone-aware form
(``services/pacing/pattern_aggregator.py:241``,
``workers/structure_enrichment.py:348``).

Test source-inspects the module to ensure no ``utcnow()`` call remains.
"""

from __future__ import annotations

import inspect

from services import analysis_status_service


def test_no_utcnow_calls_in_analysis_status_service() -> None:
    src = inspect.getsource(analysis_status_service)
    assert "datetime.utcnow" not in src, (
        "BUG-5-b regression: services/analysis_status_service.py uses "
        "datetime.utcnow(), which is deprecated since Python 3.12 and "
        "raises a DeprecationWarning. Use datetime.now(timezone.utc) "
        "instead."
    )
