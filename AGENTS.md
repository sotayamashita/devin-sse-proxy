# Repository Guidelines

## Project Structure & Module Organization
- `main.py` hosts the asyncio-based proxy bridging STDIN/STDOUT JSON-RPC to Devin SSE endpoints; keep async helpers local to this module unless reuse emerges.
- `pyproject.toml` declares the Python 3.13 runtime and runtime dependency `aiohttp`; mirror updates in `uv.lock`.
- `specs/issue.md` captures the motivating reproduction steps and should be amended when new edge cases appear.
- Ancillary assets (docs, scripts) live at repo root; create new dirs (`docs/`, `scripts/`) if scope grows.

## Build, Test, and Development Commands
- `uv sync` sets up the local virtualenv and installs runtime deps.
- `uv run python main.py --api-key <TOKEN>` starts the proxy against the default Devin endpoints; use `--sse-url` or `--rpc-url` when pointing at staging.
- `uv run python main.py --log-level DEBUG --api-key <TOKEN>` increases logging when debugging transport issues.
- `uv run python -m unittest` or `uv run pytest` executes tests once they exist; both commands respect the managed venv.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indents, snake_case for callables, and UPPER_CASE for module constants such as URLs.
- Retain type hints and explicit return annotations; async helpers should document side effects via docstrings when non-obvious.
- Prefer structured logging via the `logging` module instead of print, and gate secrets before logging payloads.
- Keep modules single-purpose; introduce packages only after code reuse is established.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`type(scope): subject`) and keep subjects under 72 characters; use bodies for rationale and validation details.
- Group unrelated changes into separate commits to keep diffs reviewable; update `README.md` or `specs/issue.md` when behavior shifts.
- Pull requests should summarize problem/solution, list manual test commands, and attach updated Claude configuration snippets or logs when applicable.
- Reference GitHub issues or tickets in the PR body (`Closes #123`) and request review from another maintainer when touching network logic.

## Security & Configuration Notes
- Never hard-code Devin API keys; rely on `--api-key` or `DEVIN_API_KEY` and avoid writing secrets to logs.
- Rotate keys if leaked and scrub shell history; prefer password managers over plain-text storage.
- When packaging for others, remind them to restart Claude Desktop after config changes and to verify `Mcp-Session-Id` headers are respected.
