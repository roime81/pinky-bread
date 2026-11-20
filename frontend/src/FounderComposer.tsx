import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle, Check, Cloud, FileImage, FileSpreadsheet, FileText, FileUp,
  Link2, LoaderCircle, Paperclip, Plus, Send, X,
} from "lucide-react";
import { type DragEvent, type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

type Artifact = {
  object_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  extraction_status?: string;
  source?: string;
};
type FounderComposerProps = {
  companyId: string;
  tenantId: string;
  onSend: (message: string, artifactIds: string[]) => Promise<void>;
};

const ACCEPTED = new Set(["pdf", "docx", "xlsx", "pptx", "csv", "txt", "md", "json", "html", "htm", "xml", "png", "jpg", "jpeg", "webp"]);

function formatBytes(value: number): string {
  if (value < 1024) return value + " B";
  if (value < 1024 * 1024) return (value / 1024).toFixed(0) + " KB";
  return (value / 1024 / 1024).toFixed(1) + " MB";
}
function fileIcon(name: string) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (["xlsx", "csv"].includes(ext || "")) return FileSpreadsheet;
  if (["png", "jpg", "jpeg", "webp"].includes(ext || "")) return FileImage;
  return FileText;
}
async function responsePayload(response: Response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Document request failed (" + response.status + ")");
  return payload;
}

