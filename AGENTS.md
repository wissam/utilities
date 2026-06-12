# Utilities Agent Notes

Follow the global `/home/wissam/AGENTS.md` directives.

This repo is for reusable local helper scripts that Codex and humans can call
instead of recreating one-off snippets during sessions.

Rules:

- Keep scripts small, auditable, and dependency-light.
- Prefer read-only helpers by default.
- Scripts that mutate external systems must make that obvious in the name,
  help text, and output.
- Do not store secrets in this repo.
- `make install` should install human-invoked scripts into `$HOME/.local/bin`.
