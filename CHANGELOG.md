# Changelog

All notable Pinky Bread changes are documented here.

## [v2.0.0-alpha.4] - 2026-11-19

### Added
- Default local Ollama service in Docker Compose using the persistent `ollama_data` volume.
- One-shot `ollama-init` bootstrap that checks installed models and pulls `REASONING_MODEL` before API and worker startup.
- Dedicated host ports for API/UI (8888), MCP (8060), Ollama (11434), PostgreSQL (5433), Valkey (6380) and SeaweedFS S3 (8333).
- Host-facing loopback binding through `PB_BIND_ADDRESS`, with Codespaces guidance for `0.0.0.0`.
- Explicit host versus container model endpoint configuration through `REASONING_API_URL` and `REASONING_CONTAINER_API_URL`.
- Full README installation guide, Docker DNS explanation, model setup, port map and environment-variable reference.
- Guarded GitHub Actions release publishing for this tagged prerelease.

### Changed
- Default inference mode is now live local Ollama (`MOCK_INFERENCE=false`); mock mode must be enabled intentionally.
- Default reasoning model is `qwen2.5:3b`.
- Standalone API runner and Makefile use host port 8888.
- MCP host port 8060 maps to container listener 8090; internal clients continue using Docker service DNS.
- Sidebar navigation uses delegated click handling and explicit pointer-event layering; cached frontend assets are versioned.
- API and company capability version updated to `2.0.0-alpha.4`.

### Notes
- First startup requires internet access to pull container images and the selected Ollama model. Model files persist across ordinary container restarts.
- Existing `.env` files are not overwritten by upgrading. Set `MOCK_INFERENCE=false` in an existing file if it still says `true`.
- This is a prerelease development platform. Authentication, production tenant isolation, OIDC/JWT-based MCP identity and production-grade audit immutability remain out of scope.
