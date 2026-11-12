from pathlib import Path
import yaml
from .schemas import AgentManifest


class AgentRegistry:
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self._agents: dict[str, AgentManifest] = {}
        self.last_errors: list[str] = []
        self.reload()

    def reload(self) -> dict:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        loaded: dict[str, AgentManifest] = {}
        errors: list[str] = []
        for path in sorted(self.config_dir.glob("*.yaml")) + sorted(self.config_dir.glob("*.yml")):
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                manifest = AgentManifest.model_validate(raw)
                agent_id = manifest.agent_metadata.agent_id
                if agent_id in loaded:
                    raise ValueError(f"Duplicate agent_id: {agent_id}")
                loaded[agent_id] = manifest
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        # Keep the last known good registry if a reload has any validation errors.
        if not errors and loaded:
            self._agents = loaded
        self.last_errors = errors
        return {"status": "reloaded" if not errors else "rejected", "active_count": len(self._agents), "validation_errors": errors}

    def get(self, agent_id: str) -> AgentManifest:
        return self._agents[agent_id]

    def all(self) -> list[AgentManifest]:
        return list(self._agents.values())

    def has(self, agent_id: str) -> bool:
        return agent_id in self._agents
