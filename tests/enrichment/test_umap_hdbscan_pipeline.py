import numpy as np

from services.enrichment.style_bucket_clusterer import StyleBucketClusterer


def _small_synthetic(seed: int = 42) -> np.ndarray:
    """60 embeddings in 1152-d — small but above min_cluster_size."""
    rng = np.random.default_rng(seed)
    blob_centers = rng.normal(size=(3, 1152)) * 5.0
    return np.concatenate(
        [rng.normal(c, 0.3, size=(20, 1152)) for c in blob_centers]
    ).astype(np.float32)


def test_umap_dim_is_10() -> None:
    """Contract: UMAP reduces embeddings to 10 dimensions (default)."""
    embeddings = _small_synthetic()
    clusterer = StyleBucketClusterer()
    labels, centroids, reducer = clusterer.fit(embeddings)
    reduced = reducer.transform(embeddings[:5])
    assert reduced.shape == (5, 10), f"Expected (5, 10), got {reduced.shape}"


def test_umap_params_match_research() -> None:
    """Contract: defaults match Research §Q2 (n_neighbors=30, min_dist=0.0, metric='cosine')."""
    clusterer = StyleBucketClusterer()
    embeddings = _small_synthetic()
    _labels, _centroids, reducer = clusterer.fit(embeddings)
    # UMAP exposes these as attributes after fit
    assert reducer.n_neighbors == 30
    assert reducer.min_dist == 0.0
    assert reducer.metric == "cosine"
    assert reducer.n_components == 10
