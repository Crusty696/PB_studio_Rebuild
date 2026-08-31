"""Laedt die Stil-Preset-Spalten, die kein Widget hat.

B-941 (Userentscheidung 2026-08-31): Von den elf Spalten der Tabelle
``style_presets`` hatten sechs keinen Leser — ``min_clip_duration``,
``max_clip_duration``, ``beat_weight``, ``kick_weight``, ``snare_weight``,
``hihat_weight``. Angewandt wurden nur ``cut_rate``, ``energy_reactivity`` und
``breakdown_behavior``, und die drei gehen ueber Widgets
(``EditWorkspaceController._apply_style_preset``).

Fuer die sechs restlichen gibt es keine Bedienelemente. Sie werden deshalb
beim Start des Auto-Edit direkt aus der Tabelle nachgeladen und in die
``AdvancedPacingSettings`` gelegt.
"""

import logging

logger = logging.getLogger(__name__)

# Reihenfolge = Reihenfolge im Settings-Objekt.
PRESET_FELDER = (
    "min_clip_duration",
    "max_clip_duration",
    "beat_weight",
    "kick_weight",
    "snare_weight",
    "hihat_weight",
)


def lade_preset_felder(preset_name: str | None) -> dict[str, float]:
    """Liefert die sechs widgetlosen Preset-Spalten als Dict.

    Leeres Dict, wenn kein Name uebergeben wurde, das Preset nicht existiert
    oder die Datenbank nicht erreichbar ist — der Aufrufer laesst die Felder
    dann auf ``None`` und der bisherige Pfad bleibt unveraendert.
    """
    name = (preset_name or "").strip()
    if not name:
        return {}

    try:
        from database import nullpool_session, StylePreset

        with nullpool_session() as session:
            preset = session.query(StylePreset).filter_by(name=name).first()
            if preset is None:
                logger.info(
                    "Stil-Preset %r nicht in der Tabelle — Preset-Felder bleiben leer.",
                    name,
                )
                return {}
            werte = {}
            for feld in PRESET_FELDER:
                wert = getattr(preset, feld, None)
                if wert is not None:
                    werte[feld] = float(wert)
    except Exception as exc:  # noqa: BLE001 — darf den Auto-Edit nie verhindern
        logger.warning("Stil-Preset %r nicht ladbar: %s", name, exc)
        return {}

    logger.info("Stil-Preset %r geladen: %s", name, werte)
    return werte
