# Chat‑Based Linux Server Manager

Prototype project for managing Linux servers through a chat‑style workflow. It consists of a FastAPI backend for server registration and SSH support, a WebSocket gateway for live agent chat, and a Streamlit frontend that provides an interactive UI.

## Project Structure

```
backend/
  app/
    api/
      v1/
        routes/
          chat.py
          commands.py
          health.py
          keys.py
          servers.py
          sessions.py
    core/
      config.py          # Settings, SSH timeout, key storage dir
      exceptions.py
    repositories/
      server_repository.py   # In‑memory server store
    schemas/
      chat.py, command.py, key.py, server.py, session.py
    services/
      key_storage_service.py
      server_service.py
      ssh_service.py
    main.py               # FastAPI app with CORS and routers
    __init__.py
  data/
    keys/                # Uploaded PEM files
  pyproject.toml
  requirements.txt

frontend/
  app.py                 # Streamlit UI, API client, session state, chat panel

src/
  gateway/
    websocket_server.py   # WebSocket gateway using the websockets library
  runtime/
    agent.py             # Orchestrates intent → routing → skill execution
    models.py            # ToolEvent, SkillRouteDecision, etc.
    ollama_client.py     # Ollama LLM wrapper for routing and skill execution
    config.py
  skills/
    base.py
    registry.py
    router.py
    ssh_skill.py         # First skill: handles all SSH‑related requests
  storage/
    session_store.py    # In‑memory chat session store
  tools/
    ssh_tool.py         # Structured SSH tool used by the SSH skill
    __init__.py

tests/
  test_server_service.py   # Unit test for server registration logic
```

## Backend (FastAPI)

- **Configuration** (`backend/app/core/config.py`): central settings loaded from `.env` (API title/version, SSH command timeout, key storage directory, etc.).
- **Service layer** (`services/`):
  - `ServerService` – CRUD for server records.
  - `SSHService` – opens SSH connections, runs commands, returns `CommandExecutionResponse`.
  - `KeyStorageService` – handles PEM key uploads.
- **API routers** (`api/v1/routes/`): `servers`, `keys`, `ssh` (test/execute), `chat` (session & streaming), `health`.

All routes are mounted under `/api/v1` and CORS is open for development.

## Frontend (Streamlit)

- **Configuration** (`frontend/app.py`): reads `API_BASE_URL` and `WEBSOCKET_URL` from `.env`.
- **Session state** tracks selected/connected server, active view (chat or server list), and chat history.
- **Sidebar** – server registration form, connection testing, navigation buttons.
- **Main area** – server table or chat panel. The chat panel talks to the WebSocket gateway, streams token events, and displays tool activity.

## Runtime, Skills & WebSocket Gateway

- **Skill registry** holds the available skills (currently only the SSH skill).
- **Skill router** asks the LLM (via Ollama) to pick the best skill based on the user message.
- **SSH skill** (`src/skills/ssh_skill.py`) drives the conversation, calling the `run_ssh_command` tool when needed.
- **WebSocket gateway** (`src/gateway/websocket_server.py`) receives a JSON chat request, invokes the agent’s `stream_turn`, and streams back events (`intent_detected`, `skill_selected`, `token`, `tool_event`, `error`, `done`).
- **Session store** (`src/storage/session_store.py`) keeps an in‑memory history per session.

## Quick Start

1. Install dependencies:
   ```bash
   uv sync
   ```
2. Run the FastAPI backend:
   ```bash
   uv run uvicorn backend.app.main:app --reload
   ```
3. Run the WebSocket gateway:
   ```bash
   uv run python -m src.gateway.websocket_server
   ```
4. Run the Streamlit UI:
   ```bash
   uv run streamlit run frontend/app.py
   ```
5. Open the URL shown by Streamlit, register a server (public IPv4, username, upload its `.pem` key), test the connection, and start chatting with the AI assistant over WebSockets.

## Notes & Future Work

- The server registry is in‑memory; a persistent DB could be added.
- Only PEM keys are supported – other formats can be integrated later.
- At the moment the only skill is the SSH skill; additional skills can be registered in `SkillRegistry` without changing the rest of the architecture.
- Security hardening (auth, rate limiting, secret management) is required for production use.
