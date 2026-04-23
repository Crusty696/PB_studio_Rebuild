import numpy as np


def test_anchors_are_pairwise_orthogonal_under_0_5() -> None:
    """Release-gate (Feasibility §7 condition 5): anchor cosine similarities < 0.5 pairwise.

    If this fails, edit config/mood_anchors_v1.yaml prompts, re-run
    scripts/generate_mood_anchors.py, commit both files together.
    """
    data = np.load("config/mood_anchors.npz")
    names = sorted(data.files)  # alphabetical order, deterministic
    assert len(names) == 10, f"Expected 10 anchors, found {len(names)}: {names}"

    vecs = np.stack([data[n] / np.linalg.norm(data[n]) for n in names])
    sim = vecs @ vecs.T
    np.fill_diagonal(sim, 0.0)
    max_off_diag = float(np.abs(sim).max())

    assert max_off_diag < 0.5, (
        f"Mood anchors not orthogonal enough (max pairwise |cosine| = {max_off_diag:.3f}).\n"
        f"Adjust prompts in config/mood_anchors_v1.yaml and regenerate .npz.\n"
        f"Similarity matrix:\n{sim}"
    )
