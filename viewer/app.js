const files = {
  state: "runtime_state.json",
  capsules: "capsule_log.json",
  invariants: "invariant_report.json",
  conflicts: "conflict_registry.json",
  interventions: "intervention_log.json",
};

const colors = {
  active: "#177b72",
  refused: "#9357a8",
  quarantined: "#c5543d",
  expired: "#7d8790",
  agent: "#2d5f9a",
  memory: "#b8801f",
};

const els = {
  dataPath: document.querySelector("#dataPath"),
  reloadButton: document.querySelector("#reloadButton"),
  statusStrip: document.querySelector("#statusStrip"),
  roundLens: document.querySelector("#roundLens"),
  roundReadout: document.querySelector("#roundReadout"),
  playRounds: document.querySelector("#playRounds"),
  flowGraph: document.querySelector("#flowGraph"),
  graphLegend: document.querySelector("#graphLegend"),
  capsuleSearch: document.querySelector("#capsuleSearch"),
  focusAgent: document.querySelector("#focusAgent"),
  pulseToggle: document.querySelector("#pulseToggle"),
  detailPane: document.querySelector("#detailPane"),
  weatherGrid: document.querySelector("#weatherGrid"),
  invariantRail: document.querySelector("#invariantRail"),
  resonanceMatrix: document.querySelector("#resonanceMatrix"),
  agentSelect: document.querySelector("#agentSelect"),
  contextGraphSummary: document.querySelector("#contextGraphSummary"),
  timeline: document.querySelector("#timeline"),
  conflictList: document.querySelector("#conflictList"),
  statusButtons: [...document.querySelectorAll("[data-status]")],
};

let runtimeData = null;
let statusFilter = "all";
let focusAgent = "all";
let searchQuery = "";
let pulseEnabled = true;
let roundLimit = 1;
let playbackTimer = null;

function getInitialPath() {
  const params = new URLSearchParams(window.location.search);
  return params.get("out") || "../runtime_out";
}

function joinPath(base, leaf) {
  return `${base.replace(/\/$/, "")}/${leaf}`;
}

