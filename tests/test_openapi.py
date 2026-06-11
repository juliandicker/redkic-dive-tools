from function_app import fastapi_app


def test_openapi_schema_generated():
    schema = fastapi_app.openapi()
    assert schema["info"]["title"] == "GasBlender API"
    assert schema["info"]["version"] == "1.0.0"


def test_openapi_endpoints_present():
    schema = fastapi_app.openapi()
    paths = schema["paths"]
    assert "/api/TrimixBlend" in paths
    assert "/api/DivePlanner" in paths


def test_openapi_request_response_models():
    schema = fastapi_app.openapi()
    components = schema.get("components", {}).get("schemas", {})
    assert "TrimixBlendRequest" in components
    assert "TrimixBlendResponse" in components
    assert "DivePlannerRequest" in components
    assert "DivePlannerResponse" in components
