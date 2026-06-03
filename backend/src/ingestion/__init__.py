"""Ingestion package: seed-corpus loader, embedder, crawler, scraper.

The package is intentionally light at import time — submodules carry
their own optional-dependency imports (``voyageai``, ``trafilatura``,
``yaml``) so importing :mod:`ingestion` from a unit test that mocks
the network never pulls in the SDKs.
"""
