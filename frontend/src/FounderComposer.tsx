import { AnimatePresence, motion } from "framer-motion";
import {
  AlertCircle, Check, FileText, LoaderCircle, Paperclip, Send, ShieldCheck, X,
} from "lucide-react";
import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Uppy from "@uppy/core";
import Dashboard from "@uppy/dashboard";
import Box from "@uppy/box";
import Dropbox from "@uppy/dropbox";
import GoogleDrive from "@uppy/google-drive";
import OneDrive from "@uppy/onedrive";
import Url from "@uppy/url";
import XHRUpload from "@uppy/xhr-upload";

type Artifact = {
  object_id: string;
  filename: string;
  content_type?: string;
  size_bytes: number;
  extraction_status?: string;
  source?: string;
};
type UploadConfig = {
  companion_url: string;
  companion_enabled: boolean;
  upload_target_base_url: string;
  max_upload_mb: number;
  max_attachments: number;
  sources: {
    google_drive: boolean;
    dropbox: boolean;
    onedrive: boolean;
    box: boolean;
    url: boolean;
  };
};
type FounderComposerProps = {
  companyId: string;
  tenantId: string;
  onSend: (message: string, artifactIds: string[]) => Promise<void>;
};

const DEFAULT_MAX_ATTACHMENTS = 5;
const ACCEPTED_FORMATS = ".pdf,.docx,.xlsx,.pptx,.csv,.json,.txt,.md,.yaml,.yml,.xml,.html,.htm,.log";

async function responsePayload(response: Response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || "Document request failed (" + response.status + ")");
  return payload;
}

function prettySize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "Ready";
  if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

