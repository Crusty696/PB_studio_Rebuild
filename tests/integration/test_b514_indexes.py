import pytest
from sqlalchemy import inspect
from database.session import get_raw_engine

def test_b514_indexes_exist():
    # Prüft, ob die neu hinzugefuegten Indizes in der produktiven DB existieren
    engine = get_raw_engine()
    inspector = inspect(engine)
    
    # Check timeline_entries indexes
    timeline_indexes = inspector.get_indexes('timeline_entries')
    timeline_idx_names = [idx['name'] for idx in timeline_indexes]
    assert 'idx_timeline_project' in timeline_idx_names, (
        f"Index idx_timeline_project fehlt auf timeline_entries. Gefunden: {timeline_idx_names}"
    )
    
    # Check hotcues indexes
    hotcues_indexes = inspector.get_indexes('hotcues')
    hotcues_idx_names = [idx['name'] for idx in hotcues_indexes]
    assert 'idx_hotcue_audio' in hotcues_idx_names, (
        f"Index idx_hotcue_audio fehlt auf hotcues. Gefunden: {hotcues_idx_names}"
    )
