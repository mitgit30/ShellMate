# ShellMate

ShellMate is a Linux server ops tool that uses an LLM to run diagnostics, handle structured deployments, and generate simple static sites. It's built around three separate operating pillars, a four-layer runtime, and a hybrid memory system that mixes SQLite state with vector search.

---

## Technology Stack

* **Frontend**: Streamlit (streams tokens over NDJSON)
* **Backend**: FastAPI, Pydantic, Uvicorn
* **Agentic Runtime**: Python ReAct/pipeline runtime, Ollama Client
* **LLM Models**: Configurable Ollama Cloud chat and embedding models
* **Database & Memory**: SQLite3 for live state, Chroma DB for semantic search
* **Remote Execution**: Paramiko (SSHv2 / SFTP), Docker CLI, Docker Compose CLI
* **Orchestration Tooling**: LangChain Core / LangChain Chroma

---

## 1. Operating Pillars

ShellMate keeps flexible, read-only diagnostics separate from anything that mutates a server. That split happens across three pillars:

* **Pillar 1: Day-to-Day Server Management (`SSHSkill`)**
  * *What it does*: Handles conversational diagnostics — disk usage, memory stats, port status, process audits, log inspection.
  * *How*: Runs a ReAct loop that executes read-only commands over SSH (via Paramiko) and turns raw output into a readable summary.
  * *Guardrails*: The prompt instructs it never to run changes or destructive commands (service restarts, package installs, etc.) without the user confirming first.

* **Pillar 2: Structured Deployment Engine (`DeploymentSkill`)**
  * *What it does*: Handles Docker and Docker Compose deployments.
  * *How*: A fixed, rule-based pipeline: `Validate` → `Gather` → `Generate` → `Approval` → `Execute` → `Verify` → `Summary`.
  * *Guardrails*: The LLM fills in parameters, reads verification output, and writes configs, but the pipeline stages and approval checkpoints themselves are hard-coded, not something the model can skip.

* **Pillar 3: Generative Web Page Builder (`BuilderSkill`)**
  * *What it does*: Generates static site assets (HTML, CSS, JS) based on style choices the user gives it.
  * *How*: A short back-and-forth to pin down the visual spec, then the `BuilderTool` writes the generated files directly to the target directory on the remote server.

---

## 2. System Architecture

The codebase has four layers:

1. **Frontend (Streamlit)**: The control panel — takes user input, shows agent status, command output, and streamed tokens.
2. **Control API (FastAPI)**: HTTP endpoints for registered hosts, credentials/keys, active sessions, and agent turns.
3. **Runtime Engine (Python)**: Routes requests via `SkillRouter`, runs the selected pillar, manages state, and triggers context extraction in the background.
4. **Execution Layer (Paramiko / Tools)**: Runs the actual SSH sessions, drives the Docker pipeline, and writes generated assets.

```text
+-------------------------------------------------------+
|                      STREAMLIT UI                     |  <- Frontend UI
+--------------------------+----------------------------+
                           | HTTP Requests / NDJSON Streams
                           v
+-------------------------------------------------------+
|                      FASTAPI API                      |  <- API & Session Management
+--------------------------+----------------------------+
                           | Instantiates
                           v
+-------------------------------------------------------+
|                    RUNTIME ENGINE                     |  <- Routing & Orchestration
|   ServerOpsAgent, SkillRouter, ContextExtractor        |
+--------------------------+----------------------------+
                           | Operations & Mutations
                           v
+-------------------------------------------------------+
|                    EXECUTION LAYER                    |  <- Target Node Execution
|   SSH (Paramiko), Docker Pipeline, Builder Tools       |
+-------------------------------------------------------+
```

---

## 3. The Hybrid Memory Architecture

Memory is split into a fast, accurate state store and a semantic historical store, managed by `MemoryManager`. This keeps prompts short while still letting the agent recall past sessions when it needs to.

