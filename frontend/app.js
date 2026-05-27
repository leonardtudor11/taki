// Taki dashboard — reads a CascadeBrief JSON and renders the departments,
// synergies, guardrail report, and (S4.2) the cascade-flow handoffs.
//
// Rendering uses the DOM API + textContent (never innerHTML on user data) so
// brief.json content cannot inject script. Citation URLs are scheme-validated.

// V7 — dept registry now includes Marketing. Order intentional: Marketing
// first in self-mode because content-gap claims drive most actionable items;
// in target-mode it still sits before GTM (marketing → sales pipeline reads).
const DEPTS = [
  {
    key: "marketing_signal", cls: "marketing", title: "Marketing",
    groups: [
      ["value_proposition", "Value proposition"],
      ["positioning", "Positioning"],
      ["brand_voice", "Brand voice"],
      ["content_gaps", "Content gaps"],
      ["channel_signals", "Channel signals"],
    ],
  },
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
  // Skip the panel entirely if the dept's payload isn't even present in the
  // brief (e.g. legacy target-mode briefs predating the Marketing dept).
  const data = brief[dept.key];
  if (data == null) return null;
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

// V6 — Strategic plan hero section. Sits at the top of the dashboard above
// the evidence panels: headline (big serif) + narrative + 3-col stat grid
// (ICP fit / deal size / urgency) + numbered prioritized plays + collapsible
// open questions. This is the "answer" the rest of the page supports.

const _OWNER_LABEL = { gtm: "GTM", finance: "Finance", security: "Security" };

// V7.17 — count-up animation when a stat value contains an integer or float.
// Categorical values ("high", "low", "act this quarter") are skipped silently
// — no parse, no flicker, original text stays put.
function _startCounterIfNumeric(valueEl) {
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const txt = valueEl.textContent || "";
  const m = txt.match(/-?\d+(?:\.\d+)?/);
  if (!m) return;
  const finalNum = parseFloat(m[0]);
  if (!isFinite(finalNum)) return;
  const isInt = Number.isInteger(finalNum);
  const prefix = txt.slice(0, m.index);
  const suffix = txt.slice(m.index + m[0].length);
  const dur = 900;
  const t0 = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - t0) / dur);
    const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
    const cur = finalNum * eased;
    const display = isInt ? String(Math.round(cur)) : cur.toFixed(1);
    valueEl.textContent = `${prefix}${display}${suffix}`;
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function _renderPlanStat(label, value, rationale, modifier) {
  const stat = el("div", { class: `plan-stat ${modifier || ""}`.trim() });
  stat.appendChild(el("div", { class: "plan-stat-label" }, label));
  const valueEl = el("div", { class: "plan-stat-value" }, String(value || "—"));
  stat.appendChild(valueEl);
  if (rationale) {
    stat.appendChild(el("div", { class: "plan-stat-rationale" }, String(rationale)));
  }
  // V7.17 — start the count-up only once the stat scrolls into view.
  // (Stats render in the plan hero which is above the fold for most viewports;
  // observer covers narrow viewports + future deeper placement.)
  if (typeof IntersectionObserver !== "undefined") {
    const obs = new IntersectionObserver((entries, o) => {
      entries.forEach((e) => {
        if (e.isIntersecting) {
          _startCounterIfNumeric(valueEl);
          o.unobserve(e.target);
        }
      });
    }, { threshold: 0.4 });
    obs.observe(stat);
  } else {
    // no IO support — fall through, value stays static
  }
  return stat;
}

function _renderPlay(play, idx) {
  const priority = play.priority || 3;
  // V7.18 — collapsible: P1 plays start expanded (highest priority = always
  // visible), P2+ start collapsed so the user can scan headlines then drill.
  const initialExpanded = priority === 1;
  const li = el("li", {
    class: `plan-play plan-play-p${priority}`,
    role: "button",
    tabindex: "0",
    "aria-expanded": initialExpanded ? "true" : "false",
  });

  const head = el("div", { class: "play-head" });
  head.appendChild(el("span", { class: "play-priority" }, `P${priority}`));
  if (play.timeframe) head.appendChild(el("span", { class: "play-timeframe" }, String(play.timeframe)));
  (play.owners || []).forEach((o) => {
    const k = String(o).toLowerCase();
    head.appendChild(el(
      "span",
      { class: `play-owner play-owner-${k}` },
      _OWNER_LABEL[k] || String(o),
    ));
  });
  li.appendChild(head);

  li.appendChild(el("div", { class: "play-text" }, String(play.text || "")));
  if (play.rationale) li.appendChild(el("div", { class: "play-rationale" }, String(play.rationale)));

  const cites = el("div", { class: "cites" });
  (play.citations || []).forEach((c) => {
    cites.appendChild(el(
      "a",
      { class: "cite", href: safeUrl(c.url), target: "_blank", rel: "noopener noreferrer" },
      `§ ${String(c.source_type || "src")}`,
    ));
  });
  if (cites.childNodes.length) li.appendChild(cites);

  // V7.18 — click anywhere on the card toggles expanded state, except when
  // clicking a citation link or its inner span (don't trap the outbound nav).
  li.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const exp = li.getAttribute("aria-expanded") === "true";
    li.setAttribute("aria-expanded", exp ? "false" : "true");
  });
  li.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      li.click();
    }
  });

  return li;
}

