from app.model_bootstrap import _installed_model_names, ollama_service_root


def test_ollama_service_root_accepts_openai_compatible_url():
    assert ollama_service_root("http://ollama:11434/v1") == "http://ollama:11434"


def test_ollama_service_root_accepts_native_api_root():
    assert ollama_service_root("http://ollama:11434") == "http://ollama:11434"


def test_installed_model_names_reads_ollama_tags_payload():
    assert _installed_model_names({
        "models": [
            {"name": "qwen2.5:3b"},
            {"model": "llama3.2:1b"},
        ]
    }) == {"qwen2.5:3b", "llama3.2:1b"}
