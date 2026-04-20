"""Streaming Multi-Track Stem Player für mehrstündige DJ-Sets.

Spielt 4 Stem-WAV-Dateien synchron ab, OHNE sie komplett in den RAM zu laden.
Nutzt soundfile.SoundFile für chunk-weises Lesen direkt von der Festplatte.
Echtzeit-Volume und Mute pro Kanal über sounddevice Callback.

Master-Clock-Prinzip: Alle Stems laufen an derselben Zeitachse.
Seek und Mute/Unmute-Wechsel halten die Synchronität aufrecht.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
import soundfile as sf
from PySide6.QtCore import QObject, Signal, QTimer

logger = logging.getLogger(__name__)

# [C-03 FIX] Module-level import statt __import__ im Callback
try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except (ImportError, OSError) as _sd_err:
    sd = None  # type: ignore[assignment]
    _SD_AVAILABLE = False
    logger.warning("sounddevice nicht verfügbar: %s", _sd_err)


# Feste Callback-Parameter
_BLOCKSIZE = 2048
_OUT_CHANNELS = 2


class StemPlayer(QObject):
    """Streaming Stem Player — liest Audio chunk-weise von Disk.

    Kein RAM-Vollladung. Jeder Stem wird als offener SoundFile-Handle
    gehalten und im Audio-Callback synchron gelesen.

    Master-Clock: Eine einzige Frame-Position steuert alle Stems.
    Beim Unmute oder Seek werden Handles re-synchronisiert.

    Signals:
        position_changed(float)  — aktuelle Position in Sekunden
        playback_finished()      — Ende des Tracks erreicht
        state_changed(str)       — "playing", "paused", "stopped"
    """

    position_changed = Signal(float)
    playback_finished = Signal()
    state_changed = Signal(str)

    STEM_NAMES = ("vocals", "drums", "bass", "other")

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        # Offene SoundFile-Handles (streaming)
        self._handles: dict[str, sf.SoundFile] = {}
        self._sr: int = 44100
        self._total_frames: int = 0
        self._channels_per_stem: dict[str, int] = {}

        # Master-Clock Position (nur im Callback geschrieben, außer bei Seek)
        self._position: int = 0

        # [C-01/C-02 FIX] Alle shared state durch _lock geschützt
        self._lock = threading.Lock()
        self._pending_seek: int | None = None
        self._needs_resync: set[str] = set()

        # Mixer-State — geschützt durch _lock
        self._volumes: dict[str, float] = {n: 1.0 for n in self.STEM_NAMES}
        self._muted: dict[str, bool] = {n: False for n in self.STEM_NAMES}
        self._was_muted: dict[str, bool] = {n: False for n in self.STEM_NAMES}

        # Playback-State
        self._state = "stopped"
        self._stream = None

        # [I-01 FIX] Pre-allocate mix buffer + mono-stereo scratch
        self._mix_buf = np.zeros((_BLOCKSIZE, _OUT_CHANNELS), dtype=np.float32)
        self._stereo_scratch = np.zeros((_BLOCKSIZE, _OUT_CHANNELS), dtype=np.float32)

        # [M-03 FIX] RT-sicherer Fehler-Flag — kein Logger im Audio-Callback
        # Wird vom QTimer (UI-Thread) abgelesen und dann geloggt.
        self._last_callback_error: str | None = None

        # Position-Update Timer (UI-Thread, 30fps)
        self._pos_timer = QTimer(self)
        self._pos_timer.setInterval(33)
        self._pos_timer.timeout.connect(self._emit_position)

    @property
    def duration(self) -> float:
        """Track-Dauer in Sekunden."""
        if self._total_frames == 0:
            return 0.0
        return self._total_frames / self._sr

    @property
    def position(self) -> float:
        """Aktuelle Position in Sekunden."""
        return self._position / self._sr

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def _set_state_safe(self, new_state: str):
        """M-19 FIX: Thread-safe state setter for use in callbacks."""
        with self._lock:
            self._state = new_state

    @property
    def is_loaded(self) -> bool:
        return self._total_frames > 0

    def load_stems(self, stem_paths: dict[str, str | None]) -> bool:
        """Öffnet Stem-WAV-Dateien zum Streaming (lädt NICHTS in den RAM).

        Args:
            stem_paths: {"vocals": path, "drums": path, ...}

        Returns:
            True wenn mindestens ein Stem geöffnet wurde.
        """
        self.stop()
        self._close_handles()
        self._total_frames = 0
        self._position = 0

        with self._lock:
            self._pending_seek = None
            self._needs_resync.clear()

        loaded_sr = None

        for name in self.STEM_NAMES:
            path = stem_paths.get(name)
            if not path or not Path(path).exists():
                continue

            try:
                handle = sf.SoundFile(path, mode="r")
                sr = handle.samplerate
                channels = handle.channels
                frames = handle.frames

                if loaded_sr is None:
                    loaded_sr = sr
                elif sr != loaded_sr:
                    # B-03 Fix: SR-Mismatch ist ein ernstes Problem (Stem wird uebersprungen).
                    # Error-Level damit es im Log auffaellt. Stems muessen alle dieselbe
                    # Sample-Rate haben, sonst laeuft ein Stem schneller/langsamer.
                    logger.error(
                        "[StemPlayer] UEBERSPRUNGEN: %s hat SR=%s, erwartet %s. "
                        "Stem wird nicht abgespielt — bitte Stems mit gleicher SR exportieren.",
                        name, sr, loaded_sr,
                    )
                    handle.close()
                    continue

                self._handles[name] = handle
                self._channels_per_stem[name] = channels
                self._total_frames = max(self._total_frames, frames)
            except (OSError, IOError, ValueError, RuntimeError) as e:
                logger.warning("[StemPlayer] Fehler beim Öffnen von %s: %s", name, e)

        if loaded_sr:
            self._sr = loaded_sr

        # Mute-Tracking zurücksetzen
        with self._lock:
            for n in self.STEM_NAMES:
                self._was_muted[n] = self._muted.get(n, False)

        logger.info("[StemPlayer] %d Stems geöffnet (Streaming), %d Frames, SR=%s, Dauer=%.1fs (%.1fh)",
                    len(self._handles), self._total_frames, self._sr,
                    self.duration, self.duration / 3600)

        return len(self._handles) > 0

    def set_volume(self, stem_name: str, value: int):
        """Setzt Lautstärke für einen Stem (0-100)."""
        with self._lock:
            if stem_name in self._volumes:
                old_vol = self._volumes[stem_name]
                new_vol = value / 100.0
                self._volumes[stem_name] = new_vol
                # [I-02 FIX] Re-sync nur wenn von near-zero zurückkommend
                if old_vol < 0.001 and new_vol >= 0.001:
                    self._needs_resync.add(stem_name)

    def set_mute(self, stem_name: str, muted: bool):
        """Setzt Mute-Status für einen Stem."""
        # [C-01 FIX] Atomic read-modify-write unter Lock
        with self._lock:
            if stem_name in self._muted:
                was = self._muted[stem_name]
                self._muted[stem_name] = muted
                if was and not muted:
                    self._needs_resync.add(stem_name)

    def play(self):
        """Startet oder setzt Wiedergabe fort."""
        # [I-08 FIX] Guard gegen fehlendes sounddevice
        if not _SD_AVAILABLE:
            logger.warning("[StemPlayer] sounddevice nicht verfügbar — Wiedergabe unmöglich.")
            self.state_changed.emit("stopped")
            return

        if not self._handles:
            # [I-09 FIX] State-Signal emittieren damit UI synchron bleibt
            self.state_changed.emit("stopped")
            return

        with self._lock:
            if self._state == "playing":
                return

            if self._position >= self._total_frames:
                self._position = 0
            position_snapshot = self._position

        # Handles seekern AUSSERHALB des Locks (Disk-I/O)
        self._seek_all_handles(position_snapshot)

        # [NEW-02 FIX] Stream erstellen unter Lock, aber start() NACH Lock-Release
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except (OSError, RuntimeError, AttributeError) as e:
                    logger.warning("[StemPlayer] Stream-Cleanup Fehler: %s", e)

            self._stream = sd.OutputStream(
                samplerate=self._sr,
                channels=_OUT_CHANNELS,
                dtype="float32",
                callback=self._audio_callback,
                blocksize=_BLOCKSIZE,
                finished_callback=self._on_stream_finished,
            )
            self._state = "playing"

        # start() außerhalb des Locks — Callback kann sofort feuern
        self._stream.start()

        self._pos_timer.start()
        self.state_changed.emit("playing")

    def pause(self):
        """Pausiert die Wiedergabe."""
        with self._lock:
            if self._state != "playing":
                return

            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except (OSError, RuntimeError, AttributeError) as e:
                    logger.warning("[StemPlayer] Pause-Cleanup Fehler: %s", e)
                self._stream = None

            self._state = "paused"

        self._pos_timer.stop()
        self.state_changed.emit("paused")

    def stop(self):
        """Stoppt die Wiedergabe und setzt Position auf 0."""
        with self._lock:
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except (OSError, RuntimeError, AttributeError) as e:
                    logger.warning("[StemPlayer] Stop-Cleanup Fehler: %s", e)
                self._stream = None

            self._state = "stopped"
            self._position = 0
            self._pending_seek = None

        self._pos_timer.stop()
        self.state_changed.emit("stopped")
        self.position_changed.emit(0.0)

    def seek(self, seconds: float):
        """Springt zur angegebenen Position in Sekunden.

        Thread-safe: Setzt einen Pending-Seek, der im nächsten
        Audio-Callback verarbeitet wird.
        """
        frame = int(seconds * self._sr)
        frame = max(0, min(frame, self._total_frames))

        with self._lock:
            is_playing = self._state == "playing"
            if is_playing:
                # [C-02 FIX] Pending Seek unter Lock
                self._pending_seek = frame
            else:
                self._position = frame

        if not is_playing:
            self._seek_all_handles(frame)
            self.position_changed.emit(self.position)

    def toggle_play_pause(self):
        """Wechselt zwischen Play und Pause."""
        if self._state == "playing":
            self.pause()
        else:
            self.play()

    def _seek_all_handles(self, frame: int):
        """Seekert alle offenen SoundFile-Handles zur angegebenen Frame-Position."""
        for name, handle in self._handles.items():
            try:
                target = min(frame, handle.frames)
                handle.seek(target)
            except (OSError, IOError, RuntimeError) as e:
                # [C-04 FIX] Seek-Fehler loggen statt verschlucken
                logger.warning("[StemPlayer] Seek-Fehler bei %s: %s", name, e)

    def _audio_callback(self, outdata: np.ndarray, frames: int,
                        time_info, status):
        """Sounddevice Callback — liest und mixt Stems chunk-weise von Disk.

        Master-Clock-Prinzip:
        - Eine Position steuert alle Stems
        - Pending Seeks werden atomar verarbeitet
        - Unmutete Stems werden automatisch re-synced
        """
        # [C-01/C-02 FIX] Snapshot mixer state unter Lock
        with self._lock:
            pending = self._pending_seek
            if pending is not None:
                self._pending_seek = None

            # Snapshot der Mixer-Dicts (billig: nur dict.copy() auf 4 Einträge)
            volumes = dict(self._volumes)
            muted = dict(self._muted)
            was_muted = dict(self._was_muted)
            needs_resync = set(self._needs_resync)
            self._needs_resync.clear()

        # Pending Seek verarbeiten
        if pending is not None:
            self._position = pending
            for name, handle in self._handles.items():
                try:
                    handle.seek(min(pending, handle.frames))
                except (OSError, IOError, RuntimeError) as e:
                    # [M-03 FIX] Flag statt logger.warning() — RT-Callback ist nicht log-sicher
                    self._last_callback_error = f"Seek-Fehler bei {name}: {e}"

        pos = self._position
        remaining = self._total_frames - pos

        if remaining <= 0:
            outdata[:] = 0
            # [C-03 FIX] sd importiert auf Module-Ebene
            raise sd.CallbackStop()

        actual_frames = min(frames, remaining)
        out_channels = outdata.shape[1]

        # [I-01 FIX] Pre-allozierter Mix-Buffer wiederverwenden
        if frames <= self._mix_buf.shape[0] and out_channels <= self._mix_buf.shape[1]:
            mix = self._mix_buf[:frames, :out_channels]
            mix[:] = 0
        else:
            mix = np.zeros((frames, out_channels), dtype=np.float32)

        for name, handle in self._handles.items():
            is_muted = muted.get(name, False)

            # Re-Sync bei Unmute oder explizitem Resync-Request
            was = was_muted.get(name, False)
            need_resync = (was and not is_muted) or (name in needs_resync)

            if need_resync and not is_muted:
                try:
                    handle.seek(min(pos, handle.frames))
                except (OSError, IOError, RuntimeError) as e:
                    # [M-03 FIX] Flag statt logger.warning() — RT-Callback ist nicht log-sicher
                    self._last_callback_error = f"Resync-Fehler bei {name}: {e}"
                    continue

            # [C-01 FIX] was_muted update unter Lock weiter unten
            if is_muted:
                continue

            vol = volumes.get(name, 1.0)
            if vol < 0.001:
                # H-02/I-02: Bei near-zero Volume wird der Handle NICHT advanced.
                # Stattdessen wird in set_volume() ein Resync-Request gesetzt wenn
                # Volume von <0.001 zurueck auf >=0.001 steigt. Der naechste Callback
                # erkennt den Resync-Request und seeked den Handle zur aktuellen
                # Master-Clock Position. So bleibt die Synchronitaet erhalten,
                # ohne bei stummem Stem unnoetig Disk-I/O zu verursachen.
                continue

            try:
                # H-10 FIX: Use handle's actual position (.tell()), not master clock
                handle_pos = handle.tell()
                read_count = min(actual_frames, max(0, handle.frames - handle_pos))
                if read_count <= 0:
                    continue

                chunk = handle.read(read_count, dtype="float32",
                                    always_2d=True)

                if chunk.shape[0] == 0:
                    continue

                read_frames = chunk.shape[0]

                # [I-01 FIX] Mono→Stereo ohne Allocation
                if chunk.shape[1] == 1 and out_channels == 2:
                    mix[:read_frames, 0] += chunk[:, 0] * vol
                    mix[:read_frames, 1] += chunk[:, 0] * vol
                elif chunk.shape[1] > out_channels:
                    mix[:read_frames] += chunk[:, :out_channels] * vol
                else:
                    mix[:read_frames] += chunk * vol

            except (OSError, IOError, ValueError, RuntimeError) as e:
                # [M-03 FIX] Flag statt logger.warning() — RT-Callback ist nicht log-sicher
                self._last_callback_error = f"Read-Fehler bei {name}: {e}"

        # [I-01 FIX] Soft-Clipping in-place
        peak = np.abs(mix).max()
        if peak > 0.95:
            scale = 1.0 / max(peak, 0.01)
            np.multiply(mix, scale, out=mix)
            # M-18 FIX: Use np.clip() instead of np.tanh() in RT callback for performance
            np.clip(mix, -1.0, 1.0, out=mix)
            np.multiply(mix, 0.95, out=mix)

        # H-01: outdata[:frames] statt [:actual_frames] ist korrekt:
        # mix ist auf (frames, out_channels) dimensioniert und mit Nullen initialisiert.
        # Bei actual_frames < frames sind die restlichen Samples bereits 0.0
        # (durch mix[:] = 0 oben), was stille am Track-Ende erzeugt.
        outdata[:frames, :out_channels] = mix

        self._position = pos + actual_frames

        # [C-01 FIX] was_muted Update unter Lock
        with self._lock:
            for n in self.STEM_NAMES:
                self._was_muted[n] = muted.get(n, False)

    def _on_stream_finished(self):
        """Wird aufgerufen wenn der Stream endet (Ende des Tracks).

        [F-016 FIX] Diese Methode wird vom Audio-Thread aufgerufen.
        QTimer darf nur vom Owner-Thread (GUI) gesteuert werden,
        daher alles via QTimer.singleShot(0, ...) in den GUI-Thread verlagern.
        """
        QTimer.singleShot(0, self._pos_timer.stop)
        # M-19 FIX: Use thread-safe state setter instead of direct setattr
        QTimer.singleShot(0, lambda: self._set_state_safe('stopped'))
        QTimer.singleShot(0, lambda: self.playback_finished.emit())
        QTimer.singleShot(0, lambda: self.state_changed.emit("stopped"))

    def _emit_position(self):
        """Emittiert die aktuelle Position (UI-Thread Timer).

        [M-03 FIX] Liest RT-Callback-Fehler-Flag aus und loggt ihn sicher im UI-Thread.
        """
        err = self._last_callback_error
        if err is not None:
            self._last_callback_error = None
            logger.warning("[StemPlayer] %s", err)
        self.position_changed.emit(self.position)

    def _close_handles(self):
        """Schließt alle offenen SoundFile-Handles."""
        for name, handle in self._handles.items():
            try:
                handle.close()
            except (OSError, RuntimeError) as e:
                # Bug-33 Fix: Fehler protokollieren statt zu verschlucken
                logger.warning("SoundFile-Handle für '%s' konnte nicht geschlossen werden: %s", name, e)
        self._handles.clear()
        self._channels_per_stem.clear()

    def cleanup(self):
        """Gibt alle Ressourcen frei."""
        self.stop()
        self._close_handles()
        self._total_frames = 0
