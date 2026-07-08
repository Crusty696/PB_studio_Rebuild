"""NEUBAU-VOLLINTEGRATION T2.5.6 (FR-S4-5): A/B-Gewichts-Vergleich als UI.

Vergleicht zwei PacingScorer-Gewichtsprofile auf dem echten Kandidatenpool
des aktiven Projekts an einem waehlbaren Zeitpunkt: Profil A = Defaults,
Profil B = drei per Spinbox veraenderte Kern-Gewichte (Energy / Audio-Mood /
Stem-Klasse). Nutzt services.pacing.ab_runner.run_ab mit dem realen
PacingScorer als scorer_factory.
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QVBoxLayout,
)

logger = logging.getLogger(__name__)


class ABCompareDialog(QDialog):
    """A/B-Vergleich zweier Scorer-Gewichtsprofile (read-only, kein Apply)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("A/B-Gewichte testen (Pacing)")
        self.setMinimumSize(560, 420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        info = QLabel(
            "Vergleicht Profil A (Standard-Gewichte) mit Profil B (deine "
            "Werte) auf dem Kandidatenpool des aktiven Projekts. "
            "Kein Eingriff in die Timeline — reine Analyse."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self.spin_time = QDoubleSpinBox()
        self.spin_time.setRange(0.0, 36000.0)
        self.spin_time.setValue(30.0)
        self.spin_time.setSuffix(" s")
        self.spin_time.setToolTip("Zeitpunkt im Track, fuer den der Kontext gebaut wird.")
        form.addRow("Zeitpunkt", self.spin_time)

        def _w(default: float) -> QDoubleSpinBox:
            sb = QDoubleSpinBox()
            sb.setRange(0.0, 2.0)
            sb.setSingleStep(0.05)
            sb.setValue(default)
            return sb

        self.spin_energy = _w(0.30)
        self.spin_mood = _w(0.25)
        self.spin_stem = _w(1.0)
        form.addRow("B: w_energy", self.spin_energy)
        form.addRow("B: w_mood_audio", self.spin_mood)
        form.addRow("B: w_stem_class", self.spin_stem)
        layout.addLayout(form)

        run_row = QHBoxLayout()
        self.btn_run = QPushButton("Vergleich ausfuehren")
        self.btn_run.setObjectName("btn_accent")
        self.btn_run.clicked.connect(self._on_run)
        run_row.addWidget(self.btn_run)
        run_row.addStretch(1)
        layout.addLayout(run_row)

        self.txt_result = QTextEdit()
        self.txt_result.setReadOnly(True)
        self.txt_result.setPlaceholderText("Ergebnis erscheint hier …")
        layout.addWidget(self.txt_result, stretch=1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)

    # ------------------------------------------------------------------
    def _load_context_and_candidates(self, t_sec: float):
        """Baut (ctx, candidates, labels) aus dem aktiven Projekt."""
        from sqlalchemy.orm import Session

        from database import AudioTrack, Scene, VideoClip, engine, get_active_project_id
        from services.pacing.bridge_mapping import build_audio_context, build_clip_features
        from services.pacing_beat_grid import _get_beat_positions

        project_id = get_active_project_id()
        if project_id is None:
            raise RuntimeError("Kein aktives Projekt.")
        with Session(engine) as s:
            track = (
                s.query(AudioTrack)
                .filter(AudioTrack.project_id == project_id,
                        AudioTrack.deleted_at.is_(None))
                .first()
            )
            if track is None:
                raise RuntimeError("Kein Audio-Track im Projekt.")
            rows = (
                s.query(Scene, VideoClip)
                .join(VideoClip, Scene.video_clip_id == VideoClip.id)
                .filter(VideoClip.project_id == project_id,
                        VideoClip.deleted_at.is_(None))
                .all()
            )
            beats = _get_beat_positions(track.id)
            ctx = build_audio_context(
                seg_start_sec=t_sec, seg_section_type=None,
                audio_track=track, beats=beats, energy_per_beat=None,
            )
            candidates, labels = [], []
            for scene, clip in rows:
                candidates.append(build_clip_features(clip.id, scene))
                from pathlib import Path
                labels.append(f"{Path(clip.file_path).stem[:34]} @{scene.start_time:.1f}s")
        if not candidates:
            raise RuntimeError("Keine analysierten Szenen im Projekt.")
        return ctx, candidates, labels

    def _on_run(self) -> None:
        try:
            from services.pacing.ab_runner import run_ab
            from services.pacing.scorer import DEFAULT_WEIGHTS, PacingScorer

            ctx, candidates, labels = self._load_context_and_candidates(
                float(self.spin_time.value()))

            weights_b = dict(DEFAULT_WEIGHTS)
            weights_b["w_energy"] = float(self.spin_energy.value())
            weights_b["w_mood_audio"] = float(self.spin_mood.value())
            weights_b["w_stem_class"] = float(self.spin_stem.value())

            def scorer_factory(weights):
                scorer = PacingScorer(weights=weights)
                return lambda clip, c: scorer.score(clip, c)[0]

            result = run_ab(candidates, ctx, DEFAULT_WEIGHTS, weights_b,
                            scorer_factory, seed=42)

            def _top(scores, k=5):
                order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
                return "\n".join(
                    f"   {labels[i]}  ->  {scores[i]:.3f}" for i in order)

            ia = candidates.index(result.choice_a)
            ib = candidates.index(result.choice_b)
            same = "IDENTISCH" if ia == ib else "UNTERSCHIEDLICH"
            self.txt_result.setPlainText(
                f"Kandidaten: {len(candidates)}  |  Wahl A vs. B: {same}\n\n"
                f"Profil A (Standard) waehlt: {labels[ia]}\n{_top(result.scores_a)}\n\n"
                f"Profil B (deine Gewichte) waehlt: {labels[ib]}\n{_top(result.scores_b)}\n"
            )
            logger.info("T2.5.6 A/B-Vergleich: %d Kandidaten, A=%s B=%s",
                        len(candidates), labels[ia], labels[ib])
        except Exception as exc:
            self.txt_result.setPlainText(f"Fehler: {exc}")
            logger.warning("A/B-Vergleich fehlgeschlagen: %s", exc)
