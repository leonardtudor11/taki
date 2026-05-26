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
  if (claim.confidence != null) {
    card.appendChild(el(
      "span", { class: "conf" }, `${Math.round(claim.confidence * 100)}%`
    ));
  }
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
  const panel = el("div", { class: `panel ${dept.cls}` });
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

function renderSynergies(synergies) {
  if (!synergies || !synergies.length) return null;
  const wrap = el("div");
  wrap.appendChild(el("div", { class: "section-title" }, "Cross-department synergy"));
  const grid = el("div", { class: "synergy-grid" });
  synergies.forEach((s) => {
    const card = el("div", { class: "synergy" });
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
    const ex = el("div", { class: "exec" });
    ex.appendChild(el("h2", null, "Executive summary"));
    ex.appendChild(el("div", null, String(brief.executive_summary)));
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
