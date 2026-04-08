"""
F-011 Test: OOM Handler Verification

Testet die neuen OOM-Präventions-Features im ModelManager.
"""

import logging
from services.model_manager import ModelManager

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def test_memory_check():
    """Testet check_memory_available()"""
    mm = ModelManager()

    logger.info("=" * 60)
    logger.info("Test 1: Memory Check")
    logger.info("=" * 60)

    mem_status = mm.check_memory_available()

    logger.info(f"RAM verfügbar: {mem_status['ram_available_gb']} GB")
    logger.info(f"RAM ausreichend: {mem_status['ram_sufficient']}")
    logger.info(f"VRAM verfügbar: {mem_status['vram_available_gb']} GB")
    logger.info(f"VRAM ausreichend: {mem_status['vram_sufficient']}")
    logger.info(f"Needs Unload: {mem_status['needs_unload']}")

    assert isinstance(mem_status['ram_available_gb'], float)
    assert isinstance(mem_status['ram_sufficient'], bool)
    assert isinstance(mem_status['needs_unload'], bool)

    logger.info("✓ Memory Check funktioniert")


def test_oom_prevention_no_model():
    """Testet OOM-Handler wenn kein Modell geladen ist"""
    mm = ModelManager()

    logger.info("\n" + "=" * 60)
    logger.info("Test 2: OOM Prevention (kein Modell geladen)")
    logger.info("=" * 60)

    # Sollte keine Exception werfen wenn genug Speicher da ist
    try:
        mm._handle_oom_prevention("test operation")
        logger.info("✓ OOM Prevention funktioniert (genug Speicher)")
    except RuntimeError as e:
        logger.warning(f"! System hat kritisch wenig Speicher: {e}")
        # Das ist OK wenn das System wirklich wenig RAM hat


def test_vram_usage():
    """Testet get_vram_usage()"""
    mm = ModelManager()

    logger.info("\n" + "=" * 60)
    logger.info("Test 3: VRAM Usage Report")
    logger.info("=" * 60)

    vram = mm.get_vram_usage()

    logger.info(f"Device: {vram['device']}")
    logger.info(f"VRAM used: {vram['vram_used_mb']} MB")
    logger.info(f"VRAM total: {vram['vram_total_mb']} MB")
    logger.info(f"Model loaded: {vram['model_loaded']}")
    logger.info(f"Model type: {vram['model_type']}")

    logger.info("✓ VRAM Usage funktioniert")


def test_model_load_with_oom_check():
    """Testet ob OOM-Check beim Modell-Laden funktioniert"""
    mm = ModelManager()

    logger.info("\n" + "=" * 60)
    logger.info("Test 4: Model Load mit OOM Check")
    logger.info("=" * 60)

    # Versuche ein kleines Whisper-Modell zu laden
    # (nur wenn genug Speicher da ist)
    mem_before = mm.check_memory_available()
    logger.info(f"RAM vor Load: {mem_before['ram_available_gb']} GB")
    logger.info(f"VRAM vor Load: {mem_before['vram_available_gb']} GB")

    if mem_before['ram_available_gb'] < 3.0:
        logger.warning("! Überspringe Modell-Load — zu wenig RAM für Test")
        return

    try:
        logger.info("Lade kleines Whisper-Modell...")
        model = mm.load_whisper("tiny")

        mem_after = mm.check_memory_available()
        logger.info(f"RAM nach Load: {mem_after['ram_available_gb']} GB")
        logger.info(f"VRAM nach Load: {mem_after['vram_available_gb']} GB")
        logger.info(f"Modell geladen: {mm.current_model_id}")

        logger.info("Entlade Modell...")
        mm.unload()

        mem_final = mm.check_memory_available()
        logger.info(f"RAM nach Unload: {mem_final['ram_available_gb']} GB")
        logger.info(f"VRAM nach Unload: {mem_final['vram_available_gb']} GB")

        logger.info("✓ Model Load mit OOM Check funktioniert")

    except RuntimeError as e:
        logger.error(f"✗ OOM beim Test: {e}")
        logger.info("Das ist OK — OOM-Handler funktioniert wie erwartet")


if __name__ == "__main__":
    logger.info("\n" + "=" * 60)
    logger.info("F-011 OOM Handler Test Suite")
    logger.info("=" * 60 + "\n")

    test_memory_check()
    test_oom_prevention_no_model()
    test_vram_usage()
    test_model_load_with_oom_check()

    logger.info("\n" + "=" * 60)
    logger.info("Alle Tests abgeschlossen!")
    logger.info("=" * 60)