function renderStrategicPlan(plan) {
  if (!plan || !plan.headline) return null;

  const wrap = el("section", { class: "plan", role: "region", "aria-label": "Strategic plan" });

  // headline
  wrap.appendChild(el("div", { class: "plan-eyebrow" }, "Strategic plan"));
  wrap.appendChild(el("h2", { class: "plan-headline" }, String(plan.headline)));

  // narrative — split on blank lines into paragraphs
  if (plan.narrative) {
    const narr = el("div", { class: "plan-narrative" });
    String(plan.narrative).split(/\n\s*\n/).forEach((p) => {
      narr.appendChild(el("p", null, p.trim()));
    });
    wrap.appendChild(narr);
  }

  // 3-col stat grid
  const stats = el("div", { class: "plan-stats" });
  const fitClass = `plan-stat-fit-${String(plan.icp_fit || "medium").toLowerCase()}`;
  stats.appendChild(_renderPlanStat("ICP fit",   plan.icp_fit,                  plan.icp_rationale,        fitClass));
  stats.appendChild(_renderPlanStat("Deal size", plan.deal_size_estimate,       plan.deal_size_rationale));
  stats.appendChild(_renderPlanStat("Urgency",   plan.urgency,                  plan.urgency_rationale));
  wrap.appendChild(stats);

  // recommended plays
  if (plan.recommended_plays && plan.recommended_plays.length) {
    wrap.appendChild(el("div", { class: "section-title" }, "Recommended plays"));
    const plays = el("ol", { class: "plan-plays" });
    plan.recommended_plays.forEach((p, i) => plays.appendChild(_renderPlay(p, i)));
    wrap.appendChild(plays);
  }

  // open questions
  if (plan.open_questions && plan.open_questions.length) {
    const det = el("details", { class: "plan-questions" });
    const sum = el("summary", { class: "plan-questions-summary" });
    sum.textContent =
      `Open questions — ${plan.open_questions.length} thing${plan.open_questions.length === 1 ? "" : "s"} the next research pass should answer`;
    det.appendChild(sum);
    const ol = el("ol", { class: "plan-questions-list" });
    plan.open_questions.forEach((q) => ol.appendChild(el("li", null, String(q))));
    det.appendChild(ol);
    wrap.appendChild(det);
  }

  return wrap;
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

// V7.19 — section → dept mapping for the synergy drawer's "related claims" view
const _SECTION_DEPT = {
  account_brief:    "gtm",
  market_signal:    "finance",
  risk_profile:     "security",
  marketing_signal: "marketing",
};

function _claimsForSynergy(brief, synergy) {
  const synergyUrls = new Set((synergy.citations || []).map((c) => c.url).filter(Boolean));
  const out = [];
  Object.entries(_SECTION_DEPT).forEach(([sec, dept]) => {
    const section = brief && brief[sec];
    if (!section) return;
    Object.entries(section).forEach(([field, claims]) => {
      if (!Array.isArray(claims)) return;
      claims.forEach((cl) => {
        if ((cl.citations || []).some((c) => synergyUrls.has(c.url))) {
          out.push({ dept, field, claim: cl });
        }
      });
    });
  });
  return out;
}

function _ensureSynergyDrawer() {
  let backdrop = document.getElementById("synergy-drawer-backdrop");
  let drawer   = document.getElementById("synergy-drawer");
  if (backdrop && drawer) return { backdrop, drawer };
  backdrop = el("div", {
    id: "synergy-drawer-backdrop",
    class: "synergy-drawer-backdrop",
    "aria-hidden": "true",
  });
  drawer = el("aside", {
    id: "synergy-drawer",
    class: "synergy-drawer",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": "Synergy details",
    tabindex: "-1",
  });
  document.body.appendChild(backdrop);
  document.body.appendChild(drawer);
  backdrop.addEventListener("click", _closeSynergyDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer.dataset.open === "true") _closeSynergyDrawer();
  });
  return { backdrop, drawer };
}

function _closeSynergyDrawer() {
  const backdrop = document.getElementById("synergy-drawer-backdrop");
  const drawer   = document.getElementById("synergy-drawer");
  if (backdrop) backdrop.dataset.open = "false";
  if (drawer)   drawer.dataset.open   = "false";
}

