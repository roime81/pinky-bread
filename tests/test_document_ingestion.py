import pytest

from app.document_ingestion import (
    extract_document_text,
    normalise_share_url,
    supported_document_type,
    validate_public_https_url,
)


def test_supported_document_type_maps_office_files():
    assert supported_document_type("strategy.docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert supported_document_type("forecast.xlsx") == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert supported_document_type("deck.pptx") == "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def test_text_document_extraction_is_bounded_and_marked():
    text, status = extract_document_text("brief.txt", "text/plain", b"First line\n\nSecond line")
    assert status == "extracted"
    assert text == "First line\nSecond line"


def test_image_attachment_is_not_misrepresented_as_extracted_text():
    text, status = extract_document_text("diagram.png", "image/png", b"not-an-image")
    assert text == ""
    assert status == "image_attached_text_extraction_not_enabled"


def test_unknown_file_type_is_rejected():
    with pytest.raises(ValueError, match="Unsupported file type"):
        supported_document_type("payload.exe")


def test_local_and_plain_http_links_are_rejected():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_public_https_url("http://example.com/document.pdf")
    with pytest.raises(ValueError, match="Private or local"):
        validate_public_https_url("https://localhost/private.pdf")
    with pytest.raises(ValueError, match="Private or local"):
        validate_public_https_url("https://127.0.0.1/private.pdf")


def test_google_drive_share_url_is_converted_to_download_url():
    result = normalise_share_url("https://drive.google.com/file/d/AbC_123/view?usp=sharing")
    assert result == "https://drive.google.com/uc?export=download&id=AbC_123"


def test_dropbox_share_url_requests_direct_download():
    result = normalise_share_url("https://www.dropbox.com/s/example/brief.pdf?dl=0")
    assert "dl=1" in result
