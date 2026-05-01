from backend.app.repositories.server_repository import InMemoryServerRepository
from backend.app.services.key_storage_service import KeyStorageService
from backend.app.services.server_service import ServerService
from backend.app.services.ssh_service import SSHService
from src.runtime.agent import ServerOpsAgent
from src.runtime.ollama_client import OllamaModelClient
from src.storage.session_store import InMemorySessionStore
from src.tools.ssh_tool import SSHCommandTool


server_repository = InMemoryServerRepository()
server_service = ServerService(server_repository=server_repository)
ssh_service = SSHService(server_service=server_service)
key_storage_service = KeyStorageService()
session_store = InMemorySessionStore()
ssh_command_tool = SSHCommandTool(ssh_service=ssh_service)
server_ops_agent = ServerOpsAgent(
    model_client=OllamaModelClient(),
    session_store=session_store,
    ssh_tool=ssh_command_tool,
)
