import importlib
from pathlib import Path


def test_vector_db_default_path_uses_current_project_after_late_import(
    tmp_path, test_db_root
):
    import database.session as db_session
    from database import set_project

    # NICHT auf das Repo-Root zuruecksetzen: set_project() legt dort eine
    # Engine an und ruft create_all auf der ECHTEN pb_studio.db. Danach
    # schreibt jeder nachfolgende Test in die reale Projekt-DB.
    repo_root = test_db_root
    project_root = tmp_path / "project"
    project_root.mkdir()
    vector_db_service = None

    set_project(project_root)
    try:
        import services.vector_db_service as vector_db_service

        vector_db_service = importlib.reload(vector_db_service)
        vector_db_service._instance = None

        service = vector_db_service.VectorDBService()

        assert service.db_path == project_root / "data" / "vector" / "embeddings.db"
        assert db_session.APP_ROOT == project_root
    finally:
        if vector_db_service is not None:
            vector_db_service._instance = None
        set_project(repo_root)
