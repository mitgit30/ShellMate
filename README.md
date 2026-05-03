# Chat‑Based Linux Server Manager

Prototype project for managing Linux servers through a chat‑style workflow. It consists of a FastAPI backend for server registration and SSH connection support, a WebSocket gateway for live agent chat, and a Streamlit frontend that provides an interactive UI.

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
      config.py          # Pydantic settings, SSH timeout, key storage dir
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
    websocket_server.py   # WebSocket chat gateway using the websockets library
  runtime/
    agent.py             # Runtime flow: understand -> route -> execute skill -> persist
    models.py            # Pydantic models for tool events and route decisions
    ollama_client.py     # Ollama client wrapper for routing and skill execution
    config.py
  skills/
    base.py
    registry.py
    router.py
    ssh_skill.py         # First skill: all SSH-oriented requests
  storage/
    session_store.py     # In‑memory chat session store
  tools/
    ssh_tool.py          # Structured SSH tool used by the SSH skill
    __init__.py

tests/
  test_server_service.py   # Unit test for server registration logic
```

## Backend (FastAPI)

- **Configuration** (`backend/app/core/config.py`): Centralised settings loaded from `.env`, including API title/version, frontend base URL, SSH command timeout, and key storage directory.
- **Service Layer** (`services/`):
  - `ServerService` manages CRUD for server records.
  - `SSHService` establishes SSH connections, runs commands, and returns `CommandExecutionResponse`.
  - `KeyStorageService` handles PEM key uploads.
- **API Routers** (`api/v1/routes/`):
  - `servers` – register, list, and delete servers.
  - `keys` – upload PEM files.
  - `ssh` – test connectivity and execute commands.
  - `chat` – start a session, send messages, and stream responses (including tool events).
  - `health` – simple health check.

All routes are mounted under `/api/v1` and the app enables CORS for any origin (development convenience).

## Frontend (Streamlit)

- **Configuration** (`frontend/app.py`): Reads `API_BASE_URL` and `WEBSOCKET_URL` from `.env`.
- **Session State**: Tracks selected/connected server, active view (`chat` or `registered_servers`), and chat history via `st.session_state`.
- **Sidebar**: Server registry form (host, username, PEM upload), connection testing panel, and navigation buttons.
- **Main Area**:
  - *Server table* – displays registered servers.
  - *Chat panel* – connects to the WebSocket gateway, streams AI responses, and shows skill/tool activity.

The UI is lightweight, styled with minimal custom CSS, and focuses on the workflow: register → connect → chat.

## Runtime, Skills \& WebSocket Gateway

- **Skill Router** (`src/skills/router.py`): Prompts the LLM with the available skills and asks it to select the best one.
- **Skill Registry** (`src/skills/registry.py`): Central list of registered skills. Phase one contains only one skill: `ssh`.
- **SSH Skill** (`src/skills/ssh_skill.py`): Handles all SSH-oriented work. It can inspect server state, logs, services, uptime, files, and other tasks by calling the structured SSH tool.
- **SSH Tool** (`src/tools/ssh_tool.py`): Validates and executes SSH commands through `SSHService`.
- **Runtime Agent** (`src/runtime/agent.py`): Runs the flow `understand intent -> route to skill -> execute skill step by step -> persist history`.
- **WebSocket Gateway** (`src/gateway/websocket_server.py`): Streams events like `intent_detected`, `skill_selected`, `tool_event`, and response tokens to the frontend using the `websockets` library.
- **Session Store** (`src/storage/session_store.py`): Simple in‑memory holder for chat sessions.

## Quick Start

1. **Install dependencies**
   ```bash
   uv sync
   ```
2. **Run the backend**
   ```bash
   uv run uvicorn backend.app.main:app --reload
   ```
3. **Run the WebSocket gateway**
   ```bash
   uv run python -m src.gateway.websocket_server
   ```
4. **Run the frontend**
   ```bash
   uv run streamlit run frontend/app.py
   ```
5. Open the Streamlit URL shown in the terminal, register a server (public IPv4, username, upload the corresponding `.pem` key), test the connection, and start chatting with the AI assistant over WebSockets. The assistant first routes the request to the `ssh` skill, then that skill can invoke the `run_ssh_command` tool to fetch live data from the connected host.

## Notes \& Future Work

- The server registry is in‑memory; persistence could be added via a database.
- Currently only PEM files are supported; other key formats could be integrated.
- The first skill layer contains only the `ssh` skill. Additional skills can be added later without changing the overall route/execute/stream architecture.
- Security hardening (rate limiting, auth, secret management) is required for production use.