function _openSynergyDrawer(synergy, brief) {
  const { backdrop, drawer } = _ensureSynergyDrawer();
  drawer.textContent = "";

  const closeBtn = el("button", {
    class: "synergy-drawer-close",
    type: "button",
    "aria-label": "Close drawer",
  }, "✕ close");
  closeBtn.addEventListener("click", _closeSynergyDrawer);
  drawer.appendChild(closeBtn);

  drawer.appendChild(el("h3", null, "Cross-department synergy"));
  drawer.appendChild(el(
    "div",
    { class: "depts-pill" },
    (synergy.contributing_depts || []).join(" + "),
  ));
  drawer.appendChild(el("div", { class: "syn-text" }, String(synergy.text || "")));

  if ((synergy.citations || []).length) {
    drawer.appendChild(el("div", { class: "syn-section-title" },
      `Grounding citations (${synergy.citations.length})`));
    synergy.citations.forEach((c) => {
      const a = el("a", {
        class: "syn-cite",
        href: safeUrl(c.url),
        target: "_blank",
        rel: "noopener noreferrer",
      });
      a.appendChild(el("div", { class: "syn-cite-url" },
        `§ ${c.source_type || "src"} · ${c.url || ""}`));
      if (c.snippet) {
        a.appendChild(el("div", { class: "syn-cite-snippet" }, `"${c.snippet}"`));
      }
      drawer.appendChild(a);
    });
  }

  const related = _claimsForSynergy(brief, synergy);
  if (related.length) {
    drawer.appendChild(el("div", { class: "syn-section-title" },
      `Related claims (${related.length})`));
    related.forEach((m) => {
      const w = el("div", { class: `syn-claim syn-claim-${m.dept}` });
      w.appendChild(el("div", { class: "syn-claim-dept" },
        `${m.dept.toUpperCase()} · ${m.field.replace(/_/g, " ")}`));
      w.appendChild(el("div", { class: "syn-claim-text" }, m.claim.text || ""));
      drawer.appendChild(w);
    });
  } else {
    drawer.appendChild(el("div", { class: "syn-section-title" }, "Related claims"));
    drawer.appendChild(el("div", { class: "syn-empty" },
      "No dept claims share the synergy's citation URLs — the synergy was inferred from cross-bundle patterns the depts didn't independently call out."));
  }

  backdrop.dataset.open = "true";
  drawer.dataset.open   = "true";
  drawer.focus({ preventScroll: true });
}

// V7.25 — Gantt chart for recommended plays.
// Parses each play's `timeframe` ("this week", "30 days", "this quarter")
// into a [start_day, end_day] span and renders horizontal bars on a
// shared timeline, colored by primary owner dept.

function _parseTimeframe(t) {
  const s = String(t || "").toLowerCase().trim();
  if (!s) return [0, 30];
  // explicit "N days" / "N day" wins
  const days = s.match(/(\d+)\s*day/);
  if (days) return [0, Math.max(1, parseInt(days[1], 10))];
  // "N weeks"
  const weeks = s.match(/(\d+)\s*week/);
  if (weeks) return [0, parseInt(weeks[1], 10) * 7];
  // "N months"
  const months = s.match(/(\d+)\s*month/);
  if (months) return [0, parseInt(months[1], 10) * 30];
  // named windows
  if (s.includes("this week") || s === "week" || s === "1w") return [0, 7];
  if (s.includes("two week") || s === "2w" || s.includes("biweek")) return [0, 14];
  if (s.includes("this month")) return [0, 30];
  if (s.includes("quarter") || /q[1-4]/.test(s)) return [0, 90];
  if (s.includes("half") || s.includes("h1") || s.includes("h2") || s.includes("6 month")) return [0, 180];
  if (s.includes("year") || s.includes("annual")) return [0, 365];
  if (s.includes("immediate") || s.includes("now")) return [0, 3];
  return [0, 30];  // safe default
}

const _OWNER_CLASS = { gtm: "gtm", finance: "finance", security: "security", marketing: "marketing" };

function renderPlanGantt(plan) {
  if (!plan || !plan.recommended_plays || !plan.recommended_plays.length) return null;
  const plays = plan.recommended_plays;
  const spans = plays.map((p) => _parseTimeframe(p.timeframe));
  const maxDay = Math.max(30, ...spans.map((s) => s[1]));

  const wrap = el("div", { class: "gantt-section" });
  wrap.appendChild(el("div", { class: "section-title" }, "Strategic plan · Gantt timeline"));
  wrap.appendChild(el(
    "div",
    { class: "gantt-hint" },
    `Bars span each play's timeframe (max ${maxDay} days). Hover for full text · click a bar to scroll to the play card.`,
  ));

  // Day scale tick row
  const scale = el("div", { class: "gantt-scale" });
  // tick every ceil(maxDay/6) days for readable spacing
  const tickStep = maxDay <= 30 ? 5 : maxDay <= 90 ? 15 : 30;
  for (let d = 0; d <= maxDay; d += tickStep) {
    const tick = el("div", { class: "gantt-tick" }, d === 0 ? "0" : `${d}d`);
    tick.style.left = `${(d / maxDay) * 100}%`;
    scale.appendChild(tick);
  }
  wrap.appendChild(scale);

  const rows = el("div", { class: "gantt-rows" });
  plays.forEach((play, i) => {
    const [start, end] = spans[i];
    const row = el("div", { class: "gantt-row" });

    const label = el("div", { class: "gantt-row-label" }, `P${play.priority || 3}`);
    row.appendChild(label);

    const track = el("div", { class: "gantt-track" });
    const ownerKey = String((play.owners || [])[0] || "").toLowerCase();
    const ownerCls = _OWNER_CLASS[ownerKey] || "default";
    const fullText = String(play.text || "");
    const bar = el(
      "div",
      {
        class: `gantt-bar gantt-bar-${ownerCls}`,
        title: `${fullText}\n${play.timeframe || ""} · owners: ${(play.owners || []).join(", ") || "—"}`,
        role: "button",
        tabindex: "0",
        "aria-label": `Play P${play.priority || 3}: ${fullText}`,
      },
      fullText,
    );
    bar.style.left  = `${(start / maxDay) * 100}%`;
    bar.style.width = `${Math.max(2, ((end - start) / maxDay) * 100)}%`;
    // click → scroll the matching .plan-play into view and expand it
    bar.addEventListener("click", () => {
      const card = document.querySelectorAll(".plan-play")[i];
      if (card) {
        card.setAttribute("aria-expanded", "true");
        card.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
    bar.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); bar.click(); }
    });
    track.appendChild(bar);
    row.appendChild(track);
    rows.appendChild(row);
  });
  wrap.appendChild(rows);
  return wrap;
}

