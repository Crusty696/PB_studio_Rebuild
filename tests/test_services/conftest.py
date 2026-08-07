"""B-770-Hermetik: ``model_router.resolve_model_for_task`` liest jetzt
``ollama.model`` aus dem ECHTEN settings.json (%APPDATA%/PBStudio). Damit
bestehende Tests (Health-Check, ask_ai, Pacing, Caption ...) nicht vom
Maschinen-Zustand abhaengen, wird der Seam per autouse auf "keine User-Wahl"
gepinnt (= Verhalten vor B-770). B-770-Tests patchen den Seam selbst
(spaeterer monkeypatch.setattr gewinnt); das Original ist dort zur
Import-Zeit gesichert.
"""
import pytest

from services import model_router


@pytest.fixture(autouse=True)
def _no_user_selected_model(monkeypatch):
    monkeypatch.setattr(model_router, "_user_selected_model", lambda: None)
