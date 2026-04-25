"""D-023 P6: PyInstaller-Bundle-Härtung Skeleton.

PyInstaller-Hooks für die Studio-Brain + Graph-Stack-Module. Werden zur
Build-Zeit eingebunden:

    pyinstaller --additional-hooks-dir=packaging \\
                --add-data services/graph;services/graph \\
                --add-data services/pacing;services/pacing \\
                main.py

Hidden imports — sonst entfernt PyInstaller diese Module beim
Tree-Shaking, weil sie dynamisch geladen werden.
"""
from __future__ import annotations

# PyInstaller-spezifische Hook-Variablen. Werden durch das pyinstaller
# Hook-System eingelesen (kein direkter Python-Import nötig).

hiddenimports = [
    # Pacing-Slices
    "services.pacing.bridge",
    "services.pacing.cut_snapper",
    "services.pacing.cut_density_modulator",
    "services.pacing.energy_match_reward",
    "services.pacing.phrase_boundary_constraint",
    "services.pacing.vocal_hold_modifier",
    "services.pacing.shot_type_classifier",
    "services.pacing.stem_class_bonus",
    "services.pacing.audio_mood_vector",
    "services.pacing.mood_match_score",
    "services.pacing.variety_memory",
    "services.pacing.section_coherence",
    "services.pacing.rl_reward",
    "services.pacing.rl_policy",
    "services.pacing.ab_runner",
    "services.pacing.decision_explainer",
    "services.pacing.rl_memory_v2",
    "services.pacing.audio_video_curves",
    "services.pacing.stem_section_aggregator",
    # Graph-Stack
    "services.graph.knn_backend",
    "services.graph.graph_service",
    "services.graph.sigma_renderer",
    "services.graph.cockpit_view_model",
]

datas = [
    # Default-Reward-Weights
    ("services/pacing/default_weights.json", "services/pacing"),
]

# Optional usearch (PRE-5 validiert) — wird nur enthalten wenn installiert
try:
    import usearch  # noqa: F401
    hiddenimports.append("usearch.index")
except ImportError:
    pass

# networkx + Submodule die PyInstaller manchmal versehentlich entfernt
hiddenimports.extend([
    "networkx.algorithms.shortest_paths.generic",
    "networkx.classes.digraph",
])