// V7.24 — Porter's Five Forces section: ECharts radar chart at top,
// 5 cards underneath with each force's assessment + citations.
const _FORCE_ORDER = [
  { key: "rivalry",        label: "Industry rivalry" },
  { key: "new_entrants",   label: "New entrants" },
  { key: "supplier_power", label: "Supplier power" },
  { key: "buyer_power",    label: "Buyer power" },
  { key: "substitutes",    label: "Substitutes" },
];

function renderFiveForces(forces) {
  if (!forces) return null;
  // skip section entirely if every force is blank
  const haveContent = _FORCE_ORDER.some((f) => {
    const force = forces[f.key];
    return force && (force.assessment || (force.citations || []).length || force.intensity);
  });
  if (!haveContent) return null;

  const wrap = el("div", { class: "porter-section" });
  wrap.appendChild(el("div", { class: "section-title" }, "Porter's Five Forces · competitive pressure 1–5"));

  // radar chart (top)
  const chartEl = el("div", { class: "porter-radar", id: "porter-radar" });
  wrap.appendChild(chartEl);

  // cards (bottom)
  const grid = el("div", { class: "porter-cards" });
  _FORCE_ORDER.forEach((f) => {
    const force = forces[f.key];
    if (!force) return;
    const inten = Math.max(1, Math.min(5, force.intensity || 3));
    const card = el("div", { class: `porter-card porter-card-i${inten}` });
    const head = el("div", { class: "porter-card-head" });
    head.appendChild(el("span", { class: "porter-card-label" }, f.label));
    head.appendChild(el("span", { class: "porter-card-intensity" }, `${inten}/5`));
    card.appendChild(head);
    // intensity meter
    const meter = el("div", { class: "porter-card-meter" });
    const fill  = el("div", { class: "porter-card-meter-fill" });
    fill.style.width = `${inten * 20}%`;
    meter.appendChild(fill);
    card.appendChild(meter);
    if (force.assessment) {
      card.appendChild(el("div", { class: "porter-card-text" }, String(force.assessment)));
    }
    if ((force.citations || []).length) {
      const cites = el("div", { class: "cites" });
      force.citations.forEach((c) => {
        cites.appendChild(el(
          "a",
          { class: "cite", href: safeUrl(c.url), target: "_blank", rel: "noopener noreferrer" },
          `§ ${c.source_type || "src"}`,
        ));
      });
      card.appendChild(cites);
    }
    grid.appendChild(card);
  });
  wrap.appendChild(grid);

  // init ECharts radar after DOM insertion
  requestAnimationFrame(() => {
    if (typeof echarts === "undefined") return;
    let inst;
    try { inst = echarts.init(chartEl, null, { renderer: "canvas" }); }
    catch (_e) { return; }
    const indicators = _FORCE_ORDER.map((f) => ({ name: f.label, max: 5 }));
    const values = _FORCE_ORDER.map((f) => (forces[f.key] && forces[f.key].intensity) || 0);
    inst.setOption({
      backgroundColor: "transparent",
      tooltip: {
        backgroundColor: "rgba(13,14,16,0.92)",
        borderColor: "#2a2620",
        textStyle: { color: "#f1ede4", fontFamily: "JetBrains Mono", fontSize: 11 },
      },
      radar: {
        indicator: indicators,
        center: ["50%", "55%"],
        radius: "62%",
        shape: "polygon",
        splitNumber: 5,
        axisName: {
          color: "#f1ede4",
          fontFamily: "JetBrains Mono",
          fontSize: 10,
          padding: [3, 3],
        },
        splitArea: { areaStyle: { color: ["rgba(255,255,255,0.018)", "rgba(255,255,255,0.005)"] } },
        splitLine: { lineStyle: { color: "#2a2620" } },
        axisLine: { lineStyle: { color: "#2a2620" } },
      },
      series: [{
        type: "radar",
        name: "intensity",
        symbol: "circle",
        symbolSize: 6,
        areaStyle: { color: "rgba(232,74,58,0.22)" },
        lineStyle: { color: "#e84a3a", width: 2 },
        itemStyle: { color: "#e84a3a" },
        data: [{ value: values, name: "1–5 force intensity" }],
      }],
    });
    window.addEventListener("resize", () => inst.resize());
  });
  return wrap;
}

