// cascade-flow.js (V3) — cytoscape-driven cascade graph.
//
// Receives the full CascadeBrief and renders an interactive node-edge graph:
//   - Bright Data source (top)
//   - 3 dept nodes in parallel (GTM, Finance, Security)
//   - Cascade Brief (bottom, vermilion — the deliverable)
// Edges:
//   - feed:    source → dept       (solid, dept-color)
//   - output:  dept → brief        (solid, dept-color)
//   - handoff: dept → dept         (curved up, dept-color, message label)
//   - synergy: dept ↔ dept         (curved down, dashed purple)
//
// Click a dept node → body[data-focus] flips → CSS dims other panels/synergies.
// Click empty canvas → clears focus.
// Hover an edge → tooltip strip shows the full handoff/synergy message.
//
// All injected user text uses textContent / cytoscape data binding — never
// innerHTML on brief content.
//
// Back-compat: if the caller passes a handoffs array (legacy), we wrap it.

const DEPT_COLOR    = {
  marketing: '#ff85c9',
  gtm:       '#5ad6e8',
  finance:   '#98e08a',
  security:  '#f0a849',
};
const SYNERGY_COLOR = '#c8a8ff';
const SHU           = '#e84a3a';
const PAPER_DIM     = '#b8b2a4';
const INK           = '#0d0e10';
const BASE_TIP      = 'Click a department to filter · hover edges to read the cross-talk';

// V7.14 — phase pips. Each phase has 3 states: pending|active|done.
// Drives a small strip under the toolbar, updated by SSE events (live mode)
// and by replay timers (offline replay). Reset at the start of every cascade.
const PHASE_PIPS = ['pii', 'leak', 'marketing', 'gtm', 'finance', 'security', 'grounding', 'strategy'];

function _buildPipsStrip() {
  const strip = flowEl('div', 'cascade-pips');
  strip.setAttribute('role', 'status');
  strip.setAttribute('aria-label', 'cascade progress');
  PHASE_PIPS.forEach((phase) => {
    const pip = flowEl('span', 'pip');
    pip.dataset.phase = phase;
    pip.dataset.state = 'pending';
    pip.appendChild(flowEl('span', 'pip-dot'));
    pip.appendChild(document.createTextNode(phase));
    strip.appendChild(pip);
  });
  return strip;
}

function _findPips() {
  const c = document.getElementById('cascade-graph');
  return c && c.parentElement && c.parentElement.querySelector('.cascade-pips');
}

function _resetPips() {
  const strip = _findPips();
  if (!strip) return;
  strip.querySelectorAll('.pip').forEach((p) => { p.dataset.state = 'pending'; });
}

function _setPip(phase, state) {
  const strip = _findPips();
  if (!strip) return;
  const pip = strip.querySelector(`.pip[data-phase="${phase}"]`);
  if (pip) pip.dataset.state = state;
}

function deptKey(name) {
  const n = String(name || '').toLowerCase();
  // 'marketing' first so 'market' matches finance only when 'marketing' isn't.
  if (n.includes('marketing') || n.includes('brand') || n.includes('positioning')) return 'marketing';
  if (n.includes('gtm') || n.includes('revenue') || n.includes('sales')) return 'gtm';
  if (n.includes('finance') || n.includes('market')) return 'finance';
  if (n.includes('security') || n.includes('compliance') || n.includes('risk')) return 'security';
  return null;
}

// Derive a 1-2 word label for a handoff/synergy edge. Full message lives in
// the tooltip strip below the graph (replay + hover both write to it), so the
// edge label only needs to communicate the TOPIC at a glance — clipping a long
// sentence with '…' is unreadable on top of an edge.
function shortLabel(message, fallback) {
  const m = String(message || '').toLowerCase();
  if (m.includes('pricing'))                                return 'pricing';
  if (m.includes('reputation'))                             return 'reputation';
  if (m.includes('hiring') || m.includes('attack surface')) return 'hiring';
  if (m.includes('churn'))                                  return 'churn risk';
  if (m.includes('growth') || m.includes('expansion'))      return 'growth';
  if (m.includes('vendor'))                                 return 'vendor';
  if (m.includes('regulatory') || m.includes('compliance')) return 'regulatory';
  // last resort: first two words, lowercased
  if (fallback) return fallback;
  return String(message || '').split(/\s+/).slice(0, 2).join(' ').toLowerCase();
}

