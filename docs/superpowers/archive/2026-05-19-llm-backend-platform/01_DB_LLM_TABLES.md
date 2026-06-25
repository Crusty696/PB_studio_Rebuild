# 01 — DB-Tabellen fuer LLM-Metadaten

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19` — Tier 1 Foundation
> Status: planned · 2026-05-19

## Ziel

Schema-Migration: neue Tabellen fuer LLM-Modell-State, Lizenz-Akzept, Usage-Stats, Projekt-Pins. Alembic-Style.

## Scope

- Neue Tabellen:
  - `llm_models_installed`  — was lokal installiert ist (Backend + ID + Version + Pfad + bytes + sha + installed_at)
  - `llm_license_accepts`   — User-Akzept pro Modell (model_id, license_id, accepted_at, accepted_by_user)
  - `llm_model_pins`        — Pin pro Projekt + Rolle (project_id, role, model_id, pinned_at)
  - `llm_usage_log`         — Per-Request Counter (model_id, role, prompt_tokens, completion_tokens, latency_ms, ok)
  - `llm_settings`          — Schluessel-Wert (HF-Token-Status, Backend-Wahl, etc. — nicht Token selbst, der ist in Keyring)
- Migrations-Skript idempotent (siehe SCHNITT-Plan-Konvention A1-A3).
- DB-Schema-Version-Bump.

## Out of Scope

- Audio-V2-Tabellen (siehe V2-Plan).
- `analysis_jobs` / `analysis_artifacts` Provenance-DB (Plan C).
- Vektor-Tabellen — siehe `21_EMBEDDINGS_AND_VECTOR_STORE.md`.

## Dependencies

- Bestehende `database/models.py` + `migrations.py`.
- D-031 Konsolidierung `ollama_service` (alt) — Migration aus alten Settings-Keys.

## Skizze

```python
# database/models.py (Auszug)

class LlmModelInstalled(Base):
    __tablename__ = "llm_models_installed"
    id            = Column(Integer, primary_key=True)
    backend       = Column(String, nullable=False)        # "ollama_embedded"
    model_id      = Column(String, nullable=False)         # "qwen3:8b-q4_K_M"
    version       = Column(String, nullable=True)          # Build-Tag
    role_hint     = Column(String, nullable=True)          # "reasoner"
    bytes_on_disk = Column(Integer, nullable=False)
    sha256        = Column(String, nullable=True)
    installed_at  = Column(DateTime, server_default=func.now())
    last_used_at  = Column(DateTime, nullable=True)

class LlmLicenseAccept(Base):
    __tablename__ = "llm_license_accepts"
    id          = Column(Integer, primary_key=True)
    model_id    = Column(String, nullable=False)
    license_id  = Column(String, nullable=False)           # "apache-2.0" / "llama-community" / ...
    accepted_at = Column(DateTime, server_default=func.now())

class LlmModelPin(Base):
    __tablename__ = "llm_model_pins"
    id         = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    role       = Column(String, nullable=False)            # "reasoner" / "vision" / ...
    model_id   = Column(String, nullable=False)
    pinned_at  = Column(DateTime, server_default=func.now())
    UniqueConstraint("project_id", "role")

class LlmUsageLog(Base):
    __tablename__ = "llm_usage_log"
    id                = Column(Integer, primary_key=True)
    model_id          = Column(String, nullable=False)
    role              = Column(String, nullable=False)
    prompt_tokens     = Column(Integer)
    completion_tokens = Column(Integer)
    latency_ms        = Column(Integer)
    ok                = Column(Boolean)
    ts                = Column(DateTime, server_default=func.now())

class LlmSetting(Base):
    __tablename__ = "llm_settings"
    key   = Column(String, primary_key=True)
    value = Column(String)
```

## Offene Klaerungs-Punkte

- [ ] Bestehende `ollama_service`-Settings-Keys (Backend, default-model) — Migrations-Strategie definieren
- [ ] sha256 von GGUF-Datei optional oder pflicht?

## Verifikation

- Migration laeuft idempotent auf existierender DB
- `pytest tests/test_db/test_llm_tables_migration.py -v` gruen
