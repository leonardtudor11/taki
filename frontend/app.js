// Taki dashboard — reads a CascadeBrief JSON and renders the departments,
// synergies, guardrail report, and (S4.2) the cascade-flow handoffs.
//
// Rendering uses the DOM API + textContent (never innerHTML on user data) so
// brief.json content cannot inject script. Citation URLs are scheme-validated.

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

function el(tag, attrs, text) {
  const e = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}

// only http(s) URLs may render as live links; everything else becomes "#".
function safeUrl(url) {
  try {
    const u = new URL(String(url || ""), window.location.href);
    return (u.protocol === "http:" || u.protocol === "https:") ? u.href : "#";
  } catch (_e) {
    return "#";
  }
}

function renderClaim(claim) {
  const card = el("div", { class: "claim" });
  // V4 confidence bar — thin hairline at the top of the card, dept-coloured.
  // Reads better than the floating "85%" text and shows uncertainty at a glance.
  const conf = (claim.confidence != null)
    ? Math.max(0, Math.min(1, Number(claim.confidence)))
    : 0.5;
  const pct = Math.round(conf * 100);
  const bar = el("div", { class: "claim-bar", title: `confidence ${pct}%`, "aria-label": `confidence ${pct} percent` });
  const fill = el("div", { class: "claim-bar-fill" });
  fill.style.width = `${pct}%`;
  bar.appendChild(fill);
  card.appendChild(bar);

  card.appendChild(document.createTextNode(String(claim.text || "")));
  const cites = el("div", { class: "cites" });
  (claim.citations || []).forEach((c) => {
    const a = el(
      "a",
      { class: "cite", href: safeUrl(c.url), target: "_blank", rel: "noopener noreferrer" },
      `§ ${String(c.source_type || "src")}`
    );
    cites.appendChild(a);
  });
  card.appendChild(cites);
  return card;
}

function renderPanel(dept, brief) {
  const data = brief[dept.key] || {};
  const panel = el("div", {
    class: `panel ${dept.cls}`,
    role: "region",
    "aria-label": `${dept.title} department`,
  });
  panel.appendChild(el("h3", null, dept.title));
  let any = false;
  dept.groups.forEach(([field, label]) => {
    const claims = data[field] || [];
    if (!claims.length) return;
    any = true;
    const g = el("div", { class: "group" });
    g.appendChild(el("h4", null, label));
    claims.forEach((c) => g.appendChild(renderClaim(c)));
    panel.appendChild(g);
  });
  if (!any) panel.appendChild(el("div", { class: "empty" }, "No grounded signals."));
  return panel;
}

// V4 — expandable drawer listing the claims the grounding guard dropped before
// they reached the brief. The hackathon judge will click this; it's the visual
// proof that hallucinations are caught, not just claimed-caught.
function renderDropped(report) {
  const dropped = (report.ungrounded_dropped || []);
  if (!dropped.length) return null;
  const details = el("details", { class: "dropped" });
  const summary = el("summary", { class: "dropped-summary" });
  summary.textContent =
    `Hallucinations caught — ${dropped.length} ungrounded claim${dropped.length === 1 ? "" : "s"} dropped before the brief`;
  details.appendChild(summary);
  const list = el("ol", { class: "dropped-list" });
  dropped.forEach((text) => {
    list.appendChild(el("li", null, String(text)));
  });
  details.appendChild(list);
  return details;
}

function renderBadges(report) {
  const wrap = el("div", { class: "badges" });
  const grounded = (report.ungrounded_dropped || []).length;
  const passedCls = report.passed ? "badge ok" : "badge";
  wrap.appendChild(el("span", { class: "badge ok" }, ""));
  wrap.lastChild.appendChild(document.createTextNode("🔒 PII redacted: "));
  wrap.lastChild.appendChild(el("b", null, String(report.pii_redactions || 0)));

  wrap.appendChild(el("span", { class: "badge ok" }, ""));
  wrap.lastChild.appendChild(document.createTextNode("🚫 Sources withheld: "));
  wrap.lastChild.appendChild(el("b", null, String((report.leak_flags || []).length)));

  wrap.appendChild(el("span", { class: "badge ok" }, ""));
  wrap.lastChild.appendChild(document.createTextNode("🎯 Ungrounded dropped: "));
  wrap.lastChild.appendChild(el("b", null, String(grounded)));

  wrap.appendChild(el("span", { class: passedCls }, ""));
  wrap.lastChild.appendChild(document.createTextNode("✅ Grounded: "));
  wrap.lastChild.appendChild(el("b", null, report.passed ? "yes" : "no"));
  return wrap;
}

