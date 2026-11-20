import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode, type ComponentType } from "react";
import {
  Activity, ArrowDownRight, ArrowRight, ArrowUpRight, Bot, Building2, Check,
  ChevronDown, CircleHelp, Clock3, Command, FileClock, FileText, GitBranch,
  LayoutDashboard, LogOut, MessageSquare, Network, PanelLeftClose,
  PanelLeftOpen, PanelRightClose, PanelRightOpen, Plus, RefreshCw, Search,
  Settings2, ShieldCheck, Sparkles, Users, Workflow, X, Zap,
} from "lucide-react";
import AgentConversations from "./App";
import FounderComposer from "./FounderComposer";

const TENANT = "demo-tenant";
const ACTOR = "founder";

type Company = {
  id: string;
  name: string;
  tenant_id: string;
  description?: string;
  data?: { vision?: string; mission?: string; values?: string[] };
};
type GraphNode = {
  id: string;
  type: string;
  name: string;
  description?: string;
  status?: string;
  data?: Record<string, any>;
  created_at?: string;
};
type GraphEdge = { id: string; source: string; target: string; relationship: string };
type Graph = { nodes: GraphNode[]; edges: GraphEdge[] };
type DurableJob = {
  job_id: string; kind: string; target_id: string; status: string; attempts: number;
  max_attempts: number; last_error?: string | null; created_at?: string; started_at?: string | null;
  completed_at?: string | null; cancel_requested?: boolean; result?: Record<string, any> | null;
};
type Coordination = { enabled: boolean; mode: "PLAN_ONLY" | "AUTO_EXECUTE"; interval_seconds: number; next_run_at?: string | null; last_run_at?: string | null };
type EventRecord = {
  event_no: number; id: string; actor_id: string; type: string;
  payload: Record<string, any>; occurred_at: string; entry_hash: string;
};
type WorkflowRun = {
  thread_id: string; prompt: string; status: string; created_at?: string;
  audit_trail?: { node_id: string; action_type: string; output_summary?: string }[];
  requires_human_approval?: boolean; pending_action?: { amount?: number; tool?: string };
};
type AgentManifest = {
  agent_metadata: { agent_id: string; display_name: string; domain: string; version: string };
  persona_and_guardrails: { system_prompt: string };
  capabilities?: { allowed_mcp_tools?: string[] };
};
type Provider = {
  label?: string; configured?: boolean; requires_api_key?: boolean;
  endpoint?: string; credential_env?: string;
};
type AgentDraft = {
  name: string; role: string; title: string; description: string; skills: string;
  responsibilities: string; system_prompt: string; seniority_level: number;
  authority: "SPECIALIST" | "COORDINATOR"; manager_id: string;
  provider: string; model_name: string; endpoint: string;
};

const blankAgent: AgentDraft = {
  name: "", role: "", title: "", description: "", skills: "", responsibilities: "",
  system_prompt: "", seniority_level: 3, authority: "SPECIALIST", manager_id: "",
  provider: "ollama", model_name: "qwen2.5:3b", endpoint: "",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Request failed (" + response.status + ")");
  return payload as T;
}

function dateTime(value?: string) {
  if (!value) return "Just now";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}
function shortId(value?: string) { return (value || "").slice(0, 8); }
function initials(value: string) {
  return value.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase() || "").join("") || "AI";
}
function nodeRole(node: GraphNode) {
  return String(node.data?.title || node.data?.role || node.type);
}
function nodeIsActive(node: GraphNode) {
  return !["ARCHIVED", "DISABLED", "PAUSED"].includes(String(node.status || "").toUpperCase());
}
function errorText(reason: unknown) {
  return reason instanceof Error ? reason.message : "Something went wrong. Please try again.";
}

const navGroups = [
  {
    label: "COMPANY",
    items: [
      { id: "company-graph", label: "Company graph", icon: Network },
      { id: "company-events", label: "Company Event Log", icon: Activity },
      { id: "founder-view", label: "Founder View", icon: LayoutDashboard },
    ],
  },
  {
    label: "WORKSPACE",
    items: [
      { id: "company-agents", label: "AI Workforce", icon: Users },
      { id: "durable-workforce", label: "Durable Workforce", icon: Zap },
      { id: "agent-messaging", label: "Agent Conversations", icon: MessageSquare },
      { id: "model-providers", label: "Model Providers", icon: Settings2 },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { id: "overview", label: "Overview", icon: LayoutDashboard },
      { id: "workflows", label: "Workflows", icon: Workflow },
      { id: "agents", label: "Workflow Templates", icon: Bot },
      { id: "audit", label: "Audit Trails", icon: ShieldCheck },
    ],
  },
];

function PageHeading({ eyebrow, title, description, actions }: {
  eyebrow: string; title: string; description: string; actions?: ReactNode;
}) {
  return (
    <div className="pb-page-heading">
      <div className="pb-page-heading-copy">
        <div className="pb-eyebrow"><span className="pb-eyebrow-dot" />{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="pb-heading-actions">{actions}</div>}
    </div>
  );
}

function EmptyState({ icon: Icon = CircleHelp, title, description, action }: {
  icon?: ComponentType<{ size?: number }>; title: string; description: string; action?: ReactNode;
}) {
  return (
    <div className="pb-empty-state">
      <div className="pb-empty-icon"><Icon size={21} /></div>
      <strong>{title}</strong>
      <p>{description}</p>
      {action}
    </div>
  );
}

