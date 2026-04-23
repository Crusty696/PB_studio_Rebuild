from pathlib import Path

import numpy as np

from services.enrichment.style_bucket_clusterer import StyleBucketClusterer


def _three_gaussian_blobs(n_per_blob: int = 30, seed: int = 42) -> np.ndarray:
    """Three well-separated 1152-d Gaussian blobs."""
    rng = np.random.default_rng(seed)
    blob_centers = rng.normal(size=(3, 1152)) * 5.0
    return np.concatenate(
        [rng.normal(c, 0.3, size=(n_per_blob, 1152)) for c in blob_centers]
    ).astype(np.float32)


def test_clusters_synthetic_three_gaussians() -> None:
    embeddings = _three_gaussian_blobs()
    clusterer = StyleBucketClusterer(min_cluster_size=8, min_samples=5)
    labels, centroids, reducer = clusterer.fit(embeddings)
    non_noise = set(labels.tolist()) - {-1}
    assert len(non_noise) == 3, f"Expected 3 clusters, got {sorted(non_noise)}"
    assert centroids.shape == (3, clusterer.DEFAULT_N_COMPONENTS)


def test_reducer_pickle_roundtrip(tmp_path: Path) -> None:
    embeddings = _three_gaussian_blobs()
    clusterer = StyleBucketClusterer()
    labels, centroids, reducer = clusterer.fit(embeddings)
    path = tmp_path / "umap_v1.pkl"
    StyleBucketClusterer.save_reducer(reducer, path)
    loaded = StyleBucketClusterer.load_reducer(path)
    new_emb = np.random.default_rng(99).normal(size=1152).astype(np.float32)
    # Transform with both: must be numerically identical
    a = reducer.transform([new_emb])
    b = loaded.transform([new_emb])
    assert np.allclose(
        a, b
    ), f"Reducer pickle roundtrip failed. diff max = {np.abs(a - b).max()}"


def test_new_clip_assigned_via_nearest_centroid_without_refit() -> None:
    embeddings = _three_gaussian_blobs()
    clusterer = StyleBucketClusterer()
    labels, centroids, reducer = clusterer.fit(embeddings)
    # Build a new embedding near the first blob (should assign to cluster 0 — whichever label that is)
    rng = np.random.default_rng(7)
    blob_centers_ref = np.random.default_rng(42).normal(size=(3, 1152)) * 5.0
    # Use the same seed chain so the blob_centers match those in _three_gaussian_blobs
    new_emb = rng.normal(blob_centers_ref[0], 0.3, size=1152).astype(np.float32)
    new_label = clusterer.assign(new_emb, centroids, reducer)
    assert new_label in set(labels.tolist()) - {-1}
