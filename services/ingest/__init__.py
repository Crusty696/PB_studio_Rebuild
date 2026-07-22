"""services.ingest — ausgelagerte, entkoppelte Helper des Ingest-Service.

AUFRAEUM B1 (konservativer God-Object-Split): reiner Verbatim-Move der
entkoppelten Leaf-Helper + Konstanten aus ``services/ingest_service.py``.
Kein Logik-Change. ``services.ingest_service`` re-importiert alle hier
definierten Namen zurueck (Re-Export), damit bestehende Importe und
Test-Patches auf ``services.ingest_service.<name>`` unveraendert
funktionieren.

Wichtig: Sub-Module hier importieren NIE ``services.ingest_service``
(kein Zirkelimport).
"""