function StatCard({ label, value, detail, icon: Icon }: {
  label: string; value: string | number; detail: string; icon: ComponentType<{ size?: number }>;
}) {
  return (
    <article className="pb-stat-card">
      <div className="pb-stat-top"><span>{label}</span><span className="pb-stat-icon"><Icon size={16} /></span></div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function AgentEditor({ company, draft, agent, onClose, onSaved }: {
  company: Company; draft: AgentDraft; agent: GraphNode | null;
  onClose: () => void; onSaved: () => Promise<void>;
}) {
  const [form, setForm] = useState<AgentDraft>(draft);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [providers, setProviders] = useState<Record<string, Provider>>({});
  const [managers, setManagers] = useState<GraphNode[]>([]);
  useEffect(() => {
    api<{ providers: Record<string, Provider> }>("/v2/model-providers")
      .then((value) => setProviders(value.providers || {})).catch(() => undefined);
    api<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
      "/v2/companies/" + company.id + "/graph?tenant_id=" + encodeURIComponent(company.tenant_id || TENANT)
    ).then((value) => setManagers((value.nodes || []).filter((item) => item.type === "agent" && item.id !== agent?.id && nodeIsActive(item))))
      .catch(() => undefined);
  }, [company.id, company.tenant_id, agent?.id]);
  const change = (key: keyof AgentDraft, value: string | number) => setForm((current) => ({ ...current, [key]: value }));
  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const payload = {
      tenant_id: company.tenant_id || TENANT,
      actor_id: ACTOR,
      name: form.name.trim(),
      role: form.role.trim(),
      title: form.title.trim(),
      description: form.description.trim(),
      skills: form.skills.split(",").map((item) => item.trim()).filter(Boolean),
      responsibilities: form.responsibilities.split("\n").map((item) => item.trim()).filter(Boolean),
      system_prompt: form.system_prompt.trim(),
      seniority_level: Number(form.seniority_level),
      authority: form.authority,
      manager_id: form.manager_id || null,
      model_configuration: {
        provider: form.provider,
        model_name: form.model_name.trim(),
        endpoint: form.endpoint.trim() || null,
      },
    };
    try {
      await api(
        agent ? "/v2/companies/" + company.id + "/agents/" + agent.id : "/v2/companies/" + company.id + "/agents",
        { method: agent ? "PATCH" : "POST", body: JSON.stringify(payload) },
      );
      await onSaved();
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="pb-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="pb-modal pb-agent-modal" role="dialog" aria-modal="true" aria-labelledby="pb-agent-modal-title">
        <header className="pb-modal-header">
          <div><div className="pb-eyebrow">YOUR VIRTUAL TEAM</div><h2 id="pb-agent-modal-title">{agent ? "Edit AI employee" : "Create AI employee"}</h2><p>Give this agent a clear remit, reporting line and model.</p></div>
          <button className="pb-icon-button" onClick={onClose} type="button" aria-label="Close dialog"><X size={18} /></button>
        </header>
        <form onSubmit={submit} className="pb-agent-form">
          <div className="pb-form-grid">
            <label>Agent name<input required minLength={2} maxLength={120} value={form.name} onChange={(e) => change("name", e.target.value)} placeholder="e.g. Mira" /></label>
            <label>Role / function<input required minLength={2} maxLength={160} value={form.role} onChange={(e) => change("role", e.target.value)} placeholder="e.g. Product strategist" /></label>
            <label>Job title<input required minLength={2} maxLength={160} value={form.title} onChange={(e) => change("title", e.target.value)} placeholder="e.g. Head of Product" /></label>
            <label>Seniority <select value={form.seniority_level} onChange={(e) => change("seniority_level", Number(e.target.value))}>{Array.from({ length: 10 }, (_, i) => <option value={i + 1} key={i}>Level {i + 1}</option>)}</select></label>
            <label className="pb-form-span">Scope and description<textarea rows={2} value={form.description} onChange={(e) => change("description", e.target.value)} placeholder="What is this agent accountable for?" /></label>
            <label>Skills <input value={form.skills} onChange={(e) => change("skills", e.target.value)} placeholder="research, planning, analysis" /></label>
            <label>Authority <select value={form.authority} onChange={(e) => change("authority", e.target.value)}><option value="SPECIALIST">Specialist</option><option value="COORDINATOR">Coordinator</option></select></label>
            <label>Reports to <select value={form.manager_id} onChange={(e) => change("manager_id", e.target.value)}><option value="">Founder</option>{managers.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
            <label>Model provider <select value={form.provider} onChange={(e) => {
              const provider = e.target.value;
              change("provider", provider);
              if (provider === "openai" && !form.model_name.startsWith("gpt")) change("model_name", "gpt-4.1-mini");
              if (provider === "gemini" && !form.model_name.startsWith("gemini")) change("model_name", "gemini-2.5-flash");
              if (provider === "ollama") change("model_name", "qwen2.5:3b");
            }}>
              <option value="ollama">Ollama (local)</option><option value="vllm">vLLM</option><option value="openai-compatible">OpenAI-compatible</option><option value="openai">OpenAI API</option><option value="gemini">Google Gemini API</option>
            </select></label>
            <label>Model identifier<input required value={form.model_name} onChange={(e) => change("model_name", e.target.value)} placeholder="Model name" /></label>
            <label className="pb-form-span">Custom endpoint <input value={form.endpoint} onChange={(e) => change("endpoint", e.target.value)} placeholder="Optional https:// endpoint" /></label>
            <label className="pb-form-span">Responsibilities<textarea rows={3} value={form.responsibilities} onChange={(e) => change("responsibilities", e.target.value)} placeholder={"One responsibility per line"} /></label>
            <label className="pb-form-span">System instructions<textarea rows={5} value={form.system_prompt} onChange={(e) => change("system_prompt", e.target.value)} placeholder="Describe how this agent should think, communicate and work." /></label>
          </div>
          {form.provider === "openai" || form.provider === "gemini" ? (
            <p className="pb-form-note">Provider credentials are configured server-side. {providers[form.provider]?.credential_env || (form.provider === "openai" ? "OPENAI_API_KEY" : "GEMINI_API_KEY")} is never stored in this agent profile.</p>
          ) : null}
          {error && <div className="pb-inline-error">{error}</div>}
          <footer className="pb-modal-actions"><button type="button" className="pb-button secondary" onClick={onClose}>Cancel</button><button type="submit" className="pb-button primary" disabled={saving}>{saving ? "Saving…" : agent ? "Save changes" : "Create AI employee"} <ArrowUpRight size={15} /></button></footer>
        </form>
      </section>
    </div>
  );
}

export default function WorkspaceApp() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [graph, setGraph] = useState<Graph>({ nodes: [], edges: [] });
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [jobs, setJobs] = useState<DurableJob[]>([]);
  const [coordination, setCoordination] = useState<Coordination>({ enabled: false, mode: "PLAN_ONLY", interval_seconds: 300 });
  const [coordinationSaving, setCoordinationSaving] = useState(false);
  const [connectMode, setConnectMode] = useState(false);
  const [connectSourceId, setConnectSourceId] = useState("");
  const [relationship, setRelationship] = useState("reports_to");
  const [eventVerification, setEventVerification] = useState<{ valid: boolean; checked_events: number } | null>(null);
  const [providers, setProviders] = useState<Record<string, Provider>>({});
  const [defaultProvider, setDefaultProvider] = useState("ollama");
  const [health, setHealth] = useState<Record<string, any>>({});
  const [runtime, setRuntime] = useState<Record<string, any>>({});
  const [workflows, setWorkflows] = useState<WorkflowRun[]>([]);
  const [templates, setTemplates] = useState<AgentManifest[]>([]);
  const [activeView, setActiveView] = useState("company-graph");
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [agentEditor, setAgentEditor] = useState<{ agent: GraphNode | null; draft: AgentDraft } | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [showCompanyForm, setShowCompanyForm] = useState(false);
  const [companyBusy, setCompanyBusy] = useState(false);
  const [leftHidden, setLeftHidden] = useState(() => {
    try { return localStorage.getItem("pinky-sidebar-hidden") === "true"; } catch { return false; }
  });
  const [chatHidden, setChatHidden] = useState(() => {
    try { const saved = localStorage.getItem("pinky-chat-panel-hidden"); return saved === null ? window.matchMedia("(max-width: 1180px)").matches : saved === "true"; } catch { return false; }
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [selectedAuditId, setSelectedAuditId] = useState("");
  const [audit, setAudit] = useState<any[]>([]);
  const [workflowPrompt, setWorkflowPrompt] = useState("");
  const [workflowDomain, setWorkflowDomain] = useState("");
  const [workflowFiles, setWorkflowFiles] = useState<File[]>([]);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [workflowResult, setWorkflowResult] = useState<WorkflowRun | null>(null);
  const [chatMessages, setChatMessages] = useState<{ role: "founder" | "agent"; name: string; content: string; created_at: string }[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const company = useMemo(() => companies.find((item) => item.id === companyId) || null, [companies, companyId]);
  const nodes = graph.nodes || [];
  const agents = useMemo(() => nodes.filter((item) => item.type === "agent"), [nodes]);
  const activeAgents = useMemo(() => agents.filter(nodeIsActive), [agents]);
  const selectedNode = nodes.find((item) => item.id === selectedNodeId) || null;
  const title = navGroups.flatMap((group) => group.items).find((item) => item.id === activeView)?.label || "Workspace";

  const loadCompanyData = useCallback(async (selected: Company) => {
    const tenant = selected.tenant_id || TENANT;
    const [nextGraph, nextEvents, nextVerify, nextJobs, nextCoordination] = await Promise.all([
      api<Graph>("/v2/companies/" + selected.id + "/graph?tenant_id=" + encodeURIComponent(tenant)),
      api<{ events: EventRecord[] }>("/v2/companies/" + selected.id + "/events?tenant_id=" + encodeURIComponent(tenant) + "&limit=200"),
      api<{ valid: boolean; checked_events: number }>("/v2/companies/" + selected.id + "/events/verify?tenant_id=" + encodeURIComponent(tenant)),
      api<{ jobs: DurableJob[] }>("/v2/companies/" + selected.id + "/jobs?tenant_id=" + encodeURIComponent(tenant) + "&limit=100"),
      api<{ coordination: Coordination | null }>("/v2/companies/" + selected.id + "/coordination?tenant_id=" + encodeURIComponent(tenant)),
    ]);
    setGraph({ nodes: nextGraph.nodes || [], edges: nextGraph.edges || [] });
    setEvents(nextEvents.events || []);
    setEventVerification(nextVerify);
    setJobs(nextJobs.jobs || []);
    setCoordination(nextCoordination.coordination || { enabled: false, mode: "PLAN_ONLY", interval_seconds: 300 });
    setSelectedNodeId("");
  }, []);

  const loadOperations = useCallback(async () => {
    const [nextHealth, nextWorkflows, nextTemplates, nextRuntime] = await Promise.all([
      api<Record<string, any>>("/api/healthz"),
      api<{ workflows: WorkflowRun[] }>("/v1/workflows"),
      api<{ agents: AgentManifest[] }>("/v1/agents"),
      api<Record<string, any>>("/v2/runtime").catch(() => ({})),
    ]);
    setHealth(nextHealth);
    setWorkflows(nextWorkflows.workflows || []);
    setTemplates(nextTemplates.agents || []);
    setRuntime(nextRuntime);
  }, []);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    setError("");
    try {
      const [companyResult, providerResult] = await Promise.all([
        api<{ companies: Company[] }>("/v2/companies?tenant_id=" + TENANT),
        api<{ providers: Record<string, Provider>; default_provider: string }>("/v2/model-providers"),
      ]);
      const list = companyResult.companies || [];
      setCompanies(list);
      setProviders(providerResult.providers || {});
      setDefaultProvider(providerResult.default_provider || "ollama");
      await loadOperations();
      const preferred = list.find((item) => item.id === companyId) || list[0] || null;
      if (preferred) {
        setCompanyId(preferred.id);
        await loadCompanyData(preferred);
      } else {
        setCompanyId("");
        setGraph({ nodes: [], edges: [] });
        setEvents([]);
        setEventVerification(null);
      }
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [companyId, loadCompanyData, loadOperations]);

  useEffect(() => { void refreshAll(); }, []);

  useEffect(() => {
    if (!company) return;
    void loadCompanyData(company).catch((reason) => setError(errorText(reason)));
  }, [companyId]);

  useEffect(() => {
    try {
      localStorage.setItem("pinky-sidebar-hidden", leftHidden ? "true" : "false");
      localStorage.setItem("pinky-chat-panel-hidden", chatHidden ? "true" : "false");
    } catch { /* local preferences are optional */ }
  }, [leftHidden, chatHidden]);

  useEffect(() => {
    if (activeView === "agent-messaging") {
      window.dispatchEvent(new CustomEvent("pinky:workspace", { detail: { view: activeView } }));
    }
  }, [activeView]);

  async function createCompany(event: FormEvent) {
    event.preventDefault();
    if (companyName.trim().length < 2) return;
    setCompanyBusy(true);
    setError("");
    try {
      const created = await api<Company>("/v2/companies", {
        method: "POST",
        body: JSON.stringify({ tenant_id: TENANT, owner_id: ACTOR, name: companyName.trim(), vision: "", mission: "", values: [] }),
      });
      const list = [...companies, created];
      setCompanies(list);
      setCompanyId(created.id);
      setCompanyName("");
      setShowCompanyForm(false);
      setNotice("Your company workspace has been created.");
      await loadCompanyData(created);
    } catch (reason) { setError(errorText(reason)); }
    finally { setCompanyBusy(false); }
  }

  async function reloadCompany() {
    if (company) await loadCompanyData(company);
    await loadOperations();
  }

  async function sendFounderInstruction(message: string, artifactIds: string[]) {
    if (!company) throw new Error("Select a company before sending an instruction.");
    setChatBusy(true);
    const now = new Date().toISOString();
    setChatMessages((items) => [...items, { role: "founder", name: "You", content: message, created_at: now }]);
    try {
      const response = await api<{
        reply?: string;
        responses?: { name: string; role?: string; reply: string; recipient_name?: string; message_kind?: string }[];
      }>("/v2/companies/" + company.id + "/chat", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: company.tenant_id || TENANT,
          actor_id: ACTOR,
          message,
          artifact_ids: artifactIds,
          history: chatMessages.slice(-12).map((item) => ({ role: item.role === "founder" ? "user" : "assistant", content: item.name + ": " + item.content })),
        }),
      });
      const responses = response.responses || [];
      const resultMessages = responses.length
        ? responses.map((item) => ({ role: "agent" as const, name: item.name + (item.role ? " · " + item.role : ""), content: item.reply, created_at: new Date().toISOString() }))
        : response.reply ? [{ role: "agent" as const, name: "AI workforce", content: response.reply, created_at: new Date().toISOString() }] : [];
      setChatMessages((items) => [...items, ...resultMessages]);
    } catch (reason) {
      setChatMessages((items) => [...items, { role: "agent", name: "System", content: errorText(reason), created_at: new Date().toISOString() }]);
      throw reason;
    } finally {
      setChatBusy(false);
    }
  }

  async function submitWorkflow(event: FormEvent) {
    event.preventDefault();
    if (!workflowPrompt.trim() || workflowBusy) return;
    setWorkflowBusy(true);
    setError("");
    setWorkflowResult(null);
    try {
      const artifacts = await Promise.all(workflowFiles.map((file) => new Promise<{ filename: string; mime_type: string; base64_data: string }>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({ filename: file.name, mime_type: file.type, base64_data: String(reader.result).split(",")[1] });
        reader.onerror = () => reject(new Error("Unable to read " + file.name));
        reader.readAsDataURL(file);
      })));
      const result = await api<WorkflowRun>("/v1/workflows/invoke", {
        method: "POST",
        body: JSON.stringify({ prompt: workflowPrompt.trim(), tenant_id: TENANT, target_domain: workflowDomain || null, artifacts }),
      });
      setWorkflowResult(result);
      setWorkflowPrompt("");
      setWorkflowFiles([]);
      await loadOperations();
      setNotice(result.status === "PENDING_APPROVAL" ? "Workflow paused for human approval." : "Workflow completed.");
    } catch (reason) { setError(errorText(reason)); }
    finally { setWorkflowBusy(false); }
  }

  async function openAudit(threadId: string) {
    setSelectedAuditId(threadId);
    setActiveView("audit");
    try {
      const result = await api<{ audit_trail: any[] }>("/v1/audit/" + encodeURIComponent(threadId));
      setAudit(result.audit_trail || []);
    } catch (reason) { setError(errorText(reason)); }
  }

  async function decideApproval(threadId: string, decision: "APPROVED" | "REJECTED") {
    const approver = window.prompt("Enter approver ID for the audit record:", "demo-approver");
    if (!approver?.trim()) return;
    try {
      const result = await api<WorkflowRun>("/v1/workflows/" + threadId + "/approve", {
        method: "POST",
        body: JSON.stringify({ approver_id: approver.trim(), decision, notes: "Reviewed in Pinky Bread workspace" }),
      });
      setWorkflowResult(result);
      await loadOperations();
      setNotice(decision === "APPROVED" ? "Approval recorded." : "Proposal rejected.");
    } catch (reason) { setError(errorText(reason)); }
  }

  async function reloadTemplates() {
    try {
      const result = await api<{ status: string; active_count?: number; validation_errors?: string[] }>("/v1/agents/reload", { method: "POST" });
      await loadOperations();
      setNotice(result.status === "reloaded" ? (result.active_count || 0) + " workflow templates loaded." : (result.validation_errors || []).join("; "));
    } catch (reason) { setError(errorText(reason)); }
  }

  async function enqueueForNode(node: GraphNode) {
    if (!company) return;
    const route = node.type === "goal"
      ? "/v2/companies/" + company.id + "/goals/" + node.id + "/jobs"
      : node.type === "work"
        ? "/v2/companies/" + company.id + "/work/" + node.id + "/jobs"
        : node.type === "meeting"
          ? "/v2/companies/" + company.id + "/meetings/" + node.id + "/jobs"
          : "";
    if (!route) return;
    const payload = node.type === "goal"
      ? { tenant_id: company.tenant_id || TENANT, actor_id: ACTOR, kind: "goal_plan" }
      : { tenant_id: company.tenant_id || TENANT, actor_id: ACTOR };
    try {
      await api(route, { method: "POST", body: JSON.stringify(payload) });
      await reloadCompany();
      setNotice("Durable " + node.type + " job queued.");
      setActiveView("durable-workforce");
    } catch (reason) { setError(errorText(reason)); }
  }

  async function cancelJob(job: DurableJob) {
    if (!company) return;
    try {
      await api("/v2/companies/" + company.id + "/jobs/" + job.job_id + "/cancel", {
        method: "POST", body: JSON.stringify({ tenant_id: company.tenant_id || TENANT, actor_id: ACTOR }),
      });
      await reloadCompany();
      setNotice("Cancellation requested for job " + shortId(job.job_id) + ".");
    } catch (reason) { setError(errorText(reason)); }
  }

  async function saveCoordination(event: FormEvent) {
    event.preventDefault();
    if (!company) return;
    setCoordinationSaving(true);
    try {
      const result = await api<{ coordination: Coordination }>("/v2/companies/" + company.id + "/coordination", {
        method: "PUT",
        body: JSON.stringify({ tenant_id: company.tenant_id || TENANT, actor_id: ACTOR, enabled: coordination.enabled, mode: coordination.mode, interval_seconds: coordination.interval_seconds }),
      });
      setCoordination(result.coordination);
      setNotice(result.coordination.enabled ? "Recurring company coordination enabled." : "Recurring company coordination disabled.");
    } catch (reason) { setError(errorText(reason)); }
    finally { setCoordinationSaving(false); }
  }

  async function connectGraphNodes(targetId: string) {
    if (!company || !connectSourceId || !targetId || connectSourceId === targetId) return;
    try {
      await api("/v2/companies/" + company.id + "/edges", {
        method: "POST",
        body: JSON.stringify({ tenant_id: company.tenant_id || TENANT, actor_id: ACTOR, source_node_id: connectSourceId, target_node_id: targetId, relationship, data: { created_from: "react_company_graph" } }),
      });
      setConnectMode(false);
      setConnectSourceId("");
      await reloadCompany();
      setNotice("Company relationship created.");
    } catch (reason) { setError(errorText(reason)); }
  }

  async function recordKpiMeasurement(node: GraphNode) {
    if (!company) return;
    const rawValue = window.prompt("Enter the measured KPI value", String(node.data?.current_value ?? ""));
    if (rawValue === null || rawValue.trim() === "") return;
    const actualValue = Number(rawValue);
    if (!Number.isFinite(actualValue)) {
      setError("Enter a valid numeric KPI value.");
      return;
    }
    const source = window.prompt("Measurement source", "Founder measurement");
    if (!source?.trim()) return;
    const evidence = window.prompt("Optional evidence or notes", "") || "";
    try {
      await api("/v2/companies/" + company.id + "/kpis/" + node.id + "/measure", {
        method: "POST",
        body: JSON.stringify({ tenant_id: company.tenant_id || TENANT, actor_id: ACTOR, actual_value: actualValue, source: source.trim(), evidence }),
      });
      await reloadCompany();
      setNotice("KPI measurement recorded.");
    } catch (reason) { setError(errorText(reason)); }
  }

  async function verifyEvents() {
    if (!company) return;
    try {
      const result = await api<{ valid: boolean; checked_events: number }>("/v2/companies/" + company.id + "/events/verify?tenant_id=" + encodeURIComponent(company.tenant_id || TENANT));
      setEventVerification(result);
      setNotice(result.valid ? "Company event hash chain verified." : "Event hash chain verification failed.");
    } catch (reason) { setError(errorText(reason)); }
  }

  async function signOut() {
    try { await fetch("/auth/logout", { method: "POST" }); }
    finally { window.location.replace("/login"); }
  }

  function editAgent(agent: GraphNode | null) {
    const data = agent?.data || {};
    const model = data.model_configuration || {};
    setAgentEditor({
      agent,
      draft: agent ? {
        name: agent.name,
        role: String(data.role || ""),
        title: String(data.title || ""),
        description: agent.description || "",
        skills: Array.isArray(data.skills) ? data.skills.join(", ") : "",
        responsibilities: Array.isArray(data.responsibilities) ? data.responsibilities.join("\n") : "",
        system_prompt: String(data.system_prompt || ""),
        seniority_level: Number(data.seniority_level || 3),
        authority: String(data.authority || "SPECIALIST").toUpperCase() === "COORDINATOR" ? "COORDINATOR" : "SPECIALIST",
        manager_id: String(data.manager_id || ""),
        provider: String(model.provider || "ollama"),
        model_name: String(model.model_name || "qwen2.5:3b"),
        endpoint: String(model.endpoint || ""),
      } : blankAgent,
    });
  }

  async function pauseAgent(agent: GraphNode) {
    try {
      await api("/v2/companies/" + company?.id + "/agents/" + agent.id, {
        method: "PATCH",
        body: JSON.stringify({ tenant_id: company?.tenant_id || TENANT, actor_id: ACTOR, status: agent.status === "PAUSED" ? "ACTIVE" : "PAUSED" }),
      });
      await reloadCompany();
    } catch (reason) { setError(errorText(reason)); }
  }

  async function addGraphNode(type: "goal" | "kpi" | "work" | "meeting") {
    if (!company) return;
    const name = window.prompt(type === "goal" ? "Name this company goal" : type === "kpi" ? "Name this KPI" : type === "work" ? "Name this work item" : "Name this meeting");
    if (!name?.trim()) return;
    try {
      await api("/v2/companies/" + company.id + "/nodes", {
        method: "POST",
        body: JSON.stringify({
          tenant_id: company.tenant_id || TENANT, actor_id: ACTOR, node_type: type,
          name: name.trim(), description: "", status: type === "work" ? "BACKLOG" : "PLANNED", data: type === "kpi" ? { unit: "value", target_value: null, current_value: null } : {},
        }),
      });
      await reloadCompany();
      setNotice(type.charAt(0).toUpperCase() + type.slice(1) + " added to the company graph.");
    } catch (reason) { setError(errorText(reason)); }
  }

  const workflowCount = workflows.length;
  const pendingCount = workflows.filter((item) => item.status === "PENDING_APPROVAL").length;
  const completedCount = workflows.filter((item) => item.status === "COMPLETED").length;
  const activeJobCount = jobs.filter((item) => ["PENDING", "RUNNING"].includes(item.status)).length;
  const goals = nodes.filter((item) => item.type === "goal");
  const workItems = nodes.filter((item) => ["work", "deliverable", "document"].includes(item.type));
  const companyNode = nodes.find((item) => item.type === "company") || company;

  return (
    <div className={"pb-shell" + (leftHidden ? " is-left-collapsed" : "") + (chatHidden ? " is-chat-collapsed" : "")}>
      <aside className="pb-sidebar">
        <div className="pb-brand-row">
          <div className="pb-brand-mark"><span /><span /><span /></div>
          <div className="pb-brand-copy"><strong>The Pinky Bread</strong><small>AUTONOMOUS ORGANIZATION</small></div>
          <button className="pb-icon-button pb-sidebar-close" onClick={() => setLeftHidden(true)} title="Collapse sidebar" aria-label="Collapse sidebar"><PanelLeftClose size={17} /></button>
        </div>
        <div className="pb-workspace-switcher"><span className="pb-company-avatar"><Building2 size={15} /></span><span><small>WORKSPACE</small><strong>{company?.name || "No company yet"}</strong></span><ChevronDown size={14} /></div>
        <nav className="pb-navigation" aria-label="Main navigation">
          {navGroups.map((group) => (
            <div className="pb-nav-group" key={group.label}>
              <div className="pb-nav-label">{group.label}</div>
              {group.items.map(({ id, label, icon: Icon }) => (
                <button key={id} className={"pb-nav-item" + (activeView === id ? " active" : "")} onClick={() => setActiveView(id)} title={label}>
                  <Icon size={17} strokeWidth={1.8} /><span>{label}</span>
                  {id === "workflows" && workflowCount > 0 && <em>{workflowCount}</em>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        {company && (
          <div className="pb-sidebar-team">
            <div className="pb-sidebar-team-heading"><span>YOUR VIRTUAL TEAM</span><button onClick={() => editAgent(null)} title="Create AI employee"><Plus size={14} /></button></div>
            <div className="pb-sidebar-agent-list">
              {activeAgents.slice(0, 5).map((agent) => (
                <button key={agent.id} onClick={() => { setActiveView("company-agents"); setSelectedNodeId(agent.id); }} className="pb-sidebar-agent">
                  <span className="pb-agent-avatar">{initials(agent.name)}</span><span><strong>{agent.name}</strong><small>{nodeRole(agent)}</small></span><i />
                </button>
              ))}
              {!activeAgents.length && <p className="pb-sidebar-empty">Your workforce starts here. Create your first AI employee.</p>}
            </div>
          </div>
        )}
        <div className="pb-sidebar-footer">
          <div className="pb-runtime-card"><div><span className="pb-runtime-dot" /> LOCAL-FIRST RUNTIME</div><strong>{health.mock_inference ? "Development simulation" : runtime.provider || "AI runtime"}</strong><small>Provider credentials stay server-side.</small></div>
          <div className="pb-user-row"><span className="pb-user-avatar">PB</span><span><strong>Workspace Admin</strong><small>Founder / operator</small></span><button onClick={() => void signOut()} title="Sign out" aria-label="Sign out"><LogOut size={15} /></button></div>
        </div>
      </aside>

      <main className="pb-main">
        <header className="pb-topbar">
          <div className="pb-topbar-leading">
            <button className="pb-icon-button" onClick={() => setLeftHidden((value) => !value)} aria-label={leftHidden ? "Show sidebar" : "Hide sidebar"} title={leftHidden ? "Show sidebar" : "Hide sidebar"}>
              {leftHidden ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>
            <div className="pb-breadcrumb"><span>Workspace</span><b>/</b><strong>{title}</strong></div>
          </div>
          <div className="pb-topbar-actions">
            <label className="pb-company-picker"><span>COMPANY</span><select id="graph-company-picker" aria-label="Select company" value={companyId} onChange={(event) => setCompanyId(event.target.value)}><option value="">Select company…</option>{companies.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><ChevronDown size={13} /></label>
            <span className="pb-environment"><i />{String(health.environment || "development").toUpperCase()}</span>
            <button className="pb-icon-button" onClick={() => void reloadCompany().catch((reason) => setError(errorText(reason)))} title="Refresh workspace" aria-label="Refresh workspace"><RefreshCw size={16} className={refreshing ? "pb-spin" : ""} /></button>
            <button className="pb-icon-button" onClick={() => setChatHidden((value) => !value)} title={chatHidden ? "Show founder chat" : "Hide founder chat"} aria-label={chatHidden ? "Show founder chat" : "Hide founder chat"}>
              {chatHidden ? <PanelRightOpen size={17} /> : <PanelRightClose size={17} />}
            </button>
          </div>
        </header>

        {(error || notice) && (
          <div className={"pb-global-feedback" + (error ? " is-error" : "")} role="status">
            <span>{error || notice}</span><button onClick={() => { setError(""); setNotice(""); }} aria-label="Dismiss message"><X size={14} /></button>
          </div>
        )}

        <div className="pb-page-scroll">
          {loading ? <div className="pb-page-loading"><span className="pb-loading-mark" /><strong>Preparing your workspace</strong><small>Connecting company graph and workforce services…</small></div> : null}

          {!loading && activeView === "company-graph" && (
            <section className="pb-page">
              <PageHeading eyebrow="THE AUTONOMOUS ORGANIZATION" title="Your company. Your agents. One living graph." description="Build your virtual organisation, define reporting lines and connect company goals to the people and work that move them forward." actions={<><button className="pb-button secondary" onClick={() => void addGraphNode("goal")} disabled={!company}><Plus size={15} /> Add goal</button><button className="pb-button secondary" onClick={() => void addGraphNode("kpi")} disabled={!company}><Plus size={15} /> Add KPI</button><button className="pb-button secondary" onClick={() => void addGraphNode("work") disabled={!company}><Plus size={15} /> Add work</button><button className="pb-button secondary" onClick={() => void addGraphNode("meeting")} disabled={!company}><Plus size={15} /> Add meeting</button><button className="pb-button primary" onClick={() => editAgent(null)} disabled={!company}><Plus size={15} /> Add AI employee</button></>} />
              {!company ? (
                <section className="pb-onboarding-card">
                  <div className="pb-onboarding-art"><div className="pb-orbit orbit-one" /><div className="pb-orbit orbit-two" /><span><Building2 size={30} /></span></div>
                  <div className="pb-onboarding-copy"><div className="pb-eyebrow">START YOUR ORGANIZATION</div><h2>Give your company a name.</h2><p>Create a company workspace first. Then define its vision, goals and AI workforce.</p>
                    {showCompanyForm ? <form className="pb-create-company-form" onSubmit={createCompany}><input autoFocus required minLength={2} value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="e.g. Northstar Studio" /><button className="pb-button primary" disabled={companyBusy}>{companyBusy ? "Creating…" : "Establish company"} <ArrowUpRight size={15} /></button></form> : <button className="pb-button primary" onClick={() => setShowCompanyForm(true)}><Plus size={15} /> Create your company</button>}
                  </div>
                </section>
              ) : (
                <div className="pb-graph-layout">
                  <section className="pb-graph-panel">
                    <div className="pb-panel-toolbar"><div><span className="pb-eyebrow">COMPANY NETWORK</span><strong>{nodes.length} nodes <i>·</i> {graph.edges.length} relationships</strong></div><div className="pb-graph-actions"><span className="pb-live-pill"><i /> LIVE GRAPH</span><button className={"pb-button small " + (connectMode ? "primary" : "secondary")} onClick={() => { setConnectMode((value) => !value); setConnectSourceId(""); }}>{connectMode ? "Cancel connect" : "Connect nodes"}</button></div></div>
                    {connectMode && <div className="pb-connect-hint"><span>{connectSourceId ? "Select a destination node" : "Select a source node"}</span><select value={relationship} onChange={(event) => setRelationship(event.target.value)}><option value="reports_to">Reports to</option><option value="owns">Owns</option><option value="contributes_to">Contributes to</option><option value="assigned_to">Assigned to</option><option value="depends_on">Depends on</option><option value="collaborates_with">Collaborates with</option><option value="participates_in">Participates in</option><option value="produces">Produces</option><option value="measures">Measures</option><option value="blocks">Blocks</option><option value="informs">Informs</option></select></div>}
                    {nodes.length <= 1 ? <EmptyState icon={Network} title="Your graph is ready to grow" description="Create an AI employee, goal or work item to begin building your organisation." action={<button className="pb-button primary" onClick={() => editAgent(null)}><Plus size={15} /> Create first agent</button>} /> : (
                      <div className="pb-graph-canvas">
                        <svg viewBox={"0 0 1000 " + Math.max(560, 190 + Math.ceil(Math.max(1, nodes.length - 1) / 3) * 148)} role="img" aria-label="Company relationship graph">
                          <defs><pattern id="pb-dot-grid" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#dfe8e0" /></pattern></defs>
                          <rect width="1000" height="100%" fill="url(#pb-dot-grid)" />
                          {(() => {
                            const positions = new Map<string, { x: number; y: number }>();
                            positions.set(company?.id || "", { x: 500, y: 82 });
                            const others = nodes.filter((item) => item.type !== "company");
                            others.forEach((item, index) => positions.set(item.id, { x: 165 + (index % 3) * 335, y: 225 + Math.floor(index / 3) * 145 }));
                            return <>
                              {graph.edges.map((edge) => {
                                const from = positions.get(edge.source), to = positions.get(edge.target);
                                if (!from || !to) return null;
                                return <path key={edge.id} d={"M " + from.x + " " + (from.y + 32) + " C " + from.x + " " + (from.y + 90) + ", " + to.x + " " + (to.y - 65) + ", " + to.x + " " + (to.y - 25)} fill="none" stroke="#c8d9ca" strokeWidth="2" strokeDasharray={edge.relationship === "reports_to" ? "0" : "5 5"} />;
                              })}
                              <g transform="translate(370 30)" className="pb-graph-node is-company" onClick={() => setSelectedNodeId(company?.id || "")} role="button" tabIndex={0}>
                                <rect width="260" height="76" rx="16" /><circle cx="34" cy="38" r="18" /><text x="34" y="43" textAnchor="middle" className="pb-node-symbol">⌂</text><text x="66" y="32" className="pb-node-title">{company?.name}</text><text x="66" y="51" className="pb-node-subtitle">COMPANY / FOUNDER</text>
                              </g>
                              {others.map((item) => {
                                const point = positions.get(item.id)!;
                                const tone = item.type === "agent" ? "agent" : item.type === "goal" ? "goal" : "work";
                                return <g key={item.id} transform={"translate(" + (point.x - 125) + " " + (point.y - 35) + ")"} className={"pb-graph-node " + tone + (selectedNodeId === item.id ? " selected" : "") + (connectSourceId === item.id ? " connect-source" : "")} onClick={() => { if (connectMode) { if (!connectSourceId) setConnectSourceId(item.id); else void connectGraphNodes(item.id); } else setSelectedNodeId(item.id); }} role="button" tabIndex={0}>
                                  <rect width="250" height="72" rx="13" /><circle cx="31" cy="36" r="17" /><text x="31" y="40" textAnchor="middle" className="pb-node-symbol">{item.type === "agent" ? "AI" : item.type === "goal" ? "◎" : "↗"}</text><text x="58" y="30" className="pb-node-title">{item.name.slice(0, 26)}</text><text x="58" y="49" className="pb-node-subtitle">{(item.type + " / " + (item.status || "ACTIVE")).toUpperCase().slice(0, 32)}</text>
                                </g>;
                              })}
                            </>;
                          })()}
                        </svg>
                        <div className="pb-graph-legend"><span><i className="company" /> Company</span><span><i className="agent" /> AI employees</span><span><i className="goal" /> Goals / KPIs</span><span><i className="work" /> Work / outcomes</span></div>
                      </div>
                    )}
                  </section>
                  <aside className="pb-inspector">
                    {selectedNode ? <>
                      <div className="pb-inspector-kicker">NODE INSPECTOR</div><div className="pb-inspector-avatar">{selectedNode.type === "agent" ? <Bot size={22} /> : <Network size={22} />}</div><h3>{selectedNode.name}</h3><span className="pb-node-type">{selectedNode.type.toUpperCase()} · {selectedNode.status || "ACTIVE"}</span>
                      <p>{selectedNode.description || "No additional description has been provided."}</p>
                      {selectedNode.type === "agent" && <><div className="pb-inspector-detail"><span>ROLE</span><strong>{nodeRole(selectedNode)}</strong></div><div className="pb-inspector-detail"><span>MODEL</span><strong>{selectedNode.data?.model_configuration?.model_name || "Default model"}</strong></div><button className="pb-button secondary full" onClick={() => editAgent(selectedNode)}>Edit agent profile</button></>}
                      {selectedNode.type === "kpi" && <button className="pb-button secondary full" onClick={() => void recordKpiMeasurement(selectedNode)}>Record KPI measurement <ArrowUpRight size={14} /></button>}
                      {["goal", "work", "meeting"].includes(selectedNode.type) && <button className="pb-button primary full" onClick={() => void enqueueForNode(selectedNode)}>{selectedNode.type === "goal" ? "Queue goal planning" : selectedNode.type === "work" ? "Queue work execution" : "Queue meeting"} <ArrowUpRight size={14} /></button>}
                      <div className="pb-inspector-detail"><span>CREATED</span><strong>{dateTime(selectedNode.created_at)}</strong></div>
                    </> : <div className="pb-inspector-empty"><div><Network size={23} /></div><strong>Select a node</strong><p>Inspect ownership, reporting lines, status and model configuration.</p></div>}
                  </aside>
                </div>
              )}
            </section>
          )}

          {!loading && activeView === "company-events" && (
            <section className="pb-page">
              <PageHeading eyebrow="COMPANY / ACTIVITY" title="Company Event Log" description="A chronological record of changes across your organisation, its agents, work and decisions." actions={<button className="pb-button secondary" onClick={() => void verifyEvents()} disabled={!company}><ShieldCheck size={15} /> Verify event chain</button>} />
              <div className="pb-section-card">
                <div className="pb-section-card-heading"><div><span className="pb-eyebrow">APPEND-ONLY EVENT STREAM</span><h2>What is changing</h2></div><span className="pb-count-pill">{events.length} events</span></div>
                {eventVerification && <div className={"pb-verification " + (eventVerification.valid ? "valid" : "invalid")}><ShieldCheck size={15} />{eventVerification.valid ? "Hash chain verified · " + eventVerification.checked_events + " events checked" : "Hash chain verification failed"}</div>}
                {!events.length ? <EmptyState icon={Activity} title="No company activity yet" description="Agent creation, goal updates and company changes will appear here." /> : <div className="pb-event-list">{[...events].reverse().map((item) => <article className="pb-event-row" key={item.id}><span className="pb-event-marker"><Activity size={14} /></span><div className="pb-event-copy"><strong>{item.type.replace(/\./g, " · ")}</strong><p>{String(item.payload?.name || item.payload?.node_id || item.payload?.changes?.name || "Company record updated")}</p><small>{item.actor_id} · {dateTime(item.occurred_at)}</small></div><span className="pb-event-number">#{item.event_no}</span></article>)}</div>}
              </div>
            </section>
          )}

          {!loading && activeView === "founder-view" && (
            <section className="pb-page">
              <PageHeading eyebrow="COMPANY / FOUNDER" title="Founder View" description="A clear operating picture of the company: objectives, people and work in one place." />
              {!company ? <EmptyState title="No company selected" description="Create a company to see your operating snapshot." action={<button className="pb-button primary" onClick={() => { setActiveView("company-graph"); setShowCompanyForm(true); }}>Create a company</button>} /> : <>
                <section className="pb-founder-banner"><div><span className="pb-eyebrow">YOUR ORGANIZATION</span><h2>{company.name}</h2><p>{company.data?.mission || "Define your mission and operating principles with your AI workforce."}</p></div><span className="pb-founder-emblem"><Sparkles size={26} /></span></section>
                <div className="pb-stat-grid"><StatCard label="Company goals" value={goals.length} detail="Objectives being pursued" icon={Command} /><StatCard label="Active agents" value={activeAgents.length} detail="Virtual employees available" icon={Users} /><StatCard label="Work items" value={workItems.length} detail="Tasks and deliverables" icon={Workflow} /><StatCard label="Recorded events" value={events.length} detail="Auditable company activity" icon={Activity} /></div>
                <div className="pb-two-column">
                  <section className="pb-section-card"><div className="pb-section-card-heading"><div><span className="pb-eyebrow">PEOPLE</span><h2>Leadership and workforce</h2></div><button className="pb-text-button" onClick={() => setActiveView("company-agents")}>Manage team <ArrowUpRight size={13} /></button></div>{activeAgents.slice(0, 6).map((agent) => <div className="pb-mini-agent" key={agent.id}><span className="pb-agent-avatar">{initials(agent.name)}</span><span><strong>{agent.name}</strong><small>{nodeRole(agent)}</small></span><span className="pb-mini-status">ACTIVE</span></div>)}{!activeAgents.length && <p className="pb-muted-copy">Create the first AI employee to start building your team.</p>}</section>
                  <section className="pb-section-card"><div className="pb-section-card-heading"><div><span className="pb-eyebrow">RECENT ACTIVITY</span><h2>Company updates</h2></div><button className="pb-text-button" onClick={() => setActiveView("company-events")}>View log <ArrowUpRight size={13} /></button></div>{[...events].reverse().slice(0, 6).map((item) => <div className="pb-mini-event" key={item.id}><span className="pb-mini-event-dot" /><span><strong>{item.type.replace(/\./g, " · ")}</strong><small>{dateTime(item.occurred_at)}</small></span></div>)}{!events.length && <p className="pb-muted-copy">No company activity has been recorded yet.</p>}</section>
                </div>
              </>}
            </section>
          )}

          {!loading && activeView === "company-agents" && (
            <section className="pb-page">
              <PageHeading eyebrow="COMPANY WORKFORCE / MANAGEMENT" title="Your AI workforce" description="Create virtual employees with their own responsibilities, skills, seniority, reporting lines and model configuration." actions={<button className="pb-button primary" onClick={() => editAgent(null)} disabled={!company}><Plus size={15} /> Create agent</button>} />
              {!company ? <EmptyState title="Create a company first" description="Your AI workforce belongs to a company workspace." action={<button className="pb-button primary" onClick={() => setActiveView("company-graph")}>Open company setup</button>} /> : <>
                <div className="pb-workforce-summary"><div><strong>{activeAgents.length}</strong><span>Active employees</span></div><div><strong>{agents.length - activeAgents.length}</strong><span>Paused / archived</span></div><div><strong>{activeAgents.filter((item) => String(item.data?.authority).toUpperCase() === "COORDINATOR").length}</strong><span>Coordinators</span></div></div>
                {agents.length ? <div className="pb-agent-grid">{agents.map((agent) => <article className="pb-agent-card" key={agent.id}><div className="pb-agent-card-top"><span className="pb-agent-avatar large">{initials(agent.name)}</span><span className={"pb-agent-status " + (nodeIsActive(agent) ? "active" : "paused")}>{agent.status || "ACTIVE"}</span></div><h3>{agent.name}</h3><p className="pb-agent-title">{agent.data?.title || agent.data?.role || "AI employee"}</p><p className="pb-agent-description">{agent.description || "No description provided."}</p><div className="pb-agent-tags"><span>Level {agent.data?.seniority_level || 3}</span><span>{agent.data?.authority === "COORDINATOR" ? "Coordinator" : "Specialist"}</span></div><div className="pb-agent-model"><span>MODEL</span><strong>{agent.data?.model_configuration?.model_name || "Default model"}</strong><small>{agent.data?.model_configuration?.provider || defaultProvider}</small></div><footer><button className="pb-button secondary small" onClick={() => editAgent(agent)}>Edit profile</button><button className="pb-button ghost small" onClick={() => void pauseAgent(agent)}>{agent.status === "PAUSED" ? "Reactivate" : "Pause"}</button></footer></article>)}</div> : <EmptyState icon={Users} title="Your virtual team starts here" description="Define your first AI employee and assign a specialist role." action={<button className="pb-button primary" onClick={() => editAgent(null)}><Plus size={15} /> Create AI employee</button>} />}
              </>}
            </section>
          )}

          {!loading && activeView === "durable-workforce" && (
            <section className="pb-page">
              <PageHeading eyebrow="EXECUTION / DURABLE RUNTIME" title="Durable Workforce" description="Monitor queued agent work, inspect execution status and configure recurring company coordination." actions={<button className="pb-button secondary" onClick={() => void reloadCompany()} disabled={!company}><RefreshCw size={14} /> Refresh jobs</button>} />
              {!company ? <EmptyState icon={Zap} title="Select a company first" description="Durable jobs and company coordination are scoped to a company workspace." /> : <>
                <div className="pb-stat-grid"><StatCard label="Total jobs" value={jobs.length} detail="PostgreSQL job records" icon={Workflow} /><StatCard label="Pending / running" value={activeJobCount} detail="Awaiting or executing work" icon={Clock3} /><StatCard label="Completed" value={jobs.filter((job) => job.status === "COMPLETED").length} detail="Successfully executed" icon={Check} /><StatCard label="Failed" value={jobs.filter((job) => job.status === "FAILED").length} detail="Require review or retry" icon={AlertCircle} /></div>
                <div className="pb-two-column">
                  <section className="pb-section-card"><div className="pb-section-card-heading"><div><span className="pb-eyebrow">FOUNDER CONTROL</span><h2>Recurring coordination</h2></div><span className={"pb-agent-status " + (coordination.enabled ? "active" : "paused")}>{coordination.enabled ? "ENABLED" : "DISABLED"}</span></div>
                    <form className="pb-workflow-form" onSubmit={saveCoordination}>
                      <label className="pb-toggle-row"><span><strong>Enable scheduled planning</strong><small>Use the assigned coordinator to review open company goals on a recurring schedule.</small></span><input type="checkbox" checked={coordination.enabled} onChange={(event) => setCoordination((value) => ({ ...value, enabled: event.target.checked }))} /></label>
                      <label>Execution mode<select value={coordination.mode} onChange={(event) => setCoordination((value) => ({ ...value, mode: event.target.value as Coordination["mode"] }))}><option value="PLAN_ONLY">Plan only · recommend work</option><option value="AUTO_EXECUTE">Auto execute · execute eligible work</option></select></label>
                      <label>Interval<select value={coordination.interval_seconds} onChange={(event) => setCoordination((value) => ({ ...value, interval_seconds: Number(event.target.value) }))}><option value={300}>Every 5 minutes</option><option value={900}>Every 15 minutes</option><option value={1800}>Every 30 minutes</option><option value={3600}>Every hour</option><option value={86400}>Daily</option></select></label>
                      <div className="pb-coordination-dates"><span>LAST RUN<strong>{dateTime(coordination.last_run_at || undefined)}</strong></span><span>NEXT RUN<strong>{dateTime(coordination.next_run_at || undefined)}</strong></span></div>
                      <button className="pb-button primary full" type="submit" disabled={coordinationSaving}>{coordinationSaving ? "Saving policy…" : "Save coordination policy"}</button>
                      <p className="pb-form-note">Auto execution is controlled by the founder. A real agent with Coordinator authority must be assigned; the scheduler does not invent a Head of Agents identity.</p>
                    </form>
                  </section>
                  <section className="pb-section-card"><div className="pb-section-card-heading"><div><span className="pb-eyebrow">QUEUE OVERVIEW</span><h2>Latest durable jobs</h2></div><span className="pb-count-pill">{jobs.length} jobs</span></div>
                    {jobs.length ? <div className="pb-job-list">{jobs.map((job) => <article className="pb-job-row" key={job.job_id}><div className="pb-job-main"><span className="pb-job-icon"><Workflow size={14} /></span><div><strong>{job.kind.replace(/_/g, " ")}</strong><small>{shortId(job.target_id)} · {dateTime(job.created_at)}</small></div></div><span className={"pb-status " + job.status.toLowerCase()}>{job.status.replace(/_/g, " ")}</span>{["PENDING", "RUNNING"].includes(job.status) && <button className="pb-button ghost small" onClick={() => void cancelJob(job)}>Cancel</button>}{job.last_error && <p className="pb-job-error">{job.last_error}</p>}</article>)}</div> : <EmptyState icon={Workflow} title="No durable jobs queued" description="Select a goal, work item or meeting in Company Graph and queue it for execution." />}
                  </section>
                </div>
              </>}
            </section>
          )}

          {!loading && activeView === "agent-messaging" && (
            <section className="pb-page pb-a2a-page">
              <div id="a2a-workspace-root"><AgentConversations /></div>
            </section>
          )}

          {!loading && activeView === "model-providers" && (
            <section className="pb-page">
              <PageHeading eyebrow="AI RUNTIME / CONFIGURATION" title="Model providers" description="Connect your virtual employees to local inference or commercial LLM APIs. Select the provider and model on each agent profile." actions={<button className="pb-button secondary" onClick={() => void refreshAll()}><RefreshCw size={14} /> Refresh status</button>} />
              <div className="pb-provider-grid">{["openai", "gemini", "ollama", "vllm", "openai-compatible"].map((key) => {
                const item = providers[key] || {};
                const configured = Boolean(item.configured);
                const missing = Boolean(item.requires_api_key && !configured);
                return <article className="pb-provider-card" key={key}><div className="pb-provider-top"><span className="pb-provider-icon"><Zap size={17} /></span><span className={"pb-provider-state " + (missing ? "missing" : "ready")}><i />{item.requires_api_key ? configured ? "API key configured" : "API key missing" : key === "ollama" ? "Local provider" : "Endpoint configured"}</span></div><h2>{item.label || key}</h2><p>{({ openai: "Use GPT models through the official OpenAI API.", gemini: "Connect Google Gemini models through the Gemini API.", ollama: "Run models locally with the Ollama service.", vllm: "Connect a self-hosted vLLM inference endpoint.", "openai-compatible": "Connect another service implementing the OpenAI Chat Completions API." } as Record<string, string>)[key]}</p><div className="pb-provider-meta"><span>ENDPOINT</span><code>{item.endpoint || "Provider default"}</code></div><div className="pb-provider-meta"><span>SERVER ENVIRONMENT</span><code>{item.credential_env || "No separate key required"}</code></div></article>;
              })}</div>
              <section className="pb-provider-security"><div><ShieldCheck size={19} /><strong>Credentials stay on the server</strong></div><p>Configure provider credentials in the project <code>.env</code> file. API keys are never stored in an agent profile or exposed to the browser.</p><pre>OPENAI_API_KEY=your-openai-api-key{"\n"}GEMINI_API_KEY=your-google-ai-studio-api-key</pre><small>Commercial API usage may incur charges under your provider account. Configure billing limits with your provider.</small></section>
            </section>
          )}

          {!loading && activeView === "overview" && (
            <section className="pb-page">
              <PageHeading eyebrow="CONTROL PLANE / OVERVIEW" title="Good morning, Founder." description="A live snapshot of your AI company, execution pipeline and operating health." actions={<button className="pb-button primary" onClick={() => setActiveView("workflows")}><Plus size={15} /> Start workflow</button>} />
              <div className="pb-stat-grid"><StatCard label="Registered templates" value={templates.length} detail="Workflow manifests loaded" icon={Bot} /><StatCard label="Workflow runs" value={workflowCount} detail="Persisted execution threads" icon={Workflow} /><StatCard label="Awaiting approval" value={pendingCount} detail="Human-in-the-loop gates" icon={Clock3} /><StatCard label="Inference mode" value={health.mock_inference ? "MOCK" : String(runtime.provider || "LOCAL").toUpperCase()} detail={health.mock_inference ? "Development simulation" : "Runtime configuration"} icon={Zap} /></div>
              <div className="pb-two-column">
                <section className="pb-section-card"><div className="pb-section-card-heading"><div><span className="pb-eyebrow">WORKFORCE</span><h2>Company health</h2></div><span className="pb-live-pill"><i /> API {health.status || "unknown"}</span></div><div className="pb-health-row"><span>Company</span><strong>{company?.name || "Not established"}</strong></div><div className="pb-health-row"><span>Active AI employees</span><strong>{activeAgents.length}</strong></div><div className="pb-health-row"><span>Model reachable</span><strong>{runtime.mock_inference ? "Mock mode" : runtime.model_reachable ? "Connected" : "Not confirmed"}</strong></div><div className="pb-health-row"><span>MCP</span><strong>{runtime.mcp_enabled ? runtime.mcp_configured ? "Configured" : "Enabled · not configured" : "Disabled"}</strong></div></section>
                <section className="pb-section-card"><div className="pb-section-card-heading"><div><span className="pb-eyebrow">RECENT EXECUTIONS</span><h2>Workflow activity</h2></div><button className="pb-text-button" onClick={() => setActiveView("workflows")}>View all <ArrowUpRight size={13} /></button></div>{workflows.slice(0, 5).map((item) => <button className="pb-workflow-row" key={item.thread_id} onClick={() => void openAudit(item.thread_id)}><span className="pb-workflow-symbol"><Workflow size={15} /></span><span><strong>{item.prompt || "Workflow execution"}</strong><small>{shortId(item.thread_id)} · {dateTime(item.created_at)}</small></span><em className={"pb-status " + (item.status || "").toLowerCase()}>{(item.status || "UNKNOWN").replace(/_/g, " ")}</em></button>)}{!workflows.length && <p className="pb-muted-copy">No workflows yet. Start one to see activity here.</p>}</section>
              </div>
            </section>
          )}

          {!loading && activeView === "workflows" && (
            <section className="pb-page">
              <PageHeading eyebrow="EXECUTION HISTORY / 002" title="Workflows" description="Run an agent workflow, provide supporting documents and review the resulting execution trace." />
              <div className="pb-workflow-layout">
                <section className="pb-section-card pb-workflow-form-card"><div className="pb-section-card-heading"><div><span className="pb-eyebrow">INTERACTION</span><h2>Start a workflow</h2></div><span className="pb-step-label">01 / 03</span></div>
                  <form className="pb-workflow-form" onSubmit={submitWorkflow}><label>Task instruction<textarea required rows={5} value={workflowPrompt} onChange={(e) => setWorkflowPrompt(e.target.value)} placeholder="Describe the task you want your AI workforce to complete…" /></label><div className="pb-form-grid"><label>Route to domain<select value={workflowDomain} onChange={(e) => setWorkflowDomain(e.target.value)}><option value="">Automatic routing</option><option value="aviation">Aviation operations</option><option value="banking">Banking / refunds</option><option value="general">General assistant</option></select></label><label>Tenant context<input value={TENANT} disabled /></label></div><label className="pb-upload-box"><FileText size={19} /><span><strong>Attach supporting documents</strong><small>PDF, PNG or JPG · up to 12 MB per file</small></span><input type="file" multiple accept="application/pdf,image/png,image/jpeg" onChange={(e) => setWorkflowFiles(Array.from(e.target.files || []))} /></label>{workflowFiles.map((file) => <div className="pb-file-row" key={file.name}>{file.name}<button type="button" onClick={() => setWorkflowFiles((items) => items.filter((item) => item !== file))}><X size={13} /></button></div>)}<button className="pb-button primary full" type="submit" disabled={workflowBusy || !workflowPrompt.trim()}>{workflowBusy ? "Executing workflow…" : "Run workflow"} <ArrowUpRight size={15} /></button></form>
                  {workflowResult && <div className="pb-workflow-result"><strong>Execution result · {workflowResult.status}</strong><p>{workflowResult.thread_id}</p>{workflowResult.audit_trail?.map((item, i) => <div key={i}><span>{item.node_id} · {item.action_type}</span><small>{item.output_summary}</small></div>)}{workflowResult.requires_human_approval && <div className="pb-approval-actions"><button className="pb-button secondary small" onClick={() => void decideApproval(workflowResult.thread_id, "REJECTED")}>Reject</button><button className="pb-button primary small" onClick={() => void decideApproval(workflowResult.thread_id, "APPROVED")}>Approve & simulate</button></div>}</div>}
                </section>
                <section className="pb-section-card"><div className="pb-section-card-heading"><div><span className="pb-eyebrow">PERSISTED EXECUTIONS</span><h2>Workflow runs</h2></div><span className="pb-count-pill">{workflows.length}</span></div>{workflows.length ? <div className="pb-workflow-list">{workflows.map((item) => <button className="pb-workflow-row" key={item.thread_id} onClick={() => void openAudit(item.thread_id)}><span className="pb-workflow-symbol"><Workflow size={15} /></span><span><strong>{item.prompt || "Workflow"}</strong><small>{shortId(item.thread_id)} · {dateTime(item.created_at)}</small></span><em className={"pb-status " + (item.status || "").toLowerCase()}>{(item.status || "UNKNOWN").replace(/_/g, " ")}</em></button>)}</div> : <EmptyState icon={Workflow} title="No workflows recorded" description="Start your first workflow to see execution history here." />}</section>
              </div>
            </section>
          )}

          {!loading && activeView === "agents" && (
            <section className="pb-page">
              <PageHeading eyebrow="LEGACY ROUTING / CONFIGURATION" title="Workflow templates" description="Static YAML manifests used by the legacy workflow router. These are separate from the dynamic AI employees in your company." actions={<button className="pb-button secondary" onClick={() => void reloadTemplates()}><RefreshCw size={14} /> Reload templates</button>} />
              {templates.length ? <div className="pb-template-grid">{templates.map((item) => <article className="pb-template-card" key={item.agent_metadata.agent_id}><div className="pb-agent-card-top"><span className="pb-provider-icon"><Bot size={18} /></span><span className="pb-version">v{item.agent_metadata.version}</span></div><h3>{item.agent_metadata.display_name}</h3><div className="pb-template-domain">{item.agent_metadata.domain} / {item.agent_metadata.agent_id}</div><p>{item.persona_and_guardrails.system_prompt}</p><div className="pb-agent-tags">{(item.capabilities?.allowed_mcp_tools || []).map((tool) => <span key={tool}>{tool}</span>)}</div></article>)}</div> : <EmptyState icon={Bot} title="No workflow templates found" description="Add a YAML manifest under config/agents and reload templates." />}
            </section>
          )}

          {!loading && activeView === "audit" && (
            <section className="pb-page">
              <PageHeading eyebrow="GOVERNANCE / EVIDENCE" title="Audit trails" description="Inspect the recorded execution events and evidence for any workflow run." actions={<button className="pb-button secondary" onClick={() => void loadOperations()}><RefreshCw size={14} /> Refresh runs</button>} />
              <section className="pb-section-card"><div className="pb-section-card-heading"><div><span className="pb-eyebrow">WORKFLOW THREAD</span><h2>Select an execution</h2></div></div><select className="pb-audit-select" value={selectedAuditId} onChange={(e) => void openAudit(e.target.value)}><option value="">Choose workflow…</option>{workflows.map((item) => <option key={item.thread_id} value={item.thread_id}>{shortId(item.thread_id)} · {(item.status || "").replace(/_/g, " ")} · {item.prompt}</option>)}</select>
                {selectedAuditId ? audit.length ? <div className="pb-audit-list">{audit.map((item, index) => <article className="pb-audit-row" key={item.entry_hash || index}><div className="pb-audit-time">{dateTime(item.timestamp_utc)}</div><div><strong>{item.node_id} · {item.action_type}</strong><p>{item.output_summary || "No output summary recorded."}</p><code>SHA-256 {item.entry_hash || "Not available"}</code></div></article>)}</div> : <EmptyState icon={FileClock} title="No audit events" description="This workflow does not have audit events to display." /> : <EmptyState icon={ShieldCheck} title="Select a workflow" description="Choose a workflow thread above to inspect its audit record." />}
              </section>
            </section>
          )}
        </div>

        <footer className="pb-statusbar"><span><i /> API {health.status || "connecting"}</span><span>{company?.name || "No company selected"}</span><span>{activeAgents.length} active agents</span><span>Pink Bread 2.0 · React workspace</span></footer>
      </main>

      <aside className="pb-chat-rail">
        <div className="pb-chat-header"><div><span className="pb-eyebrow">FOUNDER / COMMAND</span><h2>Talk to your company</h2></div><button className="pb-icon-button" onClick={() => setChatHidden(true)} aria-label="Hide founder chat" title="Hide founder chat"><X size={17} /></button></div>
        <div className="pb-chat-context"><span className="pb-company-avatar"><Sparkles size={15} /></span><span><strong>{company?.name || "No company selected"}</strong><small>{chatBusy ? "Your AI workforce is responding…" : "Your instruction will be routed to the team"}</small></span><i className={chatBusy ? "busy" : ""} /></div>
        <div className="pb-chat-transcript">
          {!chatMessages.length ? <div className="pb-chat-empty"><div><Sparkles size={24} /></div><strong>Your virtual team is ready.</strong><p>Give your agents a task, ask a question or ask two employees to discuss an issue together.</p><div className="pb-chat-suggestions"><button onClick={() => void sendFounderInstruction("Review our company goals and recommend the next three priorities.", [])}>Review company priorities</button><button onClick={() => void sendFounderInstruction("Ask my coordinator to organise a team alignment discussion.", [])}>Arrange an alignment</button></div></div> : chatMessages.map((item, index) => <article className={"pb-chat-message " + item.role} key={index}><small>{item.name} · {dateTime(item.created_at)}</small><p>{item.content}</p></article>)}
        </div>
        <div className="pb-chat-compose">
          <FounderComposer companyId={company?.id || ""} tenantId={company?.tenant_id || TENANT} onSend={sendFounderInstruction} />
        </div>
        <div className="pb-chat-footer"><span><ShieldCheck size={12} /> Company-scoped context</span><span>Shift + Enter for new line</span></div>
      </aside>

      {agentEditor && company && <AgentEditor company={company} draft={agentEditor.draft} agent={agentEditor.agent} onClose={() => setAgentEditor(null)} onSaved={async () => { setAgentEditor(null); await reloadCompany(); setNotice(agentEditor.agent ? "Agent profile updated." : "AI employee created."); }} />}
    </div>
  );
}
