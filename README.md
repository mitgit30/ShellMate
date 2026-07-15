# ShellMate

## Overview

ShellMate is an AI-assisted Linux server manager built around three operating modes:

- `Pillar 1: Day-to-Day Server Management`
- `Pillar 2: Structured Deployment Engine`
- `Pillar 3: Builder`

The system is designed to let users work with Linux servers through natural language while keeping risky infrastructure changes controlled, observable, and reviewable.

This is not a generic chatbot wrapped around shell access. It is an event-driven operations system with real SSH execution, live streaming feedback, structured validation, and approval-aware automation.

## Product Philosophy

ShellMate separates infrastructure work into three different classes of behavior.

### Pillar 1: Day-to-Day Server Management

This mode is conversational, lightweight, and flexible.

It is used for requests such as:

- check uptime
- inspect disk or RAM usage
- read logs
- inspect services
- verify ports
- troubleshoot runtime issues
- perform simple operational tasks

In this mode, the assistant can reason more freely, choose commands dynamically, and respond naturally. This is the right model for diagnostics and routine operations where flexibility is valuable.

### Pillar 2: Structured Deployment Engine

This mode is strict, stage-driven, and safety-focused.

It is used for deployment-related requests such as:

- deploy an app with Docker
- deploy a multi-service app with Docker Compose
- update an existing Docker-based deployment
- generate deployment files
- validate environment readiness before rollout

In this mode, the system does not improvise on infrastructure change. The engine keeps strict stage order and tool execution, while the LLM handles intent interpretation, parameter extraction, and user-facing communication inside that structure.

### Pillar 3: Builder

This mode is creative, design-oriented, and conversational at the front.

It is used for requests such as:

- build a landing page
- create a portfolio website
- design a static marketing site
- generate a homepage in HTML, CSS, and JavaScript
- refine an existing generated website

Builder does not behave like a raw code dump. It first understands the website direction, then generates a polished static site, saves the files onto the connected server, and only shows the code when the user explicitly asks for it. If the request is still too vague, it stays conversational and asks for stronger design direction instead of inventing a random generic website.

This separation is the core design decision of the project.

## System Model

ShellMate is organized as four cooperating layers:

```text
+---------------------------+
| Frontend                  |
| Interactive operator UI   |
+-------------+-------------+
              |
              v
+---------------------------+
| Control APIs              |
| Validation + management   |
+-------------+-------------+
              |
              v
+---------------------------+
| Realtime Runtime          |
| Routing + orchestration   |
+-------------+-------------+
              |
              v
+---------------------------+
| Remote Execution Layer    |
| SSH + build/deploy actions|
+---------------------------+
```

Each layer has a clear role:

- the frontend acts as the user control surface
- the API layer owns validated application operations
- the runtime layer drives live agent behavior
- the execution layer performs real work on remote servers

## Core Capabilities

The current architecture supports the following capabilities:

- remote server registration
- SSH key-based access to Linux servers
- connection testing
- chat-driven server operations
- live HTTP streaming of agent execution
- session-aware context handling
- structured remote command execution
- static website generation and server-side file creation
- Docker-oriented deployment workflows with approval gates
- file-based per-server memory for cross-pillar handoff

## Architecture Principles

The project is built around a few engineering rules.

### 1. Real Infrastructure

The system is grounded in real server state. When it checks logs, inspects a port, or runs a deployment action, it does so against the registered remote machine.

### 2. Streaming Over Blocking

Long-running operations should be observable while they happen. Instead of waiting for one final response, the system streams intermediate events such as routing decisions, stage transitions, tool execution, and final output.

### 3. Different Risk Levels Need Different Execution Models

Operational questions can be conversational.

Deployment changes must stay structurally controlled.

Website creation should feel conversational at the outer layer, but remain intentional in how files are generated and saved.

This is why ShellMate uses:

- one flexible mode for daily operations
- one controlled deployment mode for infrastructure change workflows
- one creative builder mode for generating static websites

### 4. Validation Before Mutation

Before any structured deployment runs, the system validates prerequisites such as environment readiness, path existence, and port availability.

### 5. Approval Before Change

When the system is about to generate files or mutate deployment state, it stops and requests explicit user approval.

## Runtime Architecture

The runtime is the decision and execution core of the system.

At a high level, every user turn follows this model:

```text
User Input
   |
   v
Intent Routing
   |
   +--> Conversational Ops Mode
   |      - dynamic reasoning
   |      - flexible command selection
   |      - fast operational responses
   |
   +--> Structured Deployment Mode
          - strict stage ordering
          - validation gates
          - approval checkpoints
          - deterministic execution
   |
   +--> Builder Mode
          - conversational discovery
          - website generation
          - server-side file creation
          - refinement on follow-up prompts
```

This makes the system predictable without sacrificing usability.

## Realtime Interaction Model

ShellMate uses realtime streaming for the conversational experience.

The frontend sends a chat request to the runtime gateway, and the runtime streams back structured events as work progresses.

Typical streamed information includes:

- routing decisions
- stage start and completion
- tool execution details
- tokenized assistant responses
- errors
- final completion

This event model makes the system auditable and easier to trust.

## Pillar 1 Architecture

The first pillar is designed for fast, conversational Linux operations.

This mode is optimized for:

- ad hoc diagnostics
- quick answers
- server introspection
- operational troubleshooting
- lightweight administrative actions

