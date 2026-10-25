/* PM board — vanilla JS, no framework. Talks to the pm/ FastAPI app.
 * Zero paid / local / no paid AI: nothing here calls a paid provider. */
"use strict";

const KNOWN_PIPELINES = [
  "animated-explainer", "animation", "avatar-spokesperson", "character-animation",
  "cinematic", "clip-factory", "documentary-montage", "framework-smoke", "hybrid",
  "localization-dub", "podcast-repurpose", "screen-demo", "talking-head",
];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let current = null;   // current project id
let tab = "overview"; // current detail tab

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

function setNotice(msg, kind) {
  const n = $("notice");
  n.textContent = msg || "";
  n.className = "notice" + (kind ? " " + kind : "");
}

/* ---- projects list ---- */
async function loadProjects() {
  try {
    const list = await api("/api/projects");
    const cards = $("cards");
    cards.innerHTML = "";
    $("empty").hidden = list.length > 0;
    $("count").textContent = `${list.length} 个`;
    $("listCount").textContent = `${list.length}`;
    for (const p of list) {
      const pid = p.project_id;
      const st = p.pm_status || "draft";
      const el = document.createElement("div");
      el.className = "card";
      el.innerHTML =
        `<div class="t">${esc(p.title || p.requirement || pid)}</div>` +
        `<div class="meta"><span class="st ${esc(st)}">${esc(st)}</span>` +
        `${esc(p.pipeline_type || p.pm && p.pm.pipeline_type || "unknown")}` +
        (p.pm_source ? ` · ${esc(p.pm_source)}` : "") + `</div>`;
      el.addEventListener("click", () => selectProject(pid));
      cards.appendChild(el);
    }
  } catch (e) {
    setNotice("加载项目失败: " + e.message, "err");
  }
}

function selectProject(pid) {
  current = pid;
  $("detailId").textContent = pid;
  loadDetail();
}

/* ---- detail ---- */
async function loadDetail() {
  if (!current) return;
  try {
    if (tab === "cost") {
      const c = await api(`/api/projects/${encodeURIComponent(current)}/cost`);
      renderCost(c);
    } else if (tab === "approvals") {
      const v = await api(`/api/projects/${encodeURIComponent(current)}`);
      renderApprovals(v);
    } else {
      const v = await api(`/api/projects/${encodeURIComponent(current)}`);
      renderOverview(v);
    }
  } catch (e) {
    $("detail").innerHTML = `<p class="muted">加载失败: ${esc(e.message)}</p>`;
  }
}

function renderOverview(v) {
  const d = $("detail");
  const pm = v.pm || {};
  d.innerHTML =
    `<div class="kv">` +
    `<div class="k">标题</div><div class="v">${esc(pm.title || v.title || "—")}</div>` +
    `<div class="k">需求</div><div class="v">${esc(pm.requirement || "—")}</div>` +
    `<div class="k">管线</div><div class="v">${esc(pm.pipeline_type || "—")}</div>` +
    `<div class="k">状态</div><div class="v">${esc(pm.status || "—")} · 来源 ${esc(pm.source || "—")}</div>` +
    `<div class="k">预算</div><div class="v">${esc(pm.cost_budget_usd ?? "—")} USD</div>` +
    `</div>` +
    (pm.concept ? `<div class="banner">${esc(pm.concept)}</div>` : "") +
    (pm.cost_estimate ? renderCostSummary(pm.cost_estimate) : "") +
    `<p class="muted">离线替身/离线概念：不代表真实 AI 服务已接入，生成质量未验收。</p>`;
}

function renderCost(c) {
  const d = $("detail");
  d.innerHTML =
    `<div class="kv">` +
    `<div class="k">预算</div><div class="v">${esc(c.budget_total_usd)} USD（模式 ${esc(c.mode)}）</div>` +
    `<div class="k">已占用</div><div class="v">${esc(c.reserved_usd)} USD</div>` +
    `<div class="k">已花费</div><div class="v">${esc(c.spent_usd)} USD</div>` +
    `<div class="k">剩余</div><div class="v">${esc(c.remaining_usd)} USD</div>` +
    `</div>` +
    (c.cost_estimate ? renderCostSummary(c.cost_estimate) : "");
}

function renderCostSummary(ce) {
  const local = (ce.local_capabilities || []).length;
  const paid = (ce.paid_capabilities || []).length;
  return (
    `<div class="cost">` +
    `<div class="kv">` +
    `<div class="k">本地能力</div><div class="v local">${local} 项</div>` +
    `<div class="k">付费能力</div><div class="v paid">${paid} 项（未接入/需授权，未调用）</div>` +
    `<div class="k">本地金额</div><div class="v">${esc(ce.total_local_usd)} USD</div>` +
    `<div class="k">付费金额</div><div class="v paid">${esc(ce.total_paid_usd)} USD（仅分类，从不调用）</div>` +
    `</div>` +
    `<p class="muted">${esc((ce.notes || []).join(" "))}</p>` +
    `</div>`
  );
}

