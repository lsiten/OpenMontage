"""PM server API tests — CRUD + dialog entry + capabilities over HTTP."""

from fastapi.testclient import TestClient

from pm import server


def _client() -> TestClient:
    return TestClient(server.app)


def test_health():
    r = _client().get("/api/health")
    assert r.status_code == 200
    assert r.json()["app"] == "pm"


def test_crud_flow():
    c = _client()
    r = c.post("/api/project", json={
        "title": "黑洞科普", "pipeline_type": "animated-explainer",
        "cost_budget_usd": 2.0, "cost_mode": "warn",
    })
    assert r.status_code == 200, r.text
    pid = r.json()["project_id"]
    assert r.json()["status"] == "draft"

    r = c.get(f"/api/project/{pid}")
    assert r.status_code == 200
    assert r.json()["title"] == "黑洞科普"

    r = c.get("/api/projects")
    assert r.status_code == 200
    assert any(p["project_id"] == pid for p in r.json())

    r = c.post(f"/api/project/{pid}/status", json={"status": "planning"})
    assert r.status_code == 200
    assert r.json()["status"] == "planning"

    r = c.patch(f"/api/project/{pid}", json={"approved": True})
    assert r.status_code == 200
    assert r.json()["approved"] is True


def test_chat_and_trigger_flow():
    c = _client()
    r = c.post("/api/chat", json={"requirement": "录一个软件操作演示"})
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["pipeline_type"]
    assert resp["cost_estimate"]["total_estimated_usd"] == 0.0

    r = c.post("/api/chat/trigger", json={
        "requirement": "录一个软件操作演示",
        "pipeline_type": resp["pipeline_type"],
        "cost_budget_usd": resp["cost_estimate"]["budget_default_usd"],
    })
    assert r.status_code == 200, r.text
    pid = r.json()["project_id"]
    assert r.json()["status"] == "draft"

    # Detail combines PM write model + read-only board state.
    r = c.get(f"/api/project/{pid}/detail")
    assert r.status_code == 200
    assert r.json()["pm"]["project_id"] == pid
    assert "board" in r.json()


def test_capabilities_endpoint():
    c = _client()
    r = c.get("/api/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0
    assert body["local_available"] >= 1
    assert "未接入" in body["note"] or body["paid"]  # paid rows present


def test_unknown_project_404():
    c = _client()
    assert c.get("/api/project/nope").status_code == 404


def test_ui_pages_served():
    c = _client()
    for path in ("/", "/chat", f"/p/{'x'}"):
        assert c.get(path).status_code == 200
