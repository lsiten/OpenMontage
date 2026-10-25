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
  const res = await fetch(path, { ...opts, signal: AbortSignal.timeout(20000) });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(`${res.status}: ${typeof error.detail === 'string' ? error.detail : '请求参数或状态无效'}`);
  }
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
      const el = document.createElement("button");
      el.type = 'button';
      el.setAttribute('aria-pressed', String(pid === current));
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
  history.replaceState(null, '', `?project=${encodeURIComponent(pid)}`);
  $("detailId").textContent = pid;
  loadDetail();
  loadManagement();
  loadProduction();
}

async function loadManagement() {
  try {
    const pid = current;
    const v = await api(`/api/projects/${encodeURIComponent(pid)}`);
    if (current !== pid) return;
    $('manage').hidden = false;
    $('productionPanel').hidden = false;
    $('editTitle').value = v.pm.title;
    $('editStatus').value = v.pm.status;
    $('editBudget').value = v.pm.cost_budget_usd;
    $('manageNotice').textContent = '';
  } catch (e) {
    if (!(e instanceof Error)) throw e;
    $('manage').hidden = true;
    $('productionPanel').hidden = true;
    setNotice(e.message, 'err');
  }
}

async function saveManagement(event) {
  event.preventDefault();
  $('saveBtn').disabled = true;
  try {
    await api(`/api/projects/${encodeURIComponent(current)}`, {
      method: 'PUT', headers: {'content-type':'application/json'},
      body: JSON.stringify({title: $('editTitle').value, status: $('editStatus').value,
        cost_budget_usd: Number($('editBudget').value)}),
    });
    $('manageNotice').textContent = '修改已保存到本地数据库。';
    await Promise.all([loadProjects(), loadDetail()]);
  } catch (e) {
    if (!(e instanceof Error)) throw e;
    $('manageNotice').textContent = `保存失败：${e.message}`;
  } finally { $('saveBtn').disabled = false; }
}

async function loadTrash() {
  const list = await api('/api/trash');
  $('trash').replaceChildren();
  for (const p of list) {
    const item = document.createElement('div');
    item.className = 'trash-item';
    const text = document.createElement('span');
    text.textContent = p.title || p.project_id;
    const restore = document.createElement('button');
    restore.textContent = '恢复';
    restore.addEventListener('click', async () => {
      restore.disabled = true;
      try {
        await api(`/api/projects/${encodeURIComponent(p.project_id)}/restore`, {method:'POST'});
        await Promise.all([loadProjects(), loadTrash()]);
        selectProject(p.project_id);
      } catch (e) {
        if (!(e instanceof Error)) throw e;
        setNotice(`恢复失败：${e.message}`, 'err');
        restore.disabled = false;
      }
    });
    item.append(text, restore);
    $('trash').append(item);
  }
  if (!list.length) $('trash').textContent = '回收站为空。';
}

async function deleteCurrent() {
  try {
    await api(`/api/projects/${encodeURIComponent(current)}`, {method:'DELETE'});
    current = null;
    history.replaceState(null, '', '/');
    $('manage').hidden = true;
    $('productionPanel').hidden = true;
    $('playback').pause();
    $('detail').textContent = '项目已移至回收站，可从项目列表下方恢复。';
    $('detailId').textContent = '';
    await Promise.all([loadProjects(), loadTrash()]);
  } catch (e) {
    if (!(e instanceof Error)) throw e;
    setNotice(`回收失败：${e.message}`, 'err');
  }
}

async function loadProduction() {
  if (!current) return;
  const pid = current;
  try {
    const [p, board] = await Promise.all([
      api(`/api/projects/${encodeURIComponent(pid)}/production`),
      api(`/api/projects/${encodeURIComponent(pid)}`),
    ]);
    if (current !== pid) return;
    const labels = {not_requested:'尚未提交', awaiting_agent:'等待 agent 接手（执行通道未接入）',
      in_progress:'实际制作中', completed:'已渲染（待独立质检）', failed:'制作失败', awaiting_human:'等待阶段审批'};
    $('productionStatus').textContent = labels[p.status] || p.status;
    $('productionError').textContent = p.error || '';
    $('productionLog').textContent = p.log || '暂无制作日志。';
    $('artifactNames').textContent = `实际产物：${p.artifact_names.join('、') || '无'}`;
    $('stages').innerHTML = (board.stages || []).map(s => `<div class="stage">${esc(s.name || s.stage)} · ${esc(s.status)}</div>`).join('');
    const plan = board.artifacts?.scene_plan;
    const scenes = plan?.scenes || plan?.data?.scenes || [];
    $('scenes').innerHTML = scenes.map(s => `<p>${esc(s.start_seconds)}–${esc(s.end_seconds)}s · ${esc(s.description)}</p>`).join('');
    const video = $('playback');
    video.hidden = !p.media_url;
    $('downloadVideo').hidden = !p.media_url;
    if (p.media_url) {
      if (video.getAttribute('src') !== p.media_url) video.src = p.media_url;
      $('downloadVideo').href = p.media_url;
    } else {
      video.pause(); video.removeAttribute('src');
    }
    $('runBtn').disabled = Boolean(p.request);
  } catch (e) {
    if (!(e instanceof Error)) throw e;
    if (current === pid) $('productionError').textContent = `制作记录加载失败：${e.message}`;
  }
}

async function submitProduction() {
  $('runBtn').disabled = true;
  try {
    await api(`/api/projects/${encodeURIComponent(current)}/run`, {
      method:'POST', headers:{'content-type':'application/json'},
      body: JSON.stringify({mode:$('productionMode').value}),
    });
    await loadProduction();
  } catch (e) {
    if (!(e instanceof Error)) throw e;
    $('productionError').textContent = `提交失败：${e.message}`;
    $('runBtn').disabled = false;
  }
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
    `<div class="k">需求</div><div class="v">${esc(pm.requirement || "—")}</div>` +
    `<div class="k">管线</div><div class="v">${esc(pm.pipeline_type || "—")}</div>` +
    `</div>` +
    (pm.concept ? `<details><summary>查看离线提案</summary><div class="banner">${esc(pm.concept)}</div></details>` : "");
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
    if (!(e instanceof Error)) throw e;
    $('capSummary').textContent = `能力菜单读取失败：${e.message}`;
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
  $('manage').addEventListener('submit', saveManagement);
  $('deleteBtn').addEventListener('click', () => $('deleteDialog').showModal());
  $('deleteDialog').addEventListener('close', () => {
    if ($('deleteDialog').returnValue === 'confirm') deleteCurrent();
  });
  $('runBtn').addEventListener('click', submitProduction);
  $('refreshBtn').addEventListener('click', loadProduction);
  setInterval(() => { if (!document.hidden) loadProduction(); }, 2500);
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
  loadTrash().catch(e => setNotice(`回收站加载失败：${e.message}`, 'err'));
  const pid = new URLSearchParams(location.search).get("project");
  if (pid) selectProject(pid);
}
init();
