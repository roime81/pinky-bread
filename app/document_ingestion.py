from __future__ import annotations

import asyncio
import ipaddress
import mimetypes
import re
import socket
from email.message import Message
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse, urlunparse

import httpx

MAX_EXTRACTED_CHARS = 60_000
REDIRECT_LIMIT = 4

_EXTENSION_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
    ".xml": "application/xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

_CONTENT_EXTENSIONS = {value: key for key, value in _EXTENSION_TYPES.items()}
_CONTENT_EXTENSIONS["image/jpeg"] = ".jpg"

class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        elif tag.lower() in {"p", "div", "br", "li", "tr", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored and data.strip():
            self.parts.append(data.strip())


def supported_document_type(filename: str, supplied_type: str | None = None) -> str:
    suffix = Path(filename).suffix.lower()
    expected = _EXTENSION_TYPES.get(suffix)
    if not expected:
        raise ValueError("Unsupported file type. Use PDF, DOCX, XLSX, PPTX, CSV, TXT, Markdown, JSON, HTML, XML or an image.")
    if supplied_type and supplied_type not in {"application/octet-stream", "binary/octet-stream"}:
        # The filename extension is the stable signal for browser uploads; do not
        # reject valid Office files reported with a generic browser MIME type.
        if supplied_type.startswith("image/") and not expected.startswith("image/"):
            raise ValueError("The uploaded MIME type does not match the filename.")
    return expected


def safe_filename(filename: str | None) -> str:
    name = Path(filename or "document").name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._")
    return name[:180] or "document"


def normalise_share_url(value: str) -> str:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    # Convert public share pages to direct-download/export endpoints where the
    # provider exposes a stable, unauthenticated download URL.
    if host in {"drive.google.com", "docs.google.com"}:
        match = re.search(r"/(?:file/d|document/d|spreadsheets/d|presentation/d)/([A-Za-z0-9_-]+)", parsed.path)
        if match:
            file_id = match.group(1)
            if host == "docs.google.com" and "/document/" in parsed.path:
                return f"https://docs.google.com/document/d/{file_id}/export?format=docx"
            if host == "docs.google.com" and "/spreadsheets/" in parsed.path:
                return f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"
            if host == "docs.google.com" and "/presentation/" in parsed.path:
                return f"https://docs.google.com/presentation/d/{file_id}/export?format=pptx"
            return f"https://drive.google.com/uc?export=download&id={quote(file_id)}"
    if host == "www.dropbox.com" or host == "dropbox.com":
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["dl"] = ["1"]
        from urllib.parse import urlencode
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    # Microsoft OneDrive/SharePoint and Box public shares generally honour
    # download=1; signed pre-authorised file URLs remain unchanged.
    if host == "1drv.ms" or host.endswith(".sharepoint.com") or host in {"onedrive.live.com", "www.box.com", "box.com"}:
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["download"] = ["1"]
        from urllib.parse import urlencode
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    return value.strip()


def validate_public_https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Document links must use HTTPS.")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Document links cannot contain credentials or a non-standard port.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Private or local network addresses are not allowed.")
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        try:
            results = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ValueError("The document host could not be resolved.") from exc
        addresses = [ipaddress.ip_address(item[4][0]) for item in results]
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("The document link resolves to a private or reserved network address.")
    return value


def _filename_from_response(url: str, content_disposition: str | None, content_type: str) -> str:
    if content_disposition:
        message = Message()
        message["content-disposition"] = content_disposition
        candidate = message.get_filename()
        if candidate:
            clean = safe_filename(candidate)
            if not Path(clean).suffix:
                suffix = _CONTENT_EXTENSIONS.get(content_type.split(";", 1)[0].strip().lower())
                if not suffix:
                    raise ValueError("The cloud link did not provide a supported document filename or content type.")
                clean += suffix
            return clean
    candidate = Path(unquote(urlparse(url).path)).name
    if candidate and Path(candidate).suffix:
        return safe_filename(candidate)
    suffix = _CONTENT_EXTENSIONS.get(content_type.split(";", 1)[0].strip().lower())
    if not suffix:
        raise ValueError("The cloud link did not provide a supported document filename or content type.")
    return "linked-document" + suffix