function flowEl(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// V7.29 — sector-conditional satellite cluster. Different industries get
// different sub-pipeline nodes injected into the cascade graph so the visual
// topology reflects each brief's sector. Pharma adds clinical pipeline +
// regulatory + partners nodes; SaaS adds tiers + PLG + logos; etc.
const SECTOR_NODE_DEFS = {
  pharma: {
    color: '#ff85c9',
    nodes: [
      { id: 'pharma_pipeline', label: 'Clinical pipeline', field: 'pipeline' },
      { id: 'pharma_subs',     label: 'Regulatory subs',   field: 'submissions' },
      { id: 'pharma_partners', label: 'Clinical partners', field: 'partners' },
    ],
  },
  saas: {
    color: '#5ad6e8',
    nodes: [
      { id: 'saas_tiers', label: 'Pricing tiers',  field: 'tiers' },
      { id: 'saas_plg',   label: 'PLG metrics',    field: 'plg_metrics' },
      { id: 'saas_logos', label: 'Reference logos', field: 'reference_logos' },
    ],
  },
  energy: {
    color: '#f0a849',
    nodes: [
      { id: 'energy_sites', label: 'Installed sites', field: 'sites' },
      { id: 'energy_certs', label: 'Certifications',  field: 'certifications' },
      { id: 'energy_grid',  label: 'Grid deals',      field: 'grid_deals' },
    ],
  },
  generic: {
    color: '#c8a8ff',
    nodes: [
      { id: 'gen_moats',   label: 'Competitive moats', field: 'moats' },
      { id: 'gen_cadence', label: 'Operating cadence', field: 'cadence' },
    ],
  },
};


// V7.32 — per-dept signal counts feed into dept node labels so each
// brief's graph reads visibly different even when cross_pollinate
// handoffs/synergies hit identical templates across cases. Source field
// names mirror agents/schemas.py:
//   Marketing → marketing_signal.{value_proposition,positioning,brand_voice,content_gaps,channel_signals}
//   GTM       → account_brief.{buying_signals,competitor_moves,hiring_signals}
//   Finance   → market_signal.{pricing_trend,expansion_contraction,web_traffic_proxy,vendor_health_flags}
//   Security  → risk_profile.{exposure_indicators,reputational_signals,regulatory_signals,third_party_risk}
const DEPT_SIGNAL_PATHS = {
  marketing: ['marketing_signal', ['value_proposition','positioning','brand_voice','content_gaps','channel_signals']],
  gtm:       ['account_brief',    ['buying_signals','competitor_moves','hiring_signals']],
  finance:   ['market_signal',    ['pricing_trend','expansion_contraction','web_traffic_proxy','vendor_health_flags']],
  security:  ['risk_profile',     ['exposure_indicators','reputational_signals','regulatory_signals','third_party_risk']],
};

function deptSignalCount(brief, dept) {
  const def = DEPT_SIGNAL_PATHS[dept];
  if (!def || !brief) return 0;
  const [block, fields] = def;
  const obj = brief[block];
  if (!obj || typeof obj !== 'object') return 0;
  let total = 0;
  for (const f of fields) {
    const v = obj[f];
    if (Array.isArray(v)) total += v.length;
  }
  return total;
}

function deptLabel(brief, dept, base) {
  const n = deptSignalCount(brief, dept);
  return n > 0 ? `${base} · ${n}` : base;
}

function buildElements(brief) {
  const els = [
    { data: { id: 'source',    label: 'Bright Data',   type: 'source', color: PAPER_DIM } },
    { data: { id: 'marketing', label: deptLabel(brief, 'marketing', 'Marketing'), type: 'dept', dept: 'marketing', color: DEPT_COLOR.marketing } },
    { data: { id: 'gtm',       label: deptLabel(brief, 'gtm',       'GTM'),       type: 'dept', dept: 'gtm',       color: DEPT_COLOR.gtm } },
    { data: { id: 'finance',   label: deptLabel(brief, 'finance',   'Finance'),   type: 'dept', dept: 'finance',   color: DEPT_COLOR.finance } },
    { data: { id: 'security',  label: deptLabel(brief, 'security',  'Security'),  type: 'dept', dept: 'security',  color: DEPT_COLOR.security } },
    { data: { id: 'brief',     label: 'Cascade Brief', type: 'brief',  color: SHU } },
    { data: { id: 'e_sm', source: 'source',    target: 'marketing', type: 'feed',   color: DEPT_COLOR.marketing } },
    { data: { id: 'e_sg', source: 'source',    target: 'gtm',       type: 'feed',   color: DEPT_COLOR.gtm } },
    { data: { id: 'e_sf', source: 'source',    target: 'finance',   type: 'feed',   color: DEPT_COLOR.finance } },
    { data: { id: 'e_ss', source: 'source',    target: 'security',  type: 'feed',   color: DEPT_COLOR.security } },
    { data: { id: 'e_mb', source: 'marketing', target: 'brief',     type: 'output', color: DEPT_COLOR.marketing } },
    { data: { id: 'e_gb', source: 'gtm',       target: 'brief',     type: 'output', color: DEPT_COLOR.gtm } },
    { data: { id: 'e_fb', source: 'finance',   target: 'brief',     type: 'output', color: DEPT_COLOR.finance } },
    { data: { id: 'e_sb', source: 'security',  target: 'brief',     type: 'output', color: DEPT_COLOR.security } },
  ];

  // V7.29 — inject sector-specific satellite nodes for the active sector.
  // Pharma briefs get pipeline+submissions+partners nodes; SaaS gets
  // tiers+PLG+logos; energy gets sites+certs+grid; generic gets moats+cadence.
  // Different brief = different graph topology. Each node label shows the
  // count of items the sector agent extracted for that bucket.
  const sector = brief && brief.sector;
  const def = sector && SECTOR_NODE_DEFS[sector];
  const sectorSignal = sector && brief && brief[`${sector}_signal`];
  if (def && sectorSignal) {
    for (const n of def.nodes) {
      const bucket = sectorSignal[n.field];
      const count = Array.isArray(bucket) ? bucket.length : 0;
      // V7.32 — ALWAYS show count (including 0) so two cases with the
      // same sector (e.g. Notion vs Supabase both saas) read distinctly
      // at a glance — '· 0' vs '· 6' tells the story without any data
      // panel inspection.
      const labelWithCount = `${n.label} · ${count}`;
      els.push({
        data: {
          id: n.id, label: labelWithCount,
          type: 'sector', sectorKey: sector,
          color: def.color,
          count: count,
        },
      });
      els.push({
        data: {
          id: `e_src_${n.id}`, source: 'source', target: n.id,
          type: 'feed', color: def.color,
        },
      });
      els.push({
        data: {
          id: `e_${n.id}_brief`, source: n.id, target: 'brief',
          type: 'output', color: def.color,
        },
      });
    }
  }

  // Stagger handoff arcs so multiple handoffs that share neighbours don't
  // pile their labels on top of each other. We assign each handoff an arc
  // class (arc-1..arc-3); the stylesheet binds different control-point
  // distances per class.
  const arcClasses = ['arc-1', 'arc-2', 'arc-3'];
  (brief.handoffs || []).forEach((h, i) => {
    const a = deptKey(h.from_dept);
    const b = deptKey(h.to_dept);
    if (!a || !b || a === b) return;
    els.push({
      data: {
        id: `h${i}`, source: a, target: b, type: 'handoff',
        color: DEPT_COLOR[a],
        label: shortLabel(h.message),
        full: String(h.message || ''),
      },
      classes: arcClasses[i % arcClasses.length],
    });
  });

  const seenPairs = new Set();
  const synArcs = ['syn-arc-1', 'syn-arc-2'];
  (brief.synergy_signals || []).forEach((s, i) => {
    const depts = (s.contributing_depts || []).map(deptKey).filter(Boolean);
    const unique = [...new Set(depts)];
    if (unique.length >= 2) {
      const key = [unique[0], unique[1]].sort().join('-');
      // collapse multiple synergies on the same pair into one edge
      if (seenPairs.has(key)) return;
      seenPairs.add(key);
      els.push({
        data: {
          id: `y${i}`, source: unique[0], target: unique[1], type: 'synergy',
          color: SYNERGY_COLOR,
          label: shortLabel(s.text, 'synergy'),
          full: String(s.text || ''),
        },
        classes: synArcs[i % synArcs.length],
      });
    }
  });

  return els;
}

function cytoStyle() {
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'rgba(13,14,16,0.92)',
        'background-opacity': 1,
        'border-width': 2,
        'border-color': 'data(color)',
        'label': 'data(label)',
        'color': 'data(color)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-family': 'JetBrains Mono, ui-monospace, monospace',
        'font-size': 11,
        'font-weight': 600,
        'shape': 'round-rectangle',
        'width': 124,
        'height': 44,
        'opacity': 0,
        'transition-property': 'border-width, opacity',
        'transition-duration': '0.2s',
      },
    },
    { selector: 'node[type="source"]', style: { width: 140, height: 38 } },
    { selector: 'node[type="brief"]',  style: { width: 160, height: 50, 'border-width': 3, 'font-size': 12 } },
    {
      selector: 'node[type="dept"]:selected',
      style: { 'border-width': 4, 'background-color': 'rgba(255,255,255,0.04)' },
    },
    // V7.29 — sector satellite nodes: slightly slimmer + dashed border to
    // distinguish from the universal dept nodes ("sector branch, not dept")
    {
      selector: 'node[type="sector"]',
      style: {
        width: 138, height: 38,
        'border-style': 'dashed',
        'font-size': 10.5,
        'font-weight': 500,
      },
    },
    // V7.32 — fade out empty sector buckets so the contrast between
    // "sector pass extracted nothing here" and "extracted N items" is
    // legible without reading the numbers.
    {
      selector: 'node[type="sector"][count = 0]',
      style: {
        'border-opacity': 0.45,
        'color': PAPER_DIM,
        'border-color': PAPER_DIM,
      },
    },

    {
      selector: 'edge',
      style: {
        width: 1.8,
        'line-color': 'data(color)',
        'target-arrow-color': 'data(color)',
        'target-arrow-shape': 'triangle',
        'target-arrow-fill': 'filled',
        // V7.39 — bumped from 1.15 → 1.6 so the triangle base is ~16px
        // (1.6 × default 10). Combined with distance-from-node=0, the
        // triangle's flat back sits exactly on the node border and the
        // tip overlaps INTO the node by ~16px. Reads as "arrow plugs
        // into the node" rather than "arrow floats nearby".
        'arrow-scale': 1.6,
        'curve-style': 'bezier',
        // V7.39 — endpoint clamps to the node body perimeter (not
        // node-or-label, which has edge cases when the label is
        // positioned inside the node). distance-from-node=0 eliminates
        // the 1px V7.32 gap that read as "disconnected" on Retina.
        'source-endpoint': 'outside-to-node',
        'target-endpoint': 'outside-to-node',
        'source-distance-from-node': 0,
        'target-distance-from-node': 0,
        // Force length calc against the perimeter intersection, not the
        // node centroid — keeps the bezier tangent computation aligned
        // with where the arrow actually lands.
        'edge-distances': 'intersection',
        opacity: 0,
        'transition-property': 'opacity, width',
        'transition-duration': '0.25s',
      },
    },
    {
      selector: 'edge[type="handoff"]',
      style: {
        'curve-style': 'unbundled-bezier',
        'control-point-weights': [0.5],
        label: 'data(label)',
        'font-family': 'JetBrains Mono, ui-monospace, monospace',
        'font-size': 11,
        'font-weight': 600,
        color: 'data(color)',
        'text-rotation': 'autorotate',
        // solid INK pad + text outline = labels readable over anything
        'text-background-color': INK,
        'text-background-opacity': 1,
        'text-background-padding': 4,
        'text-background-shape': 'round-rectangle',
        'text-border-color': 'data(color)',
        'text-border-opacity': 0.45,
        'text-border-width': 1,
        'text-outline-color': INK,
        'text-outline-width': 3,
        'text-outline-opacity': 1,
        'text-margin-y': -3,
      },
    },
    // Stagger handoff arcs so labels don't pile on the same curve.
    // V7.32 — tightened from -60/-98/-136 to -45/-78/-110.
    // V7.39 — tightened further to -32/-58/-84. The shallower the arc,
    // the closer the end-tangent stays to horizontal — and the
    // straighter the arrow tip's approach angle into the target node
    // perimeter. Steep tangents made the arrow look like it was
    // landing "off-corner".
    { selector: 'edge.arc-1', style: { 'control-point-distances': [-32] } },
    { selector: 'edge.arc-2', style: { 'control-point-distances': [-58] } },
    { selector: 'edge.arc-3', style: { 'control-point-distances': [-84] } },

    {
      selector: 'edge[type="synergy"]',
      style: {
        'curve-style': 'unbundled-bezier',
        'control-point-weights': [0.5],
        'line-style': 'dashed',
        'line-dash-pattern': [6, 4],
        label: 'data(label)',
        'font-family': 'JetBrains Mono, ui-monospace, monospace',
        'font-size': 11,
        'font-weight': 600,
        color: SYNERGY_COLOR,
        'text-rotation': 'autorotate',
        'text-background-color': INK,
        'text-background-opacity': 1,
        'text-background-padding': 4,
        'text-background-shape': 'round-rectangle',
        'text-border-color': SYNERGY_COLOR,
        'text-border-opacity': 0.45,
        'text-border-width': 1,
        'text-outline-color': INK,
        'text-outline-width': 3,
        'text-outline-opacity': 1,
        'text-margin-y': 3,
      },
    },
    // V7.39 — tightened synergy arcs from 70/108 → 52/82 to match the
    // shallower handoff curves above and keep arrow tangents close to
    // axis-aligned for clean perimeter landings.
    { selector: 'edge.syn-arc-1', style: { 'control-point-distances': [52] } },
    { selector: 'edge.syn-arc-2', style: { 'control-point-distances': [82] } },

    { selector: '.dim',      style: { opacity: 0.15 } },
    { selector: '.beam',     style: { width: 3 } },
  ];
}

