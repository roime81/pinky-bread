(() => {
  const $ = (selector) => document.querySelector(selector);
  const state = {
    companies: [],
    company: null,
    graph: { nodes: [], edges: [] },
    selectedId: null,
    connectMode: false,
    connectSource: null,
    eventSource: null,
    pollHandle: null,
    jobsPollHandle: null,
    jobsLoading: false,
    jobs: [],
    coordination: null,
    loading: false,
  };

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
    return payload;
  }

  function showError(message) {
    const target = $("#company-event-list");
    if (target) target.innerHTML = `<div class="graph-error">${escapeHtml(message)}</div>`;
  }

  function setWorkspaceVisible(hasCompany) {
    $("#company-onboarding").hidden = hasCompany;
    $("#company-dashboard").hidden = !hasCompany;
  }

  async function initialise() {
    try {
      state.companies = (await api("/v2/companies?tenant_id=demo-tenant")).companies || [];
      renderCompanyPicker();
      if (!state.companies.length) {
        setWorkspaceVisible(false);
        return;
      }
      state.company = state.companies[0];
      $("#graph-company-picker").value = state.company.id;
      await api(`/v2/companies/${state.company.id}/workforce/bootstrap`, {
        method: "POST",
        body: JSON.stringify({ tenant_id: state.company.tenant_id, actor_id: "founder" }),
      });
      await loadGraph(true);
    } catch (error) {
      setWorkspaceVisible(false);
      showError(`Company graph API unavailable: ${error.message}`);
    }
  }

  function renderCompanyPicker() {
    const picker = $("#graph-company-picker");
    if (!picker) return;
    picker.innerHTML = state.companies.map((company) =>
      `<option value="${escapeHtml(company.id)}">${escapeHtml(company.name)}</option>`
    ).join("");
  }

  async function createNode(nodeType, name, description, data = {}, status = "PLANNED") {
    const node = await api(`/v2/companies/${state.company.id}/nodes`, {
      method: "POST",
      body: JSON.stringify({
        tenant_id: state.company.tenant_id,
        actor_id: "founder",
        node_type: nodeType,
        name,
        description,
        status,
        data,
      }),
    });
    const parent = nodeType === "agent"
      ? (data.manager_id
        ? state.graph.nodes.find((item) => item.id === data.manager_id)
        : state.graph.nodes.find((item) => item.type === "agent" && ["chief_of_staff", "head_of_agents"].includes(item.data?.role)))
      : null;
    const selectedGoal = nodeType === "kpi"
      ? state.graph.nodes.find((item) => item.id === state.selectedId && item.type === "goal")
      : null;
    const sourceId = selectedGoal ? selectedGoal.id : parent ? node.id : state.company.id;
    const targetId = selectedGoal ? node.id : parent ? parent.id : node.id;
    const relationship = selectedGoal ? "measures" : parent ? "reports_to" : "owns";
    await api(`/v2/companies/${state.company.id}/edges`, {
      method: "POST",
      body: JSON.stringify({
        tenant_id: state.company.tenant_id,
        actor_id: "founder",
        source_node_id: sourceId,
        target_node_id: targetId,
        relationship,
        data: { created_from: "company_graph_workspace" },
      }),
    });
    await loadGraph();
    selectNode(node.id);
    return node;
  }

  async function loadGraph(reconnect = false) {
    if (!state.company || state.loading) return;
    state.loading = true;
    try {
      state.graph = await api(`/v2/companies/${state.company.id}/graph?tenant_id=${encodeURIComponent(state.company.tenant_id)}`);
      renderGraph();
      await loadEvents();
      await loadJobs();
      if (reconnect) connectLiveEvents();
      startJobsPolling();
    } catch (error) {
      showError(error.message);
    } finally {
      state.loading = false;
    }
  }

  function stableHash(value) {
    let hash = 2166136261;
    for (const char of String(value)) {
      hash ^= char.charCodeAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function layoutNodes(nodes, edges) {
    const width = 1000;
    const height = 650;
    const center = { x: width / 2, y: height / 2 + 4 };
    const root = nodes.find((node) => node.type === "company");
    const others = nodes.filter((node) => node.type !== "company");
    const groups = {
      goal: -2.35, kpi: -1.8, agent: -0.65, department: -0.95,
      work: 0.15, deliverable: 0.55, meeting: 1.5,
      decision: 2.35, document: 2.9, customer: 3.55, integration: -0.1,
    };
    const positions = new Map();
    if (root) positions.set(root.id, { ...center });
    others.forEach((node, index) => {
      const angle = (groups[node.type] ?? 0.3) + ((stableHash(node.id) % 1000) / 1000 - 0.5) * 0.75 + Math.floor(index / 9) * 0.18;
      const ring = 125 + (index % 3) * 65 + Math.floor(index / 10) * 25;
      positions.set(node.id, {
        x: center.x + Math.cos(angle) * ring,
        y: center.y + Math.sin(angle) * ring,
      });
    });

    // A small deterministic relaxation prevents dots from sitting on top of each other.
    for (let step = 0; step < 35; step += 1) {
      for (let i = 0; i < others.length; i += 1) {
        const a = positions.get(others[i].id);
        for (let j = i + 1; j < others.length; j += 1) {
          const b = positions.get(others[j].id);
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const distance = Math.max(1, Math.hypot(dx, dy));
          if (distance < 76) {
            const push = (76 - distance) * 0.018;
            const px = (dx / distance) * push;
            const py = (dy / distance) * push;
            a.x -= px; a.y -= py; b.x += px; b.y += py;
          }
        }
        a.x += (center.x - a.x) * 0.0015;
        a.y += (center.y - a.y) * 0.0015;
        a.x = Math.max(55, Math.min(width - 55, a.x));
        a.y = Math.max(55, Math.min(height - 55, a.y));
      }
    }
    return positions;
  }

  function renderGraph() {
    const svg = $("#company-graph-svg");
    if (!svg) return;
    const nodes = state.graph.nodes || [];
    const edges = state.graph.edges || [];
    const positions = layoutNodes(nodes, edges);
    const activeIds = new Set();
    if (state.selectedId) {
      edges.filter((edge) => edge.source === state.selectedId || edge.target === state.selectedId)
        .forEach((edge) => { activeIds.add(edge.id); });
    }

    const edgeMarkup = edges.map((edge) => {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return "";
      const active = activeIds.has(edge.id);
      const dx = target.x - source.x;
      const dy = target.y - source.y;
      const length = Math.max(1, Math.hypot(dx, dy));
      const x1 = source.x + (dx / length) * 18;
      const y1 = source.y + (dy / length) * 18;
      const x2 = target.x - (dx / length) * 15;
      const y2 = target.y - (dy / length) * 15;
      const midX = (x1 + x2) / 2;
      const midY = (y1 + y2) / 2;
      return `<g><line class="graph-edge ${active ? "is-active" : state.selectedId ? "is-muted" : ""}" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" /><text class="graph-edge-label" x="${midX.toFixed(1)}" y="${(midY - 5).toFixed(1)}" text-anchor="middle" opacity="${active ? "1" : "0"}">${escapeHtml(edge.relationship.replaceAll("_", " "))}</text></g>`;
    }).join("");

    const nodeMarkup = nodes.map((node) => {
      const point = positions.get(node.id);
      if (!point) return "";
      const selected = node.id === state.selectedId;
      const radius = node.type === "company" ? 17 : node.type === "agent" ? 11 : node.type === "goal" ? 10 : 7;
      const status = (node.status || "").toLowerCase().replaceAll(" ", "_");
      const shortLabel = node.name.length > 25 ? `${node.name.slice(0, 23)}…` : node.name;
      const subLabel = node.type === "company" ? "FOUNDER" : node.type.toUpperCase();
      return `<g class="graph-node ${escapeHtml(node.type)} status-${escapeHtml(status)} ${selected ? "selected" : ""}" data-node-id="${escapeHtml(node.id)}" transform="translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})" tabindex="0" role="button" aria-label="Inspect ${escapeHtml(node.name)}">
        <circle class="node-halo" r="${radius + 9}"></circle>
        <circle class="node-core" r="${radius}"></circle>
        <text y="${radius + 17}">${escapeHtml(shortLabel)}</text>
        <text class="node-sub" y="${radius + 29}">${subLabel}</text>
      </g>`;
    }).join("");

    svg.innerHTML = `<g class="graph-edges">${edgeMarkup}</g><g class="graph-nodes">${nodeMarkup}</g>`;
    svg.querySelectorAll("[data-node-id]").forEach((element) => {
      element.addEventListener("click", () => onNodeClick(element.dataset.nodeId));
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onNodeClick(element.dataset.nodeId);
        }
      });
    });

    $("#graph-node-count").textContent = `${nodes.length} NODES`;
    $("#graph-goal-count").textContent = nodes.filter((node) => node.type === "goal").length;
    $("#graph-agent-count").textContent = nodes.filter((node) => node.type === "agent").length;
    $("#graph-work-count").textContent = nodes.filter((node) => node.type === "work").length;
    $("#graph-company-name").textContent = state.company.name;
    $("#graph-company-mission").textContent = state.company.data?.mission || state.company.description || "Company workspace";
    if (state.selectedId) selectNode(state.selectedId, false);
  }

  async function loadJobs() {
    if (!state.company || state.jobsLoading) return;
    state.jobsLoading = true;
    try {
      const tenant = encodeURIComponent(state.company.tenant_id);
      const [jobsResult, coordinationResult] = await Promise.all([
        api(`/v2/companies/${state.company.id}/jobs?tenant_id=${tenant}&limit=30`),
        api(`/v2/companies/${state.company.id}/coordination?tenant_id=${tenant}`),
      ]);
      state.jobs = jobsResult.jobs || [];
      state.coordination = coordinationResult.coordination || null;
      renderJobs();
      renderCoordination();
    } catch (error) {
      const target = $("#company-job-list");
      if (target) target.innerHTML = `<div class="graph-error">${escapeHtml(error.message)}</div>`;
    } finally {
      state.jobsLoading = false;
    }
  }

  function renderJobs() {
    const target = $("#company-job-list");
    if (!target) return;
    const jobs = state.jobs || [];
    $("#graph-job-count").textContent = `${jobs.length} jobs`;
    target.innerHTML = jobs.slice(0, 25).map((job) => {
      const status = String(job.status || "PENDING").toLowerCase();
      const title = job.payload?.source === "company_coordination"
        ? "Head of Agents · recurring coordination"
        : `${String(job.kind || "job").replaceAll("_", " ")}`;
      const stamp = job.created_at ? new Date(job.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
      const attempts = `attempt ${job.attempts}/${job.max_attempts}`;
      const canCancel = ["PENDING", "RUNNING"].includes(job.status);
      return `<div class="company-job">
        <div class="company-job-main">
          <strong>${escapeHtml(title)}</strong>
          <small>${escapeHtml(job.target_id)} · ${escapeHtml(stamp)} · ${escapeHtml(attempts)}</small>
        </div>
        <span class="company-job-status ${escapeHtml(status)}">${escapeHtml(status)}</span>
        ${canCancel ? `<button class="graph-tool-btn" data-cancel-job="${escapeHtml(job.job_id)}">Cancel</button>` : ""}
      </div>`;
    }).join("") || '<div class="empty-state">No durable jobs yet. Plan or execute a goal to enqueue one.</div>';
  }

  function renderCoordination() {
    const policy = state.coordination;
    const stateLabel = $("#coordination-state");
    if (!stateLabel) return;
    stateLabel.textContent = !policy?.enabled
      ? "Not scheduled"
      : `${policy.mode.replaceAll("_", " ")} · every ${Math.round(policy.interval_seconds / 60)} min`;
    $("#coordination-plan-only")?.classList.toggle("is-enabled", policy?.enabled && policy?.mode === "PLAN_ONLY");
    $("#coordination-auto-execute")?.classList.toggle("is-enabled", policy?.enabled && policy?.mode === "AUTO_EXECUTE");
    $("#coordination-stop")?.classList.toggle("is-enabled", !policy?.enabled);
  }

  function startJobsPolling() {
    if (state.jobsPollHandle) return;
    state.jobsPollHandle = window.setInterval(() => loadJobs(), 2500);
  }

  function stopJobsPolling() {
    if (!state.jobsPollHandle) return;
    window.clearInterval(state.jobsPollHandle);
    state.jobsPollHandle = null;
  }

  async function configureCoordination(enabled, mode = "PLAN_ONLY") {
    if (!state.company) return;
    if (enabled && mode === "AUTO_EXECUTE") {
      const approved = window.confirm(
        "Enable continuous goal execution? The worker will run assignments for active goals without asking before each task. External financial, legal and customer-facing actions remain unavailable in this alpha."
      );
      if (!approved) return;
    }
    try {
      const result = await api(`/v2/companies/${state.company.id}/coordination`, {
        method: "PUT",
        body: JSON.stringify({
          tenant_id: state.company.tenant_id,
          actor_id: "founder",
          enabled,
          mode,
          interval_seconds: 300,
        }),
      });
      state.coordination = result.coordination;
      renderCoordination();
      toast(!enabled ? "Head of Agents coordination paused" : `Coordination enabled · ${mode.replaceAll("_", " ")}`);
      await loadJobs();
    } catch (error) { toast(error.message); }
  }

  async function enqueueGoalJob(goalId, kind) {
    if (!state.company) return;
    const result = await api(`/v2/companies/${state.company.id}/goals/${goalId}/jobs`, {
      method: "POST",
      body: JSON.stringify({
        tenant_id: state.company.tenant_id,
        actor_id: "founder",
        kind,
        idempotency_key: `founder-ui:${kind}:${goalId}:${Math.floor(Date.now() / 30000)}`,
      }),
    });
    await loadJobs();
    return result;
  }

  $("#company-job-list")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-cancel-job]");
    if (!button || !state.company) return;
    button.disabled = true;
    try {
      await api(`/v2/companies/${state.company.id}/jobs/${button.dataset.cancelJob}/cancel`, {
        method: "POST",
        body: JSON.stringify({ tenant_id: state.company.tenant_id, actor_id: "founder" }),
      });
      toast("Cancellation requested");
      await loadJobs();
    } catch (error) { toast(error.message); }
    finally { button.disabled = false; }
  });

  function onNodeClick(nodeId) {
    if (state.connectMode) {
      if (!state.connectSource) {
        state.connectSource = nodeId;
        $("#graph-mode-label").textContent = "SELECT SECOND NODE";
        $("#graph-connect").classList.add("connecting");
        return;
      }
      if (state.connectSource === nodeId) return;
      const source = state.connectSource;
      const target = nodeId;
      const relationship = prompt("Relationship type (for example: contributes_to, assigned_to, collaborates_with):", "collaborates_with");
      state.connectMode = false;
      state.connectSource = null;
      $("#graph-connect").classList.remove("connecting");
      $("#graph-mode-label").textContent = "ALL RELATIONSHIPS";
      if (relationship) createEdge(source, target, relationship.trim());
      return;
    }
    selectNode(nodeId);
  }

  async function createEdge(source, target, relationship) {
    try {
      await api(`/v2/companies/${state.company.id}/edges`, {
        method: "POST",
        body: JSON.stringify({
          tenant_id: state.company.tenant_id,
          actor_id: "founder",
          source_node_id: source,
          target_node_id: target,
          relationship,
          data: { created_from: "company_graph_workspace" },
        }),
      });
      await loadGraph();
      toast("Relationship added to the company graph");
    } catch (error) {
      toast(error.message);
    }
  }

  function selectNode(nodeId, rerender = true) {
    state.selectedId = nodeId;
    const node = state.graph.nodes.find((item) => item.id === nodeId);
    if (!node) return;
    const relatedEdges = state.graph.edges.filter((edge) => edge.source === nodeId || edge.target === nodeId);
    const related = relatedEdges.map((edge) => {
      const otherId = edge.source === nodeId ? edge.target : edge.source;
      const other = state.graph.nodes.find((item) => item.id === otherId);
      return other ? { edge, node: other } : null;
    }).filter(Boolean);
    const dataEntries = Object.entries(node.data || {}).slice(0, 12);
    $("#graph-inspector").innerHTML = `
      <div class="inspector-top"><div><div class="inspector-kind">${escapeHtml(node.type)} / NODE</div><h3 class="inspector-title">${escapeHtml(node.name)}</h3></div><span class="inspector-status">${escapeHtml(node.status)}</span></div>
      <p class="inspector-description">${escapeHtml(node.description || "No description has been added yet.")}</p>
      <div class="inspector-divider"></div>
      <div class="inspector-section-title">IDENTITY & OWNERSHIP</div>
      <div class="inspector-properties">
        <div class="inspector-property"><span>Node ID</span><b>${escapeHtml(node.id)}</b></div>
        <div class="inspector-property"><span>Created by</span><b>${escapeHtml(node.created_by)}</b></div>
        <div class="inspector-property"><span>Created</span><b>${escapeHtml(node.created_at || "—")}</b></div>
      </div>
      ${dataEntries.length ? `<div class="inspector-divider"></div><div class="inspector-section-title">PROPERTIES</div><div class="inspector-properties">${dataEntries.map(([key, value]) => `<div class="inspector-property"><span>${escapeHtml(key.replaceAll("_", " "))}</span><b>${escapeHtml(typeof value === "object" ? JSON.stringify(value) : value)}</b></div>`).join("")}</div>` : ""}
      <div class="inspector-divider"></div><div class="inspector-section-title">CONNECTED NODES · ${related.length}</div>
      <div class="inspector-links">${related.map(({ edge, node: other }) => `<div class="inspector-link"><span>${escapeHtml(edge.relationship.replaceAll("_", " "))} · ${escapeHtml(other.name)}</span><small>${escapeHtml(other.type)}</small></div>`).join("") || '<span class="inspector-description">No relationships yet.</span>'}</div>
      <div class="inspector-divider"></div><button class="secondary-btn" id="inspect-connect-node">Connect this dot</button>
    `;
    $("#inspect-connect-node").addEventListener("click", () => {
      state.connectMode = true;
      state.connectSource = nodeId;
      $("#graph-connect").classList.add("connecting");
      $("#graph-mode-label").textContent = "SELECT SECOND NODE";
      toast("Select another dot to connect it");
    });

    const actions = [];
    if (node.type === "goal") {
      actions.push('<button class="secondary-btn" id="inspect-plan-goal">Plan with Head of Agents</button>');
      actions.push('<button class="primary-btn" id="inspect-run-goal">Execute goal workflow</button>');
    }
    if (node.type === "work" && node.status !== "COMPLETED") {
      actions.push('<button class="primary-btn" id="inspect-execute-work">Execute this assignment</button>');
    }
    if (node.type === "meeting" && node.status !== "COMPLETED") {
      actions.push('<button class="primary-btn" id="inspect-convene-meeting">Convene agent meeting</button>');
    }
    if (node.type === "kpi") {
      actions.push('<button class="secondary-btn" id="inspect-record-kpi">Record KPI measurement</button>');
    }
    if (node.data?.download_endpoint) {
      actions.push(`<a class="secondary-btn graph-download-link" href="${escapeHtml(node.data.download_endpoint)}" target="_blank" rel="noopener">Download stored output</a>`);
    }
    if (actions.length) {
      $("#graph-inspector").insertAdjacentHTML("beforeend", `<div class="inspector-divider"></div><div class="inspector-section-title">ACTIONS</div><div class="inspector-actions">${actions.join("")}</div>`);
    }
    $("#inspect-plan-goal")?.addEventListener("click", () => planGoal(nodeId));
    $("#inspect-run-goal")?.addEventListener("click", () => runGoal(nodeId));
    $("#inspect-execute-work")?.addEventListener("click", () => executeWork(nodeId, node.status === "FAILED"));
    $("#inspect-convene-meeting")?.addEventListener("click", () => conveneMeetingNode(nodeId));
    $("#inspect-record-kpi")?.addEventListener("click", () => recordKpi(nodeId));
    if (rerender) renderGraph();
  }

  async function loadEvents() {
    const result = await api(`/v2/companies/${state.company.id}/events?tenant_id=${encodeURIComponent(state.company.tenant_id)}&limit=50`);
    const events = result.events || [];
    $("#graph-event-count").textContent = `${events.length} events`;
    $("#company-event-list").innerHTML = events.slice(-12).reverse().map((event) => {
      const time = event.occurred_at ? new Date(event.occurred_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
      const name = event.payload?.name || event.payload?.node_id || event.payload?.relationship || "";
      return `<div class="company-event"><time>${escapeHtml(time)}</time><strong>${escapeHtml(event.type.replaceAll(".", " ").replaceAll("_", " "))}</strong><span>${escapeHtml(String(name).slice(0, 38))}</span></div>`;
    }).join("") || '<div class="empty-state">No company events yet.</div>';
  }

  function connectLiveEvents() {
    if (!state.company || state.eventSource) return;
    try {
      const source = new EventSource(`/v2/companies/${state.company.id}/events/stream?tenant_id=${encodeURIComponent(state.company.tenant_id)}`);
      state.eventSource = source;
      source.addEventListener("graph_event", () => loadGraph());
      source.addEventListener("broker_unavailable", () => {
        source.close();
        state.eventSource = null;
        startPolling();
      });
      source.onerror = () => {
        if (source.readyState === EventSource.CLOSED) {
          source.close();
          state.eventSource = null;
          startPolling();
        }
      };
    } catch {
      startPolling();
    }
  }

  function startPolling() {
    if (state.pollHandle) return;
    state.pollHandle = window.setInterval(() => loadGraph(), 3500);
  }

  async function createCompany(event) {
    event.preventDefault();
    const name = $("#company-name").value.trim();
    if (!name) return;
    const submit = $("#company-create-form button[type=submit]");
    submit.disabled = true;
    try {
      const company = await api("/v2/companies", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: "demo-tenant",
          owner_id: "founder",
          name,
          vision: $("#company-vision").value.trim(),
          mission: $("#company-mission").value.trim(),
          values: [],
        }),
      });
      state.company = company;
      state.companies.push(company);
      renderCompanyPicker();
      setWorkspaceVisible(true);
      await api(`/v2/companies/${company.id}/workforce/bootstrap`, {
        method: "POST",
        body: JSON.stringify({ tenant_id: company.tenant_id, actor_id: "founder" }),
      });
      $("#graph-company-picker").value = company.id;
      await loadGraph(true);
      startJobsPolling();
      toast("Your company graph and virtual workforce have been created");
    } catch (error) {
      toast(error.message);
    } finally {
      submit.disabled = false;
    }
  }

  function askForName(message, placeholder) {
    const value = prompt(message, placeholder || "");
    return value && value.trim() ? value.trim() : null;
  }

  async function addGoal(nameOverride = null) {
    const name = nameOverride || askForName("What is the goal?", "Launch our first product");
    if (!name) return;
    const description = askForName("How will you know this goal is achieved?", "Define measurable success criteria") || "";
    try {
      await createNode("goal", name, description, { progress: 0, priority: "medium", target_date: null }, "PLANNED");
      toast("Goal added to the graph");
    } catch (error) { toast(error.message); }
  }


  async function addKpi() {
    const name = askForName("Name the KPI", "Paying customers");
    if (!name) return;
    const target = askForName("What is the target value?", "20");
    if (target === null) return;
    const unit = askForName("What is the unit?", "customers") || "count";
    const selectedGoal = state.graph.nodes.find((node) => node.id === state.selectedId && node.type === "goal");
    try {
      await createNode("kpi", name, `Target: ${target} ${unit}`, {
        metric: name,
        target: Number.isFinite(Number(target)) ? Number(target) : target,
        actual: null,
        unit,
        period: "monthly",
        measurement_state: "not_connected",
      }, "TRACKING");
      if (!selectedGoal) toast("KPI added. Select a goal and connect it using Connect.");
      else toast(`KPI added to ${selectedGoal.name}`);
    } catch (error) {
      toast(error.message);
    }
  }

  async function addAgent() {
    const name = askForName("Name this AI employee", "Product Agent");
    if (!name) return;
    const role = askForName("What is this agent responsible for?", "Product management") || "General specialist";
    const provider = askForName("LLM provider (ollama, openai-compatible, anthropic, etc.)", "ollama") || "ollama";
    const model = askForName("Model identifier", "llama3.1:8b") || "llama3.1:8b";
    const leaders = state.graph.nodes.filter((node) => node.type === "agent");
    const leaderOptions = ["Founder", ...leaders.map((node) => node.name)].join(", ");
    const managerName = askForName(`Who should ${name} report to? Available: ${leaderOptions}`, leaders.find((node) => ["head_of_agents", "chief_of_staff"].includes(node.data?.role))?.name || "Founder") || "Founder";
    const manager = leaders.find((node) => node.name.toLowerCase() === managerName.toLowerCase());
    try {
      await createNode("agent", name, role, {
        role, rank: "specialist", title: "Specialist",
        manager_id: manager?.id || state.company.id,
        model_configuration: { provider, model_name: model },
        runtime_status: "not_configured", assigned_goals: [],
      }, "PROPOSED");
      toast(`${name} added · reports to ${manager?.name || "Founder"} · ${provider}/${model}`);
    } catch (error) { toast(error.message); }
  }

  async function addWork() {
    const name = askForName("Name the work item", "Prepare product launch plan");
    if (!name) return;
    const goals = state.graph.nodes.filter((node) => node.type === "goal");
    const chosen = goals.length ? askForName(`Relate this work to a goal (enter a goal name). Available: ${goals.map((goal) => goal.name).join(", ")}`, goals[0].name) : null;
    try {
      const node = await createNode("work", name, "", { progress: 0, priority: "medium", workflow_state: "BACKLOG" }, "BACKLOG");
      const goal = goals.find((item) => item.name.toLowerCase() === (chosen || "").toLowerCase());
      if (goal) await createEdge(node.id, goal.id, "contributes_to");
      toast("Work item added to the graph");
    } catch (error) { toast(error.message); }
  }

  async function addMeeting() {
    const name = askForName("Name the meeting", "Weekly company alignment");
    if (!name) return;
    const agenda = askForName("What should the meeting align on?", "Review goals, blockers and next actions") || "";
    try {
      await createNode("meeting", name, agenda, { meeting_type: "alignment", meeting_state: "DRAFT", agenda }, "DRAFT");
      toast("Meeting node created. Scheduling and live meeting execution are planned next.");
    } catch (error) { toast(error.message); }
  }


  async function uploadCompanyArtifact(file) {
    if (!file || !state.company) return;
    const kind = askForName("Store this file as a document or deliverable? Enter document or deliverable.", "document");
    if (!kind) return;
    if (!["document", "deliverable"].includes(kind.toLowerCase())) {
      toast("Choose either document or deliverable");
      return;
    }
    const form = new FormData();
    form.append("file", file);
    form.append("tenant_id", state.company.tenant_id);
    form.append("actor_id", "founder");
    form.append("kind", kind.toLowerCase());
    form.append("title", file.name);
    if (state.selectedId && state.selectedId !== state.company.id) {
      form.append("related_node_id", state.selectedId);
    }
    try {
      const response = await fetch(`/v2/companies/${state.company.id}/artifacts`, {
        method: "POST",
        body: form,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || `Upload failed (${response.status})`);
      await loadGraph();
      if (payload.artifact?.node_id) selectNode(payload.artifact.node_id);
      toast(`${kind} saved to the company graph`);
    } catch (error) {
      toast(error.message);
    } finally {
      $("#company-artifact-file").value = "";
    }
  }

  async function planGoal(goalId) {
    if (!state.company) return;
    try {
      const job = await enqueueGoalJob(goalId, "goal_plan");
      selectNode(goalId);
      toast(job.deduplicated ? "A plan job is already queued or running" : `Goal planning queued · ${job.job_id.slice(0, 8)}`);
    } catch (error) { toast(error.message); }
  }

  async function runGoal(goalId) {
    if (!state.company) return;
    const button = $("#inspect-run-goal");
    if (button) { button.disabled = true; button.textContent = "Queueing…"; }
    try {
      const job = await enqueueGoalJob(goalId, "goal_execution");
      toast(job.deduplicated ? "Goal execution is already queued or running" : `Goal execution queued · ${job.job_id.slice(0, 8)}`);
      await loadGraph();
      selectNode(goalId);
    } catch (error) { toast(error.message); }
    finally { if (button) { button.disabled = false; button.textContent = "Queue goal workflow"; } }
  }

  async function executeWork(workId) {
    if (!state.company) return;
    try {
      const job = await api(`/v2/companies/${state.company.id}/work/${workId}/jobs`, {
        method: "POST",
        body: JSON.stringify({
          tenant_id: state.company.tenant_id,
          actor_id: "founder",
          idempotency_key: `founder-ui:work:${workId}:${Math.floor(Date.now() / 30000)}`,
        }),
      });
      await loadJobs();
      selectNode(workId);
      toast(job.deduplicated ? "This assignment is already queued or running" : `Assignment queued · ${job.job_id.slice(0, 8)}`);
    } catch (error) { toast(error.message); }
  }

  async function conveneMeetingNode(meetingId) {
    if (!state.company) return;
    try {
      const job = await api(`/v2/companies/${state.company.id}/meetings/${meetingId}/jobs`, {
        method: "POST",
        body: JSON.stringify({
          tenant_id: state.company.tenant_id,
          actor_id: "founder",
          idempotency_key: `founder-ui:meeting:${meetingId}:${Math.floor(Date.now() / 30000)}`,
        }),
      });
      await loadJobs();
      selectNode(meetingId);
      toast(job.deduplicated ? "This meeting is already queued or running" : `Meeting queued · ${job.job_id.slice(0, 8)}`);
    } catch (error) { toast(error.message); }
  }

  async function recordKpi(kpiId) {
    const actual = askForName("Enter the actual KPI value", "0");
    if (actual === null || !Number.isFinite(Number(actual))) return;
    const source = askForName("Where did this measurement come from?", "Founder-reported measurement");
    if (!source) return;
    const evidence = askForName("Add a short evidence note (optional)", "") || "";
    try {
      await api(`/v2/companies/${state.company.id}/kpis/${kpiId}/measure`, {
        method: "POST",
        body: JSON.stringify({
          tenant_id: state.company.tenant_id,
          actor_id: "founder",
          actual_value: Number(actual),
          source,
          evidence,
        }),
      });
      await loadGraph();
      selectNode(kpiId);
      toast("KPI measurement recorded in company history");
    } catch (error) { toast(error.message); }
  }

  async function addAgentFromCommand(name) {
    const role = askForName("What is this agent responsible for?", "General specialist") || "General specialist";
    const provider = askForName("LLM provider", "ollama") || "ollama";
    const model = askForName("Model identifier", "llama3.1:8b") || "llama3.1:8b";
    const manager = state.graph.nodes.find((node) => node.type === "agent" && ["head_of_agents", "chief_of_staff"].includes(node.data?.role));
    await createNode("agent", name, role, {
      role, rank: "specialist", title: "Specialist",
      manager_id: manager?.id || state.company.id,
      model_configuration: { provider, model_name: model },
      runtime_status: "not_configured", assigned_goals: [],
    }, "PROPOSED");
    toast(`${name} created under ${manager?.name || "Founder"}`);
  }

  function handleCommand() {
    const input = $("#company-command-input");
    const command = input.value.trim();
    if (!command) return;
    const lower = command.toLowerCase();
    if (lower.startsWith("goal:") || lower.startsWith("create goal:")) {
      addGoal(command.split(":").slice(1).join(":").trim());
    } else if (lower.startsWith("plan:")) {
      const goal = state.graph.nodes.find((node) => node.id === state.selectedId && node.type === "goal")
        || state.graph.nodes.find((node) => node.type === "goal" && node.name.toLowerCase() === command.slice(5).trim().toLowerCase());
      if (goal) planGoal(goal.id);
      else toast("Select a goal dot or use plan: with an existing goal name");
    } else if (lower.startsWith("run:")) {
      const goal = state.graph.nodes.find((node) => node.id === state.selectedId && node.type === "goal")
        || state.graph.nodes.find((node) => node.type === "goal" && node.name.toLowerCase() === command.slice(4).trim().toLowerCase());
      if (goal) runGoal(goal.id);
      else toast("Select a goal dot or use run: with an existing goal name");
    } else if (lower.startsWith("agent:") || lower.startsWith("create agent:")) {
      const name = command.split(":").slice(1).join(":").trim();
      if (name) addAgentFromCommand(name).catch((error) => toast(error.message));
    } else {
      addGoal(command);
    }
    input.value = "";
  }

  function toast(message) {
    if (typeof window.toast === "function") window.toast(message);
    else {
      const element = document.querySelector("#toast");
      if (element) {
        element.textContent = message;
        element.classList.add("show");
        window.setTimeout(() => element.classList.remove("show"), 2600);
      }
    }
  }

  $("#company-create-form")?.addEventListener("submit", createCompany);
  $("#graph-create-company-shortcut")?.addEventListener("click", () => {
    state.company = null;
    if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
    if (state.pollHandle) { window.clearInterval(state.pollHandle); state.pollHandle = null; }
    stopJobsPolling();
    $("#company-create-form").reset();
    setWorkspaceVisible(false);
  });
  $("#graph-add-goal")?.addEventListener("click", () => addGoal());
  $("#graph-add-kpi")?.addEventListener("click", addKpi);
  $("#graph-add-agent")?.addEventListener("click", addAgent);
  $("#graph-add-work")?.addEventListener("click", addWork);
  $("#graph-add-meeting")?.addEventListener("click", addMeeting);
  $("#graph-upload-file")?.addEventListener("click", () => $("#company-artifact-file")?.click());
  $("#company-artifact-file")?.addEventListener("change", (event) => uploadCompanyArtifact(event.target.files?.[0]));
  $("#graph-connect")?.addEventListener("click", () => {
    state.connectMode = !state.connectMode;
    state.connectSource = null;
    $("#graph-connect").classList.toggle("connecting", state.connectMode);
    $("#graph-mode-label").textContent = state.connectMode ? "SELECT FIRST NODE" : "ALL RELATIONSHIPS";
    toast(state.connectMode ? "Select the first dot, then the second dot" : "Connect mode cancelled");
  });
  $("#graph-refresh")?.addEventListener("click", () => loadGraph());
  $("#coordination-plan-only")?.addEventListener("click", () => configureCoordination(true, "PLAN_ONLY"));
  $("#coordination-auto-execute")?.addEventListener("click", () => configureCoordination(true, "AUTO_EXECUTE"));
  $("#coordination-stop")?.addEventListener("click", () => configureCoordination(false, "PLAN_ONLY"));
  $("#graph-company-picker")?.addEventListener("change", async (event) => {
    state.company = state.companies.find((company) => company.id === event.target.value);
    state.selectedId = null;
    if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
    if (state.pollHandle) { window.clearInterval(state.pollHandle); state.pollHandle = null; }
    await loadGraph(true);
    startJobsPolling();
  });
  $("#company-command-send")?.addEventListener("click", handleCommand);
  $("#company-command-input")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") handleCommand();
  });

  window.loadCompanyGraph = () => {
    if (!state.company) initialise();
    else loadGraph();
  };

  initialise();
})();
