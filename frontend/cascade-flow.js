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

const DEPT_COLOR    = { gtm: '#5ad6e8', finance: '#98e08a', security: '#f0a849' };
const SYNERGY_COLOR = '#c8a8ff';
const SHU           = '#e84a3a';
const PAPER_DIM     = '#b8b2a4';
const INK           = '#0d0e10';
const BASE_TIP      = 'Click a department to filter · hover edges to read the cross-talk';

function deptKey(name) {
  const n = String(name || '').toLowerCase();
  if (n.includes('gtm') || n.includes('revenue')) return 'gtm';
  if (n.includes('finance') || n.includes('market')) return 'finance';
  if (n.includes('security') || n.includes('compliance') || n.includes('risk')) return 'security';
  return null;
}

function clip(s, n) {
  s = String(s || '');
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

function flowEl(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

function buildElements(brief) {
  const els = [
    { data: { id: 'source',   label: 'Bright Data',   type: 'source', color: PAPER_DIM } },
    { data: { id: 'gtm',      label: 'GTM',           type: 'dept', dept: 'gtm',      color: DEPT_COLOR.gtm } },
    { data: { id: 'finance',  label: 'Finance',       type: 'dept', dept: 'finance',  color: DEPT_COLOR.finance } },
    { data: { id: 'security', label: 'Security',      type: 'dept', dept: 'security', color: DEPT_COLOR.security } },
    { data: { id: 'brief',    label: 'Cascade Brief', type: 'brief',  color: SHU } },
    { data: { id: 'e_sg', source: 'source',   target: 'gtm',      type: 'feed',   color: DEPT_COLOR.gtm } },
    { data: { id: 'e_sf', source: 'source',   target: 'finance',  type: 'feed',   color: DEPT_COLOR.finance } },
    { data: { id: 'e_ss', source: 'source',   target: 'security', type: 'feed',   color: DEPT_COLOR.security } },
    { data: { id: 'e_gb', source: 'gtm',      target: 'brief',    type: 'output', color: DEPT_COLOR.gtm } },
    { data: { id: 'e_fb', source: 'finance',  target: 'brief',    type: 'output', color: DEPT_COLOR.finance } },
    { data: { id: 'e_sb', source: 'security', target: 'brief',    type: 'output', color: DEPT_COLOR.security } },
  ];

  (brief.handoffs || []).forEach((h, i) => {
    const a = deptKey(h.from_dept);
    const b = deptKey(h.to_dept);
    if (!a || !b || a === b) return;
    els.push({
      data: {
        id: `h${i}`, source: a, target: b, type: 'handoff',
        color: DEPT_COLOR[a], label: clip(h.message, 32),
        full: String(h.message || ''),
      },
    });
  });

  const seenPairs = new Set();
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
          color: SYNERGY_COLOR, label: 'synergy',
          full: String(s.text || ''),
        },
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

    {
      selector: 'edge',
      style: {
        width: 1.5,
        'line-color': 'data(color)',
        'target-arrow-color': 'data(color)',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.9,
        'curve-style': 'bezier',
        opacity: 0,
        'transition-property': 'opacity, width',
        'transition-duration': '0.25s',
      },
    },
    {
      selector: 'edge[type="handoff"]',
      style: {
        'curve-style': 'unbundled-bezier',
        'control-point-distances': [-54],
        'control-point-weights': [0.5],
        label: 'data(label)',
        'font-family': 'JetBrains Mono, monospace',
        'font-size': 9,
        color: PAPER_DIM,
        'text-rotation': 'autorotate',
        'text-background-color': INK,
        'text-background-opacity': 0.95,
        'text-background-padding': 3,
        'text-margin-y': -2,
      },
    },
    {
      selector: 'edge[type="synergy"]',
      style: {
        'curve-style': 'unbundled-bezier',
        'control-point-distances': [62],
        'control-point-weights': [0.5],
        'line-style': 'dashed',
        'line-dash-pattern': [6, 4],
        label: 'data(label)',
        'font-family': 'JetBrains Mono, monospace',
        'font-size': 9,
        color: SYNERGY_COLOR,
        'text-rotation': 'autorotate',
        'text-background-color': INK,
        'text-background-opacity': 0.95,
        'text-background-padding': 3,
        'text-margin-y': 2,
      },
    },
    { selector: '.dim',      style: { opacity: 0.15 } },
    { selector: '.beam',     style: { width: 3 } },
  ];
}