// known dept keys used by the focus-filter CSS in index.html
const _DEPT_KEYS = ["gtm", "finance", "security"];

function _deptKeyFor(name) {
  const n = String(name || "").toLowerCase();
  if (n.includes("gtm") || n.includes("revenue")) return "gtm";
  if (n.includes("finance") || n.includes("market")) return "finance";
  if (n.includes("security") || n.includes("compliance") || n.includes("risk")) return "security";
  return null;
}

function renderSynergies(synergies) {
  if (!synergies || !synergies.length) return null;
  const wrap = el("div");
  wrap.appendChild(el("div", { class: "section-title" }, "Cross-department synergy"));
  const grid = el("div", { class: "synergy-grid" });
  synergies.forEach((s) => {
    // tag each synergy with `has-<dept>` per contributing department so the
    // focus-filter CSS can keep relevant synergies bright when a dept is selected.
    const depts = (s.contributing_depts || [])
      .map(_deptKeyFor)
      .filter((d) => _DEPT_KEYS.includes(d));
    const classes = ["synergy", ...depts.map((d) => `has-${d}`)];
    const card = el("div", { class: classes.join(" ") });
    card.appendChild(el("div", { class: "depts" }, (s.contributing_depts || []).join(" + ")));
    card.appendChild(el("div", null, String(s.text || "")));
    grid.appendChild(card);
  });
  wrap.appendChild(grid);
  return wrap;
}

function parseDateSafe(s) {
  if (typeof s !== "string" || s.length > 64) return null;
  const d = new Date(s);
  return isNaN(d.getTime()) ? null : d;
}

function render(brief) {
  document.getElementById("target").textContent = String(brief.target || "");
  const d = parseDateSafe(brief.generated_at);
  document.getElementById("ts").textContent = d ? `generated ${d.toLocaleString()}` : "";

  const app = document.getElementById("app");
  app.textContent = "";

  if (brief.executive_summary) {
    const ex = el("div", { class: "exec", role: "region", "aria-label": "Executive summary" });
    ex.appendChild(el("h2", null, "Executive summary"));
    ex.appendChild(el("div", null, String(brief.executive_summary)));
    app.appendChild(ex);
  }

  app.appendChild(renderBadges(brief.guardrail_report || {}));

  const dropped = renderDropped(brief.guardrail_report || {});
  if (dropped) app.appendChild(dropped);

  if (typeof renderCascadeFlow === "function") {
    // pass the whole brief — V3 cytoscape graph reads handoffs + synergies + depts.
    const flow = renderCascadeFlow(brief);
    if (flow) app.appendChild(flow);
  }

  const syn = renderSynergies(brief.synergy_signals);
  if (syn) app.appendChild(syn);

  app.appendChild(el("div", { class: "section-title" }, "Departments"));
  const cols = el("div", { class: "cols" });
  DEPTS.forEach((d) => cols.appendChild(renderPanel(d, brief)));
  app.appendChild(cols);
}

// Wire the header pull-fresh button to fire the live-demo cascade via the
// backend, sharing the cytoscape graph that cascade-flow.js already manages.
// If the backend isn't reachable, the click will surface the error in the
// cascade tooltip strip; the page still works offline (replay button suffices).
function _wireHeaderPullFresh() {
  const btn = document.getElementById("pullfresh");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const container = document.getElementById("cascade-graph");
    if (!container || !container._cy) return;
    if (typeof runLiveCascade !== "function") return;
    const tip = container.parentElement.querySelector(".cascade-tip");
    runLiveCascade(
      { mode: "demo" },
      {
        cy: container._cy, tip,
        buttons: { primary: btn },
        labelWhenRunning: "⏳ live demo running…",
      },
    );
  });
  btn.dataset.idleLabel = btn.textContent;
}

fetch("brief.json")
  .then((r) => { if (!r.ok) throw new Error(`brief.json ${r.status}`); return r.json(); })
  .then((b) => {
    render(b);
    _wireHeaderPullFresh();
  })
  .catch((e) => {
    const err = document.getElementById("error");
    err.textContent = "Could not load brief.json: " + e.message;
    err.classList.remove("hidden");
  });