function renderApprovals(v) {
  const d = $("detail");
  const approvals = v.approvals || [];
  const rows = approvals.map((a) =>
    `<div class="kv" style="margin-bottom:8px">` +
    `<div class="k">${esc(a.kind)}</div><div class="v">${esc(a.status)}</div>` +
    `<div class="k">说明</div><div class="v">${esc(a.note || "—")}</div>` +
    `</div>`
  ).join("");
  d.innerHTML = rows || `<p class="muted">暂无待审批项。</p>`;
  d.insertAdjacentHTML("afterbegin",
    `<p class="muted">付费能力需 proposal 审批 + cost_tracker.reserve + 用户确认后方可调用；敏感/真人声音/肖像/音乐不接入。</p>`);
}

/* ---- chat ---- */
function renderProposal(p) {
  const box = $("proposal");
  const ce = p.cost_estimate || {};
  box.hidden = false;
  box.innerHTML =
    `<h3>管线选择</h3>` +
    `<div class="kv">` +
    `<div class="k">管线</div><div class="v">${esc(p.pipeline_type)}</div>` +
    `<div class="k">置信度</div><div class="v">${esc(p.selection && p.selection.confidence)} · ${esc(p.selection && p.selection.reason)}</div>` +
    `<div class="k">备选</div><div class="v">${esc((p.selection && p.selection.alternatives || []).join(" / ") || "—")}</div>` +
    `</div>` +
    `<div class="banner">${esc(p.concept)}</div>` +
    renderCostSummary(ce) +
    `<h3 style="margin-top:10px">需人类审批</h3>` +
    (p.human_approval_items || []).map((i) =>
      `<div class="kv" style="margin-bottom:6px"><div class="k">${esc(i.kind)}</div>` +
      `<div class="v">${esc(i.label)} — ${esc(i.reason)}</div></div>`
    ).join("") +
    `<p class="muted">${esc(p.note)}</p>`;
}

async function doPropose() {
  const requirement = $("requirement").value.trim();
  if (!requirement) { setNotice("请先输入需求。", "err"); return; }
  setNotice("正在生成提案…");
  try {
    const p = await api("/api/chat/propose", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ requirement, pipeline_type: $("pipeline").value.trim() }),
    });
    renderProposal(p);
    setNotice("提案已生成（离线替身，未调用任何付费/真实 AI）。", "ok");
  } catch (e) {
    setNotice("生成失败: " + e.message, "err");
  }
}

async function doCreate() {
  const requirement = $("requirement").value.trim();
  if (!requirement) { setNotice("请先输入需求。", "err"); return; }
  setNotice("正在创建项目…");
  try {
    const project = await api("/api/projects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ requirement, pipeline_type: $("pipeline").value.trim() }),
    });
    setNotice(`已创建 ${project.project_id}（status=${project.status}，离线替身）。`, "ok");
    await loadProjects();
    selectProject(project.project_id);
  } catch (e) {
    setNotice("创建失败: " + e.message, "err");
  }
}

/* ---- capabilities ---- */
async function loadCapabilities() {
  try {
    const rep = await api("/api/capabilities");
    const s = rep.summary || {};
    $("capSummary").textContent =
      `本地 ${s.local || 0} · 付费 ${s.paid || 0}（未接入 ${s.unconfigured_paid || 0}）`;
    const grid = $("capGrid");
    grid.innerHTML = "";
    const all = [...(rep.paid || []), ...(rep.local || [])];
    for (const c of all.slice(0, 24)) {
      const el = document.createElement("div");
      el.className = "capcell";
      const kind = c.is_local && !c.is_paid ? "local" : "paid";
      el.innerHTML =
        `<div class="cap">${esc(c.capability)}</div>` +
        `<div class="lab">${esc(c.provider || c.tool || "—")} ` +
        `<span class="pill ${kind}">${esc(c.status_label)}</span></div>`;
      grid.appendChild(el);
    }
  } catch (e) {
    // degrade silently like Backlot ("never block, never break")
  }
}

/* ---- wiring ---- */
function init() {
  const dl = $("pipelineList");
  for (const p of KNOWN_PIPELINES) {
    const o = document.createElement("option");
    o.value = p;
    dl.appendChild(o);
  }
  $("proposeBtn").addEventListener("click", doPropose);
  $("createBtn").addEventListener("click", doCreate);
  document.querySelectorAll(".tab").forEach((t) => {
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      tab = t.dataset.tab;
      loadDetail();
    });
  });
  loadProjects();
  loadCapabilities();
  const pid = new URLSearchParams(location.search).get("project");
  if (pid) selectProject(pid);
}
init();
