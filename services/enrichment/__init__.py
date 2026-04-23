"""services/enrichment package.

Exports the canonical enricher version string so other modules (worker,
aggregator, tests) can reference it without importing the worker itself.
"""

ENRICHER_VERSION: str = "v1"
