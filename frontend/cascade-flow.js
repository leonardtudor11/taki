// Cascade-flow visual (S4.2) — renders the three departments as nodes and the
// dept->dept handoff messages as labeled wires. app.js calls this if present.
//
// Uses DOM + textContent only (no innerHTML on user data) so handoff messages
// from brief.json cannot inject HTML.

function deptClass(name) {
  const n = String(name || "").toLowerCase();
  if (n.includes("gtm") || n.includes("revenue")) return "gtm";
  if (n.includes("finance") || n.includes("market")) return "finance";
  if (n.includes("security") || n.includes("compliance")) return "security";
  return "";
}

function deptLabel(name) {
  return { gtm: "GTM", finance: "Finance", security: "Security" }[deptClass(name)]
    || String(name || "");
}

function flowEl(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function renderCascadeFlow(handoffs) {
  const wrap = flowEl("div", "flow");
  wrap.appendChild(flowEl("div", "section-title", "Cascade flow — how the departments talked"));

  const nodes = flowEl("div", "flow-nodes");
  [["gtm", "Revenue / GTM"], ["finance", "Finance / Market"], ["security", "Security / Compliance"]]
    .forEach(([cls, label]) => nodes.appendChild(flowEl("div", `node ${cls}`, label)));
  wrap.appendChild(nodes);

  if (!handoffs || !handoffs.length) {
    wrap.appendChild(flowEl("div", "empty", "No cross-department handoffs this run."));
    return wrap;
  }

  handoffs.forEach((h) => {
    const row = flowEl("div", "handoff");
    row.appendChild(flowEl("span", `hchip ${deptClass(h.from_dept)}`, deptLabel(h.from_dept)));
    row.appendChild(flowEl("span", "harrow", "→"));
    row.appendChild(flowEl("span", `hchip ${deptClass(h.to_dept)}`, deptLabel(h.to_dept)));
    row.appendChild(flowEl("span", "hmsg", String(h.message || "")));
    wrap.appendChild(row);
  });
  return wrap;
}
