import numpy as np
from typing import List, Dict, Tuple, Optional
from sklearn.cluster import HDBSCAN

class StyleClusterer:
    """
    Clusters video scenes into stylistic buckets based on SigLIP embeddings.
    Uses HDBSCAN for initial clustering and centroid distance for incremental assignment.
    """

    def __init__(self, min_cluster_size: int = 8, min_samples: int = 4):
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples

    def cluster_all(self, embeddings: np.ndarray, metadata: List[Dict]) -> Tuple[List[int], List[Dict]]:
        """
        Perform full clustering on the provided embeddings.
        
        Args:
            embeddings: np.ndarray of shape (n_samples, 1152)
            metadata: List of metadata dicts corresponding to each embedding.
            
        Returns:
            Tuple containing:
            - List of cluster labels for each embedding.
            - List of bucket metadata (id, centroid, name, count).
        """
        if len(embeddings) < self.min_cluster_size:
            # Fallback for small datasets
            labels = [0] * len(embeddings)
            centroid = np.mean(embeddings, axis=0) if len(embeddings) > 0 else np.zeros(1152)
            buckets = [{
                "id": 0,
                "centroid": centroid,
                "name": "All",
                "count": len(embeddings)
            }]
            return labels, buckets

        # HDBSCAN clustering
        clusterer = HDBSCAN(min_cluster_size=self.min_cluster_size, min_samples=self.min_samples)
        labels = clusterer.fit_predict(embeddings).tolist()
        
        unique_labels = set(labels)
        buckets = []
        
        # Calculate centroids and metadata for each cluster (excluding noise label -1)
        for label in sorted(unique_labels):
            if label == -1:
                # Noise bucket
                indices = [i for i, l in enumerate(labels) if l == -1]
                if indices:
                    centroid = np.mean(embeddings[indices], axis=0)
                    buckets.append({
                        "id": -1,
                        "centroid": centroid,
                        "name": "Unclassified",
                        "count": len(indices)
                    })
                continue
            
            indices = [i for i, l in enumerate(labels) if l == label]
            centroid = np.mean(embeddings[indices], axis=0)
            buckets.append({
                "id": label,
                "centroid": centroid,
                "name": f"Style Bucket {label}",
                "count": len(indices)
            })
            
        # If HDBSCAN only produced noise (-1), we still want a fallback
        if not any(b["id"] >= 0 for b in buckets):
            all_centroid = np.mean(embeddings, axis=0)
            buckets = [{
                "id": 0,
                "centroid": all_centroid,
                "name": "All",
                "count": len(embeddings)
            }]
            labels = [0] * len(embeddings)

        return labels, buckets

    def assign_nearest(self, embedding: np.ndarray, buckets: List[Dict]) -> int:
        """
        Assign a single embedding to the nearest existing bucket based on centroid distance.
        
        Args:
            embedding: np.ndarray of shape (1152,)
            buckets: List of bucket metadata dictionaries containing 'centroid' and 'id'.
            
        Returns:
            The ID of the nearest bucket.
        """
        if not buckets:
            return -1
            
        # Filter out noise bucket from selection if possible, or include if it's the only one
        valid_buckets = [b for b in buckets if b["id"] >= 0]
        if not valid_buckets:
            valid_buckets = buckets
            
        distances = []
        for bucket in valid_buckets:
            dist = np.linalg.norm(embedding - bucket["centroid"])
            distances.append(dist)
            
        nearest_idx = np.argmin(distances)
        return valid_buckets[nearest_idx]["id"]
