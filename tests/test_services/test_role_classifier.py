import pytest
import os
import yaml
from services.enrichment.role_classifier import RoleClassifier

@pytest.fixture
def temp_config(tmp_path):
    config_data = {
        "role_definitions": {
            "establishing": {
                "conditions": {
                    "motion_max": 0.3,
                    "duration_min": 5.0,
                    "tags_any": ["landscape"]
                },
                "confidence_base": 0.8
            },
            "action": {
                "conditions": {
                    "motion_min": 0.6,
                    "duration_max": 4.0,
                    "tags_any": ["fast"]
                },
                "confidence_base": 0.7
            }
        },
        "default_role": "filler",
        "confidence_threshold": 0.5
    }
    config_file = tmp_path / "test_rules.yaml"
    with open(config_file, "w") as f:
        yaml.dump(config_data, f)
    return str(config_file)

def test_classify_establishing(temp_config):
    classifier = RoleClassifier(temp_config)
    # slow motion (0.1 < 0.3), long (6.0 > 5.0), "landscape" tag
    role, confidence = classifier.classify(motion_score=0.1, duration=6.0, tags=["landscape", "nature"])
    assert role == "establishing"
    assert confidence == 0.8

def test_classify_action(temp_config):
    classifier = RoleClassifier(temp_config)
    # high motion (0.8 > 0.6), short (2.0 < 4.0), "fast" tag
    role, confidence = classifier.classify(motion_score=0.8, duration=2.0, tags=["fast", "car"])
    assert role == "action"
    assert confidence == 0.7

def test_classify_default(temp_config):
    classifier = RoleClassifier(temp_config)
    # No matches
    role, confidence = classifier.classify(motion_score=0.5, duration=2.0, tags=["unknown"])
    assert role == "filler"
    assert confidence == 1.0  # Default confidence is usually 1.0 or based on config

def test_config_reload(temp_config):
    classifier = RoleClassifier(temp_config)
    
    # Change config
    with open(temp_config, "r") as f:
        data = yaml.safe_load(f)
    data["role_definitions"]["new_role"] = {
        "conditions": {"motion_min": 0.9},
        "confidence_base": 0.99
    }
    with open(temp_config, "w") as f:
        yaml.dump(data, f)
    
    # Reload (implizit oder explizit, hier testen wir ob er es beim nächsten Aufruf merkt oder wir reload() rufen müssen)
    # Laut Spec: "ensure it picks up changes". Wir implementieren ein einfaches __init__ laden, 
    # aber vielleicht wäre ein manueller reload() oder file watcher gut. 
    # In der Spec steht "ensure it picks up changes", ich füge eine reload() Methode hinzu.
    classifier.reload()
    role, confidence = classifier.classify(motion_score=0.95, duration=1.0, tags=[])
    assert role == "new_role"
    assert confidence == 0.99
