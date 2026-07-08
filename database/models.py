"""
Database models for PB Studio.

Soft-Delete-Architektur (PB-Studio-Norm, siehe docs/PB_Studio_App_Beschreibung.md):
Die Top-Level-Modelle ``Project``, ``AudioTrack`` und ``VideoClip`` tragen eine
nullable ``deleted_at``-Spalte. Soft-Deletes setzen den Timestamp; aktive Reads
filtern projektweit ueber ``<Model>.deleted_at.is_(None)`` (~50 Filter-Sites in
``services/``, ``ui/`` und ``agents/``). Hartes ``DELETE FROM`` wird im normalen
App-Fluss vermieden, weil orphane Timeline-Referenzen die KI-Pipelines zum
Crashen bringen.

Bekannte Einschraenkung (siehe Bug B-186):
Kind-Tabellen (``Scene``, ``Beatgrid``, ``WaveformData``, ``StructureSegment``,
``HotCue``, ``AudioVideoAnchor``, ``PacingBlueprint``, ``TimelineEntry``,
``ClipAnchor``) haben *keine* eigene ``deleted_at``-Spalte. Die in den
Relationships konfigurierten ``ondelete="CASCADE"`` / ``cascade="all, delete-
orphan"``-Regeln greifen nur bei harten DELETEs — bei einem Eltern-Soft-Delete
bleiben Kinder physisch sichtbar. Konsumenten muessen entweder ueber den Eltern
joinen oder eigene Filter setzen.
"""
import datetime as _datetime

from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, Boolean, UniqueConstraint, JSON, DateTime, Index, BigInteger
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    path = Column(String, nullable=False)
    resolution = Column(String, nullable=False, default="1920x1080")
    fps = Column(Float, nullable=False, default=30.0)
    deleted_at = Column(DateTime, nullable=True)  # P1-FIX: Soft-Delete Support
    transition_type = Column(String, nullable=False, default="crossfade", server_default="'crossfade'")

    # Relationships — P1-FIX: lazy='selectin' verhindert N+1 Queries
    # M-37 Fix: Changed from lazy='selectin' to lazy='select' (on-demand loading)
    # This avoids 4 extra SELECTs on every Project load when relationships aren't needed
    audio_tracks = relationship("AudioTrack", back_populates="project", cascade="all, delete-orphan", passive_deletes=True, lazy='select')
    video_clips = relationship("VideoClip", back_populates="project", cascade="all, delete-orphan", passive_deletes=True, lazy='select')
    # Bug-20 Fix: fehlende back_populates ergänzt
    pacing_blueprints = relationship("PacingBlueprint", back_populates="project", cascade="all, delete-orphan", passive_deletes=True, lazy='select')
    timeline_entries = relationship("TimelineEntry", back_populates="project", cascade="all, delete-orphan", passive_deletes=True, lazy='select')

    def __repr__(self):
        return f"<Project(id={self.id}, name='{self.name}', fps={self.fps})>"


