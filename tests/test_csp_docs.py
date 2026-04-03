"""Tests for route-aware CSP headers, especially FastAPI docs pages."""

import re

from fastapi.testclient import TestClient

from app.api.main import app


client = TestClient(app)


def test_docs_csp_is_self_hosted_only() -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy", "")
    assert "https://cdn.jsdelivr.net" not in csp
    assert "https://fastapi.tiangolo.com" not in csp
    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp


def test_docs_html_uses_local_assets() -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    html = response.text
    assert "/docs-assets/swagger-ui-bundle.js" in html
    assert "/docs-assets/swagger-ui.css" in html
    assert "/docs-assets/favicon-32x32.png" in html


def test_docs_html_has_no_external_urls() -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    html = response.text
    external_matches = re.findall(r"https?://", html)
    assert len(external_matches) == 0


def test_root_csp_remains_strict() -> None:
    response = client.get("/")
    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy", "")
    assert "https://cdn.jsdelivr.net" not in csp
    assert "https://fastapi.tiangolo.com" not in csp


def test_docs_assets_are_served_locally() -> None:
    response = client.get("/docs-assets/swagger-ui-bundle.js")
    assert response.status_code == 200
    assert "SwaggerUIBundle" in response.text


def test_redoc_route_disabled() -> None:
    response = client.get("/redoc")
    assert response.status_code != 200
