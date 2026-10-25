/* PM shared JS — vanilla, no framework (mirrors backlot/ui). */
window.PM = (function () {
  async function api(path, opts) {
    const res = await fetch(path, opts);
    const text = await res.text();
    let body = null;
    if (text) { try { body = JSON.parse(text); } catch { body = text; } }
    if (!res.ok) {
      const detail = (body && (body.detail || body.message)) || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }
  function post(path, payload) { return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); }
  function patch(path, payload) { return api(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function pill(cls, text) { return `<span class="pill ${cls}">${esc(text)}</span>`; }
  return { api, post, patch, esc, pill };
})();