async function loadJson(base, leaf) {
  const res = await fetch(joinPath(base, leaf), { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`${leaf}: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

async function loadRuntime() {
  const base = els.dataPath.value.trim() || "../runtime_out";
  els.statusStrip.innerHTML = `<div class="loading">Loading ${escapeHtml(base)}...</div>`;
  try {
    let activeBase = base;
    let loaded;
    try {
      loaded = await Promise.all(Object.values(files).map((leaf) => loadJson(activeBase, leaf)));
    } catch (error) {
      if (base !== "../runtime_out") throw error;
      activeBase = "../examples/sample_runtime_out";
      loaded = await Promise.all(Object.values(files).map((leaf) => loadJson(activeBase, leaf)));
      els.dataPath.value = activeBase;
    }
    const [state, capsules, invariants, conflicts, interventions] = loaded;
    runtimeData = { state, capsules, invariants, conflicts, interventions };
    runtimeData.roundIndex = buildRoundIndex(runtimeData);
    roundLimit = runtimeData.state.rounds.length || 1;
    renderAll();
  } catch (error) {
    els.statusStrip.innerHTML = `<div class="error">Could not load runtime output. ${escapeHtml(error.message)}</div>`;
  }
}

function renderAll() {
  renderTemporalLens();
  renderStatusStrip();
  renderGraphLegend();
  renderGraphTools();
  renderFlowGraph();
  renderInvariantRail();
  renderWeather();
  renderResonanceMatrix();
  renderContextSelector();
  renderTimeline();
  renderConflicts();
  renderDetail({
    kind: "runtime",
    title: "Runtime loaded",
    body: "Select a node or route in the graph to inspect how meaning moved, degraded, or got preserved.",
    raw: {
      agents: runtimeData.state.runtime.agents.map((agent) => agent.id),
      overall_ok: runtimeData.invariants.overall_ok,
    },
  });
}

function renderObservable() {
  renderStatusStrip();
  renderGraphLegend();
  renderFlowGraph();
  renderInvariantRail();
  renderWeather();
  renderResonanceMatrix();
  renderTimeline();
  renderConflicts();
}

function renderTemporalLens() {
  const maxRound = runtimeData.state.rounds.length || 1;
  els.roundLens.min = "1";
  els.roundLens.max = String(maxRound);
  els.roundLens.value = String(roundLimit);
  const round = runtimeData.state.rounds[roundLimit - 1];
  els.roundReadout.innerHTML = `
    <strong>Round ${escapeHtml(roundLimit)} / ${escapeHtml(maxRound)}</strong>
    <span>${escapeHtml(round?.query || "No query")}</span>
  `;
}

function renderGraphTools() {
  const agents = runtimeData.state.runtime.agents;
  els.focusAgent.innerHTML = [
    `<option value="all">all agents</option>`,
    ...agents.map((agent) => `<option value="${escapeHtml(agent.id)}">${escapeHtml(agent.id)}</option>`),
  ].join("");
  els.focusAgent.value = focusAgent;
  els.capsuleSearch.value = searchQuery;
  els.pulseToggle.checked = pulseEnabled;
}

function capsuleCounts() {
  const counts = { active: 0, refused: 0, quarantined: 0, expired: 0 };
  for (const capsule of capsulesThroughRound()) {
    counts[capsule.status] = (counts[capsule.status] || 0) + 1;
  }
  return counts;
}

function renderStatusStrip() {
  const counts = capsuleCounts();
  const rounds = roundLimit;
  const conflicts = conflictsThroughRound().length;
  const interventions = interventionsThroughRound().length;
  const invariantRound = runtimeData.invariants.history[roundLimit - 1];
  const ok = (invariantRound?.overall_ok ?? runtimeData.invariants.overall_ok) ? "OK" : "Attention";
  els.statusStrip.innerHTML = [
    stat("Invariant", ok, (invariantRound?.results.length || runtimeData.invariants.latest.length) + " checks"),
    stat("Capsules", capsulesThroughRound().length, `${counts.active} active`),
    stat("Refusals", counts.refused, "valid semantic states"),
    stat("Quarantine", counts.quarantined, `${interventions} interventions`),
    stat("Conflicts", conflicts, `${rounds} rounds retained`),
  ].join("");
}

function stat(label, value, note) {
  return `<div class="stat"><div class="stat-label">${escapeHtml(label)}</div><div class="stat-value">${escapeHtml(value)}</div><div class="stat-note">${escapeHtml(note)}</div></div>`;
}

function renderGraphLegend() {
  const counts = capsuleCounts();
  const items = [
    ["active", colors.active, counts.active],
    ["refused", colors.refused, counts.refused],
    ["quarantined", colors.quarantined, counts.quarantined],
    ["agent", colors.agent, runtimeData.state.runtime.agents.length],
  ];
  els.graphLegend.innerHTML = items
    .map(([label, color, count]) => `
      <span class="legend-pill">
        <span class="legend-dot" style="background:${color}; color:${color}"></span>
        ${escapeHtml(label)} ${escapeHtml(count)}
      </span>
    `)
    .join("");
}

function renderFlowGraph() {
  const svg = els.flowGraph;
  const width = svg.clientWidth || 900;
  const height = svg.clientHeight || 560;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = "";
  svg.append(svgDefs());

  const agents = runtimeData.state.runtime.agents;
  const deliveriesAll = deliveriesThroughRound();
  const capsules = capsulesThroughRound().filter((capsule) => capsuleVisible(capsule, deliveriesAll));
  const capsuleById = new Map(capsules.map((capsule) => [capsule.id, capsule]));
  const deliveries = deliveriesAll.filter((delivery) => {
    if (!capsuleById.has(delivery.capsule_id)) return false;
    return focusAgent === "all" || delivery.source_agent === focusAgent || delivery.target_agent === focusAgent;
  });

  const agentPositions = new Map();
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;
  agents.forEach((agent, index) => {
    const angle = -Math.PI / 2 + (index / agents.length) * Math.PI * 2;
    agentPositions.set(agent.id, {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
      agent,
    });
  });

  svg.append(
    svgEl("circle", { cx, cy, r: radius * 0.72, class: "hub-ring" }),
    svgEl("circle", { cx, cy, r: radius * 0.43, class: "hub-ring" }),
    svgEl("circle", { cx, cy, r: 58, class: "hub-core" }),
    svgEl("text", {
      x: cx,
      y: cy - 4,
      "text-anchor": "middle",
      fill: "rgba(236,244,241,0.92)",
      "font-size": "12",
      "font-weight": "900",
    }, "MEANING"),
    svgEl("text", {
      x: cx,
      y: cy + 14,
      "text-anchor": "middle",
      fill: "rgba(148,169,173,0.9)",
      "font-size": "10",
      "font-weight": "800",
    }, `${capsules.length} capsules`),
  );

  const capsulePositions = new Map();
  capsules.forEach((capsule, index) => {
    const source = agentPositions.get(capsule.source_agent) || { x: cx, y: cy };
    const lane = (index % 7) - 3;
    const distance = 48 + (Math.floor(index / 7) % 4) * 34;
    const dx = source.x - cx;
    const dy = source.y - cy;
    const len = Math.max(1, Math.hypot(dx, dy));
    const tangent = { x: -dy / len, y: dx / len };
    capsulePositions.set(capsule.id, {
      x: source.x - (dx / len) * distance + tangent.x * lane * 16,
      y: source.y - (dy / len) * distance + tangent.y * lane * 16,
      capsule,
    });
  });

  for (const delivery of deliveries) {
    const from = capsulePositions.get(delivery.capsule_id);
    const to = agentPositions.get(delivery.target_agent);
    if (!from || !to) continue;
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const normal = normalize({ x: -dy, y: dx });
    const bow = delivery.status === "quarantined" ? 34 : delivery.status === "refused" ? 24 : 16;
    const c1 = {
      x: from.x + dx * 0.38 + normal.x * bow,
      y: from.y + dy * 0.38 + normal.y * bow,
    };
    const c2 = {
      x: from.x + dx * 0.68 + normal.x * bow,
      y: from.y + dy * 0.68 + normal.y * bow,
    };
    const line = svgEl("path", {
      d: `M ${from.x} ${from.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${to.x} ${to.y}`,
      class: `graph-link ${pulseEnabled ? "flow-pulse" : ""}`,
      stroke: colors[delivery.status] || "rgba(148,169,173,0.7)",
      "stroke-width": delivery.status === "quarantined" ? 2.6 : 1.25,
      "marker-end": "url(#arrowHead)",
    });
    line.addEventListener("click", () => renderDetail(routeDetail(delivery)));
    svg.append(line);
  }

  for (const pos of capsulePositions.values()) {
    const capsule = pos.capsule;
    const group = svgEl("g", { class: "graph-node", tabindex: "0" });
    group.append(
      svgEl("circle", {
        cx: pos.x,
        cy: pos.y,
        r: capsule.status === "quarantined" ? 18 : 14,
        fill: colors[capsule.status] || colors.expired,
        "fill-opacity": capsule.status === "active" ? 0.11 : 0.16,
        class: pulseEnabled ? "node-halo" : "",
      }),
      svgEl("circle", {
        cx: pos.x,
        cy: pos.y,
        r: capsule.status === "quarantined" ? 8 : 6,
        fill: colors[capsule.status] || colors.expired,
        "fill-opacity": capsule.status === "active" ? 0.92 : 0.82,
      }),
    );
    group.addEventListener("click", () => renderDetail(capsuleDetail(capsule)));
    svg.append(group);
  }

  for (const pos of agentPositions.values()) {
    const isFocused = focusAgent === "all" || focusAgent === pos.agent.id;
    const group = svgEl("g", { class: `graph-node ${isFocused ? "" : "dimmed"}`, tabindex: "0" });
    group.append(
      svgEl("circle", { cx: pos.x, cy: pos.y, r: 34, fill: colors.agent, "fill-opacity": 0.12 }),
      svgEl("circle", { cx: pos.x, cy: pos.y, r: 24, fill: colors.agent, "fill-opacity": 0.95, filter: "url(#softGlow)" }),
      svgEl("text", {
        x: pos.x,
        y: pos.y + 4,
        "text-anchor": "middle",
        fill: "#fff",
        "font-size": "12",
        "font-weight": "800",
      }, initials(pos.agent.id)),
      svgEl("text", {
        x: pos.x,
        y: pos.y + 42,
        "text-anchor": "middle",
        class: "graph-label",
      }, compactAgent(pos.agent.id)),
    );
    group.addEventListener("click", () => renderDetail(agentDetail(pos.agent)));
    svg.append(group);
  }
}

function capsuleVisible(capsule, deliveries) {
  if (statusFilter !== "all" && capsule.status !== statusFilter) return false;
  if (focusAgent !== "all") {
    const involved = capsule.source_agent === focusAgent || deliveries.some(
      (delivery) => delivery.capsule_id === capsule.id && (delivery.source_agent === focusAgent || delivery.target_agent === focusAgent),
    );
    if (!involved) return false;
  }
  if (!searchQuery) return true;
  const haystack = [
    capsule.id,
    capsule.status,
    capsule.source_agent,
    capsule.intent,
    capsule.content?.ontology,
    capsule.content?.text,
    ...(capsule.content?.claims || []),
    ...(capsule.content?.assumptions || []),
    capsule.refusal?.reason,
    capsule.refusal?.explanation,
  ].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(searchQuery.toLowerCase());
}

function renderResonanceMatrix() {
  const agents = runtimeData.state.runtime.agents.map((agent) => agent.id);
  const counts = new Map();
  let max = 1;
  for (const delivery of deliveriesThroughRound()) {
    const key = `${delivery.source_agent}→${delivery.target_agent}`;
    const next = (counts.get(key) || 0) + 1;
    counts.set(key, next);
    max = Math.max(max, next);
  }
  els.resonanceMatrix.style.setProperty("--matrix-size", agents.length + 1);
  els.resonanceMatrix.innerHTML = [
    `<div class="matrix-corner">source / target</div>`,
    ...agents.map((agent) => `<div class="matrix-head">${escapeHtml(initials(agent))}</div>`),
    ...agents.flatMap((source) => [
      `<div class="matrix-side">${escapeHtml(initials(source))}</div>`,
      ...agents.map((target) => {
        const value = source === target ? 0 : counts.get(`${source}→${target}`) || 0;
        const intensity = value / max;
        return `<button class="matrix-cell" type="button" style="--heat:${intensity}" data-source="${escapeHtml(source)}" data-target="${escapeHtml(target)}" title="${escapeHtml(source)} to ${escapeHtml(target)}: ${value} routes">${value || ""}</button>`;
      }),
    ]),
  ].join("");

  els.resonanceMatrix.querySelectorAll(".matrix-cell").forEach((cell) => {
    cell.addEventListener("click", () => {
      const source = cell.dataset.source;
      const target = cell.dataset.target;
      const routes = deliveriesThroughRound().filter(
        (delivery) => delivery.source_agent === source && delivery.target_agent === target,
      );
      renderDetail({
        title: `${source} → ${target}`,
        body: `${routes.length} routed capsules across this semantic corridor.`,
        tags: ["resonance", source, target],
        raw: routes,
      });
    });
  });
}

function renderInvariantRail() {
  const latest = runtimeData.invariants.history[roundLimit - 1]?.results || runtimeData.invariants.latest || [];
  els.invariantRail.innerHTML = latest
    .map((item) => `
      <div class="invariant-cell" title="${escapeHtml(item.message || "")}">
        <div class="invariant-score">${escapeHtml(percent(item.score ?? 0))}</div>
        <div class="invariant-name">${escapeHtml(item.name)}</div>
      </div>
    `)
    .join("");
}

function renderWeather() {
  const counts = capsuleCounts();
  const activeCapsules = capsulesThroughRound();
  const total = Math.max(1, activeCapsules.length);
  const conflicts = conflictsThroughRound().length;
  const deliveries = deliveriesThroughRound().length;
  const latest = runtimeData.invariants.history[roundLimit - 1]?.results || [];
  const nonDom = latest.find((result) => result.name === "NonDomination");
  const productive = latest.find((result) => result.name === "ProductiveDisagreement");
  const stalemate = latest.find((result) => result.name === "StalemateRisk");
  const shares = nonDom?.details?.shares || {};
  const maxShare = Object.values(shares).reduce((max, value) => Math.max(max, Number(value) || 0), 0);
  const avgLoss = average(activeCapsules.map((capsule) => capsule.metrics?.semantic_loss || 0));
  const avgAmbiguity = average(activeCapsules.map((capsule) => capsule.metrics?.ambiguity_score || 0));

  const items = [
    ["Refusal density", percent(counts.refused / total), "How much boundary-preserving non-translation is alive in the bus."],
    ["Conflict richness", (conflicts / Math.max(1, deliveries)).toFixed(2), "Unresolved conflicts retained per delivered route."],
    ["Domination pressure", percent(maxShare), "Largest influence share in the latest invariant check."],
    ["Translation haze", percent((avgLoss + avgAmbiguity) / 2), "Average loss and ambiguity across stored capsules."],
    ["Productive disagreement", percent(productive?.score ?? 1), "Whether conflict is creating commitments or safe next steps."],
    ["Stalemate risk", percent(stalemate?.details?.risk ?? 0), "How close refusal and conflict load are to non-movement."],
  ];

  els.weatherGrid.innerHTML = items
    .map(([label, value, copy]) => `
      <div class="weather-item">
        <div class="stat-label">${escapeHtml(label)}</div>
        <div class="weather-value">${escapeHtml(value)}</div>
        <p class="weather-copy">${escapeHtml(copy)}</p>
      </div>
    `)
    .join("");
}

function renderContextSelector() {
  const graphs = runtimeData.state.context_graphs;
  els.agentSelect.innerHTML = Object.keys(graphs)
    .map((agent) => `<option value="${escapeHtml(agent)}">${escapeHtml(agent)}</option>`)
    .join("");
  els.agentSelect.onchange = () => renderContextGraph(els.agentSelect.value);
  renderContextGraph(els.agentSelect.value || Object.keys(graphs)[0]);
}

function renderContextGraph(agentId) {
  const graph = runtimeData.state.context_graphs[agentId];
  if (!graph) return;
  const typeCounts = countBy(graph.nodes, (node) => node.node_type || "unknown");
  const influence = graph.influence_by_agent || {};
  const topTerms = graph.top_terms || [];
  els.contextGraphSummary.innerHTML = `
    <div class="tag-row">
      <span class="tag">${escapeHtml(graph.nodes.length)} nodes</span>
      <span class="tag">${escapeHtml(graph.edges.length)} edges</span>
      <span class="tag">drift ${escapeHtml(formatNumber(graph.drift_score || 0))}</span>
    </div>
    <h3>Influence by agent</h3>
    ${barList(influence)}
    <h3>Node texture</h3>
    ${barList(typeCounts)}
    <h3>Top terms</h3>
    <div class="tag-row">${topTerms.slice(0, 12).map(([term, score]) => `<span class="tag">${escapeHtml(term)} ${escapeHtml(formatNumber(score))}</span>`).join("")}</div>
  `;
}

function renderTimeline() {
  els.timeline.innerHTML = runtimeData.state.rounds
    .map((round) => {
      const scores = Object.entries(round.invariants.scores || {})
        .map(([name, score]) => `${name} ${formatNumber(score)}`)
        .join(" / ");
      return `
        <article class="timeline-item ${round.round <= roundLimit ? "visible-round" : "future-round"}">
          <h3>Round ${escapeHtml(round.round)}: ${escapeHtml(round.routed_count)} routes</h3>
          <p>${escapeHtml(round.query)}</p>
          <div class="tag-row">
            <span class="tag">${escapeHtml(round.produced_capsules.length)} produced</span>
            <span class="tag">${round.invariants.overall_ok ? "invariants ok" : "needs review"}</span>
          </div>
          <p>${escapeHtml(scores)}</p>
        </article>
      `;
    })
    .join("");
}

function renderConflicts() {
  const conflicts = conflictsThroughRound();
  els.conflictList.innerHTML = conflicts
    .slice(0, 40)
    .map((conflict) => `
      <article class="conflict-item">
        <h3>${escapeHtml(conflict.id)}</h3>
        <p>${escapeHtml(conflict.claims.join(" / "))}</p>
        <div class="tag-row">
          ${conflict.agents.map((agent) => `<span class="tag">${escapeHtml(agent)}</span>`).join("")}
          <span class="tag">${escapeHtml(conflict.unresolved_status)}</span>
        </div>
      </article>
    `)
    .join("");
  els.conflictList.querySelectorAll(".conflict-item").forEach((item, index) => {
    item.addEventListener("click", () => {
      const conflict = conflicts[index];
      renderDetail({
        title: conflict.id,
        body: conflict.claims.join(" / "),
        tags: [...conflict.agents, conflict.unresolved_status, "conflict"],
        raw: conflict,
      });
    });
  });
}

function capsuleDetail(capsule) {
  return {
    kind: "capsule",
    title: capsule.id,
    body: capsule.content?.text || "No capsule text.",
    tags: [capsule.status, capsule.source_agent, capsule.intent, capsule.content?.ontology].filter(Boolean),
    raw: capsule,
  };
}

function agentDetail(agent) {
  const graph = runtimeData.state.context_graphs[agent.id];
  return {
    kind: "agent",
    title: agent.id,
    body: `${agent.role} using ${agent.ontology} ontology.`,
    tags: [agent.model_backend, agent.behavior, `${graph?.nodes.length || 0} memory nodes`],
    raw: { agent, context_graph: graph },
  };
}

function routeDetail(delivery) {
  const capsule = capsulesThroughRound().find((item) => item.id === delivery.capsule_id);
  return {
    kind: "route",
    title: `${delivery.route_kind}: ${delivery.capsule_id}`,
    body: `${delivery.source_agent} delivered to ${delivery.target_agent}.`,
    tags: [delivery.status, delivery.route_kind],
    raw: { delivery, capsule },
  };
}

function renderDetail(detail) {
  const statusClass = detail.tags?.find((tag) => ["active", "refused", "quarantined"].includes(tag));
  els.detailPane.innerHTML = `
    <h3>${escapeHtml(detail.title)}</h3>
    <p class="${statusClass ? `status-${statusClass}` : ""}">${escapeHtml(detail.body)}</p>
    ${detail.tags?.length ? `<div class="tag-row">${detail.tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
    <pre class="code-block">${escapeHtml(JSON.stringify(detail.raw, null, 2))}</pre>
  `;
}

function barList(values) {
  const entries = Object.entries(values).sort((a, b) => Number(b[1]) - Number(a[1]));
  const max = entries.reduce((m, [, value]) => Math.max(m, Number(value) || 0), 0) || 1;
  return `
    <div class="bar-list">
      ${entries.map(([label, value]) => `
        <div>
          <div class="bar-label"><span>${escapeHtml(label)}</span><span>${escapeHtml(formatNumber(value))}</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, (Number(value) / max) * 100)}%"></div></div>
        </div>
      `).join("")}
    </div>
  `;
}

function countBy(items, fn) {
  return items.reduce((acc, item) => {
    const key = fn(item);
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + Number(value || 0), 0) / values.length;
}

function percent(value) {
  return `${Math.round(Number(value || 0) * 100)}%`;
}

function formatNumber(value) {
  const number = Number(value || 0);
  if (Number.isInteger(number)) return String(number);
  return number.toFixed(2);
}

function initials(id) {
  return id.split("_").map((part) => part[0]).join("").slice(0, 3).toUpperCase();
}

function compactAgent(id) {
  return id.replaceAll("_", " ");
}

function svgEl(name, attrs = {}, text = "") {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attrs)) {
    el.setAttribute(key, value);
  }
  if (text) el.textContent = text;
  return el;
}

function svgDefs() {
  const defs = svgEl("defs");
  const softGlow = svgEl("filter", { id: "softGlow", x: "-80%", y: "-80%", width: "260%", height: "260%" });
  softGlow.append(
    svgEl("feGaussianBlur", { stdDeviation: "4", result: "coloredBlur" }),
    svgEl("feMerge", {}),
  );
  softGlow.lastChild.append(svgEl("feMergeNode", { in: "coloredBlur" }), svgEl("feMergeNode", { in: "SourceGraphic" }));

  const hotGlow = svgEl("filter", { id: "hotGlow", x: "-120%", y: "-120%", width: "340%", height: "340%" });
  hotGlow.append(
    svgEl("feGaussianBlur", { stdDeviation: "7", result: "coloredBlur" }),
    svgEl("feMerge", {}),
  );
  hotGlow.lastChild.append(svgEl("feMergeNode", { in: "coloredBlur" }), svgEl("feMergeNode", { in: "SourceGraphic" }));

  const marker = svgEl("marker", {
    id: "arrowHead",
    viewBox: "0 0 10 10",
    refX: "8",
    refY: "5",
    markerWidth: "4",
    markerHeight: "4",
    orient: "auto-start-reverse",
  });
  marker.append(svgEl("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "rgba(148,169,173,0.58)" }));
  defs.append(softGlow, hotGlow, marker);
  return defs;
}

function normalize(vector) {
  const length = Math.max(1, Math.hypot(vector.x, vector.y));
  return { x: vector.x / length, y: vector.y / length };
}

function buildRoundIndex(data) {
  const capsuleRound = new Map();
  const producedRound = new Map();
  for (const round of data.state.rounds) {
    for (const id of round.produced_capsules || []) {
      producedRound.set(id, round.round);
    }
  }

  let currentRound = 1;
  for (const event of data.capsules.events || []) {
    if (producedRound.has(event.capsule_id)) {
      currentRound = producedRound.get(event.capsule_id);
    }
    if (event.capsule_id && !capsuleRound.has(event.capsule_id)) {
      capsuleRound.set(event.capsule_id, currentRound);
    }
  }

  for (const capsule of data.capsules.capsules) {
    if (!capsuleRound.has(capsule.id)) {
      capsuleRound.set(capsule.id, producedRound.get(capsule.id) || 1);
    }
  }

  const conflictRound = new Map();
  for (const conflict of data.conflicts.conflicts || []) {
    const rounds = (conflict.capsule_ids || []).map((id) => capsuleRound.get(id) || 1);
    conflictRound.set(conflict.id, Math.max(1, ...rounds));
  }

  return { capsuleRound, conflictRound };
}

function capsuleRound(capsuleId) {
  return runtimeData.roundIndex.capsuleRound.get(capsuleId) || 1;
}

function capsulesThroughRound() {
  return runtimeData.capsules.capsules.filter((capsule) => capsuleRound(capsule.id) <= roundLimit);
}

function deliveriesThroughRound() {
  return runtimeData.capsules.deliveries.filter((delivery) => capsuleRound(delivery.capsule_id) <= roundLimit);
}

function conflictsThroughRound() {
  return runtimeData.conflicts.conflicts.filter((conflict) => (
    runtimeData.roundIndex.conflictRound.get(conflict.id) || 1
  ) <= roundLimit);
}

function interventionsThroughRound() {
  return runtimeData.interventions.records.filter((record) => capsuleRound(record.target) <= roundLimit);
}

function setRoundLimit(nextRound) {
  const maxRound = runtimeData?.state.rounds.length || 1;
  roundLimit = Math.min(maxRound, Math.max(1, Number(nextRound) || 1));
  renderTemporalLens();
  renderObservable();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

els.reloadButton.addEventListener("click", loadRuntime);
els.statusButtons.forEach((button) => {
  button.addEventListener("click", () => {
    statusFilter = button.dataset.status;
    els.statusButtons.forEach((item) => item.classList.toggle("active", item === button));
    renderFlowGraph();
  });
});
els.capsuleSearch.addEventListener("input", () => {
  searchQuery = els.capsuleSearch.value.trim();
  renderFlowGraph();
});
els.focusAgent.addEventListener("change", () => {
  focusAgent = els.focusAgent.value;
  renderFlowGraph();
});
els.pulseToggle.addEventListener("change", () => {
  pulseEnabled = els.pulseToggle.checked;
  renderFlowGraph();
});
els.roundLens.addEventListener("input", () => {
  setRoundLimit(els.roundLens.value);
});
els.playRounds.addEventListener("click", () => {
  if (playbackTimer) {
    clearInterval(playbackTimer);
    playbackTimer = null;
    els.playRounds.textContent = "Play";
    return;
  }
  els.playRounds.textContent = "Pause";
  playbackTimer = setInterval(() => {
    const maxRound = runtimeData?.state.rounds.length || 1;
    if (roundLimit >= maxRound) {
      clearInterval(playbackTimer);
      playbackTimer = null;
      els.playRounds.textContent = "Play";
      setRoundLimit(1);
      return;
    }
    setRoundLimit(roundLimit + 1);
  }, 1200);
});

els.dataPath.value = getInitialPath();
loadRuntime();