Behavior in this mode is intentionally flexible. The assistant can inspect recent conversation context, choose commands, run them remotely, and summarize results naturally.

This is the right operating model for prompts like:

- "check uptime"
- "how much memory is free?"
- "show nginx logs"
- "is port 3000 open?"
- "restart nginx"

The first pillar is meant to feel like talking to a capable server operator.

## Pillar 2 Architecture

The second pillar is designed for deployment workflows where correctness and safety matter more than execution freedom.

Deployment requests can still begin conversationally, but once the user is asking for an actual rollout, the system switches into a structured engine rather than free-form reasoning.

The important design rule is:

- the engine decides what stage happens next
- the LLM decides how to interpret the request and how to communicate the result

This engine is based on fixed stages:

```text
Validate
   ->
Gather
   ->
Generate
   ->
Approval
   ->
Execute
   ->
Verify
   ->
Summary
```

The key property of this mode is that the system should not skip stages, reorder steps, or improvise destructive changes.

That is what makes it suitable for production-oriented workflows.

## Pillar 3 Architecture

The third pillar is designed for website generation and design-focused code creation.

Builder is intended for:

- static HTML/CSS/JS websites
- polished landing pages
- portfolio and product sites
- iterative visual refinement through follow-up prompts

Its workflow is deliberately different from deployment:

- vague requests stay conversational and move into a discovery step
- clear website requests generate actual site files
- generated files are saved onto the connected server
- code is shown only when the user explicitly asks for it
- if generation is not grounded enough, Builder asks for better design direction instead of producing a generic fallback site

This keeps Builder useful for real creation work without overwhelming the user with implementation details too early.

## Structured Deployment Design

The structured deployment engine is intentionally rule-based.

For Docker-focused deployment flows, the system behaves like a controlled pipeline.

Within that pipeline:

- the stages stay fixed
- tool execution stays deterministic
- the LLM handles request interpretation, missing-detail extraction, approval understanding, and user-facing summaries

### Validate

Checks preconditions such as:

- Docker availability
- Docker Compose availability when needed
- project directory presence
- target port availability

### Gather

Collects only the details that cannot be inferred confidently from the user request or environment.

### Generate

Produces deployment artifacts such as Dockerfiles, nginx configs for static sites, or Compose definitions when required.

### Approval

Pauses before writing files or executing deployment changes.

### Execute

Runs the exact deployment steps and streams progress live.

### Verify

Checks the result using status inspection, logs, and post-deployment validation.

### Summary

Explains the deployment outcome, current status, and suggested next actions.

## Safety Model

ShellMate is designed around the idea that not all actions should be treated equally.

### Safe, Read-Oriented Actions

These are suitable for conversational execution:

- checking status
- reading logs
- inspecting files
- checking ports
- retrieving metrics

### Controlled Change Actions

These require structured handling and often approval:

- generating deployment files
- building images
- starting containers
- updating deployment state
- restarting or replacing running workloads

### Destructive or Sensitive Actions

These must be explicitly guarded:

- removing containers
- deleting deployment resources
- overwriting important files
- replacing live services

This safety layering is central to the long-term reliability of the project.

## State and Continuity

The system maintains continuity so it can support follow-up actions instead of treating every prompt as isolated.

ShellMate now uses a file-based memory layer per server:

```text
memory/
  {server_id}/
    handoff.md
    server_facts.md
    session.md
```

This memory is used to pass discovered facts across pillars. For example, if the SSH pillar finds a project path, the deployment pillar can reuse that fact on the next turn.

This allows behavior such as:

- continuing an operational conversation
- pausing for deployment approval
- resuming the structured pipeline after approval
- preserving the latest generated website context
- keeping server-specific context across turns
- handing off discovered paths, ports, and environment facts between skills

This is especially important because:

- approvals and execution often happen across multiple deployment messages
- Builder needs to remember the latest generated website so it can refine or reveal the code later
- different pillars may discover facts the next pillar should not have to ask for again

## Observability

A server operations system must be inspectable while it works.

ShellMate is designed to expose its progress through structured event streaming so users can see:

- what mode it selected
- what stage it is currently in
- what tool action it is executing
- what command or deployment action was run
- whether verification passed or failed

This is important for operator confidence, debugging, and future UI evolution.

## Current Scope

At the current stage, the platform is centered on:

- Linux server management over SSH
- realtime conversational operations
- static website creation with HTML, CSS, and JavaScript
- server-side persistence of generated website files
- structured Docker deployment flows

Kubernetes is intentionally out of scope for the current phase. The focus right now is to make the Docker-oriented deployment engine solid before expanding further.

## Why This Design Matters

Most AI infrastructure assistants fail in one of two ways:

- they are too free-form and unsafe for real changes
- or they are too rigid and painful for everyday operations

ShellMate avoids that trap by giving each category of work its own proper execution model:

- flexible for day-to-day operations
- controlled for deployments
- creative but guided for building websites

That is the architectural identity of the project.

## Summary

ShellMate is an AI-assisted Linux server operations platform built on three pillars:

- a conversational server management mode for daily operations
- a structured deployment engine for safe Docker-based rollouts
- a Builder mode for generating static websites and saving them onto the server

Its architecture is designed around:

- real SSH-backed execution
- live streaming visibility
- session-aware orchestration
- validation before mutation
- approval before deployment changes

The result is a system that aims to be both usable in day-to-day server work and trustworthy when handling infrastructure changes.
