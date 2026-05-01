import socket
from pathlib import Path

import paramiko

from backend.app.core.config import get_settings
from backend.app.core.exceptions import SSHConnectionError
from backend.app.schemas.command import CommandExecutionResponse
from backend.app.schemas.session import SSHSessionResponse
from backend.app.services.server_service import ServerService


class SSHService:
    def __init__(self, server_service: ServerService) -> None:
        self._server_service = server_service
        self._settings = get_settings()

    def open_session(self, server_id: str) -> SSHSessionResponse:
        server = self._server_service.get_server_record(server_id)
        client = self._build_client()
        try:
            self._connect(client=client, server=server)
        finally:
            client.close()

        return SSHSessionResponse(
            server_id=server_id,
            connected=True,
            message=f"SSH connection to {server.host}:{server.port} succeeded.",
        )

    def execute_command(self, server_id: str, command: str) -> CommandExecutionResponse:
        server = self._server_service.get_server_record(server_id)
        client = self._build_client()

        try:
            self._connect(client=client, server=server)
            _, stdout, stderr = client.exec_command(
                command,
                timeout=self._settings.ssh_command_timeout_seconds,
            )
            exit_status = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")
        except (paramiko.SSHException, OSError, socket.timeout) as exc:
            raise SSHConnectionError(
                f"Failed to execute command on server '{server_id}': {exc}"
            ) from exc
        finally:
            client.close()

        return CommandExecutionResponse(
            server_id=server_id,
            command=command,
            stdout=stdout_text,
            stderr=stderr_text,
            exit_status=exit_status,
        )

    @staticmethod
    def _build_client() -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    @staticmethod
    def _connect(client: paramiko.SSHClient, server) -> None:
        try:
            key_path = Path(server.private_key_path)
            if not key_path.exists():
                raise SSHConnectionError(
                    f"Private key file for server '{server.id}' was not found."
                )

            connect_kwargs = {
                "hostname": server.host,
                "port": server.port,
                "username": server.username,
                "timeout": 10,
                "look_for_keys": False,
                "allow_agent": False,
                "key_filename": str(key_path),
            }

            client.connect(**connect_kwargs)
        except (paramiko.AuthenticationException, paramiko.SSHException, OSError) as exc:
            raise SSHConnectionError(
                f"Unable to establish SSH connection to '{server.id}': {exc}"
            ) from exc
