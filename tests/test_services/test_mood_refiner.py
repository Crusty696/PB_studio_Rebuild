import unittest
import numpy as np
import os
import shutil
from services.enrichment.mood_refiner import MoodRefiner

class TestMoodRefiner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config_dir = "config_test"
        if not os.path.exists(cls.config_dir):
            os.makedirs(cls.config_dir)
        cls.anchor_path = os.path.join(cls.config_dir, "mood_anchors.npz")
        
        # Create mock anchors (1152-dim)
        moods = ["euphoric", "melancholic", "dark", "aggressive", "dreamy", 
                 "playful", "tense", "calm", "uplifting", "ambient"]
        anchors = {}
        for i, mood in enumerate(moods):
            # Create unique vectors for each mood
            vec = np.zeros(1152)
            vec[i] = 1.0 
            anchors[mood] = vec
            
        np.savez(cls.anchor_path, **anchors)
        cls.refiner = MoodRefiner(anchor_path=cls.anchor_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.config_dir):
            shutil.rmtree(cls.config_dir)

    def test_refine_mood_basic(self):
        # Create a vector very close to 'euphoric' (index 0)
        scene_embedding = np.zeros(1152)
        scene_embedding[0] = 0.9
        scene_embedding[1] = 0.1
        
        mood, confidence = self.refiner.refine_mood(scene_embedding)
        self.assertEqual(mood, "euphoric")
        self.assertGreater(confidence, 0.8)

    def test_refine_mood_with_prior(self):
        # Vector is exactly 'dark' (index 2)
        scene_embedding = np.zeros(1152)
        scene_embedding[2] = 1.0
        
        # But prior is 'aggressive' (index 3)
        # Weight 0.6 for similarity (dark), 0.4 for prior (aggressive)
        # Dark similarity will be 1.0, Aggressive similarity 0.0
        # Dark score: 0.6 * 1.0 + 0.4 * 0 = 0.6
        # Aggressive score: 0.6 * 0.0 + 0.4 * 1.0 = 0.4
        mood, confidence = self.refiner.refine_mood(scene_embedding, ai_mood="aggressive")
        self.assertEqual(mood, "dark")
        
        # If prior is 'dark' too
        mood, confidence = self.refiner.refine_mood(scene_embedding, ai_mood="dark")
        self.assertEqual(mood, "dark")
        self.assertAlmostEqual(confidence, 1.0)

    def test_refine_mood_low_confidence(self):
        # All zeros or random noise with very low similarity
        scene_embedding = np.random.rand(1152) * 0.01
        mood, confidence = self.refiner.refine_mood(scene_embedding)
        
        # Should fall back to 'ambient' or 'unknown' if similarity is too low
        # In our implementation, let's say < 0.1 is too low
        if confidence < 0.1:
            self.assertIn(mood, ["ambient", "unknown"])

if __name__ == "__main__":
    unittest.main()
