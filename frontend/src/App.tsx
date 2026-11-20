import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeftRight, ArrowUpRight, Bot, Check, ChevronDown, CircleDashed,
  Clock3, Command, MessageCircle, Plus, Radio, RefreshCw, Send, Sparkles,
  Users, Workflow, X,
} from "lucide-react";
import {
  FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState,
} from "react";

type Company = { id: string; name: string; tenant_id: string };
type Agent = {
  id: string; name: string; type: string; status?: string;
  data?: { role?: string; title?: string; authority?: string; seniority_level?: number };
};
type Message = {
  message_id: string; conversation_id?: string; sequence_no?: number;
  sender_type: string; sender_agent_id?: string | null; sender_name: string;
  recipient_agent_id?: string | null; recipient_name?: string | null;
  message_kind: string; content: string; created_at?: string | null;
};
type Conversation = {
  conversation_id: string; company_id: string; title: string; status: string;
  initiator_agent_id: string; participant_agent_ids: string[]; summary?: string | null;
  updated_at?: string | null; created_at?: string | null; messages?: Message[];
};
type StreamEvent = {
  type: string; conversation_id?: string; participants?: { id: string; name: string; role: string }[];
  message?: Message; conversation?: Conversation; error?: string;
};

const TENANT = "demo-tenant";
const ACTOR = "founder";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Request failed (" + response.status + ")");
  return payload as T;
}
function role(agent: Agent): string { return agent.data?.title || agent.data?.role || "AI employee"; }
function active(agent: Agent): boolean {
  return agent.type === "agent" && !["ARCHIVED", "DISABLED", "PAUSED"].includes(agent.status || "");
}
function initials(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((x) => x[0]?.toUpperCase() || "").join("") || "AI";
}
function time(value?: string | null): string {
  const date = value ? new Date(value) : new Date();
  return Number.isNaN(date.getTime()) ? "Now" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
function dateLabel(value?: string | null): string {
  const date = value ? new Date(value) : new Date();
  return Number.isNaN(date.getTime()) ? "Recently" : date.toLocaleDateString([], { month: "short", day: "numeric" });
}
function escapeRegExp(value: string): string { return value.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&"); }
function isDiscussionIntent(message: string, agents: Agent[]): boolean {
  if (!/\b(discuss|talk|chat|speak|connect|consult|ask|tell|message|greet|introduce|meet|sync|align|brainstorm|say\s+(hello|hi))\b/i.test(message)) return false;
  const mentioned = agents.filter((agent) =>
    new RegExp("(?<![\\w])@?" + escapeRegExp(agent.name) + "(?![\\w])", "i").test(message)
  );
  if (mentioned.length >= 2) return true;
  return mentioned.length === 1 && /\b(with|to)\b/i.test(message)
    && agents.some((agent) => String(agent.data?.authority || "").toUpperCase() === "COORDINATOR" && agent.id !== mentioned[0].id);
}

function MessageBubble({ item }: { item: Message }) {
  const founder = item.sender_type === "FOUNDER";
  const summary = item.message_kind === "FOUNDER_SUMMARY";
  const ack = item.message_kind === "ACKNOWLEDGEMENT";
  const direction = item.recipient_name
    ? item.sender_name + " → " + item.recipient_name
    : founder ? "Founder instruction" : item.sender_name + " → Founder";
  return (
    <motion.article layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className={"a2a-message-row " + (founder ? "founder" : "agent") + (summary ? " summary" : "")}>
      {!founder && <div className={"a2a-message-avatar " + (summary ? "summary-avatar" : "")}>
        {summary ? <Sparkles size={15} /> : initials(item.sender_name)}
      </div>}
      <div className="a2a-message-copy">
        <div className="a2a-message-meta">
          <strong>{founder ? "You" : summary ? item.sender_name + " · Founder briefing" : item.sender_name}</strong>
          <span>{direction}</span><time>{time(item.created_at)}</time>
        </div>
        <div className={"a2a-message-bubble" + (founder ? " founder-bubble" : "") + (summary ? " summary-bubble" : "")}>
          {ack && <div className="a2a-message-kind"><Check size={11} /> ACKNOWLEDGED</div>}
          {item.message_kind === "A2A" && <div className="a2a-message-kind"><ArrowLeftRight size={11} /> DIRECT AGENT MESSAGE</div>}
          {summary && <div className="a2a-message-kind"><Sparkles size={11} /> FOUNDER UPDATE</div>}
          <p>{item.content}</p>
        </div>
      </div>
      {founder && <div className="a2a-message-avatar founder-avatar">YOU</div>}
    </motion.article>
  );
}

export default function App() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState("");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [thinking, setThinking] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const timeline = useRef<HTMLDivElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);

  const company = useMemo(() => companies.find((x) => x.id === companyId) || null, [companies, companyId]);
  const team = useMemo(() => agents.filter(active), [agents]);
  const selected = useMemo(() => conversations.find((x) => x.conversation_id === activeId) || null, [conversations, activeId]);
  const participants = useMemo(
    () => selected ? selected.participant_agent_ids.map((id) => team.find((agent) => agent.id === id)).filter((x): x is Agent => Boolean(x)) : [],
    [selected, team],
  );
  const history = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? conversations.filter((x) => x.title.toLowerCase().includes(q)) : conversations;
  }, [conversations, search]);

  const loadData = useCallback(async (id: string, tenant: string) => {
    if (!id) return;
    const query = "tenant_id=" + encodeURIComponent(tenant);
    const results = await Promise.all([
      api<{ agents: Agent[] }>("/v2/companies/" + id + "/agents?" + query),
      api<{ conversations: Conversation[] }>("/v2/companies/" + id + "/conversations?" + query),
    ]);
    setAgents(results[0].agents || []);
    setConversations(results[1].conversations || []);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const picker = document.getElementById("graph-company-picker") as HTMLSelectElement | null;
    const sync = () => { if (picker?.value) setCompanyId(picker.value); };
    picker?.addEventListener("change", sync);
    api<{ companies: Company[] }>("/v2/companies?tenant_id=" + TENANT)
      .then((result) => {
        if (cancelled) return;
        const rows = result.companies || [];
        setCompanies(rows);
        const preferred = rows.find((row) => row.id === picker?.value) || rows[0];
        if (preferred) setCompanyId(preferred.id);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; picker?.removeEventListener("change", sync); };
  }, []);

  useEffect(() => {
    if (!companyId || !company) return;
    const picker = document.getElementById("graph-company-picker") as HTMLSelectElement | null;
    if (picker && picker.value !== companyId) {
      picker.value = companyId;
      picker.dispatchEvent(new Event("change", { bubbles: true }));
    }
    setActiveId("");
    setMessages([]);
    setAgents([]);
    setConversations([]);
    setError("");
    loadData(companyId, company.tenant_id || TENANT).catch((reason: Error) => setError(reason.message));
  }, [companyId, company?.tenant_id, loadData]);

  useEffect(() => {
    if (timeline.current) timeline.current.scrollTo({ top: timeline.current.scrollHeight, behavior: "smooth" });
  }, [messages, thinking]);

  const loadThread = useCallback(async (id: string) => {
    if (!company || !id) return;
    setActiveId(id);
    setError("");
    try {
      const result = await api<Conversation>(
        "/v2/companies/" + company.id + "/conversations/" + id + "?tenant_id=" + encodeURIComponent(company.tenant_id || TENANT)
      );
      setMessages(result.messages || []);
      setConversations((rows) => rows.map((row) => row.conversation_id === id ? result : row));
    } catch (reason) { setError((reason as Error).message); }
  }, [company]);

  const appendMessage = (item: Message) => {
    setMessages((rows) => rows.some((row) => row.message_id === item.message_id) ? rows : [...rows, item]);
  };

  async function runStream(instruction: string) {
    if (!company) return;
    const response = await fetch("/v2/companies/" + company.id + "/conversations/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenant_id: company.tenant_id || TENANT, actor_id: ACTOR, message: instruction, max_turns: 6,
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Agent conversation failed (" + response.status + ")");
    }
    if (!response.body) throw new Error("Streaming is not available in this browser.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streamError = "";
    const handleFrame = (frame: string) => {
      const payload = frame.split(/\r?\n/).filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim()).join("\n");
      if (!payload) return;
      const event = JSON.parse(payload) as StreamEvent;
      if (event.type === "conversation_started" && event.message) {
        setActiveId(event.conversation_id || "");
        appendMessage(event.message);
        setThinking((event.participants?.[0]?.name || "Agent") + " is preparing an opening message");
      } else if (event.type === "message" && event.message) {
        appendMessage(event.message);
        if (event.message.message_kind === "ACKNOWLEDGEMENT") setThinking(event.message.sender_name + " is reaching out to a colleague");
        else if (event.message.recipient_name) setThinking(event.message.recipient_name + " is responding");
        else setThinking(event.message.sender_name + " is preparing your briefing");
      } else if (event.type === "complete" && event.conversation) {
        setActiveId(event.conversation.conversation_id);
        setConversations((rows) => [event.conversation!, ...rows.filter((x) => x.conversation_id !== event.conversation!.conversation_id)]);
        setThinking("");
      } else if (event.type === "error") streamError = event.error || "The discussion failed.";
    };
    try {
      while (true) {
        const result = await reader.read();
        if (result.done) break;
        buffer += decoder.decode(result.value, { stream: true });
        let match = buffer.match(/\r?\n\r?\n/);
        while (match && match.index !== undefined) {
          const frame = buffer.slice(0, match.index);
          buffer = buffer.slice(match.index + match[0].length);
          handleFrame(frame);
          match = buffer.match(/\r?\n\r?\n/);
        }
      }
      if (buffer.trim()) handleFrame(buffer);
    } finally { reader.releaseLock(); }
    if (streamError) throw new Error(streamError);
    const result = await api<{ conversations: Conversation[] }>(
      "/v2/companies/" + company.id + "/conversations?tenant_id=" + encodeURIComponent(company.tenant_id || TENANT)
    );
    setConversations(result.conversations || []);
  }

  async function send(event?: FormEvent) {
    event?.preventDefault();
    const instruction = draft.trim();
    if (!instruction || busy || !company) return;
    setDraft("");
    setError("");
    setBusy(true);
    setThinking("Routing your instruction");
    appendMessage({
      message_id: "local-" + Date.now(), sender_type: "FOUNDER", sender_name: "Founder",
      message_kind: "INSTRUCTION", content: instruction, created_at: new Date().toISOString(),
    });
    try {
      if (isDiscussionIntent(instruction, team)) {
        await runStream(instruction);
      } else {
        const result = await api<{
          reply: string;
          responses?: { agent_id?: string; name: string; reply: string; recipient_name?: string; message_kind?: string }[];
        }>("/v2/companies/" + company.id + "/chat", {
          method: "POST",
          body: JSON.stringify({
            tenant_id: company.tenant_id || TENANT, actor_id: ACTOR, message: instruction,
            history: messages.slice(-12).map((item) => ({
              role: item.sender_type === "FOUNDER" ? "user" : "assistant",
              content: item.sender_name + ": " + item.content,
            })),
          }),
        });
        const rows = result.responses || [];
        if (rows.length) rows.forEach((row, index) => appendMessage({
          message_id: "local-" + Date.now() + "-" + index,
          sender_type: "AGENT", sender_agent_id: row.agent_id || null, sender_name: row.name,
          recipient_name: row.recipient_name || null, message_kind: row.message_kind || "RESPONSE",
          content: row.reply, created_at: new Date().toISOString(),
        }));
        else if (result.reply) appendMessage({
          message_id: "local-" + Date.now() + "-reply", sender_type: "AGENT",
          sender_name: "AI workforce", message_kind: "RESPONSE", content: result.reply,
          created_at: new Date().toISOString(),
        });
      }
    } catch (reason) { setError((reason as Error).message || "The instruction could not be completed."); }
    finally { setBusy(false); setThinking(""); composer.current?.focus(); }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(); }
  }
  function newDiscussion() {
    setActiveId("");
    setMessages([]);
    setError("");
    setDraft("");
    setThinking("");
    composer.current?.focus();
  }
  const first = team[0];
  const second = team.find((item) => item.id !== first?.id);
  const status = busy ? "LIVE DISCUSSION" : selected?.status === "COMPLETED" ? "DISCUSSION COMPLETE" : "READY";

  return (
    <div className="a2a-workspace">
      <header className="a2a-page-heading">
        <div className="a2a-heading-copy">
          <div className="a2a-eyebrow"><span className="a2a-pulse" /> AGENT COLLABORATION / A2A NETWORK</div>
          <h1>Conversations between your agents.</h1>
          <p>Delegate a discussion, watch your AI employees exchange messages, and review what they agreed.</p>
        </div>
        <div className="a2a-heading-actions">
          <label className="a2a-company-select">
            <span>WORKSPACE</span>
            <select value={companyId} onChange={(event) => setCompanyId(event.target.value)} aria-label="Select company">
              {companies.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
            </select><ChevronDown size={14} />
          </label>
          <button className="a2a-primary-button" type="button" onClick={newDiscussion}><Plus size={15} /> New discussion</button>
        </div>
      </header>

      <div className="a2a-layout">
        <aside className="a2a-history-panel">
          <div className="a2a-panel-head">
            <div><span className="a2a-section-label">YOUR WORKSPACE</span><h2>Conversations</h2></div>
            <span className="a2a-count">{conversations.length}</span>
          </div>
          <label className="a2a-search"><Command size={14} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Find a discussion" /></label>
          <div className="a2a-thread-list">
            {history.length ? history.map((item) => {
              const names = item.participant_agent_ids.map((id) => team.find((agent) => agent.id === id)?.name).filter(Boolean);
              return (
                <button type="button" key={item.conversation_id}
                  className={"a2a-thread-item" + (activeId === item.conversation_id ? " selected" : "")}
                  onClick={() => void loadThread(item.conversation_id)}>
                  <span className="a2a-thread-icon"><MessageCircle size={15} /></span>
                  <span className="a2a-thread-copy"><strong>{item.title}</strong><small>{names.join(" · ") || "Agent conversation"}</small><em>{dateLabel(item.updated_at)}</em></span>
                  <span className={"a2a-status-dot " + (item.status || "").toLowerCase()} />
                </button>
              );
            }) : (
              <div className="a2a-empty-history"><div className="a2a-empty-icon"><MessageCircle size={19} /></div><strong>No discussions yet</strong><p>Ask one agent to speak with another. The full exchange is saved here.</p></div>
            )}
          </div>
          <div className="a2a-team-block">
            <div className="a2a-panel-head team-head"><div><span className="a2a-section-label">ACTIVE WORKFORCE</span><h2>Your agents</h2></div><span className="a2a-count">{team.length}</span></div>
            <div className="a2a-agent-list">
              {team.slice(0, 8).map((agent, index) => (
                <div className="a2a-agent-mini" key={agent.id}>
                  <span className={"a2a-mini-avatar tone-" + (index % 5)}>{initials(agent.name)}</span>
                  <span><strong>{agent.name}</strong><small>{role(agent)}</small></span><i />
                </div>
              ))}
              {!team.length && <p className="a2a-muted-note">Create AI employees in Your Virtual Team to begin.</p>}
            </div>
          </div>
        </aside>

        <main className="a2a-conversation-panel">
          <div className="a2a-conversation-toolbar">
            <div><span className="a2a-section-label">PRIVATE AGENT CHANNEL</span><h2>{selected?.title || "Start a conversation"}</h2>
              <p>{selected ? participants.length + " participants · " + messages.filter((x) => x.message_kind === "A2A").length + " agent messages" : "No agent thread selected"}</p></div>
            <span className={"a2a-live-status" + (busy ? " is-live" : "")}><i /> {status}</span>
          </div>

          <div className="a2a-participant-strip">
            {participants.length ? participants.map((agent, index) => (
              <div className="a2a-participant" key={agent.id}>
                <span className={"a2a-participant-avatar tone-" + (index % 5)}>{initials(agent.name)}</span>
                <span><strong>{agent.name}</strong><small>{role(agent)}</small></span>
                {index < participants.length - 1 && <ArrowLeftRight className="a2a-connector" size={14} />}
              </div>
            )) : <div className="a2a-participant-placeholder"><Users size={15} /> Every active employee can participate in a company discussion.</div>}
            {participants.length > 0 && <span className="a2a-channel-tag"><Radio size={12} /> Agent-to-agent channel</span>}
          </div>

          <div className="a2a-timeline" ref={timeline}>
            {loading ? <div className="a2a-loading"><CircleDashed size={20} className="a2a-spin" /> Loading your company workspace…</div>
              : !company ? (
                <div className="a2a-empty-thread"><div className="a2a-empty-orbit"><Bot size={28} /></div><h3>Establish your company first</h3><p>Create or select a company in Company Graph. Your agents and conversations appear here.</p></div>
              ) : messages.length ? (
                <div className="a2a-message-stack">
                  <div className="a2a-date-divider"><span>DISCUSSION TIMELINE</span></div>
                  <AnimatePresence initial={false}>{messages.map((item) => <MessageBubble item={item} key={item.message_id} />)}</AnimatePresence>
                  {busy && <motion.div className="a2a-typing" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                    <span className="a2a-typing-dots"><i /><i /><i /></span><span>{thinking || "An agent is preparing a response"}</span>
                  </motion.div>}
                  <div className="a2a-end-anchor"><span>END OF THREAD</span></div>
                </div>
              ) : (
                <div className="a2a-empty-thread">
                  <div className="a2a-empty-orbit"><ArrowLeftRight size={27} /></div>
                  <span className="a2a-section-label">A2A COMMUNICATION</span>
                  <h3>Let your agents work it out together.</h3>
                  <p>Give an instruction in natural language. The initiating agent contacts its colleague, exchanges messages, and briefs you on the outcome.</p>
                  {first && second && <div className="a2a-suggestions">
                    <button type="button" onClick={() => setDraft(first.name + ", say hello to " + second.name + ".")}>“{first.name}, say hello to {second.name}.”</button>
                    <button type="button" onClick={() => setDraft(first.name + ", discuss our next growth priorities with " + second.name + ".")}>“{first.name}, discuss growth priorities with {second.name}.”</button>
                  </div>}
                  {team.length < 2 && <div className="a2a-notice"><Users size={14} /> Create at least two active agents to start a peer conversation.</div>}
                </div>
              )}
          </div>

          <form className="a2a-composer" onSubmit={send}>
            {error && <div className="a2a-error"><X size={14} /> {error}</div>}
            <div className="a2a-composer-box">
              <textarea ref={composer} value={draft} onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKeyDown} rows={2}
                placeholder="Mira, please discuss our marketing strategy with Jamal…"
                disabled={!company || busy} aria-label="Instruction for your agents" />
              <div className="a2a-composer-footer">
                <span><Sparkles size={13} /> Mention agents by name. Each keeps their own identity and context.</span>
                <button type="submit" className="a2a-send-button" disabled={!draft.trim() || busy || !company}>
                  {busy ? <CircleDashed size={15} className="a2a-spin" /> : <Send size={15} />}
                  <span>{busy ? "Working" : "Send instruction"}</span><ArrowUpRight size={14} />
                </button>
              </div>
            </div>
            <div className="a2a-composer-note"><span><Clock3 size={11} /> Conversations are saved to PostgreSQL</span><span>Enter to send · Shift + Enter for a new line</span></div>
          </form>
        </main>

        <aside className="a2a-inspector-panel">
          <div className="a2a-inspector-heading"><span className="a2a-section-label">COLLABORATION CONTEXT</span><h2>Discussion details</h2></div>
          <div className="a2a-inspector-card">
            <div className="a2a-inspector-card-title"><Workflow size={15} /><strong>Conversation flow</strong></div>
            <div className="a2a-flow-step"><span>01</span><div><strong>Founder instruction</strong><small>Your request is routed to the initiating agent.</small></div></div><div className="a2a-flow-line" />
            <div className="a2a-flow-step"><span>02</span><div><strong>Peer exchange</strong><small>Each colleague runs with their own persona and model settings.</small></div></div><div className="a2a-flow-line" />
            <div className="a2a-flow-step"><span>03</span><div><strong>Founder briefing</strong><small>The initiating agent reports the outcome to you.</small></div></div>
          </div>
          {selected && <div className="a2a-inspector-card">
            <div className="a2a-inspector-card-title"><Users size={15} /><strong>Participants</strong></div>
            {participants.map((agent, index) => <div className="a2a-detail-agent" key={agent.id}>
              <span className={"a2a-mini-avatar tone-" + (index % 5)}>{initials(agent.name)}</span>
              <span><strong>{agent.name}</strong><small>{role(agent)}</small></span>
              {agent.id === selected.initiator_agent_id && <em>LEAD</em>}
            </div>)}
            <div className="a2a-detail-divider" />
            <div className="a2a-detail-row"><span>State</span><strong>{selected.status}</strong></div>
            <div className="a2a-detail-row"><span>Agent messages</span><strong>{messages.filter((x) => x.message_kind === "A2A").length}</strong></div>
            <div className="a2a-detail-row"><span>Started</span><strong>{dateLabel(selected.created_at)}</strong></div>
          </div>}
          <div className="a2a-guardrail-note"><span><Check size={14} /></span><div><strong>Founder visibility</strong><p>Each message is stored with sender, recipient, sequence and timestamp. Discussions cannot silently execute external actions.</p></div></div>
          <button className="a2a-refresh-button" type="button" onClick={() => company && loadData(company.id, company.tenant_id || TENANT).catch((reason: Error) => setError(reason.message))}>
            <RefreshCw size={13} /> Refresh workspace
          </button>
        </aside>
      </div>
    </div>
  );
}
