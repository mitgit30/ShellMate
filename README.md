# Chat-Based Linux Server Manager

## What This Project Is

This project is an AI-assisted Linux server manager that lets a user register a remote Linux machine, connect to it over SSH, and operate it through a chat-based interface.

The system already supports the full basic loop:

- register a server
- upload its SSH private key
- verify connectivity
- open a chat session
- send natural-language requests
- route the request to a suitable runtime skill
- execute remote actions over SSH
- stream progress and results back to the UI

At this stage, the project is best understood as a working foundation for conversational server operations rather than a finished deployment platform.

## What Has Been Achieved So Far

The current implementation already provides five important building blocks.

### 1. Server Registration and Access Management

The backend can store server connection details and manage uploaded SSH private keys. A user can register a Linux host with:

- server ID
- display name
- public IPv4 address
- SSH port
- username
- private key path

This gives the system a concrete target machine to operate on instead of acting like a generic chatbot.

### 2. Real SSH-Based Execution

The agent does not simulate server work. It connects to the registered machine through SSH and executes commands remotely. This is the core capability of the project.

That means the system can already act on real infrastructure for tasks such as:

- system inspection
- log checks
- service status checks
- filesystem exploration
- command execution

### 3. FastAPI Management Backend

The backend exposes structured APIs for managing the server layer. These APIs handle:

- server registration
- server lookup
- SSH key upload
- SSH connection testing
- direct command execution
- chat request handling

This gives the project a clean application boundary between infrastructure management and the frontend experience.

### 4. WebSocket-Based Streaming Chat

The conversational layer is already event-driven. Instead of waiting for one large blocking response, the client receives a live stream of events from the runtime.

This includes:

- routing feedback
- step progress
- tool activity
- streamed response tokens
- completion/error events

That is a strong architectural achievement because it makes the system feel interactive and transparent during longer operations.

### 5. Skill-Oriented Agent Runtime

The runtime already has the concept of skills and tool-backed execution. A user prompt is routed to a selected skill, and that skill decides which structured tool actions to run.

This gives the project:

- intent-based execution
- separation between routing and action logic
- an extensible pattern for future capabilities

Even though this design will likely evolve later, it is already a meaningful step beyond plain command execution.

## Current System Architecture

The system is organized into four main layers.

```text
+-----------------------------+
| Frontend                    |
| Streamlit chat interface    |
+-------------+---------------+
              |
              v
+-----------------------------+
| Application Backend         |
| FastAPI REST APIs           |
+-------------+---------------+
              |
              v
+-----------------------------+
| Realtime Agent Layer        |
| WebSocket gateway + runtime |
+-------------+---------------+
              |
              v
+-----------------------------+
| Remote Execution Layer      |
| SSH-based tools             |
+-----------------------------+
```

## Layer-by-Layer Explanation

### Frontend Layer

The frontend is a Streamlit application that acts as the operator console for the system.

Its job is to:

- register new servers
- upload `.pem` keys
- connect to an available server
- collect user prompts
- display streamed agent replies
- show the latest execution trace

This makes the project usable even without building a custom web frontend yet.

### Application Backend

The FastAPI backend is the structured control plane of the project. It owns the CRUD-style and validation-heavy operations that should not be part of the chat loop itself.

This layer is responsible for:

- validating input
- storing server records
- storing uploaded key files
- testing SSH connectivity
- exposing direct command APIs
- exposing standard HTTP chat endpoints

This separation is important because not every action should depend on the agent runtime.

### Realtime Agent Layer

The realtime layer is where conversational behavior happens. It sits between the UI and the remote execution tools.

Its current responsibilities are:

- accept chat messages over WebSocket
- load recent session history
- ask the router to choose a skill
- execute the selected skill
- stream events back to the frontend
- persist conversation messages

This layer gives the project its “live AI operator” behavior.

### Remote Execution Layer

The lowest layer is where the system actually interacts with a Linux machine.

Today, this is primarily SSH-driven. Tools use the SSH service to run commands on the selected server and return structured output back to the runtime.

This keeps the agent grounded in real server state rather than hallucinated answers.

## How One User Request Flows Through the System

The current request lifecycle looks like this:

