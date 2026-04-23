import numpy as np
import os
from scipy.spatial.distance import cosine

class MoodRefiner:
    """
    Refines the mood of a video scene based on SigLIP embeddings and mood anchors.
    """
    
    MOOD_CLASSES = [
        "euphoric", "melancholic", "dark", "aggressive", "dreamy",
        "playful", "tense", "calm", "uplifting", "ambient"
    ]
    
    def __init__(self, anchor_path="config/mood_anchors.npz"):
        self.anchor_path = anchor_path
        self.anchors = self._load_anchors()
        
    def _load_anchors(self):
        """
        Loads mood anchors from a .npz file. Falls back to random vectors if file is missing.
        """
        if os.path.exists(self.anchor_path):
            data = np.load(self.anchor_path)
            # Ensure all mood classes are present in the anchors
            anchors = {}
            for mood in self.MOOD_CLASSES:
                if mood in data:
                    anchors[mood] = data[mood]
                else:
                    # Fallback for missing mood in npz
                    anchors[mood] = np.random.randn(1152)
            return anchors
        else:
            # Complete fallback: generate random unit vectors as anchors for each mood
            anchors = {}
            for mood in self.MOOD_CLASSES:
                vec = np.random.randn(1152)
                anchors[mood] = vec / np.linalg.norm(vec)
            return anchors

    def refine_mood(self, embedding, ai_mood=None, threshold=0.15):
        """
        Compares embedding to mood anchors using Cosine Similarity.
        
        Args:
            embedding (np.array): 1152-dim SigLIP embedding.
            ai_mood (str, optional): Prior mood from captioning.
            threshold (float): Minimum similarity to return a specific mood.
            
        Returns:
            tuple: (best_mood, confidence)
        """
        if embedding is None or len(embedding) == 0:
            return "ambient", 0.0
            
        # Ensure embedding is a numpy array
        embedding = np.array(embedding)
        
        # Calculate Cosine Similarity to each anchor
        # Similarity = 1 - Cosine Distance
        similarities = {}
        for mood, anchor in self.anchors.items():
            try:
                # distance.cosine returns 1 - similarity
                dist = cosine(embedding, anchor)
                sim = 1.0 - dist
                similarities[mood] = sim
            except Exception:
                similarities[mood] = 0.0
                
        # Combine with prior ai_mood if provided
        # Weight 0.6 for similarity, 0.4 for prior
        final_scores = {}
        for mood in self.MOOD_CLASSES:
            sim_score = similarities.get(mood, 0.0)
            
            if ai_mood and ai_mood.lower() in self.MOOD_CLASSES:
                prior_score = 1.0 if ai_mood.lower() == mood else 0.0
                final_scores[mood] = (0.6 * sim_score) + (0.4 * prior_score)
            else:
                # If no valid prior is provided, use the similarity score directly
                final_scores[mood] = sim_score
                
        # Find best mood
        best_mood = max(final_scores, key=final_scores.get)
        confidence = final_scores[best_mood]
        
        # Low confidence fallback
        # If the best raw similarity is very low, fall back to ambient/unknown
        max_raw_sim = max(similarities.values()) if similarities else 0.0
        if max_raw_sim < threshold and (ai_mood is None or ai_mood not in self.MOOD_CLASSES):
            return "ambient", max_raw_sim
            
        return best_mood, confidence
