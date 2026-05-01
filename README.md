# Chat-Based Linux Server Manager

Prototype project for managing Linux servers through a chat-style workflow. The backend uses
FastAPI for HTTP APIs, Paramiko for SSH connectivity, and Streamlit for the prototype frontend.

## Project structure

```text
backend/
  app/
    api/
    core/
    repositories/
    schemas/
    services/
    main.py
frontend/
  app.py
tests/
```

## Features in this scaffold

- Register Linux servers in an in-memory backend registry
- Upload `.pem` SSH keys through the backend before connecting
- Test SSH connectivity through Paramiko using public IPv4 + username + uploaded `.pem`
- Execute commands remotely over SSH
- Use a Streamlit prototype UI to manage servers and run commands

## Quick start

1. Install dependencies:

   ```bash
   uv sync
   ```

2. Start the backend:

   ```bash
   uv run uvicorn backend.app.main:app --reload
   ```

3. Start the frontend:

   ```bash
   uv run streamlit run frontend/app.py
   ```

4. Open the Streamlit URL shown in the terminal.

## Notes

- The server registry is in-memory for prototyping and resets on restart.
- This prototype assumes SSH key authentication using `.pem` files.
- The next natural step is adding chat orchestration on top of the command execution API.