// Preset layout — keeps the architecture story readable: source on top,
// depts in a row, sector cluster on the row below, brief at the bottom.
// cy.fit() scales to container width.
function presetPositions(brief) {
  const positions = {
    source:    { x: 460, y: 50 },
    marketing: { x: 100, y: 220 },
    gtm:       { x: 340, y: 220 },
    finance:   { x: 580, y: 220 },
    security:  { x: 820, y: 220 },
    brief:     { x: 460, y: 500 },
  };

  // V7.29-pt4 — sector satellite nodes get an explicit row between depts
  // and brief. Without this, cytoscape leaves them at (0,0) and the
  // edges from source render off-canvas toward the upper-left.
  const sector = brief && brief.sector;
  const def = sector && SECTOR_NODE_DEFS[sector];
  if (def && def.nodes && def.nodes.length) {
    const sectorY = 360;
    const count = def.nodes.length;
    // Spread the sector cluster across the canvas width: 1 node = center,
    // 2 nodes = (240, 680), 3 nodes = (220, 460, 700)
    const xs =
      count === 1 ? [460] :
      count === 2 ? [240, 680] :
                    [220, 460, 700];
    def.nodes.forEach((n, i) => {
      positions[n.id] = { x: xs[i] || 460, y: sectorY };
    });
  }
  return positions;
}

function setTip(tip, text, active) {
  tip.textContent = text;
  if (active) tip.dataset.active = '1'; else delete tip.dataset.active;
}

function currentBaseTip() {
  const f = document.body.dataset.focus;
  return f
    ? `Filtering: ${f.toUpperCase()} department only — click the node again or empty space to clear`
    : BASE_TIP;
}

