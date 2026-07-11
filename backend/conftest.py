"""pytest configuration shared across the test suite.

`pytest-django` is configured via `pytest.ini` (DJANGO_SETTINGS_MODULE).
This file ensures the `backend/` directory is importable so that the
`config`, `catalog`, and `api` packages resolve during collection.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


import pytest


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear the process-local cache around every test.

    Cached reference data (e.g. the industry-slug set) is not transactional, so
    without this a set cached in one test could leak into the next after the DB
    rows were rolled back. Clearing before and after keeps tests independent.
    """
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
