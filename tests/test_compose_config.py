from pathlib import Path

import yaml
from yaml.constructor import ConstructorError


ROOT = Path(__file__).resolve().parents[1]


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in mapping:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key {key!r}",
                    key_node.start_mark,
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def test_docker_compose_has_no_duplicate_mapping_keys_and_keeps_llm_configuration():
    compose_path = ROOT / "docker-compose.yml"
    config = yaml.load(compose_path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)

    api_environment = config["services"]["api"]["environment"]
    assert api_environment["OPENAI_API_KEY"] == "${OPENAI_API_KEY:-}"
    assert api_environment["OPENAI_API_URL"] == "${OPENAI_API_URL:-https://api.openai.com/v1}"
    assert api_environment["GEMINI_API_KEY"] == "${GEMINI_API_KEY:-}"
    assert api_environment["GEMINI_API_URL"] == "${GEMINI_API_URL:-https://generativelanguage.googleapis.com/v1beta/openai}"
    assert api_environment["OPENAI_COMPATIBLE_API_KEY"] == "${OPENAI_COMPATIBLE_API_KEY:-}"
