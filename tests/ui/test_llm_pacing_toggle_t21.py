"""NEUBAU-VOLLINTEGRATION T2.1 (USE-007): LLM-Pacing per UI schaltbar.

Vorher: use_llm_strategist/use_llm_pacing existierten als Gates
(pacing_service:556/832), Defaults False — repo-weit kein Setter, kein UI:
Strategist + Ollama-EDL-Pacing waren toter Code.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


class _FakeStore:
    def __init__(self, initial=None):
        self.data = dict(initial or {})
        self.set_calls = []

    def get_nested(self, *path, default=None):
        cur = self.data
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur


    # ShortcutManager-Kompatibilitaet (Singleton kann je nach Test-Reihenfolge
    # mit diesem Store initialisiert werden)
    def get_shortcut(self, action_id, default=""):
        return default

    def set_all_shortcuts(self, shortcuts):
        self.data["shortcuts"] = dict(shortcuts)

    def set_nested(self, *path, value=None):
        self.set_calls.append((path, value))
        cur = self.data
        for p in path[:-1]:
            cur = cur.setdefault(p, {})
        cur[path[-1]] = value


def _make_tab(monkeypatch, store, ollama_enabled=True):
    import services.settings_store as ss
    monkeypatch.setattr(ss, "get_settings_store", lambda: store)
    monkeypatch.setattr(ss, "get_ollama_settings", lambda: {
        "enabled": ollama_enabled, "url": "http://localhost:11434", "model": "m",
    })
    from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker
    return SchnittTabPacingAnker()


class TestLlmPacingToggles:
    def test_checkboxes_load_from_store(self, monkeypatch):
        _qapp()
        tab = _make_tab(monkeypatch, _FakeStore(
            {"pacing": {"use_llm_strategist": True, "use_llm_pacing": False}}))
        assert tab.chk_llm_strategist.isChecked() is True
        assert tab.chk_llm_pacing.isChecked() is False

    def test_toggle_persists_immediately(self, monkeypatch):
        _qapp()
        store = _FakeStore()
        tab = _make_tab(monkeypatch, store)
        # Haken-2-Fix: strategist ist default True -> auf False toggeln = echte
        # Aenderung (setChecked(True) waere ein No-op ohne toggled-Signal).
        tab.chk_llm_strategist.setChecked(False)
        tab.chk_llm_pacing.setChecked(True)
        assert (("pacing", "use_llm_strategist"), False) in store.set_calls
        assert (("pacing", "use_llm_pacing"), True) in store.set_calls

    def test_disabled_when_ollama_off(self, monkeypatch):
        """Voraussetzungs-Check: Ollama in Settings aus -> Schalter gesperrt."""
        _qapp()
        tab = _make_tab(monkeypatch, _FakeStore(), ollama_enabled=False)
        assert not tab.chk_llm_strategist.isEnabled()
        assert not tab.chk_llm_pacing.isEnabled()
        assert "Ollama" in tab.chk_llm_strategist.toolTip()

    def test_defaults(self, monkeypatch):
        # Haken-2-Fix (User 2026-07-17): Strategist default AN, Pacing default AUS.
        _qapp()
        tab = _make_tab(monkeypatch, _FakeStore())
        assert tab.chk_llm_strategist.isChecked() is True
        assert tab.chk_llm_pacing.isChecked() is False


def test_settings_dataclass_accepts_flags():
    """Controller reicht Store-Werte in AdvancedPacingSettings durch."""
    from services.pacing_beat_grid import AdvancedPacingSettings
    s = AdvancedPacingSettings(
        base_cut_rate=4, energy_reactivity=50, breakdown_behavior="halve",
        vibe="", manual_density_curve=None, anchors=[],
        use_llm_strategist=True, use_llm_pacing=True,
    )
    assert s.use_llm_strategist is True and s.use_llm_pacing is True