```text
User enters prompt in UI
   |
   v
Frontend sends WebSocket chat payload
   |
   v
Gateway receives and validates message type
   |
   v
Runtime loads session history
   |
   v
Router selects the best available skill
   |
   v
Skill invokes one or more structured tools
   |
   v
Tool executes action on remote server over SSH
   |
   v
Events and tokens stream back to UI
   |
   v
Session history is updated
```

This is the most important architectural flow in the current project.

## Current Communication Model

The system uses two different communication models, each for a different kind of problem.

### REST for Structured App Operations

HTTP endpoints are used where strong validation and predictable request/response behavior matter most.

These operations include:

- registering servers
- listing servers
- uploading keys
- testing SSH connections
- direct command execution
- standard chat endpoints

### WebSockets for Realtime Agent Turns

WebSockets are used for the actual live chat experience because agent turns can involve:

- internal routing decisions
- multiple tool calls
- incremental output
- long-running tasks

This lets the UI stay responsive and makes the system easier to observe.

## Current Runtime Design

The runtime today is built around three ideas:

### 1. Session-Aware Chat

Conversation history is kept per session so follow-up prompts can use recent context.

### 2. Skill Routing

The system does not execute every request the same way. It first chooses a skill based on the prompt and recent history.

### 3. Structured Tool Calls

Skills do not directly operate on infrastructure in an ad hoc way. They call tools that return structured execution results.

This is a very good early architecture for an AI systems tool because it creates separation between:

- understanding the request
- deciding what to do
- actually doing it

## Current Skill Model

The project currently includes a small set of skills. These skills represent the first generation of the runtime design.

They cover areas such as:

- SSH-oriented server operations
- web project generation and simple hosting
- early Docker-oriented actions

This means the skill system is already functioning as an extensibility mechanism, even though the exact skill boundaries will likely be improved later.

## Current Tooling Model

The current tooling layer is built around structured command execution. Tools translate higher-level skill decisions into concrete remote commands and return normalized results such as:

- command executed
- stdout
- stderr
- exit status

This is one of the most important achievements in the codebase because it makes remote execution inspectable and streamable.

## Session and State Handling

The project already maintains in-memory session state for chat continuity. This means the runtime can preserve:

- prior user messages
- prior assistant replies
- the associated server context

This is enough for a functional prototype and makes multi-turn interactions possible.

## Current Architecture

There are several things that have been implemented

### Clear Separation of Concerns

The project has distinct layers for:

- UI
- backend APIs
- runtime orchestration
- remote execution

That makes the codebase easier to grow than a monolithic chatbot implementation.

### Real Infrastructure Integration

The system is  integrated with actual server access and remote command execution.

### Observable Agent Behavior

The WebSocket event stream makes runtime behavior visible. That is especially valuable for infrastructure tools, where users need confidence in what is happening.

### Extensible Runtime Pattern

The skill-and-tool pattern gives the project a workable extensibility path for new capabilities.

## Present Limitations

To keep the README accurate, it is important to state what is still limited right now.

### Authentication Is Narrow

The current access flow is centered on `.pem` private key authentication. Other SSH login methods are not yet part of the active implementation.

### Session Storage Is In-Memory

Chat state is currently stored in memory, which is fine for development but not ideal for long-term persistence or multi-instance scaling.

### Skill Routing Is Prototype-Level

The current router selects one skill per turn. This works for the present feature set, but it may become restrictive as workflows get more complex.

### Safety Enforcement Is Still Lightweight

Some operational safety rules exist at the prompt and workflow level, but a stronger code-enforced approval system is still a next-stage improvement.

## This Project Represents 

This project is a functional conversational control plane for Linux servers.

It  demonstrates:

- real SSH connectivity
- remote command execution
- a structured FastAPI backend
- WebSocket streaming chat
- session-aware agent orchestration
- skill-based tool execution
- a usable Streamlit operator interface

## Near-Term Direction

The next architectural improvements should build on the current foundation rather than replacing it completely.

The most natural next steps are:

- make session handling more durable and safe
- strengthen WebSocket reliability
- improve skill boundaries and routing quality
- expand infrastructure tooling in a more structured way

Those are evolutionary steps from the system that already exists today.

## Summary

This project has  achieved  foundational part of an AI Linux server manager:

- server onboarding
- authenticated remote access
- structured backend APIs
- live streaming chat execution
- skill-based runtime orchestration
- real remote command execution

The architecture is already strong enough to support meaningful server operations, and it provides a solid base for the next phase of capabilities.