function initCytoscape(container, tip, brief) {
  if (typeof cytoscape !== 'function') {
    renderTextFallback(container, tip, brief);
    return;
  }

  const positions = presetPositions(brief);
  const elements = buildElements(brief).map((el) => {
    if (el.data && positions[el.data.id]) {
      return { ...el, position: { ...positions[el.data.id] } };
    }
    return el;
  });

  const cy = cytoscape({
    container,
    elements,
    style: cytoStyle(),
    layout: { name: 'preset', fit: true, padding: 32 },
    wheelSensitivity: 0.2,
    autoungrabify: true,
    boxSelectionEnabled: false,
    userZoomingEnabled: false,    // keep the layout fixed; scrolling page should not zoom
    userPanningEnabled: false,
  });

  // Cascade entry animation: source → feeds → depts → outputs → brief → handoffs → synergies.
  // Each stage fades its layer in; total duration ~1.6s.
  const stages = [
    ['node#source',         60],
    ['edge[type="feed"]',  260],
    ['node[type="dept"]',  440],
    ['edge[type="output"]',720],
    ['node#brief',         920],
    ['edge[type="handoff"]', 1180],
    ['edge[type="synergy"]', 1420],
  ];
  stages.forEach(([sel, delay]) => {
    setTimeout(() => {
      cy.elements(sel).animate({ style: { opacity: 1 } }, { duration: 320, easing: 'ease-out' });
    }, delay);
  });

  // dept-click → focus filter
  cy.on('tap', 'node[type="dept"]', (e) => {
    const dept = e.target.data('dept');
    const current = document.body.dataset.focus;
    if (current === dept) {
      delete document.body.dataset.focus;
      cy.elements().removeClass('dim beam');
      cy.elements(':selected').unselect();
    } else {
      document.body.dataset.focus = dept;
      // visually emphasize the focused dept in the graph
      cy.elements().addClass('dim');
      const focusNode = cy.getElementById(dept);
      focusNode.removeClass('dim').select();
      cy.edges(`[source = "${dept}"], [target = "${dept}"]`).removeClass('dim').addClass('beam');
      cy.getElementById('source').removeClass('dim');
      cy.getElementById('brief').removeClass('dim');
    }
    setTip(tip, currentBaseTip());
  });

  // tap background → clear focus
  cy.on('tap', (e) => {
    if (e.target === cy) {
      delete document.body.dataset.focus;
      cy.elements().removeClass('dim beam');
      cy.elements(':selected').unselect();
      setTip(tip, BASE_TIP);
    }
  });

  // edge hover → reveal full message in tooltip strip
  cy.on('mouseover', 'edge[full]', (e) => {
    const d = e.target.data();
    const arrow = d.type === 'synergy'
      ? `⚡ synergy (${d.source.toUpperCase()} ↔ ${d.target.toUpperCase()}): `
      : `↳ ${d.source.toUpperCase()} → ${d.target.toUpperCase()}: `;
    setTip(tip, arrow + d.full, true);
    container.style.cursor = 'help';
  });
  cy.on('mouseout', 'edge[full]', () => {
    setTip(tip, currentBaseTip());
    container.style.cursor = '';
  });

  // dept-node hover cursor
  cy.on('mouseover', 'node[type="dept"]', () => { container.style.cursor = 'pointer'; });
  cy.on('mouseout',  'node[type="dept"]', () => { container.style.cursor = ''; });

  // refit graph on container resize
  let rafId = null;
  const fit = () => { if (rafId) cancelAnimationFrame(rafId); rafId = requestAnimationFrame(() => cy.fit(32)); };
  window.addEventListener('resize', fit);

  // expose for replay mode (V3.2)
  container._cy = cy;
}

function renderTextFallback(container, tip, brief) {
  // CDN unreachable — keep the dashboard readable with a text view.
  container.classList.add('cascade-graph--fallback');
  setTip(tip, 'cytoscape CDN unreachable — showing text view');
  const rows = flowEl('div');
  (brief.handoffs || []).forEach((h) => {
    const a = deptKey(h.from_dept) || String(h.from_dept || '');
    const b = deptKey(h.to_dept) || String(h.to_dept || '');
    const row = flowEl('div', 'handoff');
    row.appendChild(flowEl('span', `hchip ${a}`, (a || '').toUpperCase()));
    row.appendChild(flowEl('span', 'harrow', '→'));
    row.appendChild(flowEl('span', `hchip ${b}`, (b || '').toUpperCase()));
    row.appendChild(flowEl('span', 'hmsg', String(h.message || '')));
    rows.appendChild(row);
  });
  container.appendChild(rows);
}

// ─── V3.2 replay mode ──────────────────────────────────────────────────────
// Plays back the cascade visually so a viewer can WATCH the company think.
// Schedule is synthesized from the CascadeBrief itself (PII → leak → depts →
// grounding → handoffs → synergies → assemble) with deterministic timing, so
// no events.jsonl is needed at deploy time. If a real backend trace ever lands
// alongside brief.json, future work can prefer it for authentic timestamps.

function _claimCount(brief, dept) {
  const m = {
    marketing: 'marketing_signal',
    gtm:       'account_brief',
    finance:   'market_signal',
    security:  'risk_profile',
  };
  const d = brief[m[dept]] || {};
  return Object.values(d).filter(Array.isArray).reduce((n, l) => n + l.length, 0);
}

function _pulseNode(cy, sel) {
  const els = cy.elements(sel);
  if (els.empty()) return;
  els.animate({ style: { 'border-width': 5 } }, { duration: 240, easing: 'ease-out' });
  setTimeout(() => els.animate({ style: { 'border-width': 2 } }, { duration: 280 }), 250);
}

function _pulseEdge(cy, sel) {
  const els = cy.elements(sel);
  if (els.empty()) return;
  els.animate({ style: { width: 4 } }, { duration: 220, easing: 'ease-out' });
  setTimeout(() => els.animate({ style: { width: 1.5 } }, { duration: 300 }), 240);
}

function _reveal(cy, sel) {
  const els = cy.elements(sel);
  if (!els.empty()) els.animate({ style: { opacity: 1 } }, { duration: 280, easing: 'ease-out' });
}

function _dimAll(cy) {
  cy.elements().style('opacity', 0.14);
}

function _restore(cy) {
  cy.elements().animate({ style: { opacity: 1 } }, { duration: 380, easing: 'ease-out' });
}