// V7.24 — SWOT 2×2 grid
const _SWOT_QUADRANTS = [
  { key: "strengths",     label: "Strengths",     cls: "swot-s" },
  { key: "weaknesses",    label: "Weaknesses",    cls: "swot-w" },
  { key: "opportunities", label: "Opportunities", cls: "swot-o" },
  { key: "threats",       label: "Threats",       cls: "swot-t" },
];

function renderSwot(swot) {
  if (!swot) return null;
  const total = _SWOT_QUADRANTS.reduce(
    (n, q) => n + ((swot[q.key] || []).length), 0,
  );
  if (!total) return null;

  const wrap = el("div", { class: "swot-section" });
  wrap.appendChild(el("div", { class: "section-title" }, "SWOT · 2×2 strategic landscape"));
  const grid = el("div", { class: "swot-grid" });
  _SWOT_QUADRANTS.forEach((q) => {
    const quad = el("div", { class: `swot-quad ${q.cls}` });
    quad.appendChild(el("div", { class: "swot-quad-head" }, q.label));
    const items = swot[q.key] || [];
    if (!items.length) {
      quad.appendChild(el("div", { class: "swot-empty" }, "—"));
    } else {
      items.forEach((it) => {
        const imp = Math.max(1, Math.min(3, it.impact || 2));
        const itemEl = el("div", { class: `swot-item swot-item-i${imp}` });
        itemEl.appendChild(el("div", { class: "swot-item-text" }, String(it.text || "")));
        if ((it.citations || []).length) {
          const cites = el("div", { class: "cites" });
          it.citations.forEach((c) => {
            cites.appendChild(el(
              "a",
              { class: "cite", href: safeUrl(c.url), target: "_blank", rel: "noopener noreferrer" },
              `§ ${c.source_type || "src"}`,
            ));
          });
          itemEl.appendChild(cites);
        }
        quad.appendChild(itemEl);
      });
    }
    grid.appendChild(quad);
  });
  wrap.appendChild(grid);
  return wrap;
}

// V7.23 — Contradictions section: opposing-source claim pairs surfaced by
// the contradictions agent. Each card is a side-by-side compare w/ severity
// styling + citations under each side.
function renderContradictions(contradictions) {
  if (!contradictions || !contradictions.length) return null;
  const wrap = el("div");
  wrap.appendChild(el("div", { class: "section-title" }, "Contradictions — opposing-source claims"));
  const grid = el("div", { class: "contradictions-grid" });
  contradictions.forEach((c) => {
    const sev = Math.max(1, Math.min(3, c.severity || 2));
    const card = el("div", { class: `contradiction contradiction-sev-${sev}` });

    const head = el("div", { class: "contradiction-head" });
    head.appendChild(el("span", { class: "contradiction-axis" }, c.axis || "—"));
    head.appendChild(el("span", { class: "contradiction-severity" }, `severity ${sev}/3`));
    card.appendChild(head);

    if (c.summary) {
      card.appendChild(el("div", { class: "contradiction-summary" }, c.summary));
    }

    const cmp = el("div", { class: "contradiction-grid" });

    const sideA = el("div", { class: "contradiction-side contradiction-side-a" });
    sideA.appendChild(el("div", { class: "contradiction-side-label" }, "Source A says"));
    sideA.appendChild(el("div", { class: "contradiction-claim" }, c.claim_a || ""));
    const citesA = el("div", { class: "cites" });
    (c.citations_a || []).forEach((cite) => {
      citesA.appendChild(el(
        "a",
        { class: "cite", href: safeUrl(cite.url), target: "_blank", rel: "noopener noreferrer" },
        `§ ${cite.source_type || "src"}`,
      ));
    });
    if (citesA.childNodes.length) sideA.appendChild(citesA);
    cmp.appendChild(sideA);

    cmp.appendChild(el("div", { class: "contradiction-vs" }, "vs"));

    const sideB = el("div", { class: "contradiction-side contradiction-side-b" });
    sideB.appendChild(el("div", { class: "contradiction-side-label" }, "Source B says"));
    sideB.appendChild(el("div", { class: "contradiction-claim" }, c.claim_b || ""));
    const citesB = el("div", { class: "cites" });
    (c.citations_b || []).forEach((cite) => {
      citesB.appendChild(el(
        "a",
        { class: "cite", href: safeUrl(cite.url), target: "_blank", rel: "noopener noreferrer" },
        `§ ${cite.source_type || "src"}`,
      ));
    });
    if (citesB.childNodes.length) sideB.appendChild(citesB);
    cmp.appendChild(sideB);

    card.appendChild(cmp);
    grid.appendChild(card);
  });
  wrap.appendChild(grid);
  return wrap;
}

