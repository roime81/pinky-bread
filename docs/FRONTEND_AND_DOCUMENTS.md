# React workspace and document-aware chat

## Frontend foundation

The product workspace now runs as one React 19 + TypeScript application mounted from a single React root. The React application owns the navigation, company selector, company graph, node inspector and relationship editor, founder view, event log and hash verification, AI workforce editor, provider settings, durable job queue and recurring coordination controls, workflow execution/history, templates, audit viewer and founder chat rail. Agent-to-agent conversations are rendered as a feature within that same root.

The production bundle is built with Vite 8 into `web/app` and served by FastAPI at `/static/app`. The old imperative workspace shell and its separate script entry points are no longer loaded. The UI uses the existing FastAPI contracts and PostgreSQL-backed company graph/event records; it does not introduce a second frontend API or a parallel state store. Tailwind CSS 4, Framer Motion and Lucide remain available to the React interface.

## Using the founder composer

1. Open a company in the React workspace.
2. In the right-hand founder chat rail, write an instruction for the AI workforce.
3. Select **Attach / cloud** to open the document panel.
4. Add local documents by drag-and-drop or browse, or use any enabled Google Drive, Dropbox, OneDrive, Box or URL source in Uppy Companion.
5. Wait for each upload to finish, review the company-scoped attachment chips and remove any source that should not be included.
6. Send the instruction. The workspace passes the artifact IDs through the typed React callback to the company chat API; no legacy DOM event or second React root is used.

The composer accepts up to **5 documents per message** and enforces the configured `MAX_UPLOAD_MB` limit (12 MB by default, per file). Supported text formats are PDF, DOCX, XLSX, PPTX, CSV, JSON, TXT, Markdown, YAML, XML, HTML and LOG. The API extracts bounded text from supported files; scanned PDFs and image-only sources do not receive OCR in this flow.
## Document processing and storage

Uploaded files and imported public links use the existing company artifact API and object store:
- SeaweedFS/S3-compatible storage in Docker Compose
- Local filesystem storage in standalone development
- PostgreSQL metadata with company and tenant identifiers, checksum, source type, file type and object key
- Company graph document nodes and ownership/information relationships

Text is extracted from text-based PDFs, DOCX, XLSX, PPTX, CSV, TXT, Markdown, JSON, HTML and XML. The extracted content is bounded and supplied to agents as untrusted system context when the founder sends a message with the corresponding artifact_ids. The founder's original instruction is kept separate from the extracted document text.

Each chat request validates that every artifact ID belongs to the selected company and tenant. Agents are explicitly told to treat extracted document content as untrusted reference material, not as instructions, and to identify source filenames when using the contents.

Image files can be attached and stored, but this release does not OCR images or provide image pixels to the company chat model. Scanned PDFs without an embedded text layer may likewise provide no extracted text. The application reports this state rather than claiming that an agent has read the image or scan.

## Cloud-link import boundary

POST /v2/companies/{company_id}/document-links imports a document accessible through a public HTTPS share/download URL. Google Drive file-share URLs and Google Docs/Sheets/Slides export links are normalised where possible; Dropbox shared links are converted to direct-download mode; OneDrive, SharePoint and Box public share links are asked for download mode. Other cloud providers work when their public share URL resolves to a direct supported file download. S3-compatible pre-signed HTTPS download URLs can also be used while they remain valid.

The importer:
- permits HTTPS only
- rejects local/private/reserved network destinations and non-standard ports
- validates each redirect rather than automatically following redirects
- caps redirects and response size
- accepts only supported document types
- does not store the original full URL in document metadata

The public-link flow is not an authenticated cloud-storage connector. For private files, Uppy Companion can use provider OAuth integrations for Google Drive, Dropbox, OneDrive and Box after their provider credentials are configured on the server. Companion streams selected bytes to the internal company artifact endpoint; it does not expose the service upload token to the browser. A private Google Drive, Microsoft OneDrive/SharePoint, Dropbox Business, S3 private bucket or Azure Blob container requires a user-authorised connector with OAuth or provider credentials and an explicit access-control model. Those authenticated connectors are not enabled by this release. Do not paste private URLs containing access tokens or credentials into the public-link field.

The importer is designed for public document links, not arbitrary website crawling. URLs that resolve to private infrastructure are rejected to reduce server-side request forgery risk.

## API additions

### Upload a company document

GET /v2/upload-config

Returns the enabled Companion sources, server upload target, and current attachment/file-size limits.

POST /v2/companies/{company_id}/artifacts

Multipart fields:
- file
- tenant_id
- actor_id
- kind (document or deliverable)
- optional title
- optional related_node_id

### Import a public cloud share link

POST /v2/companies/{company_id}/document-links

JSON body:
    {
      "tenant_id": "demo-tenant",
      "actor_id": "founder",
      "url": "https://example.com/shared/strategy.pdf"
    }

### Chat with attached company documents

POST /v2/companies/{company_id}/chat

JSON body includes the existing message and history fields plus:
    {
      "artifact_ids": ["company-scoped-object-id"]
    }

The server resolves those IDs against the company and tenant before retrieving stored extraction text and passing the context to the workforce.

## Security and operational notes

- The current application is local-first alpha software. The existing caller-supplied tenant/actor fields are not a production authorization boundary; authenticated company membership and RBAC remain future work.
- Document contents are untrusted inputs. Prompt-injection-like instructions embedded in documents must not override the founder's instructions or agent system policies.
- The current document pipeline extracts text synchronously during upload/import. Large-scale asynchronous parsing, antivirus scanning, OCR, DLP, retention policies, per-source ACL synchronisation and private cloud OAuth connectors remain follow-on work.
- Companion's upload token and cloud provider OAuth secrets stay in server-side environment configuration. The token bypass is limited to the company artifact upload route; use strong, unique values outside local development.
- Commercial LLM providers may receive the extracted document context when an agent is configured to use that provider. Follow the provider's data-handling and retention policy before attaching confidential material.
