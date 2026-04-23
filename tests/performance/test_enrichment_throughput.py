import time
import numpy as np
import pytest
from services.enrichment.style_clusterer import StyleClusterer

def test_enrichment_throughput_performance():
    """
    P15: Performance Regression Test.
    Verifiziert, dass StyleClusterer.assign_nearest bei 500 Zuweisungen < 1 Sekunde bleibt.
    """
    clusterer = StyleClusterer()
    
    # 1. Mock Buckets erstellen (z.B. 10 Stil-Buckets)
    n_buckets = 10
    embedding_dim = 1152
    buckets = []
    for i in range(n_buckets):
        buckets.append({
            "id": i,
            "centroid": np.random.rand(embedding_dim).astype(np.float32),
            "name": f"Bucket {i}",
            "count": 50
        })
    
    # 2. 500 Mock Clips generieren
    n_clips = 500
    test_embeddings = np.random.rand(n_clips, embedding_dim).astype(np.float32)
    
    # 3. Latenz messen
    start_time = time.perf_counter()
    
    results = []
    for i in range(n_clips):
        bucket_id = clusterer.assign_nearest(test_embeddings[i], buckets)
        results.append(bucket_id)
        
    end_time = time.perf_counter()
    duration = end_time - start_time
    
    print(f"\nEnrichment Throughput: {n_clips} assignments in {duration:.4f}s")
    
    # Assertions
    assert len(results) == n_clips
    assert duration < 1.0, f"Performance zu niedrig: {duration:.4f}s für {n_clips} Clips (Limit: 1.0s)"

def test_kmeans_selection_logic_performance():
    """
    Simuliert die K-Means Auswahl-Logik (Top-N Auswahl pro Cluster).
    """
    n_clips = 500
    embedding_dim = 1152
    n_clusters = 5
    
    # Mock Daten: Labels für 500 Clips
    labels = np.random.randint(0, n_clusters, size=n_clips)
    embeddings = np.random.rand(n_clips, embedding_dim).astype(np.float32)
    
    start_time = time.perf_counter()
    
    # Simulation: Für jeden Cluster die zentralsten N Clips finden
    selected_indices = []
    for cluster_id in range(n_clusters):
        cluster_indices = np.where(labels == cluster_id)[0]
        if len(cluster_indices) == 0:
            continue
            
        cluster_embs = embeddings[cluster_indices]
        centroid = np.mean(cluster_embs, axis=0)
        
        # Distanzen zum Centroid berechnen
        dists = np.linalg.norm(cluster_embs - centroid, axis=1)
        
        # Top 5 nächste Clips auswählen
        top_indices = np.argsort(dists)[:5]
        selected_indices.extend(cluster_indices[top_indices])
        
    end_time = time.perf_counter()
    duration = end_time - start_time
    
    print(f"K-Means Selection: {n_clusters} clusters processing in {duration:.4f}s")
    assert duration < 0.5, f"K-Means Selection zu langsam: {duration:.4f}s"
