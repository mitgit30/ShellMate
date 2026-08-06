# ShellMate

ShellMate is an AI-assisted Linux server operations platform designed to execute diagnostics, structured deployments, and creative file generation. It is built around three operating pillars, a decoupled four-tier runtime architecture, and a secure hybrid memory engine.

---

## Technology Stack

* **Frontend**: Streamlit (NDJSON-streamed token visualization)
* **Backend**: FastAPI, Pydantic, Uvicorn
* **Agentic Runtime**: Python-native ReAct/Pipeline runtime, Ollama Client
* **LLM Models**: Configurable Ollama Cloud chat and embedding models
* **Database & Memory**: SQLite3 (Real-time state database), Chroma DB (Semantic vector store)
* **Remote Execution**: Paramiko (SSHv2 / SFTP), Docker CLI, Docker Compose CLI
* **Orchestration Tooling**: LangChain Core / LangChain Chroma

---

## 1. Operating Pillars

ShellMate separates operations into three distinct pillars to isolate flexible diagnostics from safety-critical mutations:

* **Pillar 1: Day-to-Day Server Management (`SSHSkill`)**
  * *Purpose*: Conversational diagnostics (disk usage, memory statistics, port status, process audits, log inspection).
  * *Execution*: An interactive ReAct (Reasoning and Acting) loop that executes remote, read-only terminal commands via SSH (Paramiko) and translates raw logs/data into clean summaries.
  * *Safety Guardrails*: Programmatically prompted to never execute changes or destructive commands (e.g., service restarts, package changes) without explicit user confirmation.

* **Pillar 2: Structured Deployment Engine (`DeploymentSkill`)**
  * *Purpose*: Orchestrates Docker and Docker Compose infrastructure mutations.
  * *Execution*: A deterministic, rule-based pipeline running through fixed operational stages: `Validate` -> `Gather` -> `Generate` -> `Approval` -> `Execute` -> `Verify` -> `Summary`. 
  * *Safety Guardrails*: The LLM interprets parameters, handles verification outputs, and designs configurations, but the pipeline execution structure and approval checkpoints are strictly controlled code gates.

* **Pillar 3: Generative Web Page Builder (`BuilderSkill`)**
  * *Purpose*: Generates visual static site assets (HTML, CSS, JS) grounded in custom style choices.
  * *Execution*: Conversational discovery to resolve visual specifications, followed by structured asset generation written directly to the target directory on the remote server via the `BuilderTool`.

---

## 2. System Architecture

The codebase is organized into four decoupled layers:

1. **Frontend Layer (Streamlit)**: Operates as the user control panel, receiving user inputs and displaying real-time agent status, command executions, and streamed assistant tokens.
2. **Control API Layer (FastAPI)**: Serves HTTP endpoints for registered Linux hosts, credential/key storage, active web sessions, and agent turns.
3. **Runtime Engine Layer (Python)**: Orchestrates routing via `SkillRouter`, executes selected pillars, manages state, and triggers silent context extraction.
4. **Execution Layer (Paramiko / Tools)**: Runs low-level SSH sessions on target nodes, runs Docker execution pipelines, and manages local asset creation.

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
|   ServerOpsAgent, SkillRouter, ContextExtractor      |
+--------------------------+----------------------------+
                           | Operations & Mutations
                           v
+-------------------------------------------------------+
|                    EXECUTION LAYER                    |  <- Target Node Execution
|   SSH (Paramiko), Docker Pipeline, Builder Tools      |
+-------------------------------------------------------+
```

---

## 3. The Hybrid Memory Architecture

ShellMate implements a stateful and semantic memory layer managed by the `MemoryManager`, keeping prompt contexts light and isolating long-term knowledge from short-term conversation.

```text
               +----------------------------------------+
               |             MemoryManager              |
               +-------------------+--------------------+
                                   |
                  +----------------+----------------+
                  |                                 |
                  v                                 v
   +-----------------------------+   +-----------------------------+
   |     SQLite Memory Store     |   |   Vector Historical Store   |
   |  - memory_documents         |   |  - Chroma DB Backend        |
   |  - memory_facts (Upserted)  |   |  - nomic-embed-text         |
   |  - memory_observations      |   |  - Secret Sanitizer         |
   +-----------------------------+   +-----------------------------+
