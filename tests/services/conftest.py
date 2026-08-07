"""B-770-Hermetik: Router liest jetzt ``ollama.model`` aus dem ECHTEN
settings.json (%APPDATA%/PBStudio). Bestehende Router-Tests (z.B. B-650)
muessen maschinenunabhaengig bleiben -> Seam per autouse auf "keine
User-Wahl" pinnen (= Verhalten vor B-770). Tests, die die User-Wahl testen,
patchen den Seam selbst (spaeterer setattr gewinnt).
"""
import pytest

from services import model_router


@pytest.fixture(autouse=True)
def _no_user_selected_model(monkeypatch):
    monkeypatch.setattr(model_router, "_user_selected_model", lambda: None)