function renderSynergies(synergies, brief) {
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
    const card = el("div", {
      class: classes.join(" "),
      role: "button",
      tabindex: "0",
      "aria-label": `Open synergy details: ${(s.contributing_depts || []).join(" + ")}`,
    });
    card.appendChild(el("div", { class: "depts" }, (s.contributing_depts || []).join(" + ")));
    card.appendChild(el("div", null, String(s.text || "")));
    card.addEventListener("click", () => _openSynergyDrawer(s, brief));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        card.click();
      }
    });
    grid.appendChild(card);
  });
  wrap.appendChild(grid);
  return wrap;
}

// V7.20 — 3D claims-breakdown chart. ECharts-GL bar3D w/ dept × field × count.
// CDN-loaded; if the bundle isn't reachable (offline / network blocked) the
// wrapper renders a friendly fallback line instead of failing the whole page.

const _CHART_SECTIONS = [
  { dept: 'GTM',       key: 'account_brief',    color: '#5ad6e8' },
  { dept: 'Finance',   key: 'market_signal',    color: '#98e08a' },
  { dept: 'Security',  key: 'risk_profile',     color: '#f0a849' },
  { dept: 'Marketing', key: 'marketing_signal', color: '#ff85c9' },
];

function renderClaimsChart(brief) {
  const wrap = el("div", { class: "claims-chart-wrap" });
  wrap.appendChild(el("div", { class: "section-title" }, "Grounded claims · dept × signal"));
  wrap.appendChild(el(
    "div",
    { class: "claims-chart-hint" },
    "Drag to orbit · scroll to zoom · hover a bar for the exact count",
  ));

  if (typeof echarts === "undefined") {
    wrap.appendChild(el(
      "div",
      { class: "claims-chart-empty" },
      "ECharts CDN unreachable — 3D chart skipped (panels below still cover the breakdown).",
    ));
    return wrap;
  }

  // Build (dept, field) → count matrix. Only retain fields with any data anywhere.
  const sections = _CHART_SECTIONS.map((s) => ({ ...s, data: brief[s.key] || {} }));
  const allFields = new Set();
  sections.forEach((s) => {
    Object.entries(s.data).forEach(([f, v]) => {
      if (Array.isArray(v) && v.length > 0) allFields.add(f);
    });
  });
  const fields = [...allFields];
  if (!fields.length) {
    wrap.appendChild(el(
      "div",
      { class: "claims-chart-empty" },
      "No grounded claims to chart — every dept dropped below threshold.",
    ));
    return wrap;
  }

  const depts = sections.map((s) => s.dept);
  const colors = sections.map((s) => s.color);
  const data = [];
  sections.forEach((s, di) => {
    fields.forEach((f, fi) => {
      const claims = s.data[f];
      const count = Array.isArray(claims) ? claims.length : 0;
      if (count > 0) data.push([di, fi, count]);
    });
  });

  const chart = el("div", { class: "claims-chart", id: "claims-chart" });
  wrap.appendChild(chart);

  // ECharts needs the container measured before init. Defer one frame.
  requestAnimationFrame(() => {
    let inst;
    try {
      inst = echarts.init(chart, null, { renderer: 'canvas' });
    } catch (_e) {
      chart.replaceWith(el(
        "div",
        { class: "claims-chart-empty" },
        "ECharts init failed — 3D chart unavailable.",
      ));
      return;
    }

    const maxVal = Math.max(...data.map((d) => d[2]), 1);
    inst.setOption({
      backgroundColor: 'transparent',
      tooltip: {
        backgroundColor: 'rgba(13, 14, 16, 0.92)',
        borderColor: '#2a2620',
        borderWidth: 1,
        textStyle: { color: '#f1ede4', fontFamily: 'JetBrains Mono', fontSize: 11 },
        formatter: (p) => {
          const [di, fi, v] = p.value;
          return `<b>${depts[di]}</b><br/>${fields[fi].replace(/_/g, " ")}<br/><b style="color:${colors[di]}">${v}</b> grounded claim${v === 1 ? '' : 's'}`;
        },
      },
      xAxis3D: {
        type: 'category',
        data: depts,
        axisLabel: { color: '#f1ede4', fontSize: 11, fontFamily: 'JetBrains Mono' },
        axisLine: { lineStyle: { color: '#2a2620' } },
        nameTextStyle: { color: '#b8b2a4' },
      },
      yAxis3D: {
        type: 'category',
        data: fields.map((f) => f.replace(/_/g, ' ')),
        axisLabel: { color: '#b8b2a4', fontSize: 9, fontFamily: 'JetBrains Mono' },
        axisLine: { lineStyle: { color: '#2a2620' } },
      },
      zAxis3D: {
        type: 'value',
        min: 0,
        max: maxVal + 1,
        axisLabel: { color: '#b8b2a4', fontSize: 10, fontFamily: 'JetBrains Mono' },
        axisLine: { lineStyle: { color: '#2a2620' } },
        splitLine: { lineStyle: { color: '#2a2620' } },
      },
      grid3D: {
        boxWidth:  180,
        boxDepth:  130,
        boxHeight:  70,
        viewControl: {
          autoRotate: true,
          autoRotateAfterStill: 4,
          autoRotateSpeed: 5,
          distance: 230,
          alpha: 18,
          beta: 35,
        },
        light: {
          main: { intensity: 1.2, shadow: true, alpha: 35, beta: 40 },
          ambient: { intensity: 0.35 },
        },
        environment: '#0d0e10',
        axisLine:    { lineStyle: { color: '#2a2620' } },
        axisPointer: { lineStyle: { color: '#e84a3a' } },
      },
      series: [{
        type: 'bar3D',
        data: data,
        shading: 'realistic',
        itemStyle: {
          color: (p) => colors[p.value[0]],
          opacity: 0.92,
        },
        emphasis: {
          label: {
            show: true,
            formatter: (p) => String(p.value[2]),
            textStyle: { color: '#0d0e10', fontFamily: 'JetBrains Mono', fontSize: 12, fontWeight: 'bold' },
          },
          itemStyle: { color: '#e84a3a' },
        },
      }],
    });

    // resize gracefully when the viewport changes
    window.addEventListener('resize', () => inst.resize());
  });

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

  // V6 — strategic plan hero (the conclusion). If absent, fall back to the
  // legacy templated exec summary so older briefs still render usefully.
  const planNode = renderStrategicPlan(brief.strategic_plan);
  if (planNode) {
    app.appendChild(planNode);
    // V7.25 — Gantt timeline of the plays sits right under the plan hero
    const gantt = renderPlanGantt(brief.strategic_plan);
    if (gantt) app.appendChild(gantt);
  } else if (brief.executive_summary) {
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

  // V7.20 — 3D claim-breakdown chart between cascade flow and synergies
  const chart = renderClaimsChart(brief);
  if (chart) app.appendChild(chart);

  const syn = renderSynergies(brief.synergy_signals, brief);
  if (syn) app.appendChild(syn);

  // V7.23 — Contradictions sit after synergies (both are cross-source layers)
  const contras = renderContradictions(brief.contradictions);
  if (contras) app.appendChild(contras);

  // V7.24 — Strategic-framework section: Porter's 5 Forces + SWOT side-by-side
  const porter = renderFiveForces(brief.five_forces);
  if (porter) app.appendChild(porter);
  const swot = renderSwot(brief.swot);
  if (swot) app.appendChild(swot);

  app.appendChild(el("div", { class: "section-title" }, "Departments"));
  const cols = el("div", { class: "cols" });
  DEPTS.forEach((d) => {
    const p = renderPanel(d, brief);
    if (p) cols.appendChild(p);
  });
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

// V7 — onboarding modal for self-mode. Header "🚀 analyze my business" button
// opens it; submit POSTs to /api/run mode=self with a BusinessProfile payload
// and uses the same SSE-driven cytoscape animation as live demo / live run.
function _wireSelfModal() {
  const openBtn = document.getElementById("analyzeself");
  const modal   = document.getElementById("selfmodal");
  const form    = document.getElementById("selfform");
  const warn    = document.getElementById("selfmodal-warn");
  if (!openBtn || !modal || !form) return;

  const open = () => {
    if (warn) { warn.hidden = true; warn.textContent = ""; }
    modal.hidden = false;
    // focus the first text field for keyboard flow
    const first = form.querySelector('input[name="name"]');
    if (first) setTimeout(() => first.focus(), 30);
    document.body.classList.add("modal-open");
  };
  const close = () => {
    modal.hidden = true;
    document.body.classList.remove("modal-open");
  };
  openBtn.addEventListener("click", open);
  modal.addEventListener("click", (e) => {
    if (e.target && e.target.dataset && e.target.dataset.close !== undefined) close();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) close();
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const competitorRaw = (fd.get("competitor_urls") || "").toString();
    const competitor_urls = competitorRaw
      .split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);

    const profile = {
      name:             (fd.get("name") || "").toString().trim(),
      url:              (fd.get("url")  || "").toString().trim(),
      industry:         (fd.get("industry") || "").toString().trim(),
      stage:            (fd.get("stage") || "early-revenue").toString(),
      goal:             (fd.get("goal") || "").toString().trim(),
      customer_segment: (fd.get("customer_segment") || "").toString().trim(),
      competitor_urls,
    };

    if (!profile.name || !profile.url) {
      if (warn) { warn.hidden = false; warn.textContent = "business name and URL are required"; }
      return;
    }

    const container = document.getElementById("cascade-graph");
    if (!container || !container._cy) {
      if (warn) { warn.hidden = false; warn.textContent = "cascade graph not ready — try again in a second"; }
      return;
    }
    if (typeof runLiveCascade !== "function") return;

    const tip = container.parentElement.querySelector(".cascade-tip");
    close();
    runLiveCascade(
      { mode: "self", profile },
      {
        cy: container._cy, tip,
        buttons: { primary: openBtn },
        labelWhenRunning: "⏳ analyzing…",
      },
    );
  });
}

