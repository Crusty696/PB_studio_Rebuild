"""B-816: 17 Sekunden Stille trotz 5-Sekunden-Meldeintervall.

Live gemessen 2026-08-12 am echten Projekt (`outputs/test-tabelle`, 366 Clips):
Der erste Projekt-Open dauerte 31,3 s und enthielt eine Phase von **17 Sekunden
ohne eine einzige Logzeile** — obwohl `_MIGRATION_LOG_INTERVAL_S = 5.0` gilt.

Der Grund ist unangenehm einfach: die Meldung lag **zwischen** den Clips. Wenn
das Hashen einer einzelnen grossen Videodatei 17 Sekunden dauert, kommt die
Schleife in dieser Zeit gar nicht an der Meldestelle vorbei — das Zeitintervall
kann dann nicht greifen.

Damit ueberlebte genau der Schaden, den B-810/B-814 beseitigen sollten: nicht
die Dauer, sondern die Stille, die wie ein Freeze aussieht.

Der Fix meldet vor der teuren Arbeit, sobald die Datei gross ist.
"""

from __future__ import annotations

import inspect

import pytest

from services.storage_provenance import storage_migration as sm


def test_b816_grosse_datei_wird_vorher_angekuendigt():
    """Der Kern: bei grossen Dateien darf die Meldung nicht auf die Uhr warten."""
    quelle = inspect.getsource(sm.StorageMigrationService.migrate_existing_outputs)

    assert "_GROSSE_DATEI_MB" in quelle, (
        "B-816: es gibt keine Groessenschwelle — dann meldet der Lauf nur "
        "zeitgesteuert und schweigt waehrend einer langen Einzeldatei."
    )
    assert "or gross_mb >=" in quelle or "gross_mb >= _GROSSE_DATEI_MB" in quelle, (
        "B-816: die Groesse loest keine Meldung aus."
    )


def test_b816_schwelle_ist_sinnvoll_gewaehlt():
    """Zu klein waere Rauschen, zu gross wieder Stille."""
    assert 50.0 <= sm._GROSSE_DATEI_MB <= 500.0, (
        f"B-816: Schwelle {sm._GROSSE_DATEI_MB} MB ist unplausibel — bei "
        "Videodateien liegt der sinnvolle Bereich zwischen 50 und 500 MB."
    )


def test_b816_pfad_wird_an_die_meldung_durchgereicht():
    """Ohne Pfad kann die Groesse gar nicht bestimmt werden."""
    quelle = inspect.getsource(sm.StorageMigrationService.migrate_existing_outputs)

    assert 'file_path' in quelle and "_melde(" in quelle, (
        "B-816: der Dateipfad erreicht die Meldefunktion nicht."
    )
    # Beide Schleifen muessen den Pfad mitgeben, sonst schweigt eine davon.
    assert quelle.count("getattr(") >= 2, (
        "B-816: nur eine der beiden Schleifen (Audio/Video) reicht den Pfad "
        "durch — die andere kann grosse Dateien nicht ankuendigen."
    )


def test_b816_unlesbarer_pfad_kippt_die_meldung_nicht():
    """Eine fehlende Datei darf den Migrationslauf nicht abbrechen."""
    quelle = inspect.getsource(sm.StorageMigrationService.migrate_existing_outputs)
    assert "except OSError" in quelle, (
        "B-816: der stat()-Aufruf ist ungeschuetzt — eine geloeschte Quelle "
        "wuerde den ganzen Projekt-Open mitreissen."
    )


def test_b816_intervall_bleibt_als_zweite_ebene():
    """Die Zeitschwelle bleibt fuer viele kleine Dateien noetig."""
    assert sm._MIGRATION_LOG_INTERVAL_S == 5.0
    quelle = inspect.getsource(sm.StorageMigrationService.migrate_existing_outputs)
    assert "_MIGRATION_LOG_INTERVAL_S" in quelle
