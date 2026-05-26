// Taki dashboard — reads a CascadeBrief JSON and renders the departments,
// synergies, guardrail report, and (S4.2) the cascade-flow handoffs.

const DEPTS = [
  {
    key: "account_brief", cls: "gtm", title: "Revenue / GTM",
    groups: [
      ["buying_signals", "Buying signals"],
      ["competitor_moves", "Competitor moves"],
      ["hiring_signals", "Hiring signals"],
    ],
  },
  {
    key: "market_signal", cls: "finance", title: "Finance / Market",
    groups: [
      ["pricing_trend", "Pricing trend"],
      ["expansion_contraction", "Expansion / contraction"],
      ["web_traffic_proxy", "Web-traffic proxy"],
      ["vendor_health_flags", "Vendor-health flags"],
    ],
  },
  {
    key: "risk_profile", cls: "security", title: "Security / Compliance",
    groups: [
      ["exposure_indicators", "Exposure indicators"],
      ["reputational_signals", "Reputational signals"],
      ["regulatory_signals", "Regulatory signals"],
      ["third_party_risk", "Third-party risk"],
    ],
  },
];

function el(tag, attrs = {}, html = "") {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  if (html) e.innerHTML = html;
  return e;
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function renderClaim(claim) {
  const conf = claim.confidence != null
    ? `<span class="conf">${Math.round(claim.confidence * 100)}%</span>` : "";
  const cites = (claim.citations || [])
    .map((c) => `<a class="cite" href="${esc(c.url)}" target="_blank" rel="noopener">§ ${esc(c.source_type || "src")}</a>`)
    .join("");
  return `<div class="claim">${conf}${esc(claim.text)}<div class="cites">${cites}</div></div>`;
}

function renderPanel(dept, brief) {
  const data = brief[dept.key] || {};
  const panel = el("div", { class: `panel ${dept.cls}` });
  panel.appendChild(el("h3", {}, dept.title));
  let any = false;
  dept.groups.forEach(([field, label]) => {
    const claims = data[field] || [];
    if (!claims.length) return;
    any = true;
    const g = el("div", { class: "group" });
    g.appendChild(el("h4", {}, label));
    claims.forEach((c) => (g.innerHTML += renderClaim(c)));
    panel.appendChild(g);
  });
  if (!any) panel.appendChild(el("div", { class: "empty" }, "No grounded signals."));
  return panel;
}

function renderBadges(report) {
  const wrap = el("div", { class: "badges" });
  const grounded = (report.ungrounded_dropped || []).length;
  wrap.appendChild(el("span", { class: "badge ok" }, `🔒 PII redacted: <b>${report.pii_redactions || 0}</b>`));
  wrap.appendChild(el("span", { class: "badge ok" }, `🚫 Sources withheld: <b>${(report.leak_flags || []).length}</b>`));
  wrap.appendChild(el("span", { class: "badge ok" }, `🎯 Ungrounded dropped: <b>${grounded}</b>`));
  wrap.appendChild(el("span", { class: "badge ok" }, `✅ Grounded: <b>${report.passed ? "yes" : "no"}</b>`));
  return wrap;
}

function renderSynergies(synergies) {
  if (!synergies || !synergies.length) return null;
  const wrap = el("div");
  wrap.appendChild(el("div", { class: "section-title" }, "Cross-department synergy"));
  const grid = el("div", { class: "synergy-grid" });
  synergies.forEach((s) => {
    const card = el("div", { class: "synergy" });
    card.appendChild(el("div", { class: "depts" }, (s.contributing_depts || []).join(" + ")));
    card.appendChild(el("div", {}, esc(s.text)));
    grid.appendChild(card);
  });
  wrap.appendChild(grid);
  return wrap;
}

function render(brief) {
  document.getElementById("target").textContent = brief.target || "";
  document.getElementById("ts").textContent = brief.generated_at
    ? `generated ${new Date(brief.generated_at).toLocaleString()}` : "";

  const app = document.getElementById("app");
  app.innerHTML = "";

  if (brief.executive_summary) {
    const ex = el("div", { class: "exec" });
    ex.appendChild(el("h2", {}, "Executive summary"));
    ex.appendChild(el("div", {}, esc(brief.executive_summary)));
    app.appendChild(ex);
  }

  app.appendChild(renderBadges(brief.guardrail_report || {}));

  if (typeof renderCascadeFlow === "function") {
    const flow = renderCascadeFlow(brief.handoffs || []);
    if (flow) app.appendChild(flow);
  }

  const syn = renderSynergies(brief.synergy_signals);
  if (syn) app.appendChild(syn);

  app.appendChild(el("div", { class: "section-title" }, "Departments"));
  const cols = el("div", { class: "cols" });
  DEPTS.forEach((d) => cols.appendChild(renderPanel(d, brief)));
  app.appendChild(cols);
}

fetch("brief.json")
  .then((r) => { if (!r.ok) throw new Error(`brief.json ${r.status}`); return r.json(); })
  .then(render)
  .catch((e) => {
    const err = document.getElementById("error");
    err.textContent = "Could not load brief.json: " + e.message;
    err.classList.remove("hidden");
  });
