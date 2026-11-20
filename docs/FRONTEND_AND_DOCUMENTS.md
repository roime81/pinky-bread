# React workspace and document-aware chat

## Frontend foundation

The current workspace uses:
- React 19 and TypeScript for the agent collaboration area and founder chat composer
- Vite 8 for the production build
- Tailwind CSS 4 for utility styling
- shadcn/ui-compatible component conventions with Radix UI primitives
- Motion for transitions and Lucide for icons

The company graph, navigation and existing operational views continue to use the established workspace shell while they are migrated incrementally. The document-aware composer is mounted as a React component in the founder chat rail, and the agent-conversation workspace remains React-based. This is an incremental migration, not a claim that every legacy page has already been rewritten.

## Using the founder composer

1. Open a company in Company Graph.
2. In the right-hand founder chat panel, write an instruction for the AI workforce.
3. Select **Attach files**, or drag files into the composer.
4. Optionally select **Cloud link** and paste a public HTTPS share/download link.
5. Review the attachment chips and remove any source that should not be included.
6. Submit the instruction. Pinky Bread uploads/imports the sources first, then sends the source document IDs with the chat request.

The composer supports up to 10 source files per message and uses the existing MAX_UPLOAD_MB limit (12 MB by default, per file). Supported extensions are PDF, DOCX, XLSX, PPTX, CSV, TXT, Markdown, JSON, HTML, XML, PNG, JPEG and WebP.

## Document processing and storage

Uploaded files and imported public links use the existing company artifact API and object store:
- SeaweedFS/S3-compatible storage in Docker Compose
- Local filesystem storage in standalone development
- PostgreSQL metadata with company and tenant identifiers, checksum, source type, file type and object key
- Company graph document nodes and ownership/information relationships

Text is extracted from text-based PDFs, DOCX, XLSX, PPTX, CSV, TXT, Markdown, JSON, HTML and XML. The extracted content is stored as document metadata and supplied to agents when the founder sends a message with the corresponding artifact_ids.

Each chat request validates that every artifact ID belongs to the selected company and tenant. Agents are explicitly told to treat extracted document content as untrusted reference material, not as instructions, and to identify source filenames when using the contents.

Image files can be attached and stored, but this release does not OCR images or provide image pixels to the company chat model. Scanned PDFs without an embedded text layer may likewise provide no extracted text. The application reports this state rather than claiming that an agent has read the image or scan.

## Cloud-link import boundary

POST /v2/companies/{company_id}/document-links imports a document accessible through a public HTTPS share/download URL. Google Drive file-share URLs and Google Docs/Sheets/Slides export links are normalised where possible; Dropbox shared links are converted to direct-download mode. Other cloud providers work when their public share URL resolves to a direct supported file download.

The importer:
- permits HTTPS only
- rejects local/private/reserved network destinations and non-standard ports
- validates each redirect rather than automatically following redirects
- caps redirects and response size
- accepts only supported document types
- does not store the original full URL in document metadata

This public-link flow is not an authenticated cloud-storage connector. A private Google Drive, Microsoft OneDrive/SharePoint, Dropbox Business, S3 private bucket or Azure Blob container requires a user-authorised connector with OAuth or provider credentials and an explicit access-control model. Those authenticated connectors are not enabled by this release. Do not paste private URLs containing access tokens or credentials into the public-link field.

The importer is designed for public document links, not arbitrary website crawling. URLs that resolve to private infrastructure are rejected to reduce server-side request forgery risk.

## API additions

### Upload a company document

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
- Commercial LLM providers may receive the extracted document context when an agent is configured to use that provider. Follow the provider's data-handling and retention policy before attaching confidential material.
