from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_uppy_cloud_plugins_are_declared_for_the_unified_composer():
    dependencies = json.loads(read("frontend/package.json"))["dependencies"]
    for name in (
        "@uppy/core",
        "@uppy/dashboard",
        "@uppy/xhr-upload",
        "@uppy/box",
        "@uppy/dropbox",
        "@uppy/google-drive",
        "@uppy/onedrive",
        "@uppy/url",
    ):
        assert name in dependencies


def test_document_composer_uses_the_workspace_react_callback_not_legacy_events():
    composer = read("frontend/src/FounderComposer.tsx")
    workspace = read("frontend/src/WorkspaceApp.tsx")
    entry = read("frontend/src/main.tsx")
    assert 'await onSend(message, attachments.map((item) => item.object_id))' in composer
    assert '<FounderComposer companyId={company?.id || ""}' in workspace
    assert "createRoot(container).render(" in entry
    assert 'new CustomEvent' not in composer
    assert 'window.dispatchEvent' not in composer
    assert "company-graph.js" not in entry


def test_composer_offers_enabled_companion_sources_and_accepts_fastapi_artifact_shape():
    composer = read("frontend/src/FounderComposer.tsx")
    for source in ("GoogleDrive", "Dropbox", "OneDrive", "Box", "Url"):
        assert source in composer
    assert 'fetch("/v2/upload-config")' in composer
    assert "body?.artifact || (body?.object_id ? body as Artifact : undefined)" in composer
    assert "DEFAULT_MAX_ATTACHMENTS = 5" in composer
    assert "uploadConfig.upload_target_base_url" in composer


def test_companion_and_api_share_a_scoped_server_side_upload_token():
    import yaml

    compose = yaml.safe_load(read("docker-compose.yml"))
    api_env = compose["services"]["api"]["environment"]
    companion_env = compose["services"]["companion"]["environment"]
    assert "COMPANION_UPLOAD_TOKEN" in api_env
    assert "COMPANION_UPLOAD_HEADERS" in companion_env
    assert api_env["COMPANION_UPLOAD_TARGET_BASE_URL"] == "http://api:8080"
    assert companion_env["COMPANION_UPLOAD_URLS"] == "http://api:8080/v2/companies/"
    auth = read("app/auth.py")
    assert "is_companion_upload" in auth
    assert 'scope.get("method") == "POST"' in auth
    assert "hmac.compare_digest(supplied, expected)" in auth