// Preset layout — keeps the architecture story readable: source on top,
// depts in a row, brief at the bottom. cy.fit() scales to container width.
function presetPositions() {
  return {
    source:   { x: 380, y: 50 },
    gtm:      { x: 120, y: 210 },
    finance:  { x: 380, y: 210 },
    security: { x: 640, y: 210 },
    brief:    { x: 380, y: 380 },
  };
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

  const positions = presetPositions();
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
  const m = { gtm: 'account_brief', finance: 'market_signal', security: 'risk_profile' };
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

  const timers = [];
  const at = (delay, fn) => timers.push(setTimeout(fn, delay));
  let t = 200;

  // 1. PII redaction
  at(t, () => {
    setTip(tip, '🔒 PII redaction · scrubbing emails + phones from the bundle', true);
    _pulseNode(cy, 'node#source');
    _reveal(cy, 'node#source');
  });
  t += 850;
  at(t, () => {
    const n = (brief.guardrail_report && brief.guardrail_report.pii_redactions) || 0;
    setTip(tip, `✓ PII redaction done · ${n} redaction${n === 1 ? '' : 's'}`, true);
  });

  // 2. leak / scope
  t += 700;
  at(t, () => {
    setTip(tip, '🚫 leak/scope guard · withholding confidential-marked sources', true);
    _pulseNode(cy, 'node#source');
  });
  t += 750;
  at(t, () => {
    const flags = (brief.guardrail_report && brief.guardrail_report.leak_flags) || [];
    setTip(tip, `✓ scope clean · ${flags.length} source${flags.length === 1 ? '' : 's'} withheld`, true);
  });

  // 3. parallel dept fan-out (stagger reveals so each is readable)
  t += 700;
  ['gtm', 'finance', 'security'].forEach((d, i) => {
    at(t + i * 180, () => {
      setTip(tip, `▶ ${d.toUpperCase()} agent · reading shared Bright Data bundle`, true);
      _reveal(cy, `node#${d}`);
      _reveal(cy, `edge[source = "source"][target = "${d}"]`);
      _pulseEdge(cy, `edge[source = "source"][target = "${d}"]`);
    });
  });

  // 4. dept-done emissions (staggered)
  t += 1600;
  ['gtm', 'finance', 'security'].forEach((d, i) => {
    at(t + i * 360, () => {
      const n = _claimCount(brief, d);
      setTip(tip, `✓ ${d.toUpperCase()} produced ${n} grounded claim${n === 1 ? '' : 's'}`, true);
      _pulseNode(cy, `node#${d}`);
    });
  });

  // 5. grounding join
  t += 1500;
  at(t, () => {
    const dropped = (brief.guardrail_report && brief.guardrail_report.ungrounded_dropped) || [];
    setTip(tip,
      `🎯 grounding guard · dropped ${dropped.length} uncited claim${dropped.length === 1 ? '' : 's'}`,
      true);
    ['gtm', 'finance', 'security'].forEach((d) => _pulseNode(cy, `node#${d}`));
  });

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

  // 8. assemble
  t += 600;
  at(t, () => {
    setTip(tip, '★ CascadeBrief assembled', true);
    _reveal(cy, 'edge[type = "output"]');
    _reveal(cy, 'node#brief');
    _pulseNode(cy, 'node#brief');
  });

  // 9. restore — fade panels back, clear replaying state
  t += 1400;
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

function renderCascadeFlow(brief) {
  // Back-compat: legacy callers passed handoffs only; new callers pass the brief.
  const b = Array.isArray(brief) ? { handoffs: brief } : (brief || {});

  const wrap = flowEl('div', 'flow');
  wrap.appendChild(flowEl('div', 'section-title', 'Cascade flow — how the company thought'));

  // toolbar — replay button, right-aligned
  const toolbar = flowEl('div', 'cascade-toolbar');
  const replayBtn = flowEl('button', 'cascade-replay', '▶ replay cascade');
  replayBtn.type = 'button';
  replayBtn.title = 'Watch the cascade unfold step by step';
  toolbar.appendChild(replayBtn);
  wrap.appendChild(toolbar);

  const container = flowEl('div', 'cascade-graph');
  container.id = 'cascade-graph';
  wrap.appendChild(container);

  const tip = flowEl('div', 'cascade-tip', BASE_TIP);
  wrap.appendChild(tip);

  // Wait one frame so the container is laid out before cytoscape measures it.
  requestAnimationFrame(() => {
    initCytoscape(container, tip, b);
    replayBtn.addEventListener('click', () => {
      const cy = container._cy;
      if (cy) replayCascade(b, cy, tip, replayBtn);
    });
  });
  return wrap;
}