// V7.4 — status banner. On load (and after each render) we fetch /api/status:
//   - if a cascade is running   → show a yellow 'still running' banner and
//                                  poll every 3s until it completes, then
//                                  refetch brief.json + re-render.
//   - if last run errored       → show a red banner with the error message
//                                  + any per-URL failures.
//   - if backend is unreachable → silently skip (offline replay still works).
function _statusBanner() {
  let banner = document.getElementById("status-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "status-banner";
    banner.className = "status-banner";
    banner.hidden = true;
    document.body.insertBefore(banner, document.body.firstChild);
  }
  return banner;
}

function _showBanner(kind, html) {
  const banner = _statusBanner();
  banner.className = `status-banner status-${kind}`;
  banner.innerHTML = "";
  // build via DOM nodes; only trusted strings (server-controlled) reach here
  if (typeof html === "string") {
    banner.textContent = html;
  } else if (html && html.nodeType) {
    banner.appendChild(html);
  }
  banner.hidden = false;
}

function _hideBanner() {
  const banner = document.getElementById("status-banner");
  if (banner) banner.hidden = true;
}

function _formatRunning(s) {
  const lr = s.last_run || {};
  const phase = lr.last_phase ? ` · current phase: ${lr.last_phase}` : "";
  return `🌐 a cascade is running for "${lr.target || '?'}" (mode: ${lr.mode || '?'})${phase} — this page will refresh automatically when it completes`;
}

