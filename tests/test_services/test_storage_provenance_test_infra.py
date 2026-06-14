from __future__ import annotations

from services.storage_provenance.adapter_layer import resolve_artifact_path
from services.storage_provenance.layout import StorageLayout


def test_storage_provenance_test_infra_fixtures_are_offline(
    tmp_storage_root,
    mock_v2_stems,
    mock_project_with_artifacts,
    directory_link_factory,
) -> None:
    source_sha = mock_project_with_artifacts["source_sha"]
    layout = StorageLayout(tmp_storage_root)
    link_path = layout.ensure_source_root(source_sha) / "audio" / "stems"

    directory_link_factory(link_path, mock_v2_stems["stem_dir"])

    resolved = resolve_artifact_path(
        mock_project_with_artifacts["session"],
        source_sha,
        "proxy",
        storage_root=tmp_storage_root,
    )

    assert (link_path / "vocals.flac").read_bytes() == b"vocals"
    assert resolved == mock_project_with_artifacts["artifact"]
    assert resolved.read_bytes() == b"proxy"