export default function FounderComposer({ companyId, tenantId, onSend }: FounderComposerProps) {
  const [uploadConfig, setUploadConfig] = useState<UploadConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<Artifact[]>([]);
  const [uploadPanelOpen, setUploadPanelOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const dashboardTarget = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const attachmentsRef = useRef<Artifact[]>([]);
  attachmentsRef.current = attachments;

  useEffect(() => {
    let cancelled = false;
    fetch("/v2/upload-config")
      .then(responsePayload)
      .then((config) => { if (!cancelled) setUploadConfig(config as UploadConfig); })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); })
      .finally(() => { if (!cancelled) setConfigLoading(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    setDraft("");
    setAttachments([]);
    setUploadPanelOpen(false);
    setUploading(false);
    setSending(false);
    setError("");
    setStatus("");
  }, [companyId]);

  useEffect(() => {
    if (!companyId || !uploadConfig || !uploadPanelOpen || !dashboardTarget.current) return;

    const maxAttachments = uploadConfig.max_attachments || DEFAULT_MAX_ATTACHMENTS;
    const endpoint = (file: any) => {
      const base = file.isRemote ? uploadConfig.upload_target_base_url : window.location.origin;
      return base.replace(/\/$/, "") + "/v2/companies/" + encodeURIComponent(companyId) + "/artifacts";
    };
    const uppy = new Uppy({
      autoProceed: false,
      restrictions: {
        maxNumberOfFiles: maxAttachments,
        maxFileSize: (uploadConfig.max_upload_mb || 12) * 1024 * 1024,
        allowedFileTypes: ACCEPTED_FORMATS.split(","),
      },
      meta: { tenant_id: tenantId, actor_id: "founder", kind: "document" },
    })
      .use(Dashboard, {
        inline: true,
        target: dashboardTarget.current,
        height: 245,
        hideProgressDetails: false,
        proudlyDisplayPoweredByUppy: false,
        note: "Company-scoped documents · up to five files per message",
      })
      .use(XHRUpload, {
        endpoint,
        method: "POST",
        fieldName: "file",
        formData: true,
        bundle: false,
        allowedMetaFields: ["tenant_id", "actor_id", "kind"],
        withCredentials: true,
      });

    if (uploadConfig.companion_enabled) {
      const companionOptions = {
        companionUrl: uploadConfig.companion_url,
        companionAllowedHosts: [uploadConfig.companion_url],
        companionCookiesRule: "include" as const,
      };
      if (uploadConfig.sources.url) uppy.use(Url, companionOptions);
      if (uploadConfig.sources.google_drive) uppy.use(GoogleDrive, companionOptions);
      if (uploadConfig.sources.dropbox) uppy.use(Dropbox, companionOptions);
      if (uploadConfig.sources.onedrive) uppy.use(OneDrive, companionOptions);
      if (uploadConfig.sources.box) uppy.use(Box, companionOptions);
    }

    uppy.on("file-added", (file) => {
      const waiting = uppy.getFiles().filter((item) => !item.progress.uploadComplete).length;
      if (attachmentsRef.current.length + waiting > maxAttachments) {
        uppy.removeFile(file.id);
        setError("Attach no more than " + maxAttachments + " documents to one message.");
        return;
      }
      uppy.setFileMeta(file.id, { tenant_id: tenantId, actor_id: "founder", kind: "document" });
      setError("");
      setStatus("Added " + file.name);
    });
    uppy.on("upload", () => {
      setError("");
      setUploading(true);
      setStatus("Uploading documents to company storage…");
    });
    uppy.on("upload-success", (file, response) => {
      const body = response.body as ({ artifact?: Artifact } & Partial<Artifact>) | undefined;
      const artifact = body?.artifact || (body?.object_id ? body as Artifact : undefined);
      if (!artifact?.object_id) {
        setError((file?.name || "Document") + " uploaded, but the API did not return an artifact reference.");
        return;
      }
      setAttachments((current) => {
        if (current.some((item) => item.object_id === artifact.object_id)) return current;
        return [...current, { ...artifact, source: "company-upload" }].slice(0, maxAttachments);
      });
      setStatus(artifact.filename + " is attached to this message context");
    });
    uppy.on("upload-error", (file, reason) => {
      setError((file?.name || "Upload") + ": " + (reason.message || "upload failed"));
      setStatus("");
    });
    uppy.on("restriction-failed", (_file, reason) => {
      setError(reason.message);
      setStatus("");
    });
    uppy.on("complete", () => setUploading(false));

    return () => { uppy.destroy(); };
  }, [companyId, tenantId, uploadConfig, uploadPanelOpen]);

  const cloudSources = useMemo(() => {
    const sources = uploadConfig?.sources;
    if (!sources) return [];
    return [
      sources.google_drive && "Google Drive",
      sources.dropbox && "Dropbox",
      sources.onedrive && "OneDrive",
      sources.box && "Box",
      sources.url && "URL import",
    ].filter(Boolean) as string[];
  }, [uploadConfig]);

  const send = useCallback(async (event?: FormEvent) => {
    event?.preventDefault();
    const message = draft.trim() || (attachments.length
      ? "Please review the attached documents and use them as context for my request."
      : "");
    if (!message || !companyId || sending || uploading) return;
    setSending(true);
    setError("");
    setStatus("Delivering instruction to your AI workforce…");
    try {
      await onSend(message, attachments.map((item) => item.object_id));
      setDraft("");
      setAttachments([]);
      setUploadPanelOpen(false);
      setStatus("Your instruction was delivered.");
      requestAnimationFrame(() => textarea.current?.focus());
    } catch (reason) {
      setError((reason as Error).message || "Unable to deliver this instruction.");
      setStatus("");
    } finally {
      setSending(false);
    }
  }, [attachments, companyId, draft, onSend, sending, uploading]);

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  function removeAttachment(objectId: string) {
    setAttachments((current) => current.filter((item) => item.object_id !== objectId));
  }

  const maxAttachments = uploadConfig?.max_attachments || DEFAULT_MAX_ATTACHMENTS;
  const canSend = Boolean(companyId && (draft.trim() || attachments.length) && !sending && !uploading);
  const sourcesReady = Boolean(uploadConfig?.companion_enabled && cloudSources.length);

  return (
    <form className="founder-composer" onSubmit={(event) => void send(event)}>
      <div className="founder-composer-topline">
        <span><span className="composer-status-dot" /> MESSAGE YOUR WORKFORCE</span>
        <span className="composer-company-context">{companyId ? "COMPANY CONTEXT ACTIVE" : "SELECT A COMPANY FIRST"}</span>
      </div>
      <textarea
        ref={textarea}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKeyDown}
        rows={3}
        maxLength={12000}
        placeholder={companyId ? "Ask your AI workforce to analyse, research, plan or collaborate…" : "Create or select a company first"}
        aria-label="Founder instruction"
        disabled={!companyId || sending}
      />
      <AnimatePresence initial={false}>
        {attachments.length > 0 && (
          <motion.div className="composer-attachments" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}>
            {attachments.map((item) => (
              <div className="composer-attachment" key={item.object_id}>
                <span className="composer-attachment-icon cloud"><FileText size={14} /></span>
                <span className="composer-attachment-copy"><strong>{item.filename}</strong><small>{prettySize(item.size_bytes)} · Document attached</small></span>
                <button type="button" aria-label={"Remove " + item.filename} onClick={() => removeAttachment(item.object_id)}><X size={13} /></button>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
      {(error || status) && (
        <div className={"composer-feedback" + (error ? " is-error" : "")} role="status">
          {error ? <AlertCircle size={13} /> : sending || uploading ? <LoaderCircle className="composer-spin" size={13} /> : <Check size={13} />}
          <span>{error || status}</span>
          {error && <button type="button" onClick={() => setError("")} aria-label="Dismiss error"><X size={13} /></button>}
        </div>
      )}
      <div className="founder-composer-footer">
        <div className="composer-tools">
          <button
            type="button"
            className={"composer-tool-button" + (uploadPanelOpen ? " active" : "")}
            onClick={() => setUploadPanelOpen((value) => !value)}
            disabled={!companyId || sending || uploading || attachments.length >= maxAttachments}
            title="Attach files or import from cloud storage"
          >
            <Paperclip size={15} /><span>Attach / cloud</span>
          </button>
          <span className="composer-attachment-limit">{attachments.length}/{maxAttachments}</span>
        </div>
        <button type="submit" className="composer-send-button" disabled={!canSend}>
          {sending || uploading ? <LoaderCircle className="composer-spin" size={15} /> : <Send size={15} />}
          <span>{uploading ? "Uploading…" : sending ? "Sending…" : "Send to team"}</span>
        </button>
      </div>
      {uploadPanelOpen && (
        <section className="pb-document-upload-panel" aria-label="Document upload and cloud import">
          <header>
            <div><strong>Attach documents</strong><small>Choose local files or an enabled cloud provider.</small></div>
            <button type="button" onClick={() => setUploadPanelOpen(false)} aria-label="Close document upload"><X size={14} /></button>
          </header>
          {configLoading && <p className="pb-upload-note">Checking upload services…</p>}
          {!configLoading && !uploadConfig?.companion_enabled && <p className="pb-upload-note">Local file upload is available. Configure Companion to enable cloud imports.</p>}
          {sourcesReady && <p className="pb-cloud-source-note"><ShieldCheck size={12} /> Connected sources: {cloudSources.join(" · ")}</p>}
          {uploadConfig && <div ref={dashboardTarget} className="pb-uppy-dashboard" />}
          {status && <p className="pb-upload-note">{status}</p>}
          <footer><span>{uploadConfig?.max_upload_mb || 12} MB per file · {maxAttachments} documents per message</span><button type="button" onClick={() => setUploadPanelOpen(false)}>Done</button></footer>
        </section>
      )}
      <div className="composer-help-row"><span>Shift + Enter for a new line</span><span>Local upload · Drive · Dropbox · OneDrive · Box · URL</span></div>
    </form>
  );
}
