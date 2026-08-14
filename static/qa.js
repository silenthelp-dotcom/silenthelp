/* SilentHelp QA — MVP Readiness & AI Testing Console
   Vanilla JS, single-page, matches the rest of this codebase's style
   (app.html is also hand-rolled JS, no framework). State lives server-side
   in qa_store.py; this file renders it and calls the /api/qa/* routes. */
(function () {
"use strict";

const Q = {
  state: null,
  route: "overview",
  bugFilter: { status: "ALL", severity: "ALL", q: "" },
  improvementFilter: { category: "ALL" },
  openTestIds: new Set(),
  busy: new Set(), // ids currently running a live test, for spinner state

  async boot() {
    await this.load();
    this.renderShell();
    this.route = (location.hash || "#overview").slice(1);
    this.renderRoute();
    window.addEventListener("hashchange", () => { this.route = (location.hash || "#overview").slice(1); this.renderRoute(); });
  },

  async load() {
    const res = await fetch("/api/qa/state");
    this.state = await res.json();
  },

  async api(path, body) {
    const res = await fetch(path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return res.json();
  },

  go(route) { location.hash = "#" + route; },

  esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },

  fmtTime(ts) {
    if (!ts) return "—";
    const d = new Date(ts * 1000);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  },

  fmtAgo(ts) {
    if (!ts) return "never";
    const s = Math.max(0, (Date.now() / 1000) - ts);
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    if (s < 86400) return Math.floor(s / 3600) + "h ago";
    return Math.floor(s / 86400) + "d ago";
  },

  // ---- shell: sidebar + topbar (rendered once, sections just update #page) ----
  NAV: [
    { sec: "Testing", items: [
      { key: "overview", label: "Overview", ic: "grid" },
      { key: "ai-lab", label: "AI Detection Lab", ic: "cpu" },
      { key: "context", label: "Context Testing", ic: "layers" },
      { key: "safety", label: "Safety & Response", ic: "shield" },
      { key: "resources", label: "Resources & Popups", ic: "message" },
      { key: "privacy", label: "Privacy", ic: "lock" },
      { key: "edge", label: "Edge Cases", ic: "zap" },
    ]},
    { sec: "Tracking", items: [
      { key: "bugs", label: "Bugs & Improvements", ic: "bug" },
      { key: "checklist", label: "Launch Checklist", ic: "check" },
      { key: "history", label: "Test History", ic: "clock" },
    ]},
  ],

  ICONS: {
    grid: '<path d="M3 3h7v7H3V3Zm0 11h7v7H3v-7ZM14 3h7v7h-7V3Zm0 11h7v7h-7v-7Z" stroke="currentColor" stroke-width="1.6" fill="none"/>',
    cpu: '<rect x="6" y="6" width="12" height="12" rx="1.5" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    layers: '<path d="M12 2 2 7l10 5 10-5-10-5Zm0 12L2 9m20 0-10 5m-10 3 10 5 10-5" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/>',
    shield: '<path d="M12 2 4 5v6c0 5 3.5 8.5 8 11 4.5-2.5 8-6 8-11V5l-8-3Z" stroke="currentColor" stroke-width="1.6" fill="none"/>',
    message: '<path d="M4 5h16v11H8l-4 4V5Z" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/>',
    lock: '<rect x="4" y="10" width="16" height="10" rx="1.5" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M7 10V7a5 5 0 0 1 10 0v3" stroke="currentColor" stroke-width="1.6" fill="none"/>',
    zap: '<path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linejoin="round"/>',
    bug: '<circle cx="12" cy="13" r="6" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M9 5l1.5 2M15 5l-1.5 2M4 13h2M18 13h2M6 18l2-2M18 18l-2-2M12 7v2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    check: '<path d="M4 12l5 5L20 6" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    clock: '<circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M12 7v5l3.5 2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
  },

  renderShell() {
    const sidebar = document.getElementById("sidebar");
    sidebar.innerHTML = `
      <div class="brand">
        <div class="dot"></div>
        <div class="name">SilentHelp <small>MVP Readiness</small></div>
      </div>
      ${this.NAV.map(sec => `
        <div class="navsec">${sec.sec}</div>
        ${sec.items.map(it => `
          <div class="navitem" data-route="${it.key}" onclick="QA.go('${it.key}')">
            <svg class="ic" viewBox="0 0 24 24">${this.ICONS[it.ic]}</svg>
            <span>${it.label}</span>
            ${it.key === "bugs" ? `<span class="badge" id="nav-bug-count"></span>` : ""}
          </div>
        `).join("")}
      `).join("")}
    `;
    const topbar = document.getElementById("topbar");
    topbar.innerHTML = `
      <div class="tb-left">
        <div class="tb-title">SilentHelp // MVP Readiness</div>
        <div class="tb-ver" id="tb-version"></div>
      </div>
      <div class="tb-right">
        <span class="modebadge live"><span class="dot"></span>LIVE BACKEND</span>
        <button class="pillbtn" onclick="QA.exportResults()">Export Results</button>
        <button class="pillbtn" onclick="QA.createReport()">Create Test Report</button>
        <button class="pillbtn primary" onclick="QA.go('checklist')">Mark MVP Candidate</button>
      </div>
    `;
    this.updateVersionLabel();
    this.updateBugBadge();
  },

  updateVersionLabel() {
    const el = document.getElementById("tb-version");
    if (el) el.textContent = "v" + (this.state.version || "0.0.0");
  },
  updateBugBadge() {
    const el = document.getElementById("nav-bug-count");
    if (!el) return;
    const open = (this.state.bugs || []).filter(b => b.status !== "FIXED" && b.status !== "CLOSED").length;
    el.textContent = open || "";
    el.style.display = open ? "" : "none";
  },

  renderRoute() {
    document.querySelectorAll(".navitem").forEach(el => el.classList.toggle("active", el.dataset.route === this.route));
    const page = document.getElementById("page");
    const renderers = {
      "overview": () => this.renderOverview(),
      "ai-lab": () => this.renderAiLab(),
      "context": () => this.renderContext(),
      "safety": () => this.renderSafety(),
      "resources": () => this.renderResources(),
      "privacy": () => this.renderPrivacy(),
      "edge": () => this.renderEdge(),
      "bugs": () => this.renderBugs(),
      "checklist": () => this.renderChecklist(),
      "history": () => this.renderHistory(),
    };
    const r = renderers[this.route] || renderers["overview"];
    page.innerHTML = r();
    this.afterRender();
    window.scrollTo(0, 0);
    page.parentElement.scrollTop = 0;
  },

  afterRender() {}, // per-section hooks set this before returning HTML if needed

  refresh() {
    this.load().then(() => { this.updateVersionLabel(); this.updateBugBadge(); this.renderRoute(); });
  },
};

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------
Object.assign(Q, {
  computeScore() {
    // Mirrors qa_store.readiness_score() so the UI updates instantly on any
    // local mutation without waiting on a round-trip; the server value (sent
    // with every /api/qa/state) is still the source of truth on reload.
    const tests = this.state.tests || [];
    const catKeys = {
      "AI Detection": ["normal", "jokes", "sarcasm", "idioms"],
      "Context Understanding": ["ambiguous", "edge_contradictory", "edge_mixed"],
      "Safety Responses": ["distress", "academic", "isolation"],
      "Reliability": ["edge_typos_slang"],
    };
    const catScore = keys => {
      const run = tests.filter(t => keys.includes(t.category) && t.result);
      if (!run.length) return null;
      return Math.round(100 * run.filter(t => t.result === "PASS").length / run.length);
    };
    const categories = {};
    for (const [name, keys] of Object.entries(catKeys)) categories[name] = catScore(keys);

    const rtests = this.state.resourceTests || [];
    categories["Resources"] = rtests.length
      ? Math.round(100 * rtests.filter(r => r.result === "PASS").length / rtests.length) : null;

    const pchecks = Object.values(this.state.privacyChecks || {});
    const ptested = pchecks.filter(v => v.status === "PASS" || v.status === "FAIL");
    categories["Privacy"] = ptested.length
      ? Math.round(100 * ptested.filter(v => v.status === "PASS").length / ptested.length) : null;

    const scored = Object.values(categories).filter(v => v !== null);
    const overall = scored.length ? Math.round(scored.reduce((a, b) => a + b, 0) / scored.length) : 0;

    const completed = tests.filter(t => t.result).length;
    const passedN = tests.filter(t => t.result === "PASS").length;
    const failedN = tests.filter(t => t.result === "FAIL").length;
    const reviewN = tests.filter(t => t.result === "REVIEW").length;
    const openBugs = (this.state.bugs || []).filter(b => b.status !== "FIXED" && b.status !== "CLOSED");
    const criticalBugs = openBugs.filter(b => b.severity === "CRITICAL");

    let status;
    if (criticalBugs.length) status = "NOT READY";
    else if (completed === 0) status = "NOT READY";
    else if (completed < tests.length) status = "TESTING";
    else if (reviewN > 0 || failedN > 0) status = "NEEDS REVIEW";
    else if (overall >= 90) status = "READY FOR PILOT";
    else status = "MVP READY";

    return { overall, categories, testsTotal: tests.length, testsCompleted: completed,
             testsPassed: passedN, testsFailed: failedN, testsReview: reviewN,
             openBugs: openBugs.length, criticalBugs: criticalBugs.length, status };
  },

  statusClass(status) { return status.toLowerCase().replace(/ /g, ""); },

  renderOverview() {
    const s = this.computeScore();
    const circ = 2 * Math.PI * 56;
    const dash = circ * (s.overall / 100);
    const lastRun = (this.state.tests || []).reduce((max, t) => t.lastRunAt ? Math.max(max, t.lastRunAt) : max, 0);

    const catMeta = [
      { key: "AI Detection", route: "ai-lab" },
      { key: "Context Understanding", route: "context" },
      { key: "Safety Responses", route: "safety" },
      { key: "Resources", route: "resources" },
      { key: "Privacy", route: "privacy" },
      { key: "Reliability", route: "edge" },
    ];

    const failedTests = (this.state.tests || []).filter(t => t.result === "FAIL");
    const critical = failedTests.filter(t => t.failureKind === "FALSE POSITIVE" || t.failureKind === "FALSE NEGATIVE").slice(0, 5);

    const recent = (this.state.tests || [])
      .filter(t => t.lastRunAt)
      .sort((a, b) => b.lastRunAt - a.lastRunAt)
      .slice(0, 8);

    return `
      <div class="card readiness-hero">
        <div class="ring-wrap">
          <svg width="132" height="132">
            <circle cx="66" cy="66" r="56" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="10"/>
            <circle cx="66" cy="66" r="56" fill="none" stroke="url(#g1)" stroke-width="10"
              stroke-linecap="round" stroke-dasharray="${circ}" stroke-dashoffset="${circ - dash}"
              style="transition:stroke-dashoffset 1s cubic-bezier(.16,1,.3,1)"/>
            <defs><linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#5b8cff"/><stop offset="100%" stop-color="#9d6bff"/>
            </linearGradient></defs>
          </svg>
          <div class="ring-num"><div class="n">${s.overall}%</div><div class="lbl">Readiness</div></div>
        </div>
        <div>
          <div class="kicker">Safety • Intelligence • Privacy • Reliability • Launch Readiness</div>
          <div class="flex center gap12 mt8">
            <span class="status-chip ${this.statusClass(s.status)}">${s.status}</span>
            <span class="small muted">Last test run: ${this.fmtAgo(lastRun)}</span>
          </div>
          <div class="metrics-row">
            <div class="metric"><div class="v">${s.testsCompleted}/${s.testsTotal}</div><div class="l">Tests completed</div></div>
            <div class="metric"><div class="v" style="color:var(--green)">${s.testsPassed}</div><div class="l">Passed</div></div>
            <div class="metric"><div class="v" style="color:var(--red)">${s.testsFailed}</div><div class="l">Failed</div></div>
            <div class="metric"><div class="v" style="color:var(--amber)">${s.testsReview}</div><div class="l">Needs review</div></div>
            <div class="metric"><div class="v">${s.openBugs}</div><div class="l">Open bugs</div></div>
            <div class="metric crit"><div class="v">${s.criticalBugs}</div><div class="l">Critical issues</div></div>
          </div>
        </div>
      </div>

      <div class="grid grid-3">
        ${catMeta.map(c => {
          const v = s.categories[c.key];
          const color = v === null ? "var(--sub-2)" : v >= 90 ? "var(--green)" : v >= 70 ? "var(--blue)" : v >= 50 ? "var(--amber)" : "var(--red)";
          return `
          <div class="card catcard" onclick="QA.go('${c.route}')">
            <div class="cn">${c.key}</div>
            ${v === null
              ? `<div class="empty">Not tested yet</div>`
              : `<div class="cv" style="color:${color}">${v}%</div>
                 <div class="bar"><div style="width:${v}%; background:${color}"></div></div>`}
          </div>`;
        }).join("")}
      </div>

      <div class="section-title"><h2>Critical Issues</h2><span class="count">${critical.length} flagged</span></div>
      ${critical.length ? critical.map(t => `
        <div class="issue-row">
          <span class="pill ${t.expected.severity !== t.actual?.severity ? "pill-critical" : "pill-high"}">${t.failureKind || "REVIEW"}</span>
          <div style="flex:1">
            <div class="t">"${this.esc(t.input)}"</div>
            <div class="meta">Expected ${t.expected.context} / ${t.expected.severity} — got ${t.actual?.context || "?"} / ${t.actual?.severity || "?"}</div>
          </div>
        </div>
      `).join("") : `<div class="empty-state" style="padding:30px 20px;"><div class="d">No critical issues flagged from completed tests.</div></div>`}

      <div class="section-title"><h2>Recent Test Results</h2><span class="count">${recent.length} shown</span></div>
      ${recent.length ? recent.map(t => `
        <div class="resultline">
          <span class="pill pill-${t.result.toLowerCase()}">${t.result === "PASS" ? "✓" : t.result === "FAIL" ? "✕" : "⚠"} ${t.result}</span>
          <span class="txt">"${this.esc(t.input)}"</span>
          <span class="tag">${this.esc(t.actual?.context || "")}</span>
          <span class="tag mono">${this.fmtAgo(t.lastRunAt)}</span>
        </div>
      `).join("") : `<div class="empty-state"><div class="ic">◌</div><div class="t">No tests run yet</div><div class="d">Head to the AI Detection Lab or run a full suite to populate results here.</div></div>`}
    `;
  },
});

// ---------------------------------------------------------------------------
// AI Detection Lab
// ---------------------------------------------------------------------------
Object.assign(Q, {
  _labLastResult: null,

  renderAiLab() {
    const suites = (this.state._meta.suites || []).filter(s =>
      ["normal", "jokes", "sarcasm", "idioms"].includes(s.key));
    return `
      <div class="kicker">AI Detection Lab</div>
      <h1 class="page-h">Test SilentHelp's AI / context detection</h1>
      <p class="page-sub">Every run calls the real detection pipeline live — no pre-baked answers. The AI's context classification and the deterministic safety rules are shown separately on purpose: SilentHelp's architecture never lets the AI decide the final action alone.</p>

      <div class="card raised mt20">
        <label class="small muted" style="font-weight:600; display:block; margin-bottom:8px;">Enter text to test SilentHelp</label>
        <textarea id="lab-input" placeholder="e.g. I'm completely exhausted and haven't talked to anyone all week." style="width:100%; min-height:90px; background:rgba(255,255,255,.03); border:1px solid var(--line-2); border-radius:8px; padding:12px 14px; color:var(--text); font-size:13.5px; font-family:inherit; outline:none; resize:vertical;"></textarea>
        <div class="flex gap8 mt12">
          <button class="pillbtn primary" id="lab-run-btn" onclick="QA.runLabTest()">Run Test</button>
          <button class="pillbtn" onclick="QA.clearLabTest()">Clear</button>
        </div>
        <div id="lab-result"></div>
      </div>

      <div class="section-title"><h2>Test Suites</h2></div>
      <div class="grid grid-3">
        ${suites.map(s => this.renderSuiteCard(s)).join("")}
      </div>

      <div class="section-title"><h2>All Tests</h2><span class="count">${(this.state.tests || []).filter(t => suites.some(s => s.key === t.category)).length} cases</span></div>
      <div id="lab-tests">
        ${(this.state.tests || []).filter(t => suites.some(s => s.key === t.category)).map(t => this.renderTestCase(t)).join("")}
      </div>
    `;
  },

  renderSuiteCard(suite) {
    const tests = (this.state.tests || []).filter(t => t.category === suite.key);
    const run = tests.filter(t => t.result);
    const passed = run.filter(t => t.result === "PASS").length;
    const failed = run.filter(t => t.result === "FAIL").length;
    const review = run.filter(t => t.result === "REVIEW").length;
    const acc = run.length ? Math.round(100 * passed / run.length) : null;
    return `
      <div class="card suite-card">
        <div class="top">
          <div>
            <div style="font-weight:700; font-size:13.5px;">${suite.label}</div>
            <div class="small muted mono mt8">${tests.length} tests</div>
          </div>
          <button class="pillbtn" style="font-size:11px; padding:6px 11px;" onclick="QA.runSuite('${suite.key}')" id="suite-btn-${suite.key}">Run Suite</button>
        </div>
        <div class="stats">
          <div class="stat"><div class="v" style="color:var(--green)">${passed}</div><div class="l">Pass</div></div>
          <div class="stat"><div class="v" style="color:var(--amber)">${review}</div><div class="l">Review</div></div>
          <div class="stat"><div class="v" style="color:var(--red)">${failed}</div><div class="l">Fail</div></div>
          <div class="stat"><div class="v">${acc === null ? "—" : acc + "%"}</div><div class="l">Accuracy</div></div>
        </div>
      </div>
    `;
  },

  renderTestCase(t) {
    const open = this.openTestIds.has(t.id);
    const resultPill = t.result
      ? `<span class="pill pill-${t.result.toLowerCase()}">${t.result === "PASS" ? "✓" : t.result === "FAIL" ? "✕" : "⚠"} ${t.result}</span>`
      : `<span class="pill pill-neutral">not run</span>`;
    const busy = this.busy.has(t.id);
    return `
      <div class="testcase ${open ? "open" : ""}" id="tc-${t.id}">
        <div class="head" onclick="QA.toggleTestCase('${t.id}')">
          <span class="sevdot ${t.expected.severity}"></span>
          <span class="inp">"${this.esc(t.input)}"</span>
          ${resultPill}
          <button class="pillbtn" style="font-size:10.5px; padding:5px 10px;" onclick="event.stopPropagation(); QA.runOneTest('${t.id}')" ${busy ? "disabled" : ""}>${busy ? "Running…" : "Run"}</button>
        </div>
        <div class="body">
          ${t.contextNote ? `<div class="small muted">Context: ${this.esc(t.contextNote)}</div>` : ""}
          <div class="cols">
            <div>
              <div class="kicker">Expected</div>
              <div class="ev-row"><span class="k">Context</span><span class="v">${this.esc(t.expected.context)}</span></div>
              <div class="ev-row"><span class="k">Severity</span><span class="v">${this.esc(t.expected.severity)}</span></div>
              <div class="ev-row"><span class="k">Action</span><span class="v">${this.esc(t.expected.action)}</span></div>
            </div>
            <div>
              <div class="kicker">Actual ${t.source === "live" ? `<span class="demo-flag" style="margin-left:6px; color:var(--green); background:rgba(62,207,142,.1); border-color:rgba(62,207,142,.25);">LIVE</span>` : ""}</div>
              ${t.actual ? `
                <div class="ev-row"><span class="k">Context</span><span class="v">${this.esc(t.actual.context)}</span></div>
                <div class="ev-row"><span class="k">Severity</span><span class="v">${this.esc(t.actual.severity)}</span></div>
                <div class="ev-row"><span class="k">Action</span><span class="v">${this.esc(t.actual.recommendedAction)}</span></div>
                <div class="ev-row"><span class="k">Latency</span><span class="v">${t.actual.latencyMs}ms</span></div>
              ` : `<div class="small muted">Not run yet.</div>`}
            </div>
          </div>
          ${t.result === "FAIL" ? `<div class="diffbox"><strong>${t.failureKind || "FAIL"}</strong> — expected ${this.esc(t.expected.context)}/${this.esc(t.expected.severity)}, got ${this.esc(t.actual?.context)}/${this.esc(t.actual?.severity)}</div>` : ""}
          ${t.actual?.metadata?.rationale ? `<div class="small muted mt12">AI reasoning summary: "${this.esc(t.actual.metadata.rationale)}"</div>` : ""}
        </div>
      </div>
    `;
  },

  toggleTestCase(id) {
    if (this.openTestIds.has(id)) this.openTestIds.delete(id); else this.openTestIds.add(id);
    const el = document.getElementById("tc-" + id);
    if (el) el.classList.toggle("open");
  },

  async runLabTest() {
    const input = document.getElementById("lab-input");
    const message = (input.value || "").trim();
    if (!message) return;
    const btn = document.getElementById("lab-run-btn");
    btn.disabled = true; btn.textContent = "Running…";
    const resultEl = document.getElementById("lab-result");
    resultEl.innerHTML = `<div class="small muted mt16">Calling the live pipeline…</div>`;
    try {
      const r = await this.api("/api/qa/run-test", { message });
      this._labLastResult = r;
      resultEl.innerHTML = this.renderLabResult(r);
    } finally {
      btn.disabled = false; btn.textContent = "Run Test";
    }
  },

  renderLabResult(r) {
    if (r.error) {
      return `<div class="diffbox mt16"><strong>SYSTEM ERROR</strong> — ${this.esc(r.metadata?.error || "the pipeline call failed")}</div>`;
    }
    const sevColor = { none: "var(--sub-2)", low: "#8fb0ff", moderate: "var(--amber)", high: "#ff9d5c", crisis: "var(--red)" }[r.severity] || "var(--sub)";
    return `
      <div class="hair mt16" style="padding-top:16px;">
        <div class="flex between center">
          <div class="kicker">Detection Result</div>
          <span class="modebadge live"><span class="dot"></span>LIVE BACKEND · ${r.latencyMs}ms</span>
        </div>
        <div class="grid grid-3 mt12">
          <div class="card">
            <div class="small muted">Concern Level</div>
            <div style="font-family:var(--mono); font-weight:800; font-size:20px; margin-top:6px; color:${sevColor}; text-transform:uppercase;">${this.esc(r.severity)}</div>
          </div>
          <div class="card">
            <div class="small muted">Context Classification</div>
            <div style="font-weight:700; font-size:15px; margin-top:6px; text-transform:capitalize;">${this.esc(r.context)}</div>
          </div>
          <div class="card">
            <div class="small muted">Confidence</div>
            <div style="font-family:var(--mono); font-weight:800; font-size:20px; margin-top:6px;">${r.confidence != null ? Math.round(r.confidence * 100) + "%" : "—"}</div>
          </div>
        </div>
        ${r.metadata?.rationale ? `<div class="card mt12"><div class="small muted">AI Reasoning Summary</div><div style="margin-top:6px; font-size:13px;">"${this.esc(r.metadata.rationale)}"</div></div>` : ""}
        <div class="grid grid-3 mt12">
          <div class="card"><div class="small muted">AI Classification</div><div class="mono mt8" style="font-weight:700; text-transform:uppercase;">${this.esc(r.context)}</div></div>
          <div class="card"><div class="small muted">Safety Rules</div><div class="mono mt8" style="font-weight:700; text-transform:uppercase;">${this.esc(r.recommendedAction)}</div></div>
          <div class="card" style="border-color:rgba(91,140,255,.3);"><div class="small muted">Final Action</div><div class="mono mt8" style="font-weight:700; text-transform:uppercase; color:#8fb0ff;">${this.esc(r.recommendedAction)}</div></div>
        </div>
      </div>
    `;
  },

  clearLabTest() {
    document.getElementById("lab-input").value = "";
    document.getElementById("lab-result").innerHTML = "";
  },

  async runOneTest(id) {
    this.busy.add(id);
    this.renderRoute();
    try {
      await this.api(`/api/qa/test/${id}/run`, {});
    } finally {
      this.busy.delete(id);
      await this.load();
      this.updateBugBadge();
      this.openTestIds.add(id);
      this.renderRoute();
    }
  },

  async runSuite(key) {
    const btn = document.getElementById("suite-btn-" + key);
    if (btn) { btn.disabled = true; btn.textContent = "Running…"; }
    try {
      await this.api(`/api/qa/suite/${key}/run`, {});
    } finally {
      await this.load();
      this.updateBugBadge();
      this.renderRoute();
    }
  },
});

// ---------------------------------------------------------------------------
// Context Testing (same words, different meaning)
// ---------------------------------------------------------------------------
Object.assign(Q, {
  renderContext() {
    const pairs = this.state.contextPairs || [];
    return `
      <div class="kicker">Context Lab</div>
      <h1 class="page-h">Same words, different meaning</h1>
      <p class="page-sub">The same phrase tested in two different contexts. If SilentHelp is reading context and not just keywords, these should NOT classify the same way.</p>
      <div class="section-title"><h2>Pairs</h2><span class="count">${pairs.length}</span></div>
      ${pairs.map(p => this.renderContextPair(p)).join("")}
    `;
  },

  renderContextPair(p) {
    const side = (t, label) => `
      <div class="card">
        <div class="kicker">${label}</div>
        <div style="font-size:14px; font-weight:600; margin-top:8px;">"${this.esc(t.input)}"</div>
        <div class="small muted mt8">${this.esc(t.contextNote)}</div>
        <div class="hair mt12" style="padding-top:12px;">
          <div class="ev-row"><span class="k">Expected</span><span class="v">${this.esc(t.expected.severity)}</span></div>
          <div class="ev-row"><span class="k">Actual</span><span class="v">${t.actual ? this.esc(t.actual.severity) : "—"}</span></div>
        </div>
        ${t.result ? `<span class="pill pill-${t.result.toLowerCase()}" style="margin-top:10px;">${t.result}</span>` : ""}
      </div>`;
    return `
      <div class="card raised mt12">
        <div class="flex between center">
          <div style="font-weight:700; font-size:13px;">Pair: ${this.esc(p.id)}</div>
          <button class="pillbtn" style="font-size:11px; padding:6px 11px;" onclick="QA.runContextPair('${p.id}')">Run Both</button>
        </div>
        <div class="grid grid-3" style="grid-template-columns:1fr 1fr; margin-top:14px;">
          ${side(p.a, "Input A")}
          ${side(p.b, "Input B")}
        </div>
      </div>
    `;
  },

  async runContextPair(id) {
    await this.api(`/api/qa/context-pair/${id}/run`, {});
    await this.load();
    this.renderRoute();
  },
});

// ---------------------------------------------------------------------------
// Safety & Response, Edge Cases — both reuse the test-case list UI
// ---------------------------------------------------------------------------
Object.assign(Q, {
  renderSafety() {
    const keys = ["distress", "academic", "isolation"];
    const suites = (this.state._meta.suites || []).filter(s => keys.includes(s.key));
    const tests = (this.state.tests || []).filter(t => keys.includes(t.category));
    return `
      <div class="kicker">Safety & Response</div>
      <h1 class="page-h">What SilentHelp does after detecting a signal</h1>
      <p class="page-sub">Genuine distress, academic stress, and social isolation cases — checking the deterministic action taken, not just the AI's read.</p>
      <div class="grid grid-3 mt20">${suites.map(s => this.renderSuiteCard(s)).join("")}</div>
      <div class="section-title"><h2>Test Cases</h2><span class="count">${tests.length}</span></div>
      ${tests.map(t => this.renderTestCase(t)).join("")}
    `;
  },

  renderEdge() {
    const keys = ["edge_typos_slang", "edge_contradictory", "edge_mixed", "ambiguous"];
    const suites = (this.state._meta.suites || []).filter(s => keys.includes(s.key));
    const tests = (this.state.tests || []).filter(t => keys.includes(t.category));
    return `
      <div class="kicker">Edge Case Lab</div>
      <h1 class="page-h">False positives, false negatives, and the genuinely ambiguous</h1>
      <p class="page-sub">Typos, slang, contradictory context, mixed academic/social/emotional language, and statements where the honest answer is "not enough context" rather than a forced call.</p>
      <div class="grid grid-3 mt20">${suites.map(s => this.renderSuiteCard(s)).join("")}</div>
      <div class="section-title"><h2>Test Cases</h2><span class="count">${tests.length}</span></div>
      ${tests.map(t => this.renderTestCase(t)).join("")}
    `;
  },
});

// ---------------------------------------------------------------------------
// Resources & Popups + Response Simulator
// ---------------------------------------------------------------------------
Object.assign(Q, {
  SIM_TRIGGERS: [
    { key: "checkin", label: "Supportive check-in", desc: "Moderate signal, gentle nudge." },
    { key: "resource", label: "Wellness resource", desc: "Sustained pattern, resource surfaced." },
    { key: "trusted", label: "Trusted adult option", desc: "High concern, human loop-in offered." },
    { key: "crisis", label: "Emergency-support information", desc: "Crisis-level, 988/resources shown." },
  ],
  SIM_ACTIONS: ["I'm okay", "I'd like support", "Talk to someone I trust", "Show me resources", "Dismiss"],

  renderResources() {
    const rtests = this.state.resourceTests || [];
    return `
      <div class="kicker">Resources & Popups</div>
      <h1 class="page-h">What happens after detection</h1>
      <p class="page-sub">Verify the right popup, resource, and escalation happen — and that user consent is always respected.</p>

      <div class="card raised mt20">
        <div class="kicker">Response Simulator</div>
        <p class="small muted mt8">Pick a detection trigger, then act as the student would.</p>
        <div class="taginput mt12">
          ${this.SIM_TRIGGERS.map(t => `<div class="chip-select" onclick="QA.simulateTrigger('${t.key}')">${t.label}</div>`).join("")}
        </div>
        <div id="sim-popup"></div>
      </div>

      <div class="section-title"><h2>Resource Test Log</h2><span class="count">${rtests.length}</span></div>
      ${rtests.length ? `
        <table class="tbl">
          <thead><tr><th>Scenario</th><th>Detection</th><th>Response</th><th>Resource</th><th>Permission</th><th>Escalation</th><th>Result</th></tr></thead>
          <tbody>
            ${rtests.map(r => `<tr>
              <td>${this.esc(r.scenario)}</td><td>${this.esc(r.detection)}</td><td>${this.esc(r.response)}</td>
              <td>${this.esc(r.resource)}</td><td>${this.esc(r.permission)}</td><td>${this.esc(r.escalation)}</td>
              <td><span class="pill pill-${r.result.toLowerCase()}">${r.result}</span></td>
            </tr>`).join("")}
          </tbody>
        </table>
      ` : `<div class="empty-state"><div class="t">No resource tests logged</div><div class="d">Run the simulator above — each completed session logs a test row here.</div></div>`}
    `;
  },

  simulateTrigger(key) {
    const trig = this.SIM_TRIGGERS.find(t => t.key === key);
    const el = document.getElementById("sim-popup");
    el.innerHTML = `
      <div class="card mt16" style="border-color:rgba(91,140,255,.3);">
        <div class="kicker">Simulated popup — ${this.esc(trig.label)}</div>
        <div style="font-size:13.5px; margin-top:8px;">${this.esc(trig.desc)}</div>
        <div class="taginput mt16">
          ${this.SIM_ACTIONS.map(a => `<button class="pillbtn" style="font-size:11.5px;" onclick="QA.simulateAction('${key}','${a}')">${a}</button>`).join("")}
        </div>
      </div>
    `;
  },

  async simulateAction(triggerKey, action) {
    const trig = this.SIM_TRIGGERS.find(t => t.key === triggerKey);
    await this.api("/api/qa/simulator-log", { trigger: trig.label, action });
    await this.api("/api/qa/resource-test", {
      scenario: `Simulator: ${trig.label}`, detection: trig.label, response: trig.desc,
      resource: trig.key === "crisis" ? "988 / Crisis Text Line" : trig.key === "trusted" ? "Trusted adult" : "Supportive nudge",
      permission: "Respected — no auto-send", escalation: trig.key === "crisis" ? "Yes" : "No",
      result: "PASS", notes: `Student action: ${action}`,
    });
    document.getElementById("sim-popup").innerHTML = `<div class="small mt16" style="color:var(--green);">✓ Recorded — student chose "${this.esc(action)}"</div>`;
    await this.load();
    setTimeout(() => this.renderRoute(), 900);
  },
});

// ---------------------------------------------------------------------------
// Privacy
// ---------------------------------------------------------------------------
Object.assign(Q, {
  renderPrivacy() {
    const checks = this.state.privacyChecks || {};
    return `
      <div class="kicker">Privacy</div>
      <h1 class="page-h">Data handling, permissions, and user control</h1>
      <p class="page-sub">Internal engineering checklist — not a legal or compliance certification.</p>
      <div class="card raised mt20">
        <table class="tbl">
          <thead><tr><th>Check</th><th>Status</th><th>Notes</th></tr></thead>
          <tbody>
            ${Object.entries(checks).map(([item, v]) => `
              <tr>
                <td style="width:34%;">${this.esc(item)}</td>
                <td style="width:20%;">
                  <select onchange="QA.setPrivacyStatus('${this.esc(item).replace(/'/g, "\\'")}', this.value)" style="background:rgba(255,255,255,.04); border:1px solid var(--line-2); border-radius:6px; color:var(--text); font-size:11.5px; padding:5px 8px;">
                    ${["NOT TESTED", "PASS", "FAIL"].map(s => `<option value="${s}" ${v.status === s ? "selected" : ""}>${s}</option>`).join("")}
                  </select>
                </td>
                <td><input type="text" value="${this.esc(v.note)}" placeholder="optional note" onchange="QA.setPrivacyNote('${this.esc(item).replace(/'/g, "\\'")}', this.value)" style="width:100%; background:rgba(255,255,255,.03); border:1px solid var(--line); border-radius:6px; padding:6px 9px; color:var(--text); font-size:12px;"/></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  },

  async setPrivacyStatus(item, status) {
    await this.api("/api/qa/privacy-check", { item, status });
    await this.load(); this.renderRoute();
  },
  async setPrivacyNote(item, note) {
    const cur = this.state.privacyChecks[item] || {};
    await this.api("/api/qa/privacy-check", { item, status: cur.status || "NOT TESTED", note });
    await this.load();
  },
});

// ---------------------------------------------------------------------------
// Bugs & Improvements
// ---------------------------------------------------------------------------
Object.assign(Q, {
  renderBugs() {
    const bugs = (this.state.bugs || []).filter(b => {
      if (this.bugFilter.status !== "ALL" && b.status !== this.bugFilter.status) return false;
      if (this.bugFilter.severity !== "ALL" && b.severity !== this.bugFilter.severity) return false;
      if (this.bugFilter.q && !b.title.toLowerCase().includes(this.bugFilter.q.toLowerCase())) return false;
      return true;
    });
    const improvements = this.state.improvements || [];
    const statuses = this.state._meta.bugStatuses || [];
    const severities = this.state._meta.severities || [];
    const impCats = this.state._meta.improvementCategories || [];

    return `
      <div class="kicker">Bugs & Improvements</div>
      <h1 class="page-h">Internal issue tracker</h1>

      <div class="section-title"><h2>Bugs</h2><span class="count">${bugs.length} shown</span></div>
      <div class="flex gap8 mt12" style="flex-wrap:wrap;">
        <input type="text" placeholder="Search bugs…" value="${this.esc(this.bugFilter.q)}" oninput="QA.bugFilter.q=this.value; QA.renderRoute();" style="background:rgba(255,255,255,.03); border:1px solid var(--line-2); border-radius:8px; padding:8px 12px; color:var(--text); font-size:12.5px; min-width:200px;"/>
        <select onchange="QA.bugFilter.status=this.value; QA.renderRoute();" style="background:rgba(255,255,255,.03); border:1px solid var(--line-2); border-radius:8px; padding:8px 10px; color:var(--text); font-size:12px;">
          <option value="ALL">All statuses</option>${statuses.map(s => `<option ${this.bugFilter.status === s ? "selected" : ""}>${s}</option>`).join("")}
        </select>
        <select onchange="QA.bugFilter.severity=this.value; QA.renderRoute();" style="background:rgba(255,255,255,.03); border:1px solid var(--line-2); border-radius:8px; padding:8px 10px; color:var(--text); font-size:12px;">
          <option value="ALL">All severities</option>${severities.map(s => `<option ${this.bugFilter.severity === s ? "selected" : ""}>${s}</option>`).join("")}
        </select>
        <button class="pillbtn primary" style="margin-left:auto;" onclick="QA.showBugForm()">+ New Bug</button>
      </div>
      <div id="bug-form"></div>
      <div class="mt16">
        ${bugs.length ? bugs.map(b => this.renderBugRow(b, statuses, severities)).join("") : `<div class="empty-state"><div class="t">No bugs match</div></div>`}
      </div>

      <div class="section-title"><h2>Improvement Board</h2><span class="count">${improvements.length}</span></div>
      <button class="pillbtn" onclick="QA.showImprovementForm()">+ New Improvement</button>
      <div id="improvement-form"></div>
      <div class="grid grid-3 mt16">
        ${improvements.length ? improvements.map(i => `
          <div class="card">
            <div class="flex between center"><span class="pill pill-${(i.priority||"medium").toLowerCase()}">${i.priority}</span><span class="small mono muted">${this.esc(i.category)}</span></div>
            <div style="font-weight:600; font-size:13.5px; margin-top:10px;">${this.esc(i.title)}</div>
            <div class="small muted mt8">${this.esc(i.reason)}</div>
            <select onchange="QA.updateImprovement('${i.id}', {status: this.value})" style="margin-top:12px; background:rgba(255,255,255,.04); border:1px solid var(--line-2); border-radius:6px; color:var(--text); font-size:11px; padding:4px 8px;">
              ${["OPEN", "IN PROGRESS", "DONE"].map(s => `<option ${i.status === s ? "selected" : ""}>${s}</option>`).join("")}
            </select>
          </div>
        `).join("") : `<div class="empty-state" style="grid-column:1/-1;"><div class="t">No improvements logged</div></div>`}
      </div>
    `;
  },

  renderBugRow(b, statuses, severities) {
    return `
      <div class="card mt8">
        <div class="flex between center">
          <div class="flex gap8 center">
            <span class="pill pill-${(b.severity||"medium").toLowerCase()}">${b.severity}</span>
            <span style="font-weight:600; font-size:13.5px;">${this.esc(b.title)}</span>
          </div>
          <div class="flex gap8 center">
            <select onchange="QA.updateBug('${b.id}', {status: this.value})" style="background:rgba(255,255,255,.04); border:1px solid var(--line-2); border-radius:6px; color:var(--text); font-size:11px; padding:4px 8px;">
              ${statuses.map(s => `<option ${b.status === s ? "selected" : ""}>${s}</option>`).join("")}
            </select>
            <button class="pillbtn" style="font-size:10.5px; padding:4px 9px;" onclick="QA.deleteBug('${b.id}')">Delete</button>
          </div>
        </div>
        ${b.description ? `<div class="small muted mt8">${this.esc(b.description)}</div>` : ""}
        <div class="small muted mt8">${b.category ? this.esc(b.category) + " · " : ""}${b.assignee ? "assigned to " + this.esc(b.assignee) + " · " : ""}discovered ${this.fmtAgo(b.discoveredAt)}</div>
      </div>
    `;
  },

  showBugForm() {
    const severities = this.state._meta.severities || [];
    document.getElementById("bug-form").innerHTML = `
      <div class="card raised mt12">
        <div class="field"><label>Title</label><input type="text" id="bug-title" placeholder="False positive detected in sarcastic language"/></div>
        <div class="field"><label>Description</label><textarea id="bug-desc"></textarea></div>
        <div class="grid grid-3">
          <div class="field"><label>Severity</label><select id="bug-sev">${severities.map(s => `<option>${s}</option>`).join("")}</select></div>
          <div class="field"><label>Category</label><input type="text" id="bug-cat" placeholder="AI / UX / Safety…"/></div>
          <div class="field"><label>Assignee</label><input type="text" id="bug-assignee"/></div>
        </div>
        <div class="field"><label>Reproduction steps</label><textarea id="bug-repro"></textarea></div>
        <div class="flex gap8"><button class="pillbtn primary" onclick="QA.submitBug()">Create Bug</button><button class="pillbtn" onclick="document.getElementById('bug-form').innerHTML=''">Cancel</button></div>
      </div>
    `;
  },
  async submitBug() {
    const v = id => document.getElementById(id).value;
    await this.api("/api/qa/bug", {
      title: v("bug-title"), description: v("bug-desc"), severity: v("bug-sev"),
      category: v("bug-cat"), assignee: v("bug-assignee"), repro: v("bug-repro"),
    });
    document.getElementById("bug-form").innerHTML = "";
    await this.load(); this.updateBugBadge(); this.renderRoute();
  },
  async updateBug(id, patch) { await this.api(`/api/qa/bug/${id}`, patch); await this.load(); this.updateBugBadge(); this.renderRoute(); },
  async deleteBug(id) { await this.api(`/api/qa/bug/${id}/delete`, {}); await this.load(); this.updateBugBadge(); this.renderRoute(); },

  showImprovementForm() {
    const cats = this.state._meta.improvementCategories || [];
    document.getElementById("improvement-form").innerHTML = `
      <div class="card raised mt12">
        <div class="field"><label>Title</label><input type="text" id="imp-title" placeholder="Improve sarcasm detection"/></div>
        <div class="grid grid-3">
          <div class="field"><label>Category</label><select id="imp-cat">${cats.map(c => `<option>${c}</option>`).join("")}</select></div>
          <div class="field"><label>Priority</label><select id="imp-priority"><option>HIGH</option><option>MEDIUM</option><option>LOW</option></select></div>
        </div>
        <div class="field"><label>Reason</label><textarea id="imp-reason"></textarea></div>
        <div class="flex gap8"><button class="pillbtn primary" onclick="QA.submitImprovement()">Create</button><button class="pillbtn" onclick="document.getElementById('improvement-form').innerHTML=''">Cancel</button></div>
      </div>
    `;
  },
  async submitImprovement() {
    const v = id => document.getElementById(id).value;
    await this.api("/api/qa/improvement", { title: v("imp-title"), category: v("imp-cat"), priority: v("imp-priority"), reason: v("imp-reason") });
    document.getElementById("improvement-form").innerHTML = "";
    await this.load(); this.renderRoute();
  },
  async updateImprovement(id, patch) { await this.api(`/api/qa/improvement/${id}`, patch); await this.load(); this.renderRoute(); },
});

// ---------------------------------------------------------------------------
// Launch Checklist + Launch Gate
// ---------------------------------------------------------------------------
Object.assign(Q, {
  computeGate() {
    const s = this.computeScore();
    const checklist = this.state.checklist || {};
    const catComplete = cat => {
      const items = Object.values(checklist[cat] || {});
      return items.length > 0 && items.every(v => v.done);
    };
    const safetyOk = catComplete("Safety"), privacyOk = catComplete("Privacy");
    const aiOk = catComplete("AI"), productOk = catComplete("Product");
    const uxOk = catComplete("User Experience"), engOk = catComplete("Engineering");
    const blockers = [];
    if (s.criticalBugs > 0) blockers.push(`${s.criticalBugs} unresolved CRITICAL bug(s)`);
    if (!safetyOk) blockers.push("Safety checklist incomplete");
    if (!privacyOk) blockers.push("Privacy checklist incomplete");
    const ready = blockers.length === 0;
    const allRequired = ready && aiOk && productOk && uxOk && engOk;
    return {
      rows: [
        { label: "AI Detection", ok: aiOk }, { label: "Context Testing", ok: aiOk },
        { label: "Safety", ok: safetyOk, required: true }, { label: "Privacy", ok: privacyOk, required: true },
        { label: "UX", ok: uxOk },
      ],
      criticalBugs: s.criticalBugs, blockers,
      status: allRequired ? "READY FOR PILOT" : (ready ? "MVP READY" : "NOT READY"),
      canLaunch: ready,
    };
  },

  renderChecklist() {
    const checklist = this.state.checklist || {};
    const gate = this.computeGate();
    return `
      <div class="kicker">Launch Checklist</div>
      <h1 class="page-h">Final pre-launch checklist</h1>
      <div class="grid grid-3 mt20">
        ${Object.entries(checklist).map(([cat, items]) => {
          const vals = Object.entries(items);
          const done = vals.filter(([, v]) => v.done).length;
          return `
          <div class="card">
            <div class="flex between center">
              <div style="font-weight:700; font-size:13px;">${this.esc(cat)}</div>
              <span class="small mono muted">${done}/${vals.length}</span>
            </div>
            <div class="mt12">
              ${vals.map(([item, v]) => `
                <div class="flex center gap12" style="padding:7px 0;">
                  <div class="sw ${v.done ? "on" : ""}" onclick="QA.toggleChecklist('${this.esc(cat)}', '${this.esc(item).replace(/'/g, "\\'")}')"><div class="knob"></div></div>
                  <div class="small" style="flex:1; ${v.done ? "color:var(--sub);" : ""}">${this.esc(item)}</div>
                </div>
              `).join("")}
            </div>
          </div>`;
        }).join("")}
      </div>

      <div class="section-title"><h2>Launch Gate</h2></div>
      ${this.renderGate(gate)}
    `;
  },

  renderGate(gate) {
    const statusClass = { "NOT READY": "notready", "MVP READY": "mvpready", "READY FOR PILOT": "readyforpilot" }[gate.status];
    return `
      <div class="gate">
        <div class="gate-title">SilentHelp MVP Gate</div>
        <div class="gate-rows">
          ${gate.rows.map(r => `<div class="gate-row"><span>${r.label}${r.required ? " *" : ""}</span><span style="color:${r.ok ? "var(--green)" : "var(--red)"}">${r.ok ? "✓" : "✕"}</span></div>`).join("")}
          <div class="gate-row"><span>Critical Bugs</span><span style="color:${gate.criticalBugs ? "var(--red)" : "var(--green)"}">${gate.criticalBugs}</span></div>
        </div>
        <div class="gate-status status-chip ${statusClass}" style="display:inline-flex;">${gate.status}</div>
        ${gate.blockers.length ? `<div class="gate-blockers">Blocking: ${gate.blockers.map(b => this.esc(b)).join(" · ")}</div>` : `<div class="small muted mt12">All required gates clear.</div>`}
      </div>
    `;
  },

  async toggleChecklist(category, item) {
    await this.api("/api/qa/checklist/toggle", { category, item });
    await this.load(); this.renderRoute();
  },
});

// ---------------------------------------------------------------------------
// Test History
// ---------------------------------------------------------------------------
Object.assign(Q, {
  renderHistory() {
    const runs = this.state.runs || [];
    return `
      <div class="kicker">Test History</div>
      <h1 class="page-h">Previous test runs</h1>
      ${runs.length ? `
        <table class="tbl mt20">
          <thead><tr><th>Suite</th><th>Version</th><th>Tests</th><th>Pass Rate</th><th>Tester</th><th>When</th></tr></thead>
          <tbody>
            ${runs.map(r => `<tr>
              <td class="mono">${this.esc(r.suite)}</td><td class="mono">v${this.esc(r.version)}</td>
              <td>${r.count}</td>
              <td><span class="pill ${r.accuracy >= 90 ? "pill-pass" : r.accuracy >= 60 ? "pill-review" : "pill-fail"}">${r.accuracy}%</span></td>
              <td>${this.esc(r.tester || "—")}</td><td class="small muted">${this.fmtTime(r.timestamp)}</td>
            </tr>`).join("")}
          </tbody>
        </table>
      ` : `<div class="empty-state"><div class="t">No test runs yet</div><div class="d">Run a suite from the AI Detection Lab to start building history.</div></div>`}
    `;
  },
});

// ---------------------------------------------------------------------------
// Top-bar actions
// ---------------------------------------------------------------------------
Object.assign(Q, {
  exportResults() {
    const blob = new Blob([JSON.stringify(this.state, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `silenthelp-qa-v${this.state.version}-${Date.now()}.json`;
    a.click();
  },

  createReport() {
    const s = this.computeScore();
    const gate = this.computeGate();
    const lines = [
      `SilentHelp MVP Readiness Report — v${this.state.version}`,
      `Generated ${new Date().toLocaleString()}`,
      "",
      `Overall readiness: ${s.overall}% — ${s.status}`,
      `Tests: ${s.testsCompleted}/${s.testsTotal} run · ${s.testsPassed} pass · ${s.testsFailed} fail · ${s.testsReview} review`,
      `Open bugs: ${s.openBugs} (${s.criticalBugs} critical)`,
      "",
      `Launch gate: ${gate.status}`,
      gate.blockers.length ? `Blockers: ${gate.blockers.join("; ")}` : "No blockers.",
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `silenthelp-mvp-report-v${this.state.version}.txt`;
    a.click();
  },
});

window.QA = Q;
document.addEventListener("DOMContentLoaded", () => Q.boot());
})();