function replayCascade(brief, cy, tip, button) {
  if (!cy || !brief) return;
  if (button) { button.disabled = true; button.textContent = '▶ replaying…'; }
  document.body.classList.add('replaying');
  // clear any active focus filter before we begin
  delete document.body.dataset.focus;
  cy.elements().removeClass('dim beam');
  cy.elements(':selected').unselect();
  _dimAll(cy);
  _resetPips();

  const timers = [];
  const at = (delay, fn) => timers.push(setTimeout(fn, delay));
  let t = 200;

  // 1. PII redaction
  at(t, () => {
    setTip(tip, '🔒 PII redaction · scrubbing emails + phones from the bundle', true);
    _pulseNode(cy, 'node#source');
    _reveal(cy, 'node#source');
    _setPip('pii', 'active');
  });
  t += 850;
  at(t, () => {
    const n = (brief.guardrail_report && brief.guardrail_report.pii_redactions) || 0;
    setTip(tip, `✓ PII redaction done · ${n} redaction${n === 1 ? '' : 's'}`, true);
    _setPip('pii', 'done');
  });

  // 2. leak / scope
  t += 700;
  at(t, () => {
    setTip(tip, '🚫 leak/scope guard · withholding confidential-marked sources', true);
    _pulseNode(cy, 'node#source');
    _setPip('leak', 'active');
  });
  t += 750;
  at(t, () => {
    const flags = (brief.guardrail_report && brief.guardrail_report.leak_flags) || [];
    setTip(tip, `✓ scope clean · ${flags.length} source${flags.length === 1 ? '' : 's'} withheld`, true);
    _setPip('leak', 'done');
  });

  // 3. parallel dept fan-out (stagger reveals so each is readable)
  t += 700;
  ['marketing', 'gtm', 'finance', 'security'].forEach((d, i) => {
    at(t + i * 160, () => {
      setTip(tip, `▶ ${d.toUpperCase()} agent · reading shared Bright Data bundle`, true);
      _reveal(cy, `node#${d}`);
      _reveal(cy, `edge[source = "source"][target = "${d}"]`);
      _pulseEdge(cy, `edge[source = "source"][target = "${d}"]`);
      _setPip(d, 'active');
    });
  });

  // 4. dept-done emissions (staggered)
  t += 1700;
  ['marketing', 'gtm', 'finance', 'security'].forEach((d, i) => {
    at(t + i * 320, () => {
      const n = _claimCount(brief, d);
      setTip(tip, `✓ ${d.toUpperCase()} produced ${n} grounded claim${n === 1 ? '' : 's'}`, true);
      _pulseNode(cy, `node#${d}`);
      _setPip(d, 'done');
    });
  });

  // 5. grounding join
  t += 1700;
  at(t, () => {
    const dropped = (brief.guardrail_report && brief.guardrail_report.ungrounded_dropped) || [];
    setTip(tip,
      `🎯 grounding guard · dropped ${dropped.length} uncited claim${dropped.length === 1 ? '' : 's'}`,
      true);
    ['marketing', 'gtm', 'finance', 'security'].forEach((d) => _pulseNode(cy, `node#${d}`));
    _setPip('grounding', 'active');
  });
  t += 600;
  at(t, () => { _setPip('grounding', 'done'); });

  // 6. handoffs — reveal each handoff edge with its message in the tooltip
  t += 1200;
  (brief.handoffs || []).forEach((h, i) => {
    at(t + i * 1100, () => {
      const a = deptKey(h.from_dept);
      const b = deptKey(h.to_dept);
      if (!a || !b) return;
      const eSel = `edge[id ^= "h"][source = "${a}"][target = "${b}"]`;
      _reveal(cy, eSel);
      _pulseEdge(cy, eSel);
      setTip(tip, `↳ ${a.toUpperCase()} → ${b.toUpperCase()}: ${h.message}`, true);
    });
  });
  t += (brief.handoffs || []).length * 1100;

  // 7. synergies — reveal dashed connector + reveal panels for contributing depts
  t += 600;
  (brief.synergy_signals || []).forEach((s, i) => {
    at(t + i * 1300, () => {
      _reveal(cy, 'edge[type = "synergy"]');
      _pulseEdge(cy, 'edge[type = "synergy"]');
      setTip(tip, `⚡ synergy (${(s.contributing_depts || []).join(' + ')}): ${s.text}`, true);
    });
  });
  t += (brief.synergy_signals || []).length * 1300;

  // 8. strategy — synthesize the plan (V6). Pulse brief node + emphasize plays.
  t += 700;
  at(t, () => {
    setTip(tip, '★ strategy · Chief of Staff synthesizing the plan…', true);
    _reveal(cy, 'edge[type = "output"]');
    _setPip('strategy', 'active');
  });
  t += 900;
  at(t, () => {
    const plan = brief.strategic_plan;
    if (plan) {
      const n = (plan.recommended_plays || []).length;
      setTip(tip,
        `✓ plan ready · ${n} play${n === 1 ? '' : 's'} · ${plan.urgency || ''} · ${plan.icp_fit || ''} fit`,
        true);
    } else {
      setTip(tip, '✓ assembly underway…', true);
    }
    _pulseNode(cy, 'node#brief');
    _setPip('strategy', 'done');
  });

  // 9. assemble
  t += 700;
  at(t, () => {
    setTip(tip, '★ CascadeBrief assembled', true);
    _reveal(cy, 'node#brief');
    _pulseNode(cy, 'node#brief');
  });

  // 9. restore — fade panels back, clear replaying state
  t += 1500;
  at(t, () => {
    _restore(cy);
    document.body.classList.remove('replaying');
    setTip(tip, BASE_TIP);
    if (button) { button.disabled = false; button.textContent = '▶ replay cascade'; }
  });

  // store timers on body so a second click can cancel (defensive)
  if (document.body._cascadeTimers) {
    document.body._cascadeTimers.forEach((id) => clearTimeout(id));
  }
  document.body._cascadeTimers = timers;
}

// ─── live cascade — SSE-driven animation from the backend ─────────────────
// POSTs to /api/run on the local Flask backend (server.py). Each Server-Sent
// Event maps to a cytoscape animation step, so the dashboard reflects the real
// LangGraph cascade as it fires — not just a scripted replay.

// V7.28 — backend base + auth key live on window so app.js can set them
// after fetching frontend/api.json + reading ?key=<token> URL param.
// Empty backend_base = same-origin (local `python server.py` on :5001).
// Filled = Cloud Run URL (cross-origin from Vercel-hosted frontend).
const RUN_ENDPOINT = '/api/run';
const STATUS_ENDPOINT = '/api/status';

function _apiUrl(path) {
  const base = (window.TAKI_BACKEND_BASE || '').replace(/\/$/, '');
  const key = window.TAKI_AUTH_KEY || '';
  let url = base + path;
  if (key) url += (url.includes('?') ? '&' : '?') + 'key=' + encodeURIComponent(key);
  return url;
}