class AnalysisJob(Base):
    """GLOBAL-STORAGE-PROVENANCE-2026-05-19: provenance job identity.

    Identity is content hash + step + step version + stable parameter hash.
    This table is intentionally independent from project-local media rows so
    cross-project reuse can find completed work by ``source_sha256``.
    """
    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index(
            "uq_analysis_jobs_identity",
            "source_sha256",
            "step_id",
            "step_version",
            "params_hash",
            unique=True,
        ),
        Index("ix_analysis_jobs_source_sha256", "source_sha256"),
        Index("ix_analysis_jobs_status", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_sha256 = Column(String, nullable=False)
    step_id = Column(String, nullable=False)
    step_version = Column(String, nullable=False)
    params_hash = Column(String, nullable=False)
    status = Column(String, nullable=False)
    produced_by_model = Column(String, nullable=True)
    produced_by_model_version = Column(String, nullable=True)
    coverage_percent = Column(Float, nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    error = Column(Text, nullable=True)

    artifacts = relationship(
        "AnalysisArtifact",
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class AnalysisArtifact(Base):
    """Artifact path relative to ``storage/by_sha/<prefix>/<source_sha256>/``."""
    __tablename__ = "analysis_artifacts"
    __table_args__ = (
        Index("ix_analysis_artifacts_job_id", "job_id"),
        Index("ix_analysis_artifacts_role", "artifact_role"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("analysis_jobs.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String, nullable=False)
    artifact_role = Column(String, nullable=False)
    path = Column(String, nullable=False)
    bytes = Column(BigInteger, nullable=True)
    sha256 = Column(String, nullable=True)

    job = relationship("AnalysisJob", back_populates="artifacts", lazy="joined")


class StepDep(Base):
    """Static dependency map between provenance steps."""
    __tablename__ = "step_deps"

    step_id = Column(String, primary_key=True)
    depends_on_step_id = Column(String, primary_key=True)
    uses_artifact_role = Column(String, nullable=True)


class ProjectSource(Base):
    """Last known project-local path for a content-addressed source file."""
    __tablename__ = "project_sources"
    __table_args__ = (
        Index(
            "uq_project_sources_project_source",
            "project_id",
            "source_sha256",
            unique=True,
        ),
        Index("ix_project_sources_source_sha256", "source_sha256"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_sha256 = Column(String, nullable=False)
    current_source_path = Column(String, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)


class AudioTrack(Base):
    __tablename__ = "audio_tracks"
    __table_args__ = (
        UniqueConstraint("project_id", "file_path", name="uq_audio_tracks_project_file"),
        Index("idx_audio_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=False)
    title = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    sample_rate = Column(Integer, nullable=True, default=44100)
    bpm = Column(Float, nullable=True)
    key = Column(String, nullable=True)
    energy_curve = Column(JSON, nullable=True)  # P1.7-FIX: JSON type for automatic serialization

    # Stem-Pfade (Phase 1: AI Stem Separation)
    stem_vocals_path = Column(String, nullable=True)
    stem_drums_path = Column(String, nullable=True)
    stem_bass_path = Column(String, nullable=True)
    stem_other_path = Column(String, nullable=True)

    # Phase 4: Erweiterte Audio-Analyse
    key_confidence = Column(Float, nullable=True)       # 0.0-1.0 Confidence der Key-Erkennung
    lufs = Column(Float, nullable=True)                 # EBU R128 Integrated Loudness (dB)
    mood = Column(String, nullable=True)                # "energetic", "melancholic", "dark", ...
    genre = Column(String, nullable=True)               # "Psytrance", "Techno", "House", ...
    is_dj_mix = Column(Boolean, nullable=True)  # DJ-Mix erkannt? None=unbekannt
    spectral_bands = Column(JSON, nullable=True)        # P1.7-FIX: 8-Band Frequenz-Energien
    transcription = Column(JSON, nullable=True)         # DEPRECATED: kept for DB compatibility
    deleted_at = Column(DateTime, nullable=True)       # P1-FIX: Soft-Delete Support

    # AUD-84: ML Key Detection — Modulation + Tension
    key_modulation_data = Column(JSON, nullable=True)   # P1.7-FIX: [{time, key, camelot, confidence}, ...]
    harmonic_tension_curve = Column(JSON, nullable=True)  # P1.7-FIX: [float, ...] Dissonanz pro Zeitschritt

    # Cycle 14 / Option A: Studio-Brain Bridge — Skalar-Spalten für AudioContext.
    # bridge_mapping.build_audio_context() liest diese Felder direkt; vorher
    # waren sie alle None weil sie im Schema fehlten (Bug-Hunter BUG-2).
    sub_genre = Column(String, nullable=True)            # "progressive_psy", "deep_house", ...
    spectral_hash = Column(String, nullable=True)        # 8-Band-Signatur-Hash für context-fingerprint
    harmonic_tension = Column(Float, nullable=True)      # Skalar = mean(harmonic_tension_curve), 0..1

    # P1-FIX: Lazy loading optimiert für N+1 Query Prevention
    project = relationship("Project", back_populates="audio_tracks", lazy='joined')
    beatgrid = relationship("Beatgrid", back_populates="audio_track", uselist=False, cascade="all, delete-orphan", passive_deletes=True, lazy='joined')
    waveform_data = relationship("WaveformData", back_populates="audio_track", uselist=False, cascade="all, delete-orphan", passive_deletes=True, lazy='joined')
    structure_segments = relationship("StructureSegment", back_populates="audio_track", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')
    hotcues = relationship("HotCue", back_populates="audio_track", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')
    audio_video_anchors = relationship("AudioVideoAnchor", back_populates="audio_track", foreign_keys="AudioVideoAnchor.audio_track_id", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')

    def __repr__(self):
        return f"<AudioTrack(id={self.id}, title='{self.title}', bpm={self.bpm})>"


class VideoClip(Base):
    __tablename__ = "video_clips"
    __table_args__ = (
        UniqueConstraint("project_id", "file_path", name="uq_video_clips_project_file"),
        Index("idx_video_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_path = Column(String, nullable=False)
    proxy_path = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    fps = Column(Float, nullable=True)
    codec = Column(String, nullable=True)
    playback_offset = Column(Float, nullable=False, default=0.0)  # F-001: Persistence für Auto-Edit Offset
    deleted_at = Column(DateTime, nullable=True)                 # P1-FIX: Soft-Delete Support

    # VIDEO-PIPELINE-ENGINE-2026-05-19 Phase 01: Pipeline-State
    video_pipeline_status = Column(String, nullable=True)         # pending/running/done/failed/partial
    video_pipeline_checkpoint_path = Column(String, nullable=True)
    stream_sha256 = Column(String, nullable=True)                 # content-hash, Container-uebergreifend
    embeddings_path = Column(String, nullable=True)               # SigLIP-npy-Pfad
    motion_path = Column(String, nullable=True)                   # RAFT-JSON-Pfad
    proxy_status = Column(String, nullable=True)                  # pending/done/failed/skipped

    # P1-FIX: Lazy loading optimiert
    project = relationship("Project", back_populates="video_clips", lazy='joined')
    scenes = relationship("Scene", back_populates="video_clip", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')
    audio_video_anchors = relationship("AudioVideoAnchor", back_populates="video_clip", foreign_keys="AudioVideoAnchor.video_clip_id", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')

    def __repr__(self):
        return f"<VideoClip(id={self.id}, path='{self.file_path}')>"


class Scene(Base):
    __tablename__ = "scenes"
    __table_args__ = (
        Index("idx_scene_video", "video_clip_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_clip_id = Column(Integer, ForeignKey("video_clips.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    label = Column(String, nullable=True)
    energy = Column(Float, nullable=True)

    # AUD-128: Gemma 4 Vision captioning
    ai_caption = Column(JSON, nullable=True)    # P1.7-FIX: {description, mood, motion, tags}
    ai_mood = Column(String, nullable=True)     # energetic|calm|dramatic|ambient
    ai_tags = Column(JSON, nullable=True)       # P1.7-FIX: ['tag1', 'tag2', ...]

    # VIDEO-PIPELINE-ENGINE-2026-05-19 Phase 01: Pipeline-Anker
    scene_index = Column(Integer, nullable=True)             # Reihenfolge im VideoClip
    keyframe_paths = Column(JSON, nullable=True)             # ["keyframes/0_start.jpg", ...]
    embedding_indices = Column(JSON, nullable=True)          # [42, 43, 44] -> embeddings.npy

    video_clip = relationship("VideoClip", back_populates="scenes", lazy='joined')

    def __repr__(self):
        return f"<Scene(id={self.id}, start={self.start_time}, end={self.end_time})>"


class Beatgrid(Base):
    __tablename__ = "beatgrids"
    __table_args__ = (
        Index("idx_beatgrid_audio", "audio_track_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False, unique=True)
    bpm = Column(Float, nullable=False)
    offset = Column(Float, nullable=False, default=0.0)
    beat_positions = Column(JSON, nullable=True)  # P1.7-FIX: JSON list of beat timestamps
    downbeat_positions = Column(JSON, nullable=True)   # P1.7-FIX: JSON list of downbeat timestamps
    energy_per_beat = Column(JSON, nullable=True)       # P1.7-FIX: JSON list of RMS energy per beat [0.0-1.0]
    stem_weighted_energy = Column(JSON, nullable=True)  # P1.7-FIX: JSON list of stem-weighted energy per beat [0.0-1.0]

    # AUD-83: Onset Rhythm Intelligence (OnsetRhythmService)
    onset_kick_data = Column(JSON, nullable=True)    # P1.7-FIX: [[time, strength], ...]
    onset_snare_data = Column(JSON, nullable=True)   # P1.7-FIX: [[time, strength], ...]
    onset_hihat_data = Column(JSON, nullable=True)   # P1.7-FIX: [[time, strength], ...]
    syncopation_score = Column(Float, nullable=True) # 0.0 (gerade) – 1.0 (synkopiert)
    groove_template = Column(String, nullable=True)  # String is correct for template name

    audio_track = relationship("AudioTrack", back_populates="beatgrid", lazy='joined')

    def __repr__(self):
        return f"<Beatgrid(id={self.id}, bpm={self.bpm})>"


class WaveformData(Base):
    """Frequenz-basierte Wellenform-Daten (Rekordbox-Style) pro Audio-Track."""
    __tablename__ = "waveform_data"
    __table_args__ = (
        Index("idx_waveform_audio", "audio_track_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Anzahl der Samples (Zeitschritte) — typisch 1 pro ~23ms (hop_length=512 bei sr=22050)
    num_samples = Column(Integer, nullable=False, default=0)
    duration = Column(Float, nullable=False, default=0.0)

    # P1.7-FIX: JSON-Arrays mit Amplituden [0.0 .. 1.0] pro Zeitschritt
    band_low = Column(JSON, nullable=False)    # Bass: 20-250 Hz (blau)
    band_mid = Column(JSON, nullable=False)    # Mitten: 250-4000 Hz (rosa/rot)
    band_high = Column(JSON, nullable=False)   # Höhen: 4000-20000 Hz (weiß/gelb)

    audio_track = relationship("AudioTrack", back_populates="waveform_data", lazy='joined')

    def __repr__(self):
        return f"<WaveformData(id={self.id}, samples={self.num_samples})>"


class PacingBlueprint(Base):
    __tablename__ = "pacing_blueprints"
    __table_args__ = (
        Index("idx_blueprint_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    style = Column(String, nullable=True)
    cuts_per_bar = Column(Integer, nullable=True, default=1)
    energy_curve = Column(JSON, nullable=True)  # P1.7-FIX: JSON array of energy values

    # Bug-20 Fix: back_populates ergänzt
    project = relationship("Project", back_populates="pacing_blueprints", lazy='joined')

    def __repr__(self):
        return f"<PacingBlueprint(id={self.id}, name='{self.name}')>"


class AudioVideoAnchor(Base):
    __tablename__ = "audio_video_anchors"
    __table_args__ = (
        Index("idx_anchor_audio", "audio_track_id"),
        Index("idx_anchor_video", "video_clip_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    video_clip_id = Column(Integer, ForeignKey("video_clips.id", ondelete="CASCADE"), nullable=False)
    audio_time = Column(Float, nullable=False)
    video_time = Column(Float, nullable=False)
    anchor_type = Column(String, nullable=True, default="beat")

    # Bug-20 Fix: fehlende Relationships ergänzt + DB-19 Fix: back_populates
    audio_track = relationship("AudioTrack", back_populates="audio_video_anchors", foreign_keys=[audio_track_id], lazy='joined')
    video_clip = relationship("VideoClip", back_populates="audio_video_anchors", foreign_keys=[video_clip_id], lazy='joined')

    def __repr__(self):
        return f"<AudioVideoAnchor(id={self.id}, type='{self.anchor_type}')>"


class ClipAnchor(Base):
    """Ein manueller Anker-Marker auf einem Timeline-Clip (Audio oder Video).

    Wird fuer die manuelle Synchronisation genutzt: Wenn ein Audio- und ein
    Video-Clip jeweils einen Anker haben, koennen sie exakt aufeinander
    ausgerichtet werden.
    """
    __tablename__ = "clip_anchors"
    __table_args__ = (
        Index("idx_clip_anchor_entry", "timeline_entry_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    timeline_entry_id = Column(Integer, ForeignKey("timeline_entries.id", ondelete="CASCADE"), nullable=False)
    time_offset = Column(Float, nullable=False)  # Offset in Sekunden relativ zum Clip-Start
    label = Column(String, nullable=True, default="")
    color = Column(String, nullable=True, default="#FF3333")

    # Bug-20 Fix: Rückbeziehung zu TimelineEntry ergänzt
    timeline_entry = relationship("TimelineEntry", back_populates="anchors", lazy='joined')

    def __repr__(self):
        return f"<ClipAnchor(id={self.id}, entry={self.timeline_entry_id}, offset={self.time_offset})>"


class AIPacingMemory(Base):
    """KI-Langzeitgedaechtnis: Speichert manuelle Schnitt-Entscheidungen fuer zukuenftige Auto-Edits.

    Wird befuellt wenn der User auf 'Als KI-Regel lernen' klickt. Die Kombination
    aus Audio-Kontext und Video-Entscheidung beeinflusst kuenftige Auto-Edits.
    """
    __tablename__ = "ai_pacing_memory"
    __table_args__ = (
        Index("idx_pacing_memory_audio", "audio_track_id"),
        Index("idx_pacing_memory_scene", "scene_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=True, default=lambda: _datetime.datetime.utcnow())

    # ── Audio-Kontext ──
    bpm = Column(Float, nullable=True)
    bass_energy = Column(Float, nullable=True)    # 0.0-1.0
    drum_energy = Column(Float, nullable=True)    # 0.0-1.0
    overall_energy = Column(Float, nullable=True) # 0.0-1.0
    mood = Column(String, nullable=True)          # "drop", "peak", "buildup", "breakdown", "warmup"
    audio_time = Column(Float, nullable=True)     # Zeitstempel im Audio (Sekunden)

    # ── Video-Entscheidung ──
    raft_motion = Column(Float, nullable=True)       # RAFT motion score (0.0-1.0)
    siglip_tags = Column(JSON, nullable=True)        # P1.7-FIX: ["outdoor", "energetic", ...]
    cut_type = Column(String, nullable=True)         # "hard_cut", "crossfade", "loop", "trim"
    crossfade_duration = Column(Float, nullable=True, default=0.0)
    section_type = Column(String, nullable=True)     # "DROP", "BUILDUP", "BREAKDOWN", ...

    # ── Referenz ──
    scene_id = Column(Integer, ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="SET NULL"), nullable=True)
    label = Column(String, nullable=True)

    def __repr__(self):
        return f"<AIPacingMemory(id={self.id}, bpm={self.bpm}, mood='{self.mood}')>"


class StructureSegment(Base):
    """Song-Struktur Segment (INTRO, BUILDUP, DROP, BREAKDOWN, OUTRO etc.)."""
    __tablename__ = "structure_segments"
    __table_args__ = (
        Index("idx_structure_audio", "audio_track_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    start_time = Column(Float, nullable=False)          # Sekunden
    end_time = Column(Float, nullable=False)             # Sekunden
    label = Column(String, nullable=False)               # "INTRO", "BUILDUP", "DROP", "BREAKDOWN", "OUTRO"
    energy = Column(Float, nullable=True)                # Durchschnittliche Energie 0.0-1.0
    confidence = Column(Float, nullable=True)            # Erkennungs-Confidence 0.0-1.0

    audio_track = relationship("AudioTrack", back_populates="structure_segments", lazy='joined')

    def __repr__(self):
        return f"<StructureSegment(id={self.id}, label='{self.label}', {self.start_time:.1f}-{self.end_time:.1f})>"


class HotCue(Base):
    """Manueller Marker auf einem Audio-Track (wie Rekordbox HotCues)."""
    __tablename__ = "hotcues"

    __table_args__ = (
        Index("idx_hotcue_audio", "audio_track_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audio_track_id = Column(Integer, ForeignKey("audio_tracks.id", ondelete="CASCADE"), nullable=False)
    time = Column(Float, nullable=False)                 # Zeitposition in Sekunden
    label = Column(String, nullable=True, default="")    # z.B. "Drop 1", "Breakdown"
    color = Column(String, nullable=True, default="#FF3333")  # Hex-Farbe
    cue_type = Column(String, nullable=True, default="cue")   # "cue", "loop", "fade"

    audio_track = relationship("AudioTrack", back_populates="hotcues", lazy='joined')

    def __repr__(self):
        return f"<HotCue(id={self.id}, time={self.time:.2f}, label='{self.label}')>"


class ModelRegistry(Base):
    """Registry aller installierten KI-Modelle (Ollama + HuggingFace).

    Verfolgt: Name, Quelle, Größe, letzte Nutzung, Installationsdatum, Status.
    Basis für Auto-Cleanup-Vorschläge (ungenutzte Modelle nach X Tagen).
    """
    __tablename__ = "model_registry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(String, nullable=False, unique=True)   # "gemma3:4b" | "google/siglip-so400m-patch14-384"
    source = Column(String, nullable=False)                   # "ollama" | "huggingface"
    display_name = Column(String, nullable=True)
    size_mb = Column(Float, nullable=True)
    installed_at = Column(DateTime, nullable=True)            # M-38 Fix: DateTime instead of String
    last_used_at = Column(DateTime, nullable=True)            # M-38 Fix: DateTime instead of String
    status = Column(String, nullable=False, default="installed")  # "installed" | "downloading" | "error"
    local_path = Column(String, nullable=True)                # HF-Cache-Pfad
    metadata_json = Column(JSON, nullable=True)               # P1.7-FIX: Parameter, Tags, Quantisierung

    def __repr__(self):
        return f"<ModelRegistry(model_id='{self.model_id}', source='{self.source}', size={self.size_mb})>"


class AgentFeedback(Base):
    """Nutzerfeedback auf KI-Agenten-Antworten — AP-5 (AUD-12).

    Basis fuer Auto-Prompt-Optimization: Positive Beispiele werden als
    Few-Shot-Beispiele in den System-Prompt injiziert, negative werden gefiltert.

    rating:  1 = positiv (Daumen hoch), -1 = negativ (Daumen runter), 0 = neutral
    """
    __tablename__ = "agent_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, nullable=True, default=lambda: _datetime.datetime.utcnow())

    # ── Kontext ──
    session_id = Column(String, nullable=True)           # Chat-Session-ID
    model_id = Column(String, nullable=True)             # "gemma3:4b" oder "google/siglip-so400m-patch14-384"
    backend = Column(String, nullable=True, default="ollama")  # "ollama" | "huggingface"

    # ── Query + Antwort ──
    user_query = Column(Text, nullable=False)            # Ursprüngliche Benutzeranfrage
    ai_response = Column(Text, nullable=False)           # KI-Antwort (JSON oder Text)
    action_name = Column(String, nullable=True)          # Erkannte Aktion (z.B. "analyze_audio")

    # ── Feedback ──
    rating = Column(Integer, nullable=False, default=0)  # 1=positiv, -1=negativ, 0=neutral
    user_comment = Column(Text, nullable=True)           # Optionaler Kommentar

    def __repr__(self):
        return f"<AgentFeedback(id={self.id}, action='{self.action_name}', rating={self.rating})>"


class StylePreset(Base):
    """Pacing Style-Preset (Techno, House, D&B etc.) mit Standard-Parametern."""
    __tablename__ = "style_presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)   # "Techno", "House", etc.
    cut_rate = Column(Float, nullable=True, default=1.0)
    energy_reactivity = Column(Float, nullable=True, default=0.7)
    breakdown_behavior = Column(String, nullable=True, default="halve")  # "halve", "16beat", "none"
    min_clip_duration = Column(Float, nullable=True, default=1.0)
    max_clip_duration = Column(Float, nullable=True, default=8.0)
    beat_weight = Column(Float, nullable=True, default=1.0)
    kick_weight = Column(Float, nullable=True, default=1.0)
    snare_weight = Column(Float, nullable=True, default=0.8)
    hihat_weight = Column(Float, nullable=True, default=0.3)
    description = Column(String, nullable=True)

    def __repr__(self):
        return f"<StylePreset(id={self.id}, name='{self.name}')>"


class TimelineEntry(Base):
    """Ein Clip auf der Timeline mit Position und Spur."""
    __tablename__ = "timeline_entries"

    __table_args__ = (
        Index("idx_timeline_project", "project_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    # B-187 / D-028: ``track`` ist ein App-Layer-Discriminator-Whitelist
    # ("audio" | "video"). DB validiert die Whitelist NICHT — Konsumenten
    # muessen das tun. Test-Riegel:
    # tests/test_database.py::TestPolymorphicMediaIdAppLayerInvariants
    track = Column(String, nullable=False)          # "audio" oder "video"
    # B-187 / D-028: ``media_id`` zeigt polymorph auf ``audio_tracks.id``
    # (wenn track == "audio") ODER ``video_clips.id`` (wenn track == "video").
    # Bewusst KEIN ForeignKey, weil SQL keine Disjunktiv-FKs kennt.
    # Referential Integrity wird im App-Layer durchgesetzt (siehe D-028).
    # Bei Hard-Delete des Ziel-Tracks bleibt diese Zeile als Orphan zurueck;
    # Konsumenten muessen via Lookup (z. B. ``ui/timeline.py``) Tot-Eintraege
    # filtern.
    media_id = Column(Integer, nullable=False)       # AudioTrack.id oder VideoClip.id
    start_time = Column(Float, nullable=False, default=0.0)
    end_time = Column(Float, nullable=True)
    lane = Column(Integer, nullable=False, default=0)

    # Phase 3: Crossfade-Dauer in Sekunden (0 = harter Cut)
    crossfade_duration = Column(Float, nullable=True, default=0.0)

    # Source-Offsets: Position im Quell-Video (fuer korrekten Export-Schnitt)
    source_start = Column(Float, nullable=True, default=0.0)  # Sekunden im Quell-Video
    source_end = Column(Float, nullable=True)                  # Sekunden im Quell-Video

    # Phase 3: Crossfade-Dauer und Farbkorrektur-Parameter (FFmpeg-Filter)
    brightness = Column(Float, nullable=True, default=0.0)   # -1.0 bis 1.0
    contrast = Column(Float, nullable=True, default=1.0)     # 0.0 bis 3.0

    # SCHNITT-Redesign 2026-05-09: Clip-Locking. Gelockte Clips bleiben bei
    # Auto-Edit-Reruns unveraendert.
    locked = Column(Boolean, nullable=False, default=False, server_default="0")

    # Bug-20 Fix: Rückbeziehungen zu Project und ClipAnchor ergänzt
    project = relationship("Project", back_populates="timeline_entries", lazy='joined')
    anchors = relationship("ClipAnchor", back_populates="timeline_entry", cascade="all, delete-orphan", passive_deletes=True, lazy='selectin')

    def __repr__(self):
        return f"<TimelineEntry(id={self.id}, track='{self.track}', start={self.start_time})>"


class AnalysisStatus(Base):
    """Status-Tracking fuer Daten-Analyse-Schritte pro Medien-Datei — VAD-36.

    Ermoeglicht Persistenz des Analyse-Fortschritts (scene_detection, bpm_detection, etc.)
    ueber App-Neustarts hinweg. Verhindert Doppel-Analysen und bietet Basis fuer UI-Dashboard.
    """
    __tablename__ = "analysis_status"
    __table_args__ = (
        UniqueConstraint("media_type", "media_id", "step_key", name="uq_analysis_status_media_step"),
        Index("idx_analysis_media", "media_type", "media_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    # B-188 / D-028: Polymorpher Discriminator analog zu ``TimelineEntry.track``.
    # Whitelist {"audio", "video"} wird im App-Layer durchgesetzt, nicht in der
    # DB. Test-Riegel: tests/test_database.py::TestPolymorphicMediaIdAppLayerInvariants.
    media_type = Column(String, nullable=False)              # "video" | "audio"
    # B-188 / D-028: Polymorpher Pointer ohne SQL-FK. Zeigt auf
    # ``audio_tracks.id`` (media_type == "audio") oder ``video_clips.id``
    # (media_type == "video"). Bei Hard-Delete des Ziel-Tracks bleibt der
    # ``analysis_status``-Eintrag als Orphan zurueck — Konsumenten (UI-
    # Dashboard, Worker-Dispatch) muessen tot-gestempelte Ziele auffangen.
    media_id = Column(Integer, nullable=False)               # FK to video_clips.id or audio_tracks.id
    step_key = Column(String, nullable=False)                # "scene_detection", "bpm_detection", etc.
    status = Column(String, nullable=False, default="pending")  # "pending" | "running" | "done" | "error"
    value_summary = Column(JSON, nullable=True)              # Summary of results, e.g. {"scenes": 12, "avg_motion": 0.73}
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    def __repr__(self):
        return f"<AnalysisStatus(id={self.id}, media_type='{self.media_type}', media_id={self.media_id}, step='{self.step_key}', status='{self.status}')>"


class TimelineSnapshot(Base):
    """SCHNITT-Redesign 2026-05-09: Snapshot des Timeline-State fuer Hybrid-Undo.

    Bei jedem Auto-Edit-Run und jedem Re-Generate persistiert
    ``services/timeline_snapshot_service.py`` den serialisierten Clip-State
    (``payload_json``) zusammen mit einer monotonen ``version`` und einem
    optionalen ``label``. Konsumenten: Timeline-State-Manager (Task 2.2)
    + Snapshot-Service (Task 2.3).
    """
    __tablename__ = "timeline_snapshots"
    __table_args__ = (
        Index("idx_snapshot_project_version", "project_id", "version"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    label = Column(String, nullable=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: _datetime.datetime.utcnow(),
    )

    def __repr__(self):
        return f"<TimelineSnapshot(id={self.id}, project_id={self.project_id}, v={self.version})>"


class ProjectNote(Base):
    """SCHNITT-Redesign 2026-05-09: Markdown-Notes pro Projekt (Sub-Tab "RL & Notes").

    1:1-Beziehung zum Projekt — UNIQUE-Constraint auf ``project_id``
    erzwingt genau einen Note-Eintrag pro Projekt. Genutzt vom
    ``services/project_notes_service.py`` (Task 2.4) mit Auto-Save
    (1 Sekunde Debounce). ``content_md`` ist Markdown-Text, default leer.
    """
    __tablename__ = "project_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    content_md = Column(Text, nullable=False, default="")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: _datetime.datetime.utcnow(),
        onupdate=lambda: _datetime.datetime.utcnow(),
    )

    def __repr__(self):
        return f"<ProjectNote(project_id={self.project_id}, len={len(self.content_md)})>"