function _formatError(s) {
  const lr = s.last_run || {};
  const wrap = document.createElement("div");
  const head = document.createElement("div");
  head.className = "status-banner-head";
  head.textContent = `✗ last cascade for "${lr.target || '?'}" failed`;
  wrap.appendChild(head);

  const body = document.createElement("div");
  body.className = "status-banner-body";
  body.textContent = lr.error || "unknown error";
  wrap.appendChild(body);

  const urlErrs = lr.url_errors || [];
  if (urlErrs.length) {
    const ul = document.createElement("ul");
    ul.className = "status-banner-list";
    urlErrs.forEach((e) => {
      const li = document.createElement("li");
      li.textContent = `${e.url} (${e.subject || "?"}): ${e.error}`;
      ul.appendChild(li);
    });
    wrap.appendChild(ul);
  }

  const dismiss = document.createElement("button");
  dismiss.className = "status-banner-dismiss";
  dismiss.type = "button";
  dismiss.textContent = "dismiss";
  dismiss.addEventListener("click", _hideBanner);
  wrap.appendChild(dismiss);

  return wrap;
}

let _statusPollTimer = null;
function _stopPolling() {
  if (_statusPollTimer) { clearTimeout(_statusPollTimer); _statusPollTimer = null; }
}

function _pollStatus() {
  _stopPolling();
  fetch("/api/status", { cache: "no-store" })
    .then((r) => r.ok ? r.json() : null)
    .then((s) => {
      if (!s) return;
      if (s.running) {
        _showBanner("running", _formatRunning(s));
        _statusPollTimer = setTimeout(_pollStatus, 3000);
      } else {
        // run just finished. Refetch brief + re-render.
        const lr = s.last_run || {};
        if (lr.status === "completed") {
          _showBanner("ok", `✓ cascade for "${lr.target}" completed · ${lr.dropped || 0} ungrounded dropped`);
          setTimeout(_hideBanner, 6000);
          fetch("brief.json", { cache: "no-store" })
            .then((r) => r.json())
            .then((b) => render(b))
            .catch(() => {});
        } else if (lr.status === "error") {
          _showBanner("error", _formatError(s));
        }
      }
    })
    .catch(() => {});
}

function _checkStatusOnLoad() {
  fetch("/api/status", { cache: "no-store" })
    .then((r) => r.ok ? r.json() : null)
    .then((s) => {
      if (!s) return;
      if (s.running) {
        _showBanner("running", _formatRunning(s));
        _statusPollTimer = setTimeout(_pollStatus, 3000);
      } else if (s.last_run && s.last_run.status === "error") {
        _showBanner("error", _formatError(s));
      }
    })
    .catch(() => {});
}

fetch("brief.json")
  .then((r) => { if (!r.ok) throw new Error(`brief.json ${r.status}`); return r.json(); })
  .then((b) => {
    render(b);
    _wireHeaderPullFresh();
    _wireSelfModal();
    _checkStatusOnLoad();
  })
  .catch((e) => {
    const err = document.getElementById("error");
    err.textContent = "Could not load brief.json: " + e.message;
    err.classList.remove("hidden");
  });