```

### 3.1. Real-Time State: SQLite Memory Store
Active system parameters are recorded in SQLite (`backend/data/memory.db`) to ensure the agent receives a single, accurate, non-contradictory state:
* **`memory_documents`**: Stores the latest session state and latest inter-skill handoff description per server. It is not the complete historical summary archive.
* **`memory_facts`**: Stores categories like `Paths`, `Packages`, `Ports`, and `Containers`. Facts are matched using a hash of the content and saved using an upsert (`ON CONFLICT DO UPDATE`) operation, preventing port conflict hallucinations.
* **`memory_observations`**: Tracks transaction payloads and observation event history.

### 3.2. Semantic Context: Chroma Vector DB
Historical execution summaries are stored semantically to inform the agent of past server actions across sessions:
* **Vector Store**: Uses Chroma DB through LangChain and the configured Ollama Cloud embedding model.
* **Indexing**: After a completed turn produces a useful handoff, the summary is sanitized and indexed once. New summaries receive new embeddings; existing summaries are not re-embedded on every request.
* **Secret Redaction**: Raw agent summaries are parsed by an automated regex-based sanitizer before embedding, redacting SSH private keys and masking credentials to prevent vector leakages.
* **Server Scoping**: Vector queries are filtered by metadata attributes (`server_id`, `session_id`, `observed_date`) to guarantee complete process isolation between target nodes.

### 3.3. Prompt Composition & Date-Aware Heuristics
* The `PromptComposer` automatically scans user requests for historical keywords (*previously, earlier, history, ago, last time*).
* It decodes relative and absolute temporal queries (e.g., *"yesterday"*, *"3 days ago"*) into calendar dates.
* Date-bounded queries are semantic-searched against Chroma and injected under. If no entries are found, a strict instruction is appended (`Do not invent activity for this date range`) to prevent LLM hallucinations.

---

## 4. Run & Development Guide

### 4.1. Prerequisites
* Python 3.11+
* Ollama Cloud credentials, or an accessible Ollama-compatible endpoint
* Target Linux nodes with SSH access

### 4.2. Model Configuration
Configure the model endpoint and credentials in `.env`:
```bash
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_API_KEY=your-ollama-cloud-key
OLLAMA_MODEL=your-chat-model
OLLAMA_EMBEDDING_MODEL=your-embedding-model
SHELLMATE_API_KEY=your-shellmate-api-key
CORS_ALLOWED_ORIGINS=http://localhost:8501
```

### 4.3. Starting the Backend (FastAPI)
The backend manages SSH communication, database operations, and proxy streaming.
```bash
# Navigate to project root
uv run uvicorn backend.app.main:app --reload
```
By default, the backend runs on [http://localhost:8000](http://localhost:8000).

### 4.4. Starting the Frontend (Streamlit)
The frontend serves the chat interface.
```bash
uv run streamlit run frontend/app.py
```
By default, the frontend runs on [http://localhost:8501](http://localhost:8501).

### 4.5. Memory Migration (Legacy Data)
If you have legacy Markdown files in `memory/{server_id}`, run the migration utility to parse and load them into SQLite:
```bash
uv run python -m src.memory.migrate_markdown --source memory --database backend/data/memory.db
```

### 4.6. Running Unit Tests
Unit tests verify routing accuracy, prompt assembly, database mutations, and secret sanitization.
```bash
uv run pytest
```

### 4.7. Running with Docker Compose
Build and start the frontend and backend containers:

```bash
docker compose up --build -d
```

The Compose setup persists SQLite, ChromaDB, SSH keys, and logs through host-mounted directories. The `.env` file is injected as configuration and excluded from Docker images.

Run the optional Evidently evaluation job separately:

```bash
docker compose --profile evaluation run --rm evaluation
```
