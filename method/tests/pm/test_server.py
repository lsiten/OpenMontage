"""Server tests: the FastAPI surface via TestClient (isolated DB + projects).

The `client` fixture (conftest) points the PM store and every PROJECTS_DIR
at a per-test temp location, so these never touch the real workspace.
"""

from __future__ import annotations


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["app"] == "pm"


def test_create_and_get(client):
    r = client.post("/api/projects",
                    json={"requirement": "product promo animation", "title": "Promo"})
    assert r.status_code == 201
    body = r.json()
    pid = body["project_id"]
    assert body["status"] == "proposed"
    # detail (PM DB + Backlot derivation overlay)
    r2 = client.get(f"/api/projects/{pid}")
    assert r2.status_code == 200
    assert r2.json().get("pm") is not None
    # list is a list of views
    r3 = client.get("/api/projects")
    assert isinstance(r3.json(), list)


def test_get_unknown_returns_404(client):
    assert client.get("/api/projects/no-such-project").status_code == 404


def test_update_status(client):
    r = client.post("/api/projects", json={"requirement": "a talking head video"})
    pid = r.json()["project_id"]
    r2 = client.put(f"/api/projects/{pid}", json={"status": "in_progress"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "in_progress"
    # status view reflects the update
    r3 = client.get(f"/api/projects/{pid}/status")
    assert r3.status_code == 200
    assert r3.json()["pm_status"] == "in_progress"


def test_cost_view_zero_paid(client):
    r = client.post("/api/projects", json={"requirement": "make a short film"})
    pid = r.json()["project_id"]
    r2 = client.get(f"/api/projects/{pid}/cost")
    assert r2.status_code == 200
    body = r2.json()
    # a positive budget, never a paid dollar figure
    assert body["budget_total_usd"] >= 0.0
    est = body.get("cost_estimate")
    if est is not None:
        assert est["total_paid_usd"] == 0.0


def test_capabilities_zero_paid_boundary(client):
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert "local" in body and "paid" in body and "summary" in body
    assert isinstance(body["local"], list)
    assert isinstance(body["paid"], list)
    # every paid capability is shown as 未接入/需授权 (never run)
    for c in body["paid"]:
        assert c["status_label"] == "未接入/需授权"


def test_propose(client):
    r = client.post("/api/chat/propose", json={"requirement": "make a cinematic trailer"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_offline_substitute"] is True
    assert body["cost_estimate"]["total_paid_usd"] == 0.0
    assert any(it["kind"] == "sensitive" for it in body["human_approval_items"])


def test_delete(client):
    r = client.post("/api/projects", json={"requirement": "clip factory test"})
    pid = r.json()["project_id"]
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    # after delete, the detail 404s (on-disk board must not keep it alive)
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_index_and_ui_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "/ui/index.js" in r.text
    r2 = client.get("/ui/index.js")
    assert r2.status_code == 200
    assert "function" in r2.text or "const" in r2.text
