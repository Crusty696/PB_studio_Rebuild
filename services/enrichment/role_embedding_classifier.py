"""services/enrichment/role_embedding_classifier.py
====================================================

Rollenbestimmung aus dem BILD statt aus einer Wortliste.

Befund (2026-07-26), der das noetig macht
-----------------------------------------
``services/enrichment/role_classifier.py`` + ``config/enrichment_rules.yaml``
lieferten fuer 27 von 27 realen Szenen ``filler``:

* Die Regeln verlangen Tags wie ``crowd/landscape/closeup/face``; das VLM
  liefert ``jungle/bioluminescent/dancer/mystical``. ``"dancer"`` matcht
  ``"dance"`` nicht — Schnittmenge leer.
* Die einzige tag-freie Regel (``transition``) verlangt Szenendauer < 1 s,
  reale Szenen sind 4.3–10 s. Sie feuert nie.

Ergebnis: ``role_fit`` / ``tension_fit`` waren ueber alle Kandidaten
konstant und damit als Bewertungsachse wirkungslos.

Loesung
-------
Cosine gegen Rollen-Prototypen im SigLIP-Embedding-Raum — dieselbe Mechanik,
die ``MoodAnchorMatcher`` fuer Moods schon erfolgreich nutzt. Die Prototypen
liegen als ``config/role_prototypes.npz`` (ein 1152-d-Vektor pro Rolle,
erzeugt von ``scripts/generate_role_prototypes.py``).

Ehrlichkeits-Regel
------------------
Fehlen Prototypen oder Embedding, gibt es KEINEN stillen ``filler``-Default.
Der Aufrufer bekommt eine Exception bzw. ``unknown`` samt Grund.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PROTOTYPES_PATH: Path = _REPO_ROOT / "config" / "role_prototypes.npz"

# Vom Prototypen-Generator und vom Vector-Store gemeinsam genutztes Modell.
EXPECTED_SIGLIP_MODEL: str = "google/siglip-so400m-patch14-384"

ROLE_PROTOTYPE_VERSION: str = "rp1"

# B-729 Kalibrierung (2026-08-08): SigLIP-Text-Prototypen haben pro Rolle
# systematisch verschiedene Basis-Naehe zu ALLEN Bildern (gemessen ueber
# 440 Szenen: establishing mean-Cosine 0.047, action 0.004). Roher argmax
# degeneriert dadurch zu establishing/hero (317/120 von 440, vier Rollen
# praktisch nie). Teil-Zentrierung score - alpha * korpus_mean korrigiert
# den Prompt-Bias; alpha=1.0 ueberkorrigiert (filler/transition werden
# Auffangbecken — Sichtpruefung 2026-08-08), alpha=0.5 ist der per
# Frame-Sichtpruefung validierte Kompromiss.
DEFAULT_CALIBRATION_ALPHA: float = 0.5

# Softmax-Temperatur ueber den Cosine-Scores. Analog MoodAnchorMatcher
# (dort 0.1). SigLIP-Text/Bild-Cosines liegen eng beieinander (~0.0–0.15),
# eine kleinere Temperatur macht die Verteilung entscheidungsfaehig.
DEFAULT_TEMPERATURE: float = 0.05

_EPS: float = 1e-9


class RolePrototypesUnavailable(RuntimeError):
    """Prototypen-Datei fehlt oder ist unbrauchbar — Rolle bleibt ``unknown``."""


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x, axis=-1, keepdims=True))
    result: np.ndarray = e / e.sum(axis=-1, keepdims=True)
    return result


class RoleEmbeddingClassifier:
    """Naechster Rollen-Prototyp per Cosine, mit Softmax-Konfidenz.

    Parameters
    ----------
    prototypes_path:
        ``.npz`` aus ``scripts/generate_role_prototypes.py``.
    temperature:
        Softmax-Temperatur. Kleiner = entscheidungsfreudiger.
    """

    def __init__(
        self,
        prototypes_path: str | Path | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> None:
        path = Path(prototypes_path or DEFAULT_PROTOTYPES_PATH)
        if not path.exists():
            raise RolePrototypesUnavailable(
                f"Rollen-Prototypen fehlen: {path}. "
                "Erzeugen mit: python scripts/generate_role_prototypes.py"
            )
        try:
            data = np.load(str(path))
            names = sorted(n for n in data.files if not n.startswith("_"))
            if not names:
                raise RolePrototypesUnavailable(
                    f"Rollen-Prototypen-Datei {path} enthaelt keine Rollen-Arrays."
                )
            protos = np.stack([data[n] for n in names], axis=0).astype(np.float32)
        except RolePrototypesUnavailable:
            raise
        except (OSError, ValueError) as exc:
            raise RolePrototypesUnavailable(
                f"Rollen-Prototypen {path} nicht ladbar: {exc}"
            ) from exc

        self.path = path
        self._temperature = float(temperature)
        self._names: list[str] = names
        norms = np.linalg.norm(protos, axis=1, keepdims=True)
        if np.any(norms < _EPS):
            raise RolePrototypesUnavailable(
                f"Rollen-Prototypen {path} enthalten einen Null-Vektor."
            )
        self._protos_normalized: np.ndarray = protos / norms  # (R, D)
        # B-729: per-Rolle-Bias (Korpus-Mean-Cosine), None = unkalibriert.
        self._corpus_bias: np.ndarray | None = None
        self._calibration_alpha: float = 0.0

    # ------------------------------------------------------------------
    def set_corpus_calibration(
        self,
        corpus_embeddings: np.ndarray,
        alpha: float = DEFAULT_CALIBRATION_ALPHA,
    ) -> None:
        """B-729: Prompt-Bias-Korrektur aus dem Szenen-Korpus ableiten.

        Misst pro Rolle den mittleren Cosine ueber *corpus_embeddings*
        und zieht davon ``alpha``-anteilig bei jeder Klassifikation ab
        (``score - alpha * korpus_mean``). ``alpha=0`` deaktiviert die
        Kalibrierung (Bestandsverhalten).

        Raises
        ------
        ValueError
            Bei leerem Korpus, Dim-Mismatch oder alpha ausserhalb [0, 1].
        """
        if not 0.0 <= float(alpha) <= 1.0:
            raise ValueError(f"calibration alpha must be in [0, 1], got {alpha}")
        embs = np.asarray(corpus_embeddings, dtype=np.float32)
        if embs.ndim != 2 or embs.shape[0] == 0:
            raise ValueError(
                f"corpus must be non-empty 2-D (N, D), got shape {embs.shape}"
            )
        if embs.shape[1] != self.dim:
            raise ValueError(
                f"corpus embedding dim {embs.shape[1]} != prototype dim {self.dim}"
            )
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        valid = norms[:, 0] > _EPS
        if not np.any(valid):
            raise ValueError("corpus contains no embeddings with non-zero norm")
        scores = (embs[valid] / norms[valid]) @ self._protos_normalized.T
        self._corpus_bias = scores.mean(axis=0).astype(np.float32)  # (R,)
        self._calibration_alpha = float(alpha)
        logger.info(
            "B-729: Rollen-Kalibrierung gesetzt (alpha=%.2f, N=%d): %s",
            self._calibration_alpha,
            int(valid.sum()),
            {n: round(float(b), 4) for n, b in zip(self._names, self._corpus_bias)},
        )

    def _adjust(self, scores: np.ndarray) -> np.ndarray:
        """Kalibrierte Scores; unkalibriert = unveraendert."""
        if self._corpus_bias is None or self._calibration_alpha <= 0.0:
            return scores
        return scores - self._calibration_alpha * self._corpus_bias

    # ------------------------------------------------------------------
    @property
    def roles(self) -> list[str]:
        return list(self._names)

    @property
    def dim(self) -> int:
        return int(self._protos_normalized.shape[1])

    @staticmethod
    def available(prototypes_path: str | Path | None = None) -> bool:
        """True, wenn die Prototypen-Datei existiert (ohne sie zu laden)."""
        return Path(prototypes_path or DEFAULT_PROTOTYPES_PATH).exists()

    # ------------------------------------------------------------------
    def classify(self, embedding: np.ndarray) -> tuple[str, float]:
        """``(role, confidence)`` fuer ein einzelnes Szenen-Embedding.

        Raises
        ------
        ValueError
            Bei Null-Norm oder Dimensions-Mismatch (z.B. 768-d SigLIP2-base
            gegen 1152-d so400m-Prototypen) — bewusst laut statt still falsch.
        """
        emb = np.asarray(embedding, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(emb))
        if norm < _EPS:
            raise ValueError("embedding has zero L2 norm — cannot classify role")
        if emb.shape[0] != self.dim:
            raise ValueError(
                f"embedding dim {emb.shape[0]} != role-prototype dim {self.dim}; "
                f"Prototypen und Video-Embedder muessen dasselbe SigLIP-Modell "
                f"({EXPECTED_SIGLIP_MODEL}) nutzen"
            )
        scores = self._adjust(self._protos_normalized @ (emb / norm))  # (R,)
        probs = _softmax(scores / self._temperature)
        idx = int(np.argmax(probs))
        return self._names[idx], float(probs[idx])

    def classify_batch(self, embeddings: np.ndarray) -> list[tuple[str, float]]:
        """Vektorisierte Variante fuer eine ``(N, D)``-Matrix."""
        embs = np.asarray(embeddings, dtype=np.float32)
        if embs.ndim != 2:
            raise ValueError(f"expected 2-D (N, D) array, got shape {embs.shape}")
        if embs.shape[1] != self.dim:
            raise ValueError(
                f"embedding dim {embs.shape[1]} != role-prototype dim {self.dim}"
            )
        norms = np.linalg.norm(embs, axis=1, keepdims=True)
        if np.any(norms < _EPS):
            raise ValueError("one or more embeddings have zero L2 norm")
        scores = self._adjust((embs / norms) @ self._protos_normalized.T)  # (N, R)
        probs = _softmax(scores / self._temperature)
        idxs = np.argmax(probs, axis=1)
        return [
            (self._names[int(j)], float(probs[i, int(j)]))
            for i, j in enumerate(idxs)
        ]

    # ------------------------------------------------------------------
    def _get_prototype(self, name: str) -> np.ndarray:
        """Normierter Prototyp-Vektor — fuer Tests (synthetische Embeddings)."""
        idx = self._names.index(name)
        result: np.ndarray = self._protos_normalized[idx].copy()
        return result