async def fetch_public_document(url: str, max_bytes: int) -> tuple[bytes, str, str, str]:
    current = normalise_share_url(url)
    validate_public_https_url(current)
    timeout = httpx.Timeout(30.0, connect=8.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers={"User-Agent": "PinkyBread-DocumentImporter/1.0"}) as client:
        for _ in range(REDIRECT_LIMIT + 1):
            validate_public_https_url(current)
            async with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("The cloud provider returned an invalid redirect.")
                    current = urljoin(current, location)
                    continue
                if response.status_code < 200 or response.status_code >= 300:
                    raise ValueError(f"The document host returned HTTP {response.status_code}. Check that the share link is accessible.")
                content_type = response.headers.get("content-type", "application/octet-stream").split(";", 1)[0].strip().lower()
                filename = _filename_from_response(current, response.headers.get("content-disposition"), content_type)
                detected = supported_document_type(filename, content_type)
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise ValueError(f"The linked document exceeds the {max_bytes // (1024 * 1024)} MB import limit.")
                return bytes(chunks), filename, detected, current
    raise ValueError("The cloud link redirected too many times.")


def _validate_office_archive(content: bytes) -> None:
    import zipfile
    from io import BytesIO

    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 2_000:
                raise ValueError("Office document contains too many archive entries.")
            total_size = sum(item.file_size for item in entries)
            if total_size > 100 * 1024 * 1024:
                raise ValueError("Office document expands beyond the 100 MB safety limit.")
            for item in entries:
                if item.file_size and item.compress_size == 0:
                    raise ValueError("Office document contains an invalid compressed entry.")
                if item.compress_size and item.file_size / item.compress_size > 200:
                    raise ValueError("Office document compression ratio exceeds the safety limit.")
                if ".." in Path(item.filename).parts:
                    raise ValueError("Office document contains an unsafe archive path.")
    except zipfile.BadZipFile as exc:
        raise ValueError("The uploaded Office document is not a valid Office archive.") from exc


def extract_document_text(filename: str, content_type: str, content: bytes) -> tuple[str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return "", "image_attached_text_extraction_not_enabled"
    if suffix in {".docx", ".xlsx", ".pptx"}:
        _validate_office_archive(content)
    try:
        if suffix == ".pdf":
            import fitz
            with fitz.open(stream=content, filetype="pdf") as document:
                text = "\n".join(page.get_text("text") for page in document)
        elif suffix == ".docx":
            from docx import Document
            document = Document(__import__("io").BytesIO(content))
            pieces = [paragraph.text for paragraph in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    pieces.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(pieces)
        elif suffix == ".xlsx":
            from openpyxl import load_workbook
            workbook = load_workbook(__import__("io").BytesIO(content), read_only=True, data_only=True)
            pieces = []
            for sheet in workbook.worksheets:
                pieces.append(f"[Sheet: {sheet.title}]")
                for row in sheet.iter_rows(values_only=True, max_row=500):
                    values = [str(value) for value in row if value is not None]
                    if values:
                        pieces.append(" | ".join(values))
            workbook.close()
            text = "\n".join(pieces)
        elif suffix == ".pptx":
            from pptx import Presentation
            presentation = Presentation(__import__("io").BytesIO(content))
            pieces = []
            for index, slide in enumerate(presentation.slides, start=1):
                pieces.append(f"[Slide {index}]")
                for shape in slide.shapes:
                    if getattr(shape, "has_text_frame", False) and shape.text.strip():
                        pieces.append(shape.text.strip())
                    if getattr(shape, "has_table", False):
                        for row in shape.table.rows:
                            pieces.append(" | ".join(cell.text for cell in row.cells))
            text = "\n".join(pieces)
        elif suffix in {".html", ".htm"}:
            parser = _VisibleTextParser()
            parser.feed(content.decode("utf-8", errors="replace"))
            text = "\n".join(parser.parts)
        else:
            text = content.decode("utf-8-sig", errors="replace")
    except ValueError:
        raise
    except Exception as exc:
        return "", f"extraction_failed:{type(exc).__name__}"
    cleaned = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    if not cleaned:
        return "", "no_extractable_text"
    return cleaned[:MAX_EXTRACTED_CHARS], "extracted"
