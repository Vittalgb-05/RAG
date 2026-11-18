"""Test suite verifying OpenAPI specification completeness and contract integrity."""

import json
from pathlib import Path
from api.main import app


EXPECTED_ENDPOINTS = {
    "/api/v1/health": ["get"],
    "/api/v1/telemetry": ["get"],
    "/api/v1/telemetry/stream": ["get"],
    "/api/v1/diagnostics": ["get"],
    "/api/v1/diagnostics/logs": ["get"],
    "/api/v1/settings": ["get"],
    "/api/v1/settings/cloud": ["put"],
    "/api/v1/settings/cloud/credentials": ["delete"],
    "/api/v1/documents": ["get", "post", "delete"],
    "/api/v1/documents/{doc_id}": ["get", "delete"],
    "/api/v1/documents/{doc_id}/pages/{page_num}": ["get"],
    "/api/v1/documents/{doc_id}/evidence": ["get"],
    "/api/v1/documents/{doc_id}/pages/{page_num}/image": ["get"],
    "/api/v1/documents/{doc_id}/reindex": ["post"],
    "/api/v1/jobs": ["get"],
    "/api/v1/jobs/{job_id}": ["get"],
    "/api/v1/jobs/{job_id}/events": ["get"],
    "/api/v1/jobs/{job_id}/cancel": ["post"],
    "/api/v1/chat/sessions": ["get", "post"],
    "/api/v1/chat/sessions/{session_id}": ["get", "patch", "delete"],
    "/api/v1/chat/sessions/{session_id}/export": ["get"],
    "/api/v1/chat/sessions/{session_id}/messages/stream": ["post"],
    "/api/v1/chat/sessions/{session_id}/stop": ["post"],
    "/api/v1/summaries": ["get", "post"],
    "/api/v1/summaries/{doc_id}/{profile}": ["get"],
    "/api/v1/summaries/{doc_id}/{profile}/export": ["get"],
    "/api/v1/summaries/{doc_id}": ["delete"],
    "/api/v1/search": ["post"],
    "/api/v1/visualize/embeddings": ["get"],
    "/api/v1/visualize/query-trace": ["post"],
}


def test_openapi_schema_generation():
    schema = app.openapi()
    assert schema is not None
    assert schema.get("openapi", "").startswith("3.")
    assert schema.get("info", {}).get("title") == "RAG Assistant API"

    paths = schema.get("paths", {})
    for path, methods in EXPECTED_ENDPOINTS.items():
        assert path in paths, f"Missing expected path in OpenAPI: {path}"
        for method in methods:
            assert method in paths[path], f"Missing {method.upper()} for path: {path}"


def test_openapi_file_sync():
    schema = app.openapi()
    root_openapi = Path("openapi.json")
    assert root_openapi.exists(), "openapi.json must exist at repo root"

    stored_schema = json.loads(root_openapi.read_text(encoding="utf-8"))
    assert stored_schema["info"]["title"] == schema["info"]["title"]
    assert set(stored_schema["paths"].keys()) == set(schema["paths"].keys())
