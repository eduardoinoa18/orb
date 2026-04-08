"""Pytest configuration for ORB.

This file tells pytest where to find our Python packages.
Because our top-level package is called 'platform' (which shadows Python's
standard-library 'platform' module), we explicitly insert the project root
at the front of sys.path so the local package always wins.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import app

# Make sure `orb-platform/` is the first place Python looks for imports.
# We renamed 'platform/' to 'app/' to avoid shadowing Python's built-in
# 'platform' stdlib module (which caused pytest to crash at startup).
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def client():
	"""FastAPI TestClient for making HTTP requests to the app."""
	return TestClient(app)