export default function FounderComposer({ companyId, tenantId, onSend }: FounderComposerProps) {
  const [maxFileMb, setMaxFileMb] = useState(12);
  const [draft, setDraft] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [linked, setLinked] = useState<Artifact[]>([]);
  const [linkValue, setLinkValue] = useState("");
  const [showLink, setShowLink] = useState(false);
  const [busy, setBusy] = useState(false);
  const [linkBusy, setLinkBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch("/v2/capabilities")
      .then(responsePayload)
      .then((payload) => {
        const configured = Number(payload.max_upload_mb);
        if (Number.isFinite(configured) && configured > 0 && configured <= 250) setMaxFileMb(configured);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    setDraft("");
    setFiles([]);
    setLinked([]);
    setLinkValue("");
    setShowLink(false);
    setError("");
    setStatus("");
    setBusy(false);
  }, [companyId]);

  function addFiles(fileList: FileList | File[]) {
    setError("");
    const incoming = Array.from(fileList);
    const accepted: File[] = [];
    const rejected: string[] = [];
    for (const file of incoming) {
      const ext = file.name.split(".").pop()?.toLowerCase() || "";
      if (!ACCEPTED.has(ext)) {
        rejected.push(file.name + " is not a supported document format.");
        continue;
      }
      if (file.size > maxFileMb * 1024 * 1024) {
        rejected.push(file.name + " exceeds the " + maxFileMb + " MB per-file limit.");
        continue;
      }
      accepted.push(file);
    }
    const merged = [...files];
    for (const candidate of accepted) {
      if (!merged.some((item) => item.name === candidate.name && item.size === candidate.size && item.lastModified === candidate.lastModified)) merged.push(candidate);
    }
    if (merged.length + linked.length > 10) rejected.push("Attach up to 10 documents per message.");
    setFiles(merged.slice(0, Math.max(0, 10 - linked.length)));
    if (rejected.length) setError(rejected.join(" "));
    if (fileInput.current) fileInput.current.value = "";
  }

  function handleDrop(event: DragEvent<HTMLFormElement>) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
  }

  async function importLink(event?: FormEvent) {
    event?.preventDefault();
    const url = linkValue.trim();
    if (!companyId || !url || linkBusy || linked.length + files.length >= 10) return;
    setLinkBusy(true);
    setError("");
    setStatus("Importing shared document…");
    try {
      const response = await fetch("/v2/companies/" + encodeURIComponent(companyId) + "/document-links", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, actor_id: "founder", url }),
      });
      const payload = await responsePayload(response);
      setLinked((current) => [...current, { ...payload.artifact, source: "cloud" }]);
      setLinkValue("");
      setStatus("Cloud document added to this message.");
    } catch (reason) {
      setError((reason as Error).message);
      setStatus("");
    } finally {
      setLinkBusy(false);
    }
  }

  async function uploadFile(file: File): Promise<Artifact> {
    const form = new FormData();
    form.append("file", file);
    form.append("tenant_id", tenantId);
    form.append("actor_id", "founder");
    form.append("kind", "document");
    const response = await fetch("/v2/companies/" + encodeURIComponent(companyId) + "/artifacts", {
      method: "POST",
      body: form,
    });
    const payload = await responsePayload(response);
    return payload.artifact as Artifact;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!companyId) {
      setError("Create or select a company before attaching documents.");
      return;
    }
    if (!message) {
      setError("Write an instruction for your AI workforce.");
      textarea.current?.focus();
      return;
    }
    setBusy(true);
    setError("");
    const uploaded: Artifact[] = [...linked];
    try {
      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        setStatus("Uploading " + (index + 1) + " of " + files.length + " · " + file.name);
        uploaded.push(await uploadFile(file));
      }
      setStatus("Delivering instruction to your AI workforce…");
      await onSend(message, uploaded.map((item) => item.object_id));
      setDraft("");
      setFiles([]);
      setLinked([]);
      setShowLink(false);
      setStatus("Your instruction was delivered.");
      requestAnimationFrame(() => textarea.current?.focus());
    } catch (reason) {
      setError((reason as Error).message || "Unable to deliver this instruction.");
      setStatus("");
    } finally {
      setBusy(false);
    }
  }

  function onTextareaKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  const attachedCount = files.length + linked.length;
  const disabled = busy || linkBusy || !companyId;

  return (
    <form
      className={"founder-composer" + (dragging ? " is-dragging" : "")}
      onSubmit={submit}
      onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
      onDragLeave={(event) => {
        const next = event.relatedTarget as Node | null;
        if (!next || !event.currentTarget.contains(next)) setDragging(false);
      }}
      onDrop={handleDrop}
    >
      <div className="founder-composer-topline">
        <span><span className="composer-status-dot" /> MESSAGE YOUR WORKFORCE</span>
        <span className="composer-company-context">{companyId ? "COMPANY CONTEXT ACTIVE" : "SELECT A COMPANY FIRST"}</span>
      </div>
      <textarea
        ref={textarea}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onTextareaKeyDown}
        rows={3}
        maxLength={12000}
        placeholder="Ask your AI workforce to analyse, research, plan or collaborate…"
        aria-label="Founder instruction"
        disabled={!companyId || busy}
      />
      <AnimatePresence initial={false}>
        {(files.length > 0 || linked.length > 0) && (
          <motion.div className="composer-attachments" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
            {files.map((file, index) => {
              const Icon = fileIcon(file.name);
              return <div className="composer-attachment" key={file.name + file.lastModified + index}><span className="composer-attachment-icon"><Icon size={14} /></span><span className="composer-attachment-copy"><strong>{file.name}</strong><small>{formatBytes(file.size)} · Ready to upload</small></span><button type="button" aria-label={"Remove " + file.name} onClick={() => setFiles((items) => items.filter((_, i) => i !== index))}><X size={13} /></button></div>;
            })}
            {linked.map((item) => {
              const Icon = item.content_type.startsWith("image/") ? FileImage : fileIcon(item.filename);
              return <div className="composer-attachment" key={item.object_id}><span className="composer-attachment-icon cloud"><Icon size={14} /></span><span className="composer-attachment-copy"><strong>{item.filename}</strong><small>{formatBytes(item.size_bytes)} · Cloud document imported</small></span><button type="button" aria-label={"Remove " + item.filename} onClick={() => setLinked((items) => items.filter((x) => x.object_id !== item.object_id))}><X size={13} /></button></div>;
            })}
          </motion.div>
        )}
      </AnimatePresence>
      <AnimatePresence initial={false}>
        {showLink && (
          <motion.div className="composer-link-row" initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -5 }}>
            <Link2 size={15} />
            <input type="url" value={linkValue} onChange={(event) => setLinkValue(event.target.value)} placeholder="Paste a public HTTPS share link or signed download URL…" aria-label="Cloud document URL" onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void importLink(); } }} />
            <button type="button" disabled={!linkValue.trim() || linkBusy || disabled} onClick={() => void importLink()}>{linkBusy ? <LoaderCircle className="composer-spin" size={14} /> : <Plus size={14} />} Add</button>
            <button type="button" className="composer-link-close" onClick={() => setShowLink(false)} aria-label="Close link field"><X size={14} /></button>
          </motion.div>
        )}
      </AnimatePresence>
      {(error || status) && <div className={"composer-feedback" + (error ? " is-error" : "")} role="status">{error ? <AlertCircle size={13} /> : busy || linkBusy ? <LoaderCircle className="composer-spin" size={13} /> : <Check size={13} />}<span>{error || status}</span>{error && <button type="button" onClick={() => setError("")} aria-label="Dismiss error"><X size={13} /></button>}</div>}
      {dragging && <div className="composer-drop-overlay"><FileUp size={22} /><strong>Drop documents to attach</strong><span>PDF, Office, CSV, text and images</span></div>}
      <div className="founder-composer-footer">
        <div className="composer-tools">
          <input ref={fileInput} type="file" multiple accept=".pdf,.docx,.xlsx,.pptx,.csv,.txt,.md,.json,.html,.htm,.xml,.png,.jpg,.jpeg,.webp" hidden onChange={(event) => event.target.files && addFiles(event.target.files)} />
          <button type="button" className="composer-tool-button" onClick={() => fileInput.current?.click()} disabled={disabled || attachedCount >= 10} title="Attach files"><Paperclip size={15} /><span>Attach files</span></button>
          <button type="button" className={"composer-tool-button" + (showLink ? " active" : "")} onClick={() => setShowLink((value) => !value)} disabled={disabled || attachedCount >= 10} title="Add a cloud document link"><Cloud size={15} /><span>Cloud link</span></button>
          <span className="composer-attachment-limit">{attachedCount}/10</span>
        </div>
        <button type="submit" className="composer-send-button" disabled={disabled || !draft.trim()}>{busy ? <LoaderCircle className="composer-spin" size={15} /> : <Send size={15} />}<span>{busy ? "Preparing…" : "Send to team"}</span></button>
      </div>
      <div className="composer-help-row"><span>Shift + Enter for a new line</span><span>Drop files here · {maxFileMb} MB per file</span></div>
      {showLink && <p className="composer-cloud-note">Supports public HTTPS share links from Drive, Dropbox, OneDrive and other storage services. Private files require an authenticated connector and cannot be fetched by the public-link importer.</p>}
    </form>
  );
}
