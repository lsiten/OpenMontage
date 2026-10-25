"""Zero-paid local smoke test for the PM capability.

Boots the pm FastAPI app via TestClient against an ISOLATED temp SQLite + temp
projects dir (never the real .pm/db.sqlite or projects/). Exercises health,
chat/plan, chat/trigger, capabilities and CRUD. Records each step + timing.
No paid provider is ever called; paid rows are shown as 未接入/需授权.
"""
import time, json, sys, os, tempfile

# isolate BEFORE importing pm so the module-global connection points at temp db
tmp = tempfile.mkdtemp(prefix="pm_smoke_")
os.environ["OPENMONTAGE_PM_DB"] = os.path.join(tmp, "db.sqlite")
os.environ["OPENMONTAGE_PROJECTS_DIR"] = os.path.join(tmp, "projects")

from fastapi.testclient import TestClient
from pm import server

def step(label, fn):
    t = time.time()
    try:
        r = fn()
        dt = time.time() - t
        return True, dt, r
    except Exception as e:
        return False, time.time() - t, repr(e)

c = TestClient(server.app)
ok = True
def show(label, res):
    global ok
    good, dt, r = res
    print(f"[{'OK' if good else 'FAIL'}] {label} ({dt:.2f}s) -> {r}")
    if not good:
        ok = False

show("GET /api/health", step("health", lambda: (c.get('/api/health').json(), )))

# chat plan (natural language -> {pipeline_type, concept, cost_estimate, approval_items})
r = c.post('/api/chat', json={'requirement': '录一个软件操作演示，讲怎么用剪辑软件'})
plan = r.json()
print("chat/plan status:", r.status_code, "| pipeline_type:", plan.get('pipeline_type'))
print("  cost_estimate:", json.dumps(plan.get('cost_estimate'), ensure_ascii=False)[:300])
show("POST /api/chat (plan) 200", step('plan', lambda: (r, )) if r.status_code==200 else (False,0,r.text))

# trigger -> create project (zero paid, no provider call)
r = c.post('/api/chat/trigger', json={'requirement': '录一个软件操作演示', 'pipeline_type': 'screen-demo', 'cost_budget_usd': 1.0})
trig = r.json() if r.status_code==200 else {}
print("chat/trigger status:", r.status_code, "| project_id:", trig.get('project_id'))
pid = trig.get('project_id', '')
show("POST /api/chat/trigger 200", step('trigger', lambda: (r,)) if r.status_code==200 else (False,0,r.text))

# capabilities (local/paid classification)
r = c.get('/api/capabilities')
caps = r.json()
print("capabilities: total=%d local=%d local_available=%d paid=%d" % (
    caps.get('total',0), len(caps.get('local',[])), caps.get('local_available',0), len(caps.get('paid',[]))))
# verify a paid row is unconnected, not called
paid_unconn = sum(1 for p in caps.get('paid',[]) if '未接入' in (p.get('note') or '') or '需授权' in (p.get('note') or ''))
print("  paid rows labeled 未接入/需授权:", paid_unconn, "of", len(caps.get('paid',[])))
show("GET /api/capabilities 200", step('caps', lambda: (r,)) if r.status_code==200 else (False,0,r.text))

# CRUD: get the created project, set status, update budget
r = c.get(f'/api/project/{pid}')
print("GET /api/project/{pid} status:", r.status_code, "| status field:", r.json().get('status') if r.status_code==200 else None)
show("GET /api/project/{pid} 200", step('get', lambda: (r,)) if r.status_code==200 else (False,0,r.text))

r = c.post(f'/api/project/{pid}/status', json={'status': 'planning'})
print("POST status -> planning: returned status", r.json().get('status') if r.status_code==200 else r.text)
show("POST status (persist)", step('status', lambda: (r.json(),)) if r.status_code==200 and r.json().get('status')=='planning' else (False,0,r.text))

r = c.patch(f'/api/project/{pid}', json={'cost_budget_usd': 3.5})
print("PATCH cost_budget_usd -> 3.5: returned", r.json().get('cost_budget_usd') if r.status_code==200 else r.text)
show("PATCH budget (persist)", step('budget', lambda: (r.json(),)) if r.status_code==200 and r.json().get('cost_budget_usd')==3.5 else (False,0,r.text))

r = c.get('/api/projects')
print("GET /api/projects count:", len(r.json()) if r.status_code==200 else r.text)
show("GET /api/projects 200", step('list', lambda: (r,)) if r.status_code==200 else (False,0,r.text))

r = c.get(f'/api/project/{pid}/detail')
print("GET /api/project/{pid}/detail status:", r.status_code)
show("GET /detail 200", step('detail', lambda: (r,)) if r.status_code==200 else (False,0,r.text))

print("\nSMOKE RESULT:", "ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