```text
               +----------------------------------------+
               |             MemoryManager               |
               +-------------------+--------------------+
                                   |
                  +----------------+----------------+
                  |                                 |
                  v                                 v
   +-----------------------------+   +-----------------------------+
   |     SQLite Memory Store      |   |   Vector Historical Store    |
   |  - memory_documents          |   |  - Chroma DB Backend         |
   |  - memory_facts (Upserted)   |   |  - nomic-embed-text          |
   |  - memory_observations       |   |  - Secret Sanitizer          |
   +-----------------------------+   +-----------------------------+
```

### 3.1. Real-Time State: SQLite Memory Store
Current system state lives in SQLite (`backend/data/memory.db`), so the agent always works off one consistent, non-contradictory picture:
* **`memory_documents`**: The latest session state and the latest handoff description between skills, per server. Not a full historical log — just the current snapshot.
* **`memory_facts`**: Categorized facts (`Paths`, `Packages`, `Ports`, `Containers`). Matched by a content hash and upserted (`ON CONFLICT DO UPDATE`), so the agent doesn't hallucinate stale port assignments.
* **`memory_observations`**: Transaction payloads and the history of observation events.

### 3.2. Semantic Context: Chroma Vector DB
Past execution summaries are stored semantically so the agent can pull in relevant history from earlier sessions:
* **Vector Store**: Chroma DB via LangChain, using the configured Ollama Cloud embedding model.
* **Indexing**: Once a turn produces a useful handoff summary, it gets sanitized and embedded a single time. Existing summaries aren't re-embedded on later requests.
* **Secret Redaction**: A regex-based sanitizer strips SSH private keys and masks credentials before anything gets embedded, so secrets don't end up in the vector store.
* **Server Scoping**: Queries are filtered by `server_id`, `session_id`, and `observed_date`, so results from one server never leak into another.

### 3.3. Prompt Composition & Date-Aware Heuristics
* `PromptComposer` scans incoming requests for historical keywords (*previously, earlier, history, ago, last time*).
* It resolves relative and absolute date references (*"yesterday"*, *"3 days ago"*) into actual calendar dates.
* Date-bounded queries get run against Chroma. If nothing matches, the prompt is given an explicit instruction not to invent activity for that range.

---

## 4. Run & Development Guide

### 4.1. Prerequisites
* Python 3.11+
* Ollama Cloud credentials, or an accessible Ollama-compatible endpoint
* Target Linux nodes with SSH access

### 4.2. Model Configuration
Set the model endpoint and credentials in `.env`:
```bash
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_API_KEY=your-ollama-cloud-key
OLLAMA_MODEL=your-chat-model
OLLAMA_EMBEDDING_MODEL=your-embedding-model
CORS_ALLOWED_ORIGINS=http://localhost:8501
```

There's one shared SQLite database for the whole app. Users live in `users`, and
servers are scoped by `servers.user_id` — there's no per-user database file. Create
an account through `POST /api/v1/auth/register` or the frontend's **Create new**
button. Passwords are stored as scrypt hashes, never plaintext. Legacy servers with
no owner get assigned to the first account created after this migration.

### 4.3. Starting the Backend (FastAPI)
Handles SSH communication, database operations, and proxy streaming.
```bash
# From the project root
uv run uvicorn backend.app.main:app --reload
```
Runs on [http://localhost:8000](http://localhost:8000) by default.

### 4.4. Starting the Frontend (Streamlit)
Serves the chat interface.
```bash
uv run streamlit run frontend/app.py
```
Runs on [http://localhost:8501](http://localhost:8501) by default.

### 4.5. Memory Migration (Legacy Data)
If you've got old Markdown files under `memory/{server_id}`, migrate them into SQLite with:
```bash
uv run python -m src.memory.migrate_markdown --source memory --database backend/data/memory.db
```

### 4.6. Running Unit Tests
Tests cover routing accuracy, prompt assembly, database mutations, and secret sanitization.
```bash
uv run pytest
```

### 4.7. Running with Docker Compose
Build and start both containers:

```bash
docker compose up --build -d
```

SQLite, ChromaDB, SSH keys, and logs persist through host-mounted volumes. `.env` is injected at runtime and excluded from the images.

To run the optional Evidently evaluation job separately:

```bash
docker compose --profile evaluation run --rm evaluation
```