async function _streamSSE(payload, onEvent, onError) {
  let res;
  try {
    res = await fetch(_apiUrl(RUN_ENDPOINT), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (e) {
    onError({
      error: 'backend unreachable — start it with `python server.py` in another terminal',
      cause: String(e && e.message || e),
    });
    return;
  }
  if (!res.ok) {
    let body = { error: `HTTP ${res.status} ${res.statusText}` };
    try { body = await res.json(); } catch (_e) {}
    onError(body);
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    let chunk;
    try {
      chunk = await reader.read();
    } catch (e) {
      onError({ error: 'stream broken', cause: String(e) });
      return;
    }
    if (chunk.done) break;
    buf += decoder.decode(chunk.value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const dataLine = block.split('\n').find((l) => l.startsWith('data: '));
      if (!dataLine) continue;
      try {
        onEvent(JSON.parse(dataLine.slice(6)));
      } catch (_e) { /* swallow malformed line */ }
    }
  }
}

function _handleLiveEvent(ev, cy, tip) {
  switch (ev.phase) {
    case 'audit':
      if (ev.status === 'fixed') {
        setTip(tip, `🔧 audit fixed: ${ev.original} → ${ev.normalized}`, true);
      } else if (ev.status === 'dropped') {
        setTip(tip, `✗ audit dropped: ${ev.original} — ${ev.reason || 'unknown'}`, true);
      } else if (ev.status === 'summary') {
        const parts = [];
        if (ev.ok) parts.push(`${ev.ok} ok`);
        if (ev.fixed) parts.push(`${ev.fixed} fixed`);
        if (ev.dropped) parts.push(`${ev.dropped} dropped`);
        setTip(tip, `🔍 URL audit · ${parts.join(' · ') || 'no URLs'}`, true);
      } else if (ev.status === 'ok') {
        // no-op — the summary line covers it; keep individual 'ok' silent
      }
      break;
    case 'serp':
      // V7.22 — Google SERP discovery streams BEFORE fetch. Tip-only updates;
      // no pip — the pip strip starts at 'pii' phase below.
      // V7.26 — also handles tier_summary + tier_dropped events
      if (ev.status === 'serp_start') {
        setTip(tip, `🔎 SERP discovery · ${ev.query}`, true);
      } else if (ev.status === 'serp_done') {
        const n = ev.found || 0;
        setTip(tip, `🔎 SERP · "${ev.query}" → ${n} external source${n === 1 ? '' : 's'}`, true);
      } else if (ev.status === 'serp_error') {
        setTip(tip, `⚠ SERP query failed: ${ev.query} (${ev.error || 'unknown'})`, true);
      } else if (ev.status === 'summary') {
        const n = ev.discovered || 0;
        const added = ev.added_to_bundle != null ? ` · ${ev.added_to_bundle} scraped into bundle` : '';
        const ind = ev.industry ? ` · industry: ${ev.industry}` : '';
        const reg = ev.region ? ` · region: ${ev.region}` : '';
        setTip(tip, `🔎 SERP discovery done · ${n} external URL${n === 1 ? '' : 's'} found${added}${ind}${reg}`, true);
      } else if (ev.status === 'tier_summary') {
        const t = ev.tiers || {};
        const parts = Object.keys(t).sort().map((k) => `${k}=${t[k]}`);
        setTip(tip, `🔎 SERP tiers · ${parts.join(' · ')} · kept ${ev.kept || 0}`, true);
      }
      break;
    case 'fetch':
      if (ev.status === 'url_error') {
        setTip(tip, `✗ scrape failed: ${ev.url} — ${ev.error || 'unknown'}`, true);
        break;
      }
      if (ev.status === 'discovered') {
        setTip(tip, `🔎 found ${ev.concept || 'sub-page'}: ${ev.url}`, true);
        break;
      }
      if (ev.status === 'start') {
        let msg;
        if (ev.mode === 'self') {
          const c = ev.competitor_urls || 0;
          msg = `🌐 Bright Data · scraping ${ev.self_urls || 1} of your page${ev.self_urls === 1 ? '' : 's'} + ${c} competitor URL${c === 1 ? '' : 's'} for ${ev.target}…`;
        } else if (ev.mode === 'live') {
          msg = `🌐 Bright Data · fetching ${ev.urls || ''} source${ev.urls === 1 ? '' : 's'} for ${ev.target || 'target'}…`;
        } else {
          msg = '📦 loading shared bundle (demo fixture)…';
        }
        setTip(tip, msg, true);
        _reveal(cy, 'node#source');
        _pulseNode(cy, 'node#source');
      } else {
        const c = (ev.competitors || []).length;
        const extra = c ? ` (competitors: ${(ev.competitors || []).join(', ')})` : '';
        setTip(tip,
          `✓ ${ev.sources || 0} source${ev.sources === 1 ? '' : 's'} ready in shared bundle${extra}`,
          true);
      }
      break;
    case 'pii':
      if (ev.status === 'start') {
        setTip(tip, '🔒 PII redaction · scrubbing emails + phones', true);
        _pulseNode(cy, 'node#source');
        _setPip('pii', 'active');
      } else {
        const n = ev.redactions || 0;
        setTip(tip, `✓ ${n} PII redaction${n === 1 ? '' : 's'}`, true);
        _setPip('pii', 'done');
      }
      break;
    case 'leak':
      if (ev.status === 'start') {
        setTip(tip, '🚫 leak/scope guard · withholding confidential-marked sources', true);
        _pulseNode(cy, 'node#source');
        _setPip('leak', 'active');
      } else {
        const n = (ev.flags || []).length;
        setTip(tip, `✓ ${n} source${n === 1 ? '' : 's'} withheld`, true);
        _setPip('leak', 'done');
      }
      break;
    case 'dept': {
      const d = ev.dept;
      if (!d) break;
      if (ev.status === 'start') {
        setTip(tip, `▶ ${d.toUpperCase()} agent · reading shared bundle`, true);
        _reveal(cy, `node#${d}`);
        _reveal(cy, `edge[source = "source"][target = "${d}"]`);
        _pulseEdge(cy, `edge[source = "source"][target = "${d}"]`);
        _setPip(d, 'active');
      } else {
        const n = ev.claims || 0;
        setTip(tip, `✓ ${d.toUpperCase()} produced ${n} claim${n === 1 ? '' : 's'}`, true);
        _pulseNode(cy, `node#${d}`);
        _setPip(d, 'done');
      }
      break;
    }
    case 'grounding':
      if (ev.status === 'start') {
        setTip(tip, '🎯 grounding guard · checking every citation against the bundle', true);
        _setPip('grounding', 'active');
      } else {
        const n = ev.dropped || 0;
        setTip(tip, `🎯 grounding done · ${n} ungrounded claim${n === 1 ? '' : 's'} dropped`, true);
        ['gtm', 'finance', 'security'].forEach((d) => _pulseNode(cy, `node#${d}`));
        _setPip('grounding', 'done');
      }
      break;
    case 'handoff': {
      const a = deptKey(ev.from);
      const b = deptKey(ev.to);
      if (!a || !b) break;
      const sel = `edge[id ^= "h"][source = "${a}"][target = "${b}"]`;
      _reveal(cy, sel);
      _pulseEdge(cy, sel);
      setTip(tip, `↳ ${a.toUpperCase()} → ${b.toUpperCase()}: ${ev.message || ''}`, true);
      break;
    }
    case 'synergy':
      _reveal(cy, 'edge[type = "synergy"]');
      _pulseEdge(cy, 'edge[type = "synergy"]');
      setTip(tip, `⚡ synergy (${(ev.depts || []).join(' + ')}): ${ev.text || ''}`, true);
      break;
    case 'contradictions':
      // V7.23 — runs in parallel w/ strategy; no pip (the pip strip stops at strategy)
      if (ev.status === 'start') {
        setTip(tip, '⚖ contradictions · scanning claims for opposing-source pairs…', true);
      } else if (ev.status === 'done') {
        const n = ev.found || 0;
        setTip(tip,
          n ? `⚖ contradictions · ${n} opposing-source pair${n === 1 ? '' : 's'} found`
            : '⚖ contradictions · no opposing-source pairs surfaced',
          true);
      } else if (ev.status === 'error') {
        setTip(tip, `⚠ contradictions failed: ${ev.error || 'unknown'} (brief still assembled)`, true);
      }
      break;
    case 'porter':
      // V7.24 — parallel framework agent; no pip
      if (ev.status === 'start') {
        setTip(tip, "⌬ Porter's Five Forces · scoring competitive pressure…", true);
      } else if (ev.status === 'done') {
        setTip(tip, `⌬ Porter · rivalry=${ev.rivalry}/5 · new=${ev.new_entrants}/5 · sup=${ev.supplier_power}/5 · buy=${ev.buyer_power}/5 · sub=${ev.substitutes}/5`, true);
      } else if (ev.status === 'error') {
        setTip(tip, `⚠ Porter failed: ${ev.error || 'unknown'} (brief still assembled)`, true);
      }
      break;
    case 'swot':
      // V7.24 — parallel framework agent; no pip
      if (ev.status === 'start') {
        setTip(tip, '◰ SWOT · classifying strengths/weaknesses/opportunities/threats…', true);
      } else if (ev.status === 'done') {
        setTip(tip, `◰ SWOT · ${ev.s||0}S / ${ev.w||0}W / ${ev.o||0}O / ${ev.t_||0}T`, true);
      } else if (ev.status === 'error') {
        setTip(tip, `⚠ SWOT failed: ${ev.error || 'unknown'} (brief still assembled)`, true);
      }
      break;
    case 'pestle':
      // V7.26 — parallel macro-env agent; no pip
      if (ev.status === 'start') {
        setTip(tip, '🌍 PESTLE · scoring macro forces (political/economic/social/tech/legal/env)…', true);
      } else if (ev.status === 'done') {
        setTip(tip, `🌍 PESTLE · P=${ev.political}/5 · E=${ev.economic}/5 · S=${ev.social}/5 · T=${ev.technological}/5 · L=${ev.legal}/5 · Env=${ev.environmental}/5`, true);
      } else if (ev.status === 'error') {
        setTip(tip, `⚠ PESTLE failed: ${ev.error || 'unknown'} (brief still assembled)`, true);
      }
      break;
    case 'strategy':
      if (ev.status === 'start') {
        setTip(tip, '★ strategy · Chief of Staff synthesizing the plan…', true);
        _reveal(cy, 'edge[type = "output"]');
        _setPip('strategy', 'active');
      } else if (ev.status === 'done') {
        const n = ev.plays || 0;
        setTip(tip,
          `✓ plan ready · ${n} play${n === 1 ? '' : 's'} · ${ev.urgency || ''} · ${ev.icp_fit || ''} fit`,
          true);
        _pulseNode(cy, 'node#brief');
        _setPip('strategy', 'done');
      } else if (ev.status === 'error') {
        setTip(tip, `✗ strategy failed: ${ev.error || 'unknown'} (brief still assembled)`, true);
        _setPip('strategy', 'done');
      }
      break;
    case 'assemble':
      _reveal(cy, 'edge[type = "output"]');
      _reveal(cy, 'node#brief');
      _pulseNode(cy, 'node#brief');
      setTip(tip, '★ CascadeBrief assembled', true);
      break;
    case 'complete':
      setTip(tip,
        `✓ live cascade done · target: ${ev.target || '?'} · ${ev.dropped || 0} ungrounded dropped`,
        true);
      break;
    case 'error':
      setTip(tip, `✗ ${ev.error || 'unknown error'}`, true);
      break;
  }
}

function _restoreFromLive(cy, tip, buttons) {
  _restore(cy);
  document.body.classList.remove('replaying');
  Object.values(buttons || {}).forEach((b) => { if (b) b.disabled = false; });
  setTip(tip, BASE_TIP);
}

function runLiveCascade(payload, ctx) {
  const { cy, tip, buttons, labelWhenRunning } = ctx;
  if (!cy) return;
  // Pre-flight: clear any focus, dim graph + page for the animation
  Object.values(buttons || {}).forEach((b) => { if (b) b.disabled = true; });
  if (buttons && buttons.primary) buttons.primary.textContent = labelWhenRunning || '⏳ running…';
  document.body.classList.add('replaying');
  delete document.body.dataset.focus;
  cy.elements().removeClass('dim beam');
  cy.elements(':selected').unselect();
  _dimAll(cy);
  _resetPips();
  setTip(tip, '⏳ contacting backend…', true);

  let sawComplete = false;
  let sawError = false;

  _streamSSE(
    payload,
    (ev) => {
      if (ev.phase === 'complete') sawComplete = true;
      if (ev.phase === 'error') sawError = true;
      _handleLiveEvent(ev, cy, tip);
    },
    (err) => {
      sawError = true;
      const detail = err.blockers ? `${err.error} (${err.blockers.join('; ')})` : err.error;
      setTip(tip, `✗ ${detail || 'request failed'}`, true);
    },
  ).then(() => {
    // Restore button labels regardless of outcome
    if (buttons && buttons.primary) {
      buttons.primary.textContent = buttons.primary.dataset.idleLabel || buttons.primary.textContent;
    }
    setTimeout(() => _restoreFromLive(cy, tip, buttons), sawError ? 600 : 1200);

    // On a successful run the backend wrote a fresh frontend/brief.json — pull
    // it in and re-render the dashboard so the panels reflect new data.
    if (sawComplete && !sawError && typeof render === 'function') {
      fetch('brief.json', { cache: 'no-store' })
        .then((r) => r.ok ? r.json() : null)
        .then((b) => { if (b) setTimeout(() => render(b), 1400); })
        .catch(() => {});
    }
  });
}

// ─── toolbar UI ───────────────────────────────────────────────────────────

function _buildLiveForm() {
  // small popover form for ⚡ live run: target + URL list. Hidden by default.
  const form = flowEl('form', 'cascade-liveform');
  form.hidden = true;
  form.setAttribute('aria-label', 'Live cascade run inputs');

  const targetLabel = flowEl('label', 'cascade-livefield');
  targetLabel.appendChild(flowEl('span', 'cascade-livelabel', 'target'));
  const targetInput = flowEl('input', 'cascade-liveinput');
  targetInput.name = 'target';
  targetInput.type = 'text';
  targetInput.placeholder = 'Stripe';
  targetInput.required = true;
  targetLabel.appendChild(targetInput);

  const urlsLabel = flowEl('label', 'cascade-livefield');
  urlsLabel.appendChild(flowEl('span', 'cascade-livelabel', 'urls'));
  const urlsArea = flowEl('textarea', 'cascade-liveinput cascade-liveurls');
  urlsArea.name = 'urls';
  urlsArea.rows = 3;
  urlsArea.placeholder =
    'one per line\nhttps://stripe.com/pricing:pricing\nhttps://stripe.com/jobs:jobs';
  urlsLabel.appendChild(urlsArea);

  const actions = flowEl('div', 'cascade-liveactions');
  const cancel = flowEl('button', 'cascade-liveclose', 'cancel');
  cancel.type = 'button';
  const submit = flowEl('button', 'cascade-livesubmit', '⚡ run');
  submit.type = 'submit';
  actions.appendChild(cancel);
  actions.appendChild(submit);

  form.appendChild(targetLabel);
  form.appendChild(urlsLabel);
  form.appendChild(actions);

  return { form, targetInput, urlsArea, cancel, submit };
}

function _wireToolbar(toolbar, container, tip) {
  // Toolbar children:
  //   ▶ replay cascade      (always works — animates cached brief.json)
  //   ▶ live demo          (real backend, fixture cascade, no keys)
  //   ⚡ live run ▾        (real backend, Bright Data + LLM; popover for target/urls)
  const replayBtn  = flowEl('button', 'cascade-replay',   '▶ replay cascade');
  const demoBtn    = flowEl('button', 'cascade-livedemo', '▶ live demo');
  const liveBtn    = flowEl('button', 'cascade-liverun',  '⚡ live run ▾');
  [replayBtn, demoBtn, liveBtn].forEach((b) => { b.type = 'button'; });
  replayBtn.title = 'Animate the cached cascade — works offline';
  demoBtn.title   = 'Run the cascade live against the fixture bundle (no keys needed)';
  liveBtn.title   = 'Run the cascade live against a real target via Bright Data (.env keys required)';
  replayBtn.dataset.idleLabel = replayBtn.textContent;
  demoBtn.dataset.idleLabel   = demoBtn.textContent;
  liveBtn.dataset.idleLabel   = liveBtn.textContent;

  const liveWrap = flowEl('div', 'cascade-liverun-wrap');
  liveWrap.appendChild(liveBtn);

  const { form, targetInput, urlsArea, cancel, submit } = _buildLiveForm();
  liveWrap.appendChild(form);

  toolbar.appendChild(replayBtn);
  toolbar.appendChild(demoBtn);
  toolbar.appendChild(liveWrap);

  const buttons = { primary: null, replay: replayBtn, demo: demoBtn, live: liveBtn };

  const getCy = () => container._cy;

  replayBtn.addEventListener('click', () => {
    const cy = getCy(); if (!cy) return;
    replayCascade(container._brief, cy, tip, replayBtn);
  });

  demoBtn.addEventListener('click', () => {
    const cy = getCy(); if (!cy) return;
    runLiveCascade({ mode: 'demo' }, {
      cy, tip,
      buttons: { ...buttons, primary: demoBtn },
      labelWhenRunning: '⏳ live demo running…',
    });
  });

  liveBtn.addEventListener('click', () => {
    form.hidden = !form.hidden;
    if (!form.hidden) setTimeout(() => targetInput.focus(), 30);
  });
  cancel.addEventListener('click', () => { form.hidden = true; });
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const target = (targetInput.value || '').trim();
    const urls = (urlsArea.value || '')
      .split(/[\n,]/)
      .map((u) => u.trim())
      .filter(Boolean);
    if (!target || !urls.length) {
      setTip(tip, '✗ target and at least one URL required', true);
      return;
    }
    form.hidden = true;
    const cy = getCy(); if (!cy) return;
    runLiveCascade({ mode: 'live', target, urls }, {
      cy, tip,
      buttons: { ...buttons, primary: liveBtn },
      labelWhenRunning: '⏳ live run…',
    });
  });

  // Reflect backend availability — if /api/status is unreachable, mark
  // live buttons as such; replay still works either way.
  fetch(_apiUrl(STATUS_ENDPOINT), { cache: 'no-store' })
    .then((r) => r.ok ? r.json() : null)
    .then((s) => {
      if (!s) {
        demoBtn.classList.add('backend-down');
        liveBtn.classList.add('backend-down');
        demoBtn.title = 'Backend not running — start it with: python server.py';
        liveBtn.title = demoBtn.title;
      } else if (!(s.modes && s.modes.live)) {
        liveBtn.classList.add('backend-down');
        liveBtn.title = 'Live mode blocked: ' + (s.live_blockers || []).join('; ');
      }
    })
    .catch(() => {
      demoBtn.classList.add('backend-down');
      liveBtn.classList.add('backend-down');
      demoBtn.title = 'Backend not running — start it with: python server.py';
      liveBtn.title = demoBtn.title;
    });
}

function renderCascadeFlow(brief) {
  // Back-compat: legacy callers passed handoffs only; new callers pass the brief.
  const b = Array.isArray(brief) ? { handoffs: brief } : (brief || {});

  const wrap = flowEl('div', 'flow');
  wrap.appendChild(flowEl('div', 'section-title', 'Cascade flow — how the company thought'));

  const toolbar = flowEl('div', 'cascade-toolbar');
  wrap.appendChild(toolbar);

  // V7.14 — visible phase pips strip (sits between toolbar and graph)
  wrap.appendChild(_buildPipsStrip());

  const container = flowEl('div', 'cascade-graph');
  container.id = 'cascade-graph';
  container._brief = b;
  wrap.appendChild(container);

  const tip = flowEl('div', 'cascade-tip', BASE_TIP);
  wrap.appendChild(tip);

  // Wait one frame so the container is laid out before cytoscape measures it.
  requestAnimationFrame(() => {
    initCytoscape(container, tip, b);
    _wireToolbar(toolbar, container, tip);
  });
  return wrap;
}
