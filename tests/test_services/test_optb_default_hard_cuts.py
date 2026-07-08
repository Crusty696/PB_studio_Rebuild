"""AUDIT-FIXPLAN Option B: Default-Uebergaenge = harte Beat-Cuts.

Der crossfade-Export (xfade-Filtergraph) ist bei langen Timelines noch
limitiert (B9, ausstehend). Bis dahin ist der stabile Standard 'cut'.
Dieser Test sichert den Default ab (Regression-Guard fuer die Entscheidung).
"""
from services.pacing_beat_grid import AdvancedPacingSettings


def test_pacing_settings_default_transition_is_cut():
    assert AdvancedPacingSettings().transition_type == "cut"


def test_project_model_default_transition_is_cut():
    from database.models import Project
    # SQLAlchemy column default greift erst beim Insert/Flush — hier pruefen
    # wir das deklarierte Default-Argument direkt.
    col = Project.__table__.columns["transition_type"]
    assert col.default.arg == "cut"
    assert "cut" in str(col.server_default.arg)
