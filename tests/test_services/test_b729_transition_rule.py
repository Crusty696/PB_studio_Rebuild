"""B-729 — transition-Regel-Schwellen (config/enrichment_rules.yaml).

Alt: duration_lt 1.0 / motion_gte 0.6 — feuerte bei realen 4.3-10s-Szenen nie.
Neu: duration_lt 2.0 / motion_gte 0.5. Diese Tests pinnen das neue Verhalten
gegen die ECHTE Regel-Datei (kein tmp-YAML).
"""

from services.enrichment.role_classifier import classify_role_detail


def test_transition_fires_for_short_moving_scene() -> None:
    # 1.5 s / motion 0.7: unter alter Schwelle (duration_lt 1.0) KEIN Treffer,
    # mit B-729-Schwellen (duration_lt 2.0, motion_gte 0.5) Regel-Treffer.
    role, conf, matched = classify_role_detail(
        motion=0.7, duration=1.5, tags=set()
    )
    assert matched is True
    assert role == "transition"
    assert conf >= 0.8


def test_transition_does_not_fire_for_long_scene() -> None:
    # 5 s Szene: transition darf nicht feuern, egal wie viel Motion.
    role, conf, matched = classify_role_detail(
        motion=0.7, duration=5.0, tags=set()
    )
    assert not (matched and role == "transition")


def test_transition_does_not_fire_below_motion_threshold() -> None:
    # Kurz, aber ruhig (motion 0.4 < 0.5): keine transition.
    role, conf, matched = classify_role_detail(
        motion=0.4, duration=1.5, tags=set()
    )
    assert not (matched and role == "transition")
