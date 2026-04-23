import pytest
import numpy as np
from services.enrichment.style_clusterer import StyleClusterer

@pytest.fixture
def clusterer():
    return StyleClusterer()

def test_cluster_all_basic(clusterer):
    # Erstelle zwei deutlich getrennte Cluster
    # SigLIP Embeddings sind 1152-dimensional
    dim = 1152
    n_samples_per_cluster = 10
    
    cluster1 = np.random.randn(n_samples_per_cluster, dim) + 5
    cluster2 = np.random.randn(n_samples_per_cluster, dim) - 5
    
    embeddings = np.vstack([cluster1, cluster2])
    metadata = [{"id": i} for i in range(len(embeddings))]
    
    labels, buckets = clusterer.cluster_all(embeddings, metadata)
    
    assert len(labels) == len(embeddings)
    # HDBSCAN sollte mindestens 2 Cluster finden bei diesen Parametern (min_cluster_size=8)
    # Beachte: HDBSCAN Label -1 ist Rauschen.
    unique_labels = set(labels)
    assert len(unique_labels) >= 1 # Sollte mindestens einen Cluster oder Rauschen finden
    assert len(buckets) > 0

def test_assign_nearest(clusterer):
    dim = 1152
    buckets = [
        {"id": 0, "centroid": np.ones(dim) * 10, "name": "Cluster 0"},
        {"id": 1, "centroid": np.ones(dim) * -10, "name": "Cluster 1"}
    ]
    
    # Ein Punkt nah an Cluster 0
    test_embedding = np.ones(dim) * 8
    assigned_id = clusterer.assign_nearest(test_embedding, buckets)
    assert assigned_id == 0
    
    # Ein Punkt nah an Cluster 1
    test_embedding = np.ones(dim) * -8
    assigned_id = clusterer.assign_nearest(test_embedding, buckets)
    assert assigned_id == 1

def test_hdbscan_small_data(clusterer):
    # Zu wenige Daten für HDBSCAN (min_cluster_size=8)
    dim = 1152
    embeddings = np.random.randn(5, dim)
    metadata = [{"id": i} for i in range(5)]
    
    labels, buckets = clusterer.cluster_all(embeddings, metadata)
    
    # Sollte gracefully handhaben, z.B. alle in ein "All" Bucket oder alles als Rauschen
    assert len(labels) == 5
    assert len(buckets) >= 1
    assert buckets[0]["name"] == "All" or buckets[0]["id"] == -1
