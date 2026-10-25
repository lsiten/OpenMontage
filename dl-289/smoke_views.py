import os, sys, tempfile
_T = tempfile.mkdtemp(prefix="pmqa2_")
os.environ["OPENMONTAGE_PM_DB"] = os.path.join(_T, "pm.sqlite")
os.environ["OPENMONTAGE_PROJECTS_DIR"] = os.path.join(_T, "projects")
sys.path.insert(0, os.getcwd())
from fastapi.testclient import TestClient
from pm import server
c = TestClient(server.app)
# create
r = c.post("/api/project", json={"title":"成本视图验证","pipeline_type":"cinematic","cost_budget_usd":5.0,"cost_mode":"warn"})
assert r.status_code==200, r.text
pid = r.json()["project_id"]
# list
r = c.get("/api/projects"); assert r.status_code==200 and any(p["project_id"]==pid for p in r.json()), "list fail"
print("list view OK, count=", len(r.json()))
# detail/get
r = c.get(f"/api/project/{pid}"); assert r.status_code==200 and r.json()["project_id"]==pid
print("get view OK")
# status
r = c.post(f"/api/project/{pid}/status", json={"status":"planning","updated_by":"qa"}); assert r.status_code==200 and r.json()["status"]=="planning"
print("status view OK ->", r.json()["status"])
# cost
r = c.get(f"/api/project/{pid}/cost"); assert r.status_code==200, r.text
cc = r.json(); assert cc.get("cost_budget_usd")==5.0 and cc.get("currency")=="usd", cc
print("cost view OK ->", {k:cc[k] for k in ("cost_budget_usd","cost_reserved_usd","cost_spent_usd","cost_mode","currency")})
# detail full
r = c.get(f"/api/project/{pid}/detail"); assert r.status_code==200 and "board" in r.json()
print("detail view OK, keys=", list(r.json().keys()))
print("ALL VIEWS OK")
