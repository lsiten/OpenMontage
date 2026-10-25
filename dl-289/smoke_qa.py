import os, sys, tempfile, json
# Isolate DB + projects dir BEFORE importing pm
_TMP = tempfile.mkdtemp(prefix="pmqa_")
os.environ["OPENMONTAGE_PM_DB"] = os.path.join(_TMP, "pm.sqlite")
os.environ["OPENMONTAGE_PROJECTS_DIR"] = os.path.join(_TMP, "projects")
sys.path.insert(0, os.getcwd())

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS" if cond else "FAIL"), "|", name, ("| "+detail) if detail else "")

from fastapi.testclient import TestClient
from pm import server, store, chat, capabilities
c = TestClient(server.app)

# 1. /api/health
r = c.get("/api/health")
check("1 /api/health ==200 {ok,app:pm}", r.status_code==200 and r.json()=={"ok":True,"app":"pm"}, f"body={r.text[:120]}")

# 2. /api/chat plan -> {pipeline_type, concept, cost_estimate(local/paid), approval_items}
r = c.post("/api/chat", json={"requirement":"录一个软件操作演示"})
check("2 /api/chat ==200", r.status_code==200, f"body={r.text[:120]}")
b = r.json()
check("2a plan.pipeline_type set", bool(b.get("pipeline_type")), f"pipeline_type={b.get('pipeline_type')}")
check("2b plan.concept present + is_ai_generated False", b.get("concept") is not None and b["concept"].get("is_ai_generated")==False, f"concept={json.dumps(b.get('concept'),ensure_ascii=False)[:160]}")
check("2c plan.cost_estimate local/paid present", "local" in b.get("cost_estimate",{}) and "paid" in b.get("cost_estimate",{}))
check("2d plan.total_estimated_usd==0.0 (zero-paid)", b.get("cost_estimate",{}).get("total_estimated_usd")==0.0, f"total={b.get('cost_estimate',{}).get('total_estimated_usd')}")
check("2e plan.approval_items is list", isinstance(b.get("approval_items"), list), f"n={len(b.get('approval_items',[]))}")

# 3. /api/chat/trigger -> create project; notes contains '未调用付费 provider'
r = c.post("/api/chat/trigger", json={"requirement":"录一个软件操作演示","pipeline_type":b["pipeline_type"],"cost_budget_usd":b["cost_estimate"]["budget_default_usd"]})
check("3 /api/chat/trigger ==200", r.status_code==200, f"body={r.text[:160]}")
pid = r.json().get("project_id")
check("3a trigger created project_id", bool(pid), f"pid={pid}")
# verify notes in DB (author smoke checked notes='未调用付费 provider')
p = store.get_project(pid)
check("3b trigger notes contains '未调用付费 provider'", p is not None and "未调用付费 provider" in (p.notes or ""), f"notes={p.notes if p else None}")
check("3c trigger status draft + requires_approval True", p is not None and p.status=="draft" and p.requires_approval is True, f"status={p.status if p else None} req={p.requires_approval if p else None}")
# marker written to projects dir
marker = os.path.join(_TMP,"projects",pid,"project.json")
check("3d runtime projects/<id>/project.json marker written", os.path.isfile(marker), f"exists={os.path.isfile(marker)}")

# 4. /api/capabilities -> 117 items, local 62 / paid 55
r = c.get("/api/capabilities")
check("4 /api/capabilities ==200", r.status_code==200)
cap = r.json()
check("4a total==117", cap.get("total")==117, f"total={cap.get('total')}")
check("4b local==62", len(cap.get("local",[]))==62, f"local={len(cap.get('local',[]))}")
check("4c paid==55", len(cap.get("paid",[]))==55, f"paid={len(cap.get('paid',[]))}")
check("4d note mentions 未接入/需授权", "未接入" in cap.get("note","") or "需授权" in cap.get("note",""), f"note={cap.get('note')}")
# paid rows all unconnected/需授权 (no default call)
paid_notes = [x.get("note","") for x in cap.get("paid",[])]
check("4e paid rows all labeled unconnected/需授权 or configured-not-called", all(("未接入" in n or "需授权" in n or "不默认调用" in n) for n in paid_notes if n) and all(x.get("status") in ("unavailable","available") for x in cap.get("paid",[])), f"sample={[ (x.get('status'),x.get('note')) for x in cap.get('paid',[])[:3] ]}")

# 5. CRUD persistence: create -> reset (reconnect) -> get/list still there
store.reset()  # force reconnect to same OPENMONTAGE_PM_DB file
p2 = store.get_project(pid)
check("5 CRUD persists across connection reset", p2 is not None and p2.project_id==pid, f"reloaded={p2.project_id if p2 else None}")
# update status persisted
store.set_status(pid, "planning")
p3 = store.get_project(pid)
check("5a set_status persisted (planning)", p3 is not None and p3.status=="planning", f"status={p3.status if p3 else None}")
# update_project fix #2: approved flag
store.update_project(pid, type("U",(),{}) if False else __import__("pm.schemas",fromlist=["ProjectUpdate"]).ProjectUpdate(approved=True, updated_by="qa"))
p4 = store.get_project(pid)
check("5b update_project sets approved (fix#2 alignment)", p4 is not None and p4.approved is True, f"approved={p4.approved if p4 else None}")
# list
lst = store.list_projects()
check("5c list_projects contains pid", any(x.project_id==pid for x in lst), f"count={len(lst)}")

# 6. detail endpoint combines pm + board + approvals + artifacts
r = c.get(f"/api/project/{pid}/detail")
check("6 /api/project/{id}/detail ==200 with pm+board+approvals+artifacts", r.status_code==200 and all(k in r.json() for k in ("pm","board","approvals","artifacts")), f"keys={list(r.json().keys()) if r.status_code==200 else r.text[:120]}")

# 7. RLock no-deadlock: concurrent creates from a thread pool
import threading, concurrent.futures as cf
def mk(_): 
    from pm.schemas import ProjectCreate
    return store.create_project(ProjectCreate(title=f"t{random.randint(1,99999)}", pipeline_type="animated-explainer"))
import random
ok=0; err=0
with cf.ThreadPoolExecutor(max_workers=8) as ex:
    futs=[ex.submit(mk,None) for _ in range(24)]
    for f in futs:
        try:
            if f.result().project_id: ok+=1
        except Exception as e:
            err+=1; print("  create err:", e)
check("7 concurrent create (RLock, no deadlock) all ok", err==0 and ok==24, f"ok={ok} err={err}")

print("\n===== SUMMARY =====")
passed = sum(1 for _,ok,_ in results if ok)
print(f"{passed}/{len(results)} checks passed")
for name,ok,detail in results:
    if not ok: print("  FAIL:", name, "|", detail)
sys.exit(0 if passed==len(results) else 1)
