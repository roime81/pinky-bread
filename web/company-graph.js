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
    reloadRequested: false,
    chatHistory: [],
    chatSending: false,
    modelProviders: null,
    nodePositions: {},
    drag: null,
    suppressAgentClick: false,
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
    $("#graph-company-picker-wrap").hidden = !hasCompany;
    $("#graph-add-agent").hidden = !hasCompany;
    $("#agent-management-panel").hidden = !hasCompany;
  }

  function loadCompanyNodePositions() {
    state.nodePositions = {};
    if (!state.company) return;
    try {
      const saved = JSON.parse(localStorage.getItem(`pinky-graph-layout:${state.company.id}`) || "{}");
      if (saved && typeof saved === "object" && !Array.isArray(saved)) {
        state.nodePositions = saved;
      }
    } catch {
      state.nodePositions = {};
    }
  }

  function saveCompanyNodePositions() {
    if (!state.company) return;
    try {
      localStorage.setItem(`pinky-graph-layout:${state.company.id}`, JSON.stringify(state.nodePositions));
    } catch {
      toast("The browser could not save the custom graph layout.");
    }
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
      loadCompanyNodePositions();
      setWorkspaceVisible(true);
      try { state.chatHistory = JSON.parse(localStorage.getItem(`pinky-chat:${state.company.id}`) || "[]"); } catch { state.chatHistory = []; }
      $("#graph-company-picker").value = state.company.id;
      await loadGraph(true);
      restoreChatHistory();
      refreshAiRuntime();
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
    if (!state.company) return;
    if (state.loading) {
      state.reloadRequested = true;
      return;
    }
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
      if (state.reloadRequested) {
        state.reloadRequested = false;
        window.setTimeout(() => loadGraph(), 0);
      }
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
    // Restore founder-arranged agent positions after the automatic layout pass.
    for (const [nodeId, saved] of Object.entries(state.nodePositions || {})) {
      if (!saved || !Number.isFinite(Number(saved.x)) || !Number.isFinite(Number(saved.y))) continue;
      if (!positions.has(nodeId)) continue;
      positions.set(nodeId, {
        x: Math.max(45, Math.min(width - 45, Number(saved.x))),
        y: Math.max(45, Math.min(height - 45, Number(saved.y))),
      });
    }
    return positions;
  }

  function renderGraph() {
    const svg = $("#company-graph-svg");
    if (!svg) return;
    // Archived identities remain in PostgreSQL and the audit trail, but leave
    // the active company canvas so "Remove agent" really removes the person from
    // the live organisation view.
    const nodes = (state.graph.nodes || []).filter((node) =>
      !(node.type === "agent" && node.status === "ARCHIVED")
    );
    const visibleNodeIds = new Set(nodes.map((node) => node.id));
    const edges = (state.graph.edges || []).filter((edge) =>
      visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target)
    );
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
      return `<g class="graph-node ${escapeHtml(node.type)} status-${escapeHtml(status)} ${selected ? "selected" : ""} ${state.drag?.nodeId === node.id ? "dragging" : ""}" data-node-id="${escapeHtml(node.id)}" transform="translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})" tabindex="0" role="button" aria-label="Inspect ${escapeHtml(node.name)}">
        <circle class="node-halo" r="${radius + 9}"></circle>
        <circle class="node-core" r="${radius}"></circle>
        <text y="${radius + 17}">${escapeHtml(shortLabel)}</text>
        <text class="node-sub" y="${radius + 29}">${subLabel}</text>
      </g>`;
    }).join("");

    svg.innerHTML = `<g class="graph-edges">${edgeMarkup}</g><g class="graph-nodes">${nodeMarkup}</g>`;
    svg.querySelectorAll("[data-node-id]").forEach((element) => {
      element.addEventListener("click", (event) => {
        if (state.suppressAgentClick && element.classList.contains("agent")) {
          state.suppressAgentClick = false;
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        onNodeClick(element.dataset.nodeId);
      });
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onNodeClick(element.dataset.nodeId);
        }
      });
    });

    $("#graph-node-count").textContent = `${nodes.length} NODES`;
    $("#graph-goal-count").textContent = nodes.filter((node) => node.type === "goal").length;
    $("#graph-agent-count").textContent = nodes.filter((node) => node.type === "agent" && node.status !== "ARCHIVED").length;
    $("#graph-work-count").textContent = nodes.filter((node) => node.type === "work").length;
    renderAgentDirectory();
    if (state.selectedId) selectNode(state.selectedId, false);
  }

  function graphPointFromPointer(svg, event) {
    const matrix = svg.getScreenCTM();
    if (!matrix) return null;
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const transformed = point.matrixTransform(matrix.inverse());
    return { x: transformed.x, y: transformed.y };
  }

  function bindAgentNodeDragging() {
    const svg = $("#company-graph-svg");
    if (!svg || svg.dataset.dragBound === "true") return;
    svg.dataset.dragBound = "true";

    svg.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || state.connectMode || !state.company) return;
      const target = event.target instanceof Element ? event.target.closest(".graph-node.agent") : null;
      if (!target) return;
      const point = graphPointFromPointer(svg, event);
      const transform = /translate\(([-\d.]+)\s+([-\d.]+)\)/.exec(target.getAttribute("transform") || "");
      if (!point || !transform) return;
      const nodeId = target.dataset.nodeId;
      state.drag = {
        nodeId,
        pointerId: event.pointerId,
        startX: Number(transform[1]),
        startY: Number(transform[2]),
        pointerX: point.x,
        pointerY: point.y,
        startClientX: event.clientX,
        startClientY: event.clientY,
        moved: false,
      };
      try { svg.setPointerCapture(event.pointerId); } catch {}
      event.preventDefault();
    });

    svg.addEventListener("pointermove", (event) => {
      const drag = state.drag;
      if (!drag || drag.pointerId !== event.pointerId) return;
      const point = graphPointFromPointer(svg, event);
      if (!point) return;
      const deltaClient = Math.hypot(event.clientX - drag.startClientX, event.clientY - drag.startClientY);
      if (!drag.moved && deltaClient < 4) return;
      drag.moved = true;
      const x = Math.max(45, Math.min(955, drag.startX + point.x - drag.pointerX));
      const y = Math.max(45, Math.min(605, drag.startY + point.y - drag.pointerY));
      state.nodePositions[drag.nodeId] = { x, y };
      renderGraph();
      event.preventDefault();
    });

    const finishDrag = (event, cancelled = false) => {
      const drag = state.drag;
      if (!drag || drag.pointerId !== event.pointerId) return;
      state.drag = null;
      if (drag.moved) {
        saveCompanyNodePositions();
        state.suppressAgentClick = !cancelled;
        if (state.suppressAgentClick) window.setTimeout(() => { state.suppressAgentClick = false; }, 0);
        renderGraph();
      }
      try {
        if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
      } catch {}
    };
    svg.addEventListener("pointerup", (event) => finishDrag(event));
    svg.addEventListener("pointercancel", (event) => finishDrag(event, true));
    svg.addEventListener("lostpointercapture", (event) => {
      if (state.drag?.pointerId === event.pointerId) finishDrag(event, true);
    });
  }

  async function loadJobs() {
    if (!$("#company-job-list") || !state.company || state.jobsLoading) return;
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
    if (!$("#company-job-list") || state.jobsPollHandle) return;
    state.jobsPollHandle = window.setInterval(() => loadJobs(), 2500);
  }

  function stopJobsPolling() {
    if (!state.jobsPollHandle) return;
    window.clearInterval(state.jobsPollHandle);
    state.jobsPollHandle = null;
  }

  async function configureCoordination(enabled, mode = "PLAN_ONLY") {
    if (!state.company) return;
    if (enabled && !activeAgents().some(_isCoordinatorForUi)) {
      toast("Create an agent with Coordinator authority before enabling recurring coordination.");
      return;
    }
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

  async function updateAgent(node, payload) {
    const request = {
      tenant_id: state.company.tenant_id,
      actor_id: "founder",
      ...(payload.name ? { name: payload.name } : {}),
      ...(payload.description !== undefined ? { description: payload.description } : {}),
      ...(payload.data_patch?.role ? { role: payload.data_patch.role } : {}),
      ...(payload.data_patch?.title ? { title: payload.data_patch.title } : {}),
      ...(payload.data_patch?.model_configuration ? { model_configuration: payload.data_patch.model_configuration } : {}),
      ...(payload.data_patch?.seniority_level ? { seniority_level: payload.data_patch.seniority_level } : {}),
      ...(payload.data_patch?.authority ? { authority: payload.data_patch.authority } : {}),
      ...(payload.status ? { status: payload.status } : {}),
    };
    await api(`/v2/companies/${state.company.id}/agents/${node.id}`, {
      method: "PATCH",
      body: JSON.stringify(request),
    });
    await loadGraph();
    selectNode(node.id);
  }

  async function editAgent(node) { openAgentEditor(node); }

  async function changeAgentRank(node, promote) {
    const action = promote ? "promote" : "demote";
    const result = await api(`/v2/companies/${state.company.id}/agents/${node.id}/${action}`, {
      method: "POST",
      body: JSON.stringify({ tenant_id: state.company.tenant_id, actor_id: "founder" }),
    });
    await loadGraph();
    selectNode(node.id);
    toast(`${node.name} seniority updated to level ${result.data?.seniority_level || "—"}`);
  }

  async function archiveAgent(node) {
    if (!window.confirm(`Archive ${node.name}? Its work history and deliverables will be preserved.`)) return;
    await api(`/v2/companies/${state.company.id}/agents/${node.id}`, {
      method: "DELETE",
      body: JSON.stringify({ tenant_id: state.company.tenant_id, actor_id: "founder" }),
    });
    state.selectedId = null;
    await loadGraph();
    renderAgentDirectory();
    toast("Agent archived; history preserved");
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
    if (node.type === "agent") {
      actions.push('<button class="secondary-btn" id="inspect-edit-agent">Edit agent & model</button>');
      actions.push('<button class="secondary-btn" id="inspect-promote-agent">Promote agent</button>');
      actions.push('<button class="secondary-btn" id="inspect-demote-agent">Demote agent</button>');
      if (node.status !== "ARCHIVED") actions.push('<button class="secondary-btn" id="inspect-archive-agent">Archive agent</button>');
    }
    if (node.type === "goal") {
      actions.push('<button class="secondary-btn" id="inspect-plan-goal">Plan with company coordinator</button>');
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
    $("#inspect-edit-agent")?.addEventListener("click", () => editAgent(node).catch((error) => toast(error.message)));
    $("#inspect-promote-agent")?.addEventListener("click", () => changeAgentRank(node, true).catch((error) => toast(error.message)));
    $("#inspect-demote-agent")?.addEventListener("click", () => changeAgentRank(node, false).catch((error) => toast(error.message)));
    $("#inspect-archive-agent")?.addEventListener("click", () => archiveAgent(node).catch((error) => toast(error.message)));
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
          values: [],
        }),
      });
      state.company = company;
      loadCompanyNodePositions();
      state.chatHistory = [];
      state.companies.push(company);
      renderCompanyPicker();
      setWorkspaceVisible(true);
      $("#graph-company-picker").value = company.id;
      $("#graph-company-picker").dispatchEvent(new Event("change", { bubbles: true }));
      await loadGraph(true);
      restoreChatHistory();
      refreshAiRuntime();
      startJobsPolling();
      toast("Company created. Build the virtual team you want by adding your own agents.");
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

  function activeAgents() {
    return (state.graph.nodes || []).filter((node) =>
      node.type === "agent" && !["ARCHIVED", "DISABLED", "PAUSED"].includes(String(node.status || "").toUpperCase())
    );
  }

  function _isCoordinatorForUi(agent) {
    const data = agent?.data || {};
    const authority = String(data.authority || "").trim().toUpperCase();
    const role = String(data.role || "").trim().toLowerCase();
    return authority === "COORDINATOR" || ["head_of_agents", "chief_of_staff", "chief-of-staff"].includes(role);
  }

  function renderAgentDirectory() {
    const agents = activeAgents();
    const managers = new Map(
      (state.graph.edges || [])
        .filter((edge) => edge.relationship === "reports_to")
        .map((edge) => [edge.source, edge.target])
    );
    const agentById = new Map(agents.map((agent) => [agent.id, agent]));
    const cards = agents.map((agent) => {
      const data = agent.data || {};
      const model = data.model_configuration || {};
      const managerId = data.manager_id || managers.get(agent.id);
      const manager = managerId ? agentById.get(managerId) : null;
      const coordinator = _isCoordinatorForUi(agent);
      const modelLabel = [model.provider || "workspace", model.model_name || "default model"].join(" · ");
      const seniority = Number(data.seniority_level || 3);
      return `
        <article class="company-agent-card">
          <div class="company-agent-card-top">
            <span class="company-agent-avatar">${escapeHtml(agent.name.slice(0, 1).toUpperCase())}</span>
            <span class="company-agent-state"><i></i> ${escapeHtml(agent.status || "ACTIVE")}</span>
          </div>
          <div class="company-agent-identity">
            <strong>${escapeHtml(agent.name)}</strong>
            <span>${escapeHtml(data.title || data.role || "AI employee")}</span>
          </div>
          <p class="company-agent-description">${escapeHtml(agent.description || "No role description yet.")}</p>
          <div class="company-agent-meta">
            <span class="company-agent-tag ${coordinator ? "coordinator" : ""}">${coordinator ? "COORDINATOR" : "SPECIALIST"}</span>
            <span>Level ${Number.isFinite(seniority) ? seniority : 3}</span>
          </div>
          <div class="company-agent-model" title="${escapeHtml(modelLabel)}">MODEL · ${escapeHtml(modelLabel)}</div>
          <div class="company-agent-manager">Reports to · <b>${escapeHtml(manager?.name || "Founder")}</b></div>
          <div class="company-agent-actions">
            <button type="button" class="secondary-btn" data-select-agent="${escapeHtml(agent.id)}">Inspect</button>
            <button type="button" class="secondary-btn" data-edit-agent="${escapeHtml(agent.id)}">Edit</button>
          </div>
        </article>`;
    }).join("");
    const empty = '<div class="company-agent-empty"><strong>Your workforce starts here.</strong><span>Create your first AI employee, assign a model and define who they report to.</span></div>';
    const markup = cards || empty;
    const mainList = $("#company-agent-list");
    const workspaceList = $("#workspace-agent-list");
    if (mainList) mainList.innerHTML = markup;
    if (workspaceList) workspaceList.innerHTML = markup;
    const count = $("#workspace-agent-count");
    const pageCount = $("#ai-workspace-agent-count");
    const countLabel = `${agents.length} ${agents.length === 1 ? "agent" : "agents"}`;
    if (count) count.textContent = countLabel;
    if (pageCount) pageCount.textContent = countLabel;
  }

  function renderAgentProviderHelp() {
    const provider = $("#agent-editor-provider")?.value || "ollama";
    const model = $("#agent-editor-model");
    const endpoint = $("#agent-editor-endpoint");
    const help = $("#agent-provider-help");
    const defaults = {
      ollama: { model: "qwen2.5:3b", endpoint: "http://ollama:11434/v1", env: "No commercial API key required" },
      vllm: { model: "your-model-id", endpoint: "Your vLLM /v1 endpoint", env: "VLLM_API_KEY" },
      "openai-compatible": { model: "your-model-id", endpoint: "Your gateway /v1 endpoint", env: "OPENAI_COMPATIBLE_API_KEY (or VLLM_API_KEY)" },
      openai: { model: "gpt-4.1-mini", endpoint: "https://api.openai.com/v1", env: "OPENAI_API_KEY" },
      gemini: { model: "gemini-4-hydrogen", endpoint: "https://generativelanguage.googleapis.com/v1beta/openai", env: "GEMINI_API_KEY" },
    };
    const selected = defaults[provider] || defaults.ollama;
    if (model) {
      const previousDefault = model.dataset.providerDefault || "qwen2.5:3b";
      if (!model.value || model.value === previousDefault) model.value = selected.model;
      model.dataset.providerDefault = selected.model;
      model.placeholder = `e.g. ${selected.model}`;
    }
    if (endpoint) endpoint.placeholder = selected.endpoint;
    if (help) {
      const status = state.modelProviders?.providers?.[provider];
      const credential = status?.requires_api_key
        ? (status.configured ? "API key configured" : `${selected.env} is not configured`)
        : (provider === "ollama" ? "Local Ollama provider" : `${selected.env} is configured on the server`);
      help.textContent = `${credential}. Set credentials in Model Providers / .env. API keys are not saved in the agent profile or sent to the browser.`;
      help.classList.toggle("is-missing", Boolean(status?.requires_api_key && !status.configured));
    }
  }

  async function refreshModelProviderStatus() {
    try {
      state.modelProviders = await api("/v2/model-providers");
      renderAgentProviderHelp();
    } catch {
      state.modelProviders = null;
    }
  }

  function openAgentEditor(agent = null) {
    const form = $("#agent-editor-form");
    if (!form) return;
    form.reset();
    const data = agent?.data || {};
    const model = data.model_configuration || {};
    $("#agent-editor-id").value = agent?.id || "";
    $("#agent-editor-heading").textContent = agent ? "Edit AI employee" : "Create an AI employee";
    $("#agent-editor-name").value = agent?.name || "";
    $("#agent-editor-role").value = data.role || "";
    $("#agent-editor-title").value = data.title || "Specialist";
    $("#agent-editor-level").value = data.seniority_level || 3;
    $("#agent-editor-authority").value = data.authority || "SPECIALIST";
    $("#agent-editor-description").value = agent?.description || "";
    $("#agent-editor-skills").value = (data.skills || []).join(", ");
    $("#agent-editor-responsibilities").value = (data.responsibilities || []).join("\n");
    $("#agent-editor-prompt").value = data.system_prompt || "";
    $("#agent-editor-provider").value = model.provider || "ollama";
    $("#agent-editor-model").value = model.model_name || "qwen2.5:3b";
    $("#agent-editor-endpoint").value = model.endpoint || "";
    const providerSelect = $("#agent-editor-provider");
    if (providerSelect && providerSelect.dataset.providerHelpBound !== "true") {
      providerSelect.addEventListener("change", renderAgentProviderHelp);
      providerSelect.dataset.providerHelpBound = "true";
    }
    renderAgentProviderHelp();
    if (!state.modelProviders) refreshModelProviderStatus();
    const manager = $("#agent-editor-manager");
    manager.innerHTML = '<option value="">Reports directly to founder</option>' + activeAgents()
      .filter((item) => item.id !== agent?.id)
      .map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.name)}</option>`).join("");
    const reporting = state.graph.edges.find((edge) => edge.source === agent?.id && edge.relationship === "reports_to");
    manager.value = data.manager_id || reporting?.target || "";
    $("#agent-editor-feedback").textContent = "";
    const dialog = $("#agent-editor-dialog");
    if (!dialog.open) dialog.showModal();
    window.setTimeout(() => $("#agent-editor-name")?.focus(), 0);
  }

  async function saveAgent(event) {
    event.preventDefault();
    if (!state.company) return;
    const save = $("#agent-editor-save");
    save.disabled = true;
    $("#agent-editor-feedback").textContent = "Saving agent…";
    const id = $("#agent-editor-id").value;
    const managerId = $("#agent-editor-manager").value || null;
    const modelConfiguration = {
      provider: $("#agent-editor-provider").value,
      model_name: $("#agent-editor-model").value.trim(),
      endpoint: $("#agent-editor-endpoint").value.trim() || null,
    };
    const payload = {
      tenant_id: state.company.tenant_id,
      actor_id: "founder",
      name: $("#agent-editor-name").value.trim(),
      role: $("#agent-editor-role").value.trim(),
      title: $("#agent-editor-title").value.trim(),
      description: $("#agent-editor-description").value.trim(),
      skills: $("#agent-editor-skills").value.split(",").map((v) => v.trim()).filter(Boolean),
      responsibilities: $("#agent-editor-responsibilities").value.split("\n").map((v) => v.trim()).filter(Boolean),
      system_prompt: $("#agent-editor-prompt").value.trim(),
      seniority_level: Number($("#agent-editor-level").value),
      authority: $("#agent-editor-authority").value,
      manager_id: managerId,
      model_configuration: modelConfiguration,
    };
    try {
      if (id) {
        await api(`/v2/companies/${state.company.id}/agents/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await api(`/v2/companies/${state.company.id}/agents`, { method: "POST", body: JSON.stringify(payload) });
      }
      $("#agent-editor-dialog").close();
      await loadGraph();
      renderAgentDirectory();
      toast(id ? "Agent profile updated" : "AI employee created");
    } catch (error) {
      $("#agent-editor-feedback").textContent = error.message;
      toast(error.message);
    } finally {
      save.disabled = false;
    }
  }
  async function addAgent() {
    if (!state.company) {
      toast("Create a company before adding AI employees.");
      return;
    }
    openAgentEditor();
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

  function restoreChatHistory() {
    const log = $("#company-conversation");
    if (!log) return;
    if (!state.chatHistory.length) {
      log.innerHTML = '<div class="conversation-welcome"><span class="conversation-mark">PB</span><div><strong>Welcome to your company workspace.</strong><p>Create or select a company, then start a conversation with your AI workforce.</p><small>Try: <code>goal: Launch our first product</code> · <code>agent: Product Lead</code> · <code>plan: [goal name]</code></small></div></div>';
      return;
    }
    log.innerHTML = "";
    state.chatHistory.forEach((item) => {
      const entry = document.createElement("div");
      entry.className = `conversation-entry ${item.role === "user" ? "founder" : "assistant"}`;
      const avatar = document.createElement("span");
      avatar.className = "conversation-avatar";
      avatar.textContent = item.role === "user" ? "YOU" : "AI";
      const copy = document.createElement("div");
      copy.className = "conversation-copy";
      const heading = document.createElement("strong");
      heading.textContent = item.role === "user" ? "Founder" : "AI employee";
      const body = document.createElement("p");
      body.textContent = item.content;
      copy.append(heading, body);
      entry.append(avatar, copy);
      log.append(entry);
    });
    log.scrollTop = log.scrollHeight;
  }

  async function refreshAiRuntime() {
    const indicator = $("#ai-runtime-status");
    if (!indicator) return;
    indicator.textContent = "CHECKING MODEL";
    indicator.classList.remove("online", "offline", "mock");
    try {
      const status = await api("/v2/runtime");
      if (status.mock_inference) {
        indicator.textContent = "MOCK MODE";
        indicator.classList.add("mock");
        indicator.title = "Mock mode is enabled; live AI responses are disabled.";
      } else if (status.model_reachable) {
        indicator.textContent = status.model_available ? "MODEL ONLINE" : "MODEL REACHABLE · MODEL NOT FOUND";
        indicator.classList.add(status.model_available ? "online" : "offline");
        indicator.title = status.model_error || `${status.provider} · ${status.model}`;
      } else {
        indicator.textContent = "MODEL OFFLINE";
        indicator.classList.add("offline");
        indicator.title = status.model_error || "Model endpoint is unreachable";
      }
    } catch (error) {
      indicator.textContent = "RUNTIME UNKNOWN";
      indicator.classList.add("offline");
      indicator.title = error.message;
    }
  }

  function appendConversationEntry(kind, title, message) {
    const log = $("#company-conversation");
    if (!log) return;
    log.querySelector(".conversation-welcome")?.remove();
    const entry = document.createElement("div");
    entry.className = `conversation-entry ${kind}`;
    const avatar = document.createElement("span");
    avatar.className = "conversation-avatar";
    avatar.textContent = kind === "founder" ? "YOU" : kind === "assistant" ? "AI" : "PB";
    const copy = document.createElement("div");
    copy.className = "conversation-copy";
    const heading = document.createElement("strong");
    heading.textContent = title;
    const body = document.createElement("p");
    body.textContent = message;
    copy.append(heading, body);
    entry.append(avatar, copy);
    log.append(entry);
    log.scrollTop = log.scrollHeight;
  }

  async function sendAiMessage(message) {
    if (!state.company || state.chatSending) return;
    if (!activeAgents().length) {
      appendConversationEntry("system", "Create your first AI employee", "Add an agent to your company before starting an AI conversation.");
      toast("Create an AI agent first");
      return;
    }
    const history = state.chatHistory.slice(-12);
    state.chatSending = true;
    const send = $("#company-command-send");
    if (send) { send.disabled = true; send.textContent = "Thinking…"; }
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 570000);
    const pending = document.createElement("div");
    pending.className = "conversation-entry assistant pending";
    pending.textContent = "AI employee is thinking…";
    $("#company-conversation")?.append(pending);
    try {
      const result = await api(`/v2/companies/${state.company.id}/chat`, {
        method: "POST",
        body: JSON.stringify({
          tenant_id: state.company.tenant_id,
          actor_id: "founder",
          message,
          history,
        }),
        signal: controller.signal,
      });
      pending.remove();
      const responses = Array.isArray(result.responses) ? result.responses : [];
      if (responses.length) {
        responses.forEach((item) => appendConversationEntry("assistant", item.name || "AI employee", item.reply || ""));
      } else {
        appendConversationEntry("assistant", result.agent?.name || "AI workforce", result.reply || "The model returned an empty response.");
      }
      state.chatHistory.push({ role: "user", content: message }, { role: "assistant", content: result.reply || "" });
      state.chatHistory = state.chatHistory.slice(-30);
      try { localStorage.setItem(`pinky-chat:${state.company.id}`, JSON.stringify(state.chatHistory)); } catch {}
      toast(`${responses.length || 1} AI employee${responses.length === 1 ? "" : "s"} responded · ${result.mode || "LIVE"}`);
    } catch (error) {
      pending.remove();
      const message = error.name === "AbortError"
        ? "The model did not respond within 570 seconds. Check model availability and server logs."
        : error.message;
      appendConversationEntry("system", "AI request failed", message);
      toast(message);
    } finally {
      window.clearTimeout(timeout);
      state.chatSending = false;
      if (send) { send.disabled = false; send.innerHTML = 'Send <span>↗</span>'; }
    }
  }

  function handleCommand(event) {
    event?.preventDefault();
    const input = $("#company-command-input");
    const command = input.value.trim();
    if (!command || state.chatSending) return;
    if (!state.company) {
      appendConversationEntry("system", "Create your company first", "Open Company Graph and establish a company before sending instructions to your AI workforce.");
      toast("Create or select a company first");
      return;
    }
    const lower = command.toLowerCase();
    appendConversationEntry("founder", "Founder", command);
    input.value = "";
    if (lower.startsWith("goal:") || lower.startsWith("create goal:")) {
      addGoal(command.split(":").slice(1).join(":").trim()).catch((error) => appendConversationEntry("system", "Goal creation failed", error.message));
    } else if (lower.startsWith("plan:")) {
      const goal = state.graph.nodes.find((node) => node.id === state.selectedId && node.type === "goal")
        || state.graph.nodes.find((node) => node.type === "goal" && node.name.toLowerCase() === command.slice(5).trim().toLowerCase());
      if (goal) planGoal(goal.id);
      else appendConversationEntry("system", "Goal not found", "Select a goal or use plan: followed by its exact name.");
    } else if (lower.startsWith("run:")) {
      const goal = state.graph.nodes.find((node) => node.id === state.selectedId && node.type === "goal")
        || state.graph.nodes.find((node) => node.type === "goal" && node.name.toLowerCase() === command.slice(4).trim().toLowerCase());
      if (goal) runGoal(goal.id);
      else appendConversationEntry("system", "Goal not found", "Select a goal or use run: followed by its exact name.");
    } else if (lower.startsWith("agent:") || lower.startsWith("create agent:")) {
      const name = command.split(":").slice(1).join(":").trim();
      if (name) openAgentEditorWithName(name);
    } else {
      sendAiMessage(command);
    }
  }

  function openAgentEditorWithName(name) {
    openAgentEditor();
    $("#agent-editor-name").value = name;
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
    state.chatHistory = [];
    restoreChatHistory();
    if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
    if (state.pollHandle) { window.clearInterval(state.pollHandle); state.pollHandle = null; }
    stopJobsPolling();
    $("#company-create-form").reset();
    setWorkspaceVisible(false);
  });
  $("#graph-add-goal")?.addEventListener("click", () => addGoal());
  $("#graph-add-kpi")?.addEventListener("click", addKpi);
  $("#graph-add-agent")?.addEventListener("click", addAgent);
  $("#graph-add-agent-directory")?.addEventListener("click", addAgent);
  $("#agent-editor-form")?.addEventListener("submit", saveAgent);
  $("#agent-editor-close")?.addEventListener("click", () => $("#agent-editor-dialog").close());
  $("#agent-editor-cancel")?.addEventListener("click", () => $("#agent-editor-dialog").close());
  const handleAgentDirectoryClick = (event) => {
    const edit = event.target.closest("[data-edit-agent]");
    const select = event.target.closest("[data-select-agent]");
    const agentId = edit?.dataset.editAgent || select?.dataset.selectAgent;
    if (!agentId) return;
    const agent = (state.graph.nodes || []).find((node) => node.id === agentId);
    if (!agent) return;
    if (edit) openAgentEditor(agent);
    else {
      state.selectedId = agentId;
      if ($("#view-company-graph")?.classList.contains("active")) selectNode(agentId);
      else toast(`Selected ${agent.name}. Open Company graph to inspect its relationships.`);
    }
  };
  $("#company-agent-list")?.addEventListener("click", handleAgentDirectoryClick);
  $("#workspace-agent-list")?.addEventListener("click", handleAgentDirectoryClick);
  $("#workspace-add-agent")?.addEventListener("click", addAgent);
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
    loadCompanyNodePositions();
    try { state.chatHistory = JSON.parse(localStorage.getItem(`pinky-chat:${state.company.id}`) || "[]"); } catch { state.chatHistory = []; }
    state.selectedId = null;
    if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
    if (state.pollHandle) { window.clearInterval(state.pollHandle); state.pollHandle = null; }
    await loadGraph(true);
    restoreChatHistory();
    refreshAiRuntime();
    startJobsPolling();
  });
  $("#company-command-form")?.addEventListener("submit", handleCommand);

  window.loadCompanyGraph = () => {
    if (!state.company) return initialise();
    return loadGraph();
  };
  window.loadCompanyAgents = () => {
    if (!state.company) return initialise();
    if (!state.graph.nodes?.length) return loadGraph(true);
    return renderAgentDirectory();
  };

  bindAgentNodeDragging();
  initialise();
})();
