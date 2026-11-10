# ShellMate Architectural Flow Diagram

This document contains the high-level architectural flow of the ShellMate project, mapping a user's conversational prompt through the routing, execution, memory, and background extraction pipelines.

## High-Level Flow 

```mermaid
graph TD
    %% Define styles and classes
    classDef ui fill:#E1F5FE,stroke:#0288D1,stroke-width:2px,color:#01579B;
    classDef api fill:#E8F5E9,stroke:#388E3C,stroke-width:2px,color:#1B5E20;
    classDef agent fill:#FFFDE7,stroke:#FBC02D,stroke-width:2px,color:#F57F17;
    classDef skill fill:#EDE7F6,stroke:#7B1FA2,stroke-width:2px,color:#4A148C;
    classDef database fill:#ECEFF1,stroke:#455A64,stroke-width:2px,color:#263238;
    classDef remote fill:#FFEBEE,stroke:#D32F2F,stroke-width:2px,color:#B71C1C;

    %% Components
    User([User Operator])
    
    subgraph Frontend [Streamlit UI Layer]
        UI[Streamlit Chat Interface]:::ui
    end

    subgraph Gateway [Control & API Gateway]
        Middleware[Auth & Trace Middleware]:::api
        FastAPI[FastAPI Endpoints]:::api
    end

    subgraph Runtime [Agentic Runtime Layer]
        Agent[ServerOpsAgent]:::agent
        Router[SkillRouter]:::agent
        Composer[PromptComposer]:::agent
    end

    subgraph Execution [Execution Pillars]
        SSHSkill[Pillar 1: SSH Skill]:::skill
        DeploySkill[Pillar 2: Deployment Skill]:::skill
        BuilderSkill[Pillar 3: Builder Skill]:::skill
        
        DeployEngine[Deployment Engine]:::skill
        DockerPipeline[Docker Rollout Pipeline]:::skill
    end

    subgraph Memory [Hybrid Memory Layer]
        MemMgr[Memory Manager]:::database
        SQLite[(SQLite Store)]:::database
        Chroma[(Chroma Vector DB)]:::database
    end

    subgraph Extractor [Background Observation Layer]
        CtxExtractor[Context Extractor]:::agent
        Sanitizer[Secret Sanitizer]:::agent
    end

    subgraph Infrastructure [Remote Linux Server]
        RemoteSSH[SSH Shell Session]:::remote
        DockerDaemon[Docker Daemon / Containers]:::remote
        FileSystem[Target Directory System]:::remote
    end

    %% Interactions & Flows
    User -->|Sends Prompt| UI
    UI -->|HTTP Request with X-API-Key| Middleware
    Middleware -->|Sets Context request_id| FastAPI
    FastAPI -->|Invokes Turn| Agent

    %% Routing Flow
    Agent -->|Evaluate message| Router
    Router -->|1. Keyword Heuristics| Router
    Router -->|2. LLM Intent Classify| Router
    Router -->|Selects Skill| SSHSkill
    Router -->|Selects Skill| DeploySkill
    Router -->|Selects Skill| BuilderSkill

    %% Memory Hydration Flow
    SSHSkill & DeploySkill & BuilderSkill -->|Query Prompt System| Composer
    Composer -->|Get Handoffs/Facts| MemMgr
    MemMgr -->|1. Fetch Current State| SQLite
    
    %% Historical Vector Flow
    Composer -->|If historical query| MemMgr
    MemMgr -->|2. Fetch semantic summaries| Chroma
    MemMgr -->|Return integrated memory| Composer
    Composer -->|Injected Prompt| SSHSkill & DeploySkill & BuilderSkill

    %% Execution Flows
    SSHSkill -->|Run diagnostics| RemoteSSH
    DeploySkill -->|Invoke| DeployEngine
    DeployEngine -->|Run validation & compose| DockerPipeline
    DockerPipeline -->|Requires User Approval| UI
    UI -->|Approve/Reject| DockerPipeline
    DockerPipeline -->|Mutate workloads| DockerDaemon

    BuilderSkill -->|Write HTML/CSS/JS assets| FileSystem

    %% Streaming Output
    SSHSkill & DockerPipeline & BuilderSkill -->|Yield NDJSON event streams| FastAPI
    FastAPI -->|Stream tokens / status events| UI

    %% Silent Fact Extraction Loop
    Agent -->|After turn finishes, spawns background task| CtxExtractor
    CtxExtractor -->|Analyze chat & tool logs| CtxExtractor
    CtxExtractor -->|Update active facts & ports| SQLite
    CtxExtractor -->|Summarize turn| Sanitizer
    Sanitizer -->|Filter private keys & credentials| Chroma
```

---

## Process Phase Breakdown

### 1. Ingress & Routing
* **API Validation**: FastAPI routes authenticate clients via a shared API key check (`require_api_key`) and generate/assign request tracking IDs (`set_request_id`) for telemetry.
* **Skill Router**: Determines which execution model to trigger. Direct queries bypassing AI logic are captured deterministically via heuristics to guarantee prompt routing to Docker and static site tasks.

### 2. Context Hydration
* **Prompt Composer**: Gathers the context blocks (handoffs, active ports, directory paths).
* **Temporal Detection**: Automatically detects queries referencing "earlier", "yesterday", or "ago" and targets queries at Chroma DB, using date range boundaries.

### 3. Loop Execution
* **Pillar 1 (SSH)**: A dynamic, agentic ReAct loop executing commands on the host via Paramiko.
* **Pillar 2 (Deployment)**: A strict, multi-stage state machine that prevents model improvisation, verifying environment readiness and blocking for approval before modifying containers.
* **Pillar 3 (Builder)**: Conversations dynamically guide the creation of custom web pages, writing assets directly over SSH/SFTP.

### 4. Background Observations
* **Fact Extractor**: Runs silently after the client receives the output, updating SQLite facts (`memory_facts` table) using conflict-safe upsert queries.
* **Vector Archival**: Writes clean execution logs to Chroma DB after stripping SSH keys and passwords, ensuring future prompts can query historical logs safely.
