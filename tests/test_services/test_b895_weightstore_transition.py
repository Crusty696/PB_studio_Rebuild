from pathlib import Path

from services.brain.context_resolver import CutContext, context_keys
from services.brain.storage.migration_runner import migrate
from services.brain.weight_store import WeightStore


def test_weight_learning_crosses_confidence_threshold_without_scale_jump(tmp_path) -> None:
    db_path = tmp_path / "weights.db"
    migration_dir = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "brain"
        / "storage"
        / "sql_migrations"
        / "weights"
    )
    migrate(db_path, migration_dir)
    store = WeightStore(db_path)
    keys = context_keys(CutContext())
    try:
        for _ in range(9):
            store.update("kick_weight", 0, keys[0], 1.0, 0.0)
        weight_at_nine = store.get_posterior_mean("kick_weight", keys)

        store.update("kick_weight", 0, keys[0], 1.0, 0.0)
        weight_at_ten = store.get_posterior_mean("kick_weight", keys)
    finally:
        store.close()

    assert weight_at_nine > 1.2
    assert weight_at_ten > weight_at_nine
    assert (weight_at_ten - weight_at_nine) / weight_at_nine < 0.10